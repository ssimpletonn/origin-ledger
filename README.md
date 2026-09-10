# OriginLedger — DApp для лицензирования контента

Платформа фиксации авторства контента и его лицензирования через смарт-контракты.

## Структура репозитория

```
originledger/
├── contracts/          # Truffle-проект (Solidity)
│   ├── contracts/
│   │   ├── PROVToken.sol        # ERC-20, fixed supply, burnable
│   │   └── ContentRegistry.sol  # регистрация контента, bond, challenge
│   ├── migrations/
│   ├── test/
│   └── truffle-config.js
│   └── scripts/
│       └── export_deployment.js # пишет deployments/<network>.json
├── deployments/         # адреса + ABI + chainId задеплоенных контрактов
├── backend/             # FastAPI + web3.py — индексация событий, REST API
│   └── app/             # config, db, models, schemas, chain, indexer, main
├── frontend/            # Next.js (App Router) + wagmi/viem — UI
│   ├── app/             # витрина / register / verifier
│   ├── components/      # ContentCard, Actions, WalletButton, Nav
│   └── lib/             # api, wagmi, contracts (ABI-фрагменты), hash, format
└── docker-compose.yml   # Postgres + backend
```

## Быстрый старт (контракты)

```bash
cd contracts
npm install

# терминал 1: локальная нода
ganache --port 8545 --wallet.deterministic --miner.defaultTransactionGasLimit estimate

# терминал 2: компиляция, деплой
truffle compile
truffle migrate --network development

# экспорт адресов + ABI + chainId в deployments/development.json
truffle exec scripts/export_deployment.js --network development
```

`scripts/export_deployment.js` пишет `deployments/development.json` (адреса,
ABI, `chainId`, `burnFeeBps`, `challengePeriod`) — оттуда их читают backend и
frontend.

## Быстрый старт (backend + frontend)

```bash
# из корня репозитория, после export_deployment.js

# Postgres + backend API (FastAPI + индексер событий)
docker compose up --build
#   API:     http://localhost:8000
#   Swagger: http://localhost:8000/docs

# frontend (Next.js)
cd frontend
npm install
cp .env.local.example .env.local     # вписать адреса из deployments/development.json + chainId
npm run dev                          # http://localhost:3000
```

> При создании сети через ganache сид: myth like bonus scare over problem client lizard pioneer submit female collect