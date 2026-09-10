"""Конфигурация backend'а. Всё через переменные окружения / .env."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ (на два уровня выше этого файла: app/config.py -> app -> backend)
BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- БД ---
    database_url: str = "postgresql+psycopg2://originledger:originledger@localhost:5432/originledger"

    # --- Нода ---
    rpc_url: str = "http://127.0.0.1:8545"

    # Файл деплоя (deployments/<network>.json). Путь абсолютный или относительно repo root.
    deployment_file: str = "deployments/development.json"

    # С какого блока начинать индексацию, если состояние индексера пустое.
    start_block: int = 0

    # Пауза между опросами ноды, секунды.
    poll_interval: float = 3.0

    # Максимальный размер диапазона блоков за один getLogs (защита от слишком больших ответов).
    log_batch_size: int = 2000

    # CORS для фронта.
    cors_origins: str = "http://localhost:3000"

    @property
    def deployment_path(self) -> Path:
        p = Path(self.deployment_file)
        return p if p.is_absolute() else (REPO_ROOT / p)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
