"""FastAPI-приложение OriginLedger: каталог контента + статус challenge.

Эндпоинты синхронные — FastAPI уводит их в threadpool, поэтому sync-web3
и sync-SQLAlchemy не блокируют event loop. Индексер крутится в отдельном потоке.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Path, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import indexer
from .chain import get_registry, get_w3, load_deployment, to_hex
from .config import get_settings
from .db import get_db, init_db
from .models import Content, ContentStatus, IndexerState
from .schemas import (
    ConfigOut,
    ContentList,
    ContentOut,
    ContractInfo,
    HealthOut,
    StatsOut,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("originledger")
settings = get_settings()

_STATUS_BY_NAME = {
    "active": ContentStatus.ACTIVE,
    "challenged": ContentStatus.CHALLENGED,
    "revoked": ContentStatus.REVOKED,
    "cleared": ContentStatus.CLEARED,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    try:
        load_deployment()
    except FileNotFoundError as exc:
        log.warning("%s", exc)
    indexer.start()
    try:
        yield
    finally:
        indexer.stop()


app = FastAPI(title="OriginLedger API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["GET"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------- helpers


def _registry_params() -> tuple[int, int]:
    """(burnFeeBps, challengePeriod) — читаем из контракта, при сбое берём из деплой-файла."""
    d = load_deployment()
    try:
        reg = get_registry()
        return int(reg.functions.burnFeeBps().call()), int(reg.functions.challengePeriod().call())
    except Exception as exc:  # noqa: BLE001
        log.warning("не удалось прочитать параметры реестра из ноды (%s), беру из деплой-файла", exc)
        return d.burn_fee_bps, d.challenge_period


# ---------------------------------------------------------------- system routes


@app.get("/health", response_model=HealthOut)
def health(db: Session = Depends(get_db)) -> HealthOut:
    st = db.get(IndexerState, 1)
    chain_connected = False
    chain_id = latest = None
    try:
        w3 = get_w3()
        chain_connected = w3.is_connected()
        if chain_connected:
            chain_id = w3.eth.chain_id
            latest = w3.eth.block_number
    except Exception:  # noqa: BLE001
        pass
    return HealthOut(
        status="ok",
        chain_connected=chain_connected,
        chain_id=chain_id,
        latest_block=latest,
        last_scanned_block=st.last_scanned_block if st else -1,
        indexer_alive=indexer.is_alive(),
    )


@app.get("/api/config", response_model=ConfigOut)
def config() -> ConfigOut:
    try:
        d = load_deployment()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    burn_fee_bps, challenge_period = _registry_params()
    return ConfigOut(
        network=d.network,
        chain_id=d.chain_id,
        rpc_url=settings.rpc_url,
        prov_token=ContractInfo(address=d.prov_token_address, abi=d.prov_token_abi),
        content_registry=ContractInfo(address=d.registry_address, abi=d.registry_abi),
        burn_fee_bps=burn_fee_bps,
        challenge_period=challenge_period,
    )


# -------------------------------------------------------------- content routes


@app.get("/api/contents", response_model=ContentList)
def list_contents(
    db: Session = Depends(get_db),
    status: str | None = Query(None, description="active|challenged|revoked|cleared"),
    author: str | None = Query(None, description="адрес автора (0x...)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> ContentList:
    stmt = select(Content)
    count_stmt = select(func.count()).select_from(Content)

    if status is not None:
        key = status.lower()
        if key not in _STATUS_BY_NAME:
            raise HTTPException(status_code=422, detail=f"неизвестный статус: {status}")
        stmt = stmt.where(Content.status == int(_STATUS_BY_NAME[key]))
        count_stmt = count_stmt.where(Content.status == int(_STATUS_BY_NAME[key]))

    if author is not None:
        a = to_hex(author)
        stmt = stmt.where(func.lower(Content.author) == a)
        count_stmt = count_stmt.where(func.lower(Content.author) == a)

    total = db.execute(count_stmt).scalar_one()
    rows = db.execute(
        stmt.order_by(Content.id.desc()).limit(limit).offset(offset)
    ).scalars().all()

    return ContentList(
        items=[ContentOut.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@app.get("/api/contents/by-hash/{content_hash}", response_model=ContentOut)
def get_by_hash(
    content_hash: str = Path(..., description="keccak256 файла, 0x + 64 hex"),
    db: Session = Depends(get_db),
) -> ContentOut:
    row = db.execute(
        select(Content).where(func.lower(Content.content_hash) == to_hex(content_hash))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="контент с таким хэшем не найден")
    return ContentOut.model_validate(row)


@app.get("/api/contents/{content_id}", response_model=ContentOut)
def get_content(content_id: int = Path(..., ge=1), db: Session = Depends(get_db)) -> ContentOut:
    row = db.get(Content, content_id)
    if row is None:
        raise HTTPException(status_code=404, detail="контент не найден")
    return ContentOut.model_validate(row)


@app.get("/api/stats", response_model=StatsOut)
def stats(db: Session = Depends(get_db)) -> StatsOut:
    by_status = dict(
        db.execute(select(Content.status, func.count()).group_by(Content.status)).all()
    )
    st = db.get(IndexerState, 1)
    return StatsOut(
        total=sum(by_status.values()),
        active=by_status.get(int(ContentStatus.ACTIVE), 0),
        challenged=by_status.get(int(ContentStatus.CHALLENGED), 0),
        revoked=by_status.get(int(ContentStatus.REVOKED), 0),
        cleared=by_status.get(int(ContentStatus.CLEARED), 0),
        last_scanned_block=st.last_scanned_block if st else -1,
        chain_id=st.chain_id if st else 0,
    )
