"""Подключение к ноде и загрузка контрактов из deployments/<network>.json."""
from __future__ import annotations

import json
from functools import lru_cache

from web3 import Web3

from .config import get_settings

settings = get_settings()


class Deployment:
    def __init__(self, raw: dict):
        self.network: str = raw.get("network", "unknown")
        self.chain_id: int = int(raw.get("chainId", 0))
        self.prov_token_address: str = Web3.to_checksum_address(raw["PROVToken"]["address"])
        self.prov_token_abi: list = raw["PROVToken"]["abi"]
        self.registry_address: str = Web3.to_checksum_address(raw["ContentRegistry"]["address"])
        self.registry_abi: list = raw["ContentRegistry"]["abi"]
        params = raw.get("ContentRegistry", {}).get("params", {}) or {}
        self.burn_fee_bps: int = int(params.get("burnFeeBps", 0))
        self.challenge_period: int = int(params.get("challengePeriod", 0))


@lru_cache
def load_deployment() -> Deployment:
    path = settings.deployment_path
    if not path.exists():
        raise FileNotFoundError(
            f"Файл деплоя не найден: {path}. Сначала: truffle migrate && "
            f"truffle exec scripts/export_deployment.js --network <network>"
        )
    return Deployment(json.loads(path.read_text()))


@lru_cache
def get_w3() -> Web3:
    return Web3(Web3.HTTPProvider(settings.rpc_url, request_kwargs={"timeout": 20}))


@lru_cache
def get_registry():
    d = load_deployment()
    return get_w3().eth.contract(address=d.registry_address, abi=d.registry_abi)


@lru_cache
def get_token():
    d = load_deployment()
    return get_w3().eth.contract(address=d.prov_token_address, abi=d.prov_token_abi)


# topic0 -> имя события. Считаем от сигнатур, не полагаясь на порядок в ABI.
_EVENT_SIGNATURES = {
    "ContentRegistered": "ContentRegistered(uint256,address,bytes32,string,uint256)",
    "ChallengeRaised": "ChallengeRaised(uint256,address)",
    "ChallengeResolved": "ChallengeResolved(uint256,bool)",
    "BondWithdrawn": "BondWithdrawn(uint256,address,uint256)",
}


def to_hex(x) -> str:
    """HexBytes/bytes/str -> '0x'-префиксный lowercase hex.
    hexbytes 1.x .hex() отдаёт БЕЗ '0x', поэтому нормализуем явно."""
    if isinstance(x, str):
        return x.lower() if x.startswith("0x") else "0x" + x.lower()
    if hasattr(x, "to_0x_hex"):
        return x.to_0x_hex().lower()
    return "0x" + bytes(x).hex()


@lru_cache
def event_topic_map() -> dict[str, str]:
    return {to_hex(Web3.keccak(text=sig)): name for name, sig in _EVENT_SIGNATURES.items()}
