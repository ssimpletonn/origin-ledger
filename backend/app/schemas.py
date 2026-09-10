"""Pydantic-схемы ответов. Все uint256 отдаём СТРОКАМИ —
JS теряет точность выше 2^53, фронт превращает их в BigInt."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_serializer

from .models import ContentStatus

_STATUS_NAME = {
    ContentStatus.ACTIVE: "Active",
    ContentStatus.CHALLENGED: "Challenged",
    ContentStatus.REVOKED: "Revoked",
    ContentStatus.CLEARED: "Cleared",
}


class ContentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    author: str
    content_hash: str
    license_uri: str
    bond_total: int
    bond_remaining: int
    bond_refunded: int
    status: int
    status_name: str = ""
    challenger: str | None
    registered_at: int
    block_number: int
    tx_hash: str

    @field_serializer("bond_total", "bond_remaining", "bond_refunded")
    def _ser_uint256(self, v: int) -> str:
        return str(v)

    def model_post_init(self, __context) -> None:
        try:
            object.__setattr__(self, "status_name", _STATUS_NAME[ContentStatus(self.status)])
        except ValueError:
            object.__setattr__(self, "status_name", f"Unknown({self.status})")


class ContentList(BaseModel):
    items: list[ContentOut]
    total: int
    limit: int
    offset: int


class StatsOut(BaseModel):
    total: int
    active: int
    challenged: int
    revoked: int
    cleared: int
    last_scanned_block: int
    chain_id: int


class ContractInfo(BaseModel):
    address: str
    abi: list


class ConfigOut(BaseModel):
    network: str
    chain_id: int
    rpc_url: str
    prov_token: ContractInfo
    content_registry: ContractInfo
    burn_fee_bps: int
    challenge_period: int


class HealthOut(BaseModel):
    status: str
    chain_connected: bool
    chain_id: int | None
    latest_block: int | None
    last_scanned_block: int
    indexer_alive: bool
