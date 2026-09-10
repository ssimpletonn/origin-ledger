# Backend — OriginLedger API

Индексирует события `ContentRegistry` с ноды в Postgres и отдаёт каталог контента
+ статус challenge. Фронт читает данные отсюда, не из ноды напрямую.

## Компоненты

| Файл | Назначение |
|------|-----------|
| `app/config.py`   | настройки из `.env` |
| `app/db.py`       | SQLAlchemy engine/session, `init_db()` |
| `app/models.py`   | `Content`, `IndexerState` (uint256 → `NUMERIC(78,0)`) |
| `app/schemas.py`  | Pydantic-ответы; uint256 отдаются **строками** |
| `app/chain.py`    | Web3, загрузка `deployments/<network>.json`, topic-хэши событий |
| `app/indexer.py`  | фоновый поток: `getLogs` → сортировка по `(block, logIndex)` → upsert |
| `app/main.py`     | FastAPI, lifespan запускает индексер |

## Статусы (`status` в ответе)

`0 Active` · `1 Challenged` · `2 Revoked` · `3 Cleared`

## API

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/health` | связь с нодой, живость индексера, `last_scanned_block` |
| GET | `/api/config` | адреса, ABI, `chainId`, `burnFeeBps`, `challengePeriod` (читаются из контракта) |
| GET | `/api/contents?status=&author=&limit=&offset=` | список (сортировка по `id` убыв.) |
| GET | `/api/contents/{id}` | одна запись |
| GET | `/api/contents/by-hash/{hash}` | поиск по keccak256 файла |
| GET | `/api/stats` | счётчики по статусам + прогресс индексера |

## Запуск через Docker (рекомендуется)

Из корня репозитория:

```bash
# 1. нода
npx ganache --port 8545 --wallet.deterministic --miner.defaultTransactionGasLimit estimate

# 2. деплой + экспорт адресов
cd contracts
npx truffle migrate --network development
npx truffle exec scripts/export_deployment.js --network development
cd ..

# 3. Postgres + backend
docker compose up --build
# API: http://localhost:8000  ·  Swagger: http://localhost:8000/docs
```

## Запуск без Docker

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # выставить DATABASE_URL на локальный Postgres, RPC_URL=http://127.0.0.1:8545
uvicorn app.main:app --reload
```

Нужен запущенный Postgres.
