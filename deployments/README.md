# Deployments

Сюда после деплоя (`truffle migrate --network <network>`) кладём JSON вида:

```json
{
  "network": "sepolia",
  "PROVToken": { "address": "0x...", "abi": "../contracts/build/contracts/PROVToken.json" },
  "ContentRegistry": { "address": "0x...", "abi": "../contracts/build/contracts/ContentRegistry.json" }
}
```

Backend и frontend читают адреса отсюда.
