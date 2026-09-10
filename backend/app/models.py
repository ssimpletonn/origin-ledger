"""ORM-модели. uint256 хранится в NUMERIC(78,0) — BIGINT переполняется
(bond уже 1e19, totalSupply 1e26)."""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

UINT256 = Numeric(78, 0)


class ContentStatus(enum.IntEnum):
    """Значения строго соответствуют enum Status в ContentRegistry.sol."""

    ACTIVE = 0
    CHALLENGED = 1
    REVOKED = 2
    CLEARED = 3


class Content(Base):
    __tablename__ = "contents"

    # id == contentId в контракте (начинается с 1).
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)

    author: Mapped[str] = mapped_column(String(42), index=True)
    content_hash: Mapped[str] = mapped_column(String(66), unique=True, index=True)
    license_uri: Mapped[str] = mapped_column(String, default="")

    # Полный размер внесённого залога (для отображения "заблокировано").
    bond_total: Mapped[int] = mapped_column(UINT256, default=0)
    # Остаток bond'а в контракте (0 после withdraw/revoke).
    bond_remaining: Mapped[int] = mapped_column(UINT256, default=0)
    # Сколько реально вернулось автору при withdrawBond (событие BondWithdrawn).
    bond_refunded: Mapped[int] = mapped_column(UINT256, default=0)

    status: Mapped[int] = mapped_column(Integer, default=ContentStatus.ACTIVE, index=True)
    challenger: Mapped[str | None] = mapped_column(String(42), nullable=True)

    registered_at: Mapped[int] = mapped_column(BigInteger)  # block.timestamp (unix, сек)

    # Метаданные последнего изменившего запись события — для отладки/аудита.
    block_number: Mapped[int] = mapped_column(BigInteger)
    tx_hash: Mapped[str] = mapped_column(String(66))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=lambda: datetime.now(timezone.utc)
    )


class IndexerState(Base):
    """Одна строка (id=1). Хранит прогресс сканирования и «отпечаток» деплоя —
    если chain_id или адрес реестра сменились (ганаш пересоздан, редеплой),
    состояние сбрасывается, иначе индексер навсегда застрянет с пустым диапазоном."""

    __tablename__ = "indexer_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    last_scanned_block: Mapped[int] = mapped_column(BigInteger, default=0)
    chain_id: Mapped[int] = mapped_column(BigInteger, default=0)
    registry_address: Mapped[str] = mapped_column(String(42), default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=lambda: datetime.now(timezone.utc)
    )
