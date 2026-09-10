require("dotenv").config();

module.exports = {
  networks: {
    // Локальная сеть Ganache (GUI-приложение или `ganache` CLI).
    // По умолчанию Ganache CLI поднимается на 127.0.0.1:8545.
    development: {
      host: "127.0.0.1",
      port: 8545,
      network_id: "*",
    },

    // Отдельный профиль под `ganache` CLI с фиксированным mnemonic —
    // удобно для воспроизводимых демо на защите.
    ganache_cli: {
      host: "127.0.0.1",
      port: 7545,
      network_id: "5777",
    },
  },

  mocha: {
    timeout: 100000,
  },

  compilers: {
    solc: {
      version: "0.8.24",
      settings: {
        optimizer: {
          enabled: true,
          runs: 200,
        },
        // solc >= 0.8.20 по умолчанию таргетит EVM "shanghai" и вставляет опкод
        // PUSH0, которого нет в старых Ganache (GUI-приложение, ganache-cli,
        // Ganache 7 до ~7.7). Из-за этого контракт "деплоится", но по адресу
        // пусто / миграция падает. "paris" убирает PUSH0 и совместим со всеми.
        evmVersion: "paris",
      },
    },
  },
};
