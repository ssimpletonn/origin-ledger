"""Индексер событий ContentRegistry.

Живёт в отдельном потоке (запускается из lifespan в main.py). Каждые
POLL_INTERVAL секунд забирает новые логи реестра, декодирует, применяет к БД
в порядке (blockNumber, logIndex) и двигает курсор last_scanned_block.
"""
from __future__ import annotations

import logging
import threading
import time

from web3.exceptions import Web3Exception

from .chain import event_topic_map, get_registry, get_w3, load_deployment, to_hex
from .config import get_settings
from .db import SessionLocal
from .models import Content, ContentStatus, IndexerState

log = logging.getLogger("originledger.indexer")
settings = get_settings()

_thread: threading.Thread | None = None
_stop = threading.Event()
_alive = threading.Event()


def is_alive() -> bool:
    return _alive.is_set()


# ---------------------------------------------------------------- state helpers


def _get_or_reset_state(db) -> IndexerState:
    """Берём строку состояния. Если отпечаток деплоя (chain_id + адрес реестра)
    не совпал — ганаш пересоздан / был редеплой: чистим индекс и начинаем заново."""
    d = load_deployment()
    st = db.get(IndexerState, 1)

    fingerprint_changed = st is not None and (
        st.chain_id != d.chain_id
        or st.registry_address.lower() != d.registry_address.lower()
    )

    if st is None or fingerprint_changed:
        if fingerprint_changed:
            log.warning(
                "Отпечаток деплоя изменился (chain_id %s->%s, registry %s->%s) — сброс индекса",
                st.chain_id, d.chain_id, st.registry_address, d.registry_address,
            )
            db.query(Content).delete()
            db.delete(st)
            db.flush()
        st = IndexerState(
            id=1,
            last_scanned_block=max(settings.start_block - 1, -1),
            chain_id=d.chain_id,
            registry_address=d.registry_address,
        )
        db.add(st)
        db.flush()
    return st


# ---------------------------------------------------------------- log handling


def _apply_log(db, name: str, ev, raw) -> None:
    args = ev["args"]
    cid = int(args["contentId"])
    block_number = int(raw["blockNumber"])
    tx_hash = to_hex(raw["transactionHash"])

    if name == "ContentRegistered":
        blk = get_w3().eth.get_block(block_number)
        c = db.get(Content, cid)
        if c is None:
            c = Content(id=cid)
            db.add(c)
        c.author = to_hex(args["author"])
        c.content_hash = to_hex(args["contentHash"])
        c.license_uri = args["licenseURI"]
        c.bond_total = int(args["bond"])
        c.bond_remaining = int(args["bond"])
        c.bond_refunded = 0
        c.status = int(ContentStatus.ACTIVE)
        c.challenger = None
        c.registered_at = int(blk["timestamp"])
        c.block_number = block_number
        c.tx_hash = tx_hash
        return

    c = db.get(Content, cid)
    if c is None:
        log.warning("%s для неизвестного contentId=%s — пропуск", name, cid)
        return

    if name == "ChallengeRaised":
        c.status = int(ContentStatus.CHALLENGED)
        c.challenger = to_hex(args["challenger"])
    elif name == "ChallengeResolved":
        # событие несёт только bool; true->Revoked(2), false->Cleared(3)
        if bool(args["contentWasDuplicate"]):
            c.status = int(ContentStatus.REVOKED)
            c.bond_remaining = 0  # bond сожжён полностью
        else:
            c.status = int(ContentStatus.CLEARED)
    elif name == "BondWithdrawn":
        # amount в событии == возвращённая часть (95%), НЕ весь bond.
        c.bond_refunded = int(args["amount"])
        c.bond_remaining = 0

    c.block_number = block_number
    c.tx_hash = tx_hash


def _decode(registry, raw):
    """raw log -> (event_name, decoded) либо None, если это чужое событие."""
    topics = raw.get("topics") or []
    if not topics:
        return None
    name = event_topic_map().get(to_hex(topics[0]))
    if name is None:
        return None
    decoded = getattr(registry.events, name)().process_log(raw)
    return name, decoded


# ---------------------------------------------------------------- main loop


def _scan_once(registry) -> None:
    w3 = get_w3()
    latest = w3.eth.block_number

    with SessionLocal() as db:
        st = _get_or_reset_state(db)
        from_block = st.last_scanned_block + 1
        db.commit()

    if from_block > latest:
        return

    while from_block <= latest:
        to_block = min(from_block + settings.log_batch_size - 1, latest)
        raw_logs = w3.eth.get_logs(
            {"address": registry.address, "fromBlock": from_block, "toBlock": to_block}
        )
        decoded = []
        for raw in raw_logs:
            got = _decode(registry, raw)
            if got is not None:
                decoded.append((raw, got[0], got[1]))

        # строгий детерминированный порядок применения
        decoded.sort(key=lambda t: (int(t[0]["blockNumber"]), int(t[0]["logIndex"])))

        with SessionLocal() as db:
            st = _get_or_reset_state(db)
            for raw, name, ev in decoded:
                _apply_log(db, name, ev, raw)
                # flush после каждого события: следующий _apply_log в этом же
                # батче может делать db.get() по только что вставленной записи
                # (напр. ContentRegistered и ChallengeRaised в одном диапазоне
                # блоков при первой синхронизации). autoflush=False, поэтому явно.
                db.flush()
            st.last_scanned_block = to_block
            db.commit()

        if decoded:
            log.info("блоки %s..%s: применено событий=%d", from_block, to_block, len(decoded))
        from_block = to_block + 1


def _run() -> None:
    _alive.set()
    log.info("индексер запущен, rpc=%s", settings.rpc_url)

    # дожидаемся и ноды, и файла деплоя (миграции могут ещё не отработать)
    registry = None
    while not _stop.is_set():
        try:
            if get_w3().is_connected():
                registry = get_registry()  # бросит FileNotFoundError, если деплоя ещё нет
                break
        except FileNotFoundError as exc:
            log.warning("%s", exc)
        except Exception as exc:  # noqa: BLE001
            log.warning("нода недоступна: %s", exc)
        _stop.wait(settings.poll_interval)

    while not _stop.is_set() and registry is not None:
        try:
            _scan_once(registry)
        except (Web3Exception, OSError) as exc:
            log.warning("ошибка опроса ноды: %s", exc)
        except Exception:  # noqa: BLE001
            log.exception("непредвиденная ошибка в индексере")
        _stop.wait(settings.poll_interval)

    _alive.clear()
    log.info("индексер остановлен")


def start() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_run, name="indexer", daemon=True)
    _thread.start()


def stop() -> None:
    _stop.set()
    if _thread:
        _thread.join(timeout=10)
