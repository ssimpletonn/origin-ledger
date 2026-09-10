/* eslint-disable no-console */
// Экспорт задеплоенных адресов и ABI в ../deployments/<network>.json.
//
// Запуск (после `truffle migrate`):
//   npx truffle exec scripts/export_deployment.js --network development
//
// Backend и frontend читают адреса/ABI/chainId только из этого файла и никогда
// не хардкодят их у себя (см. deployments/README.md).

const fs = require("fs");
const path = require("path");

const PROVToken = artifacts.require("PROVToken");
const ContentRegistry = artifacts.require("ContentRegistry");

module.exports = async function (callback) {
  try {
    const token = await PROVToken.deployed();
    const registry = await ContentRegistry.deployed();

    const chainId = await web3.eth.getChainId();
    const networkName = artifacts.options && artifacts.options.network
      ? artifacts.options.network
      : (config.network || "development");

    // Параметры контракта нужны фронту для расчёта времени разблокировки и
    // ожидаемого возврата — читаем их из самого контракта, а не из констант.
    const [burnFeeBps, challengePeriod] = await Promise.all([
      registry.burnFeeBps(),
      registry.challengePeriod(),
    ]);

    const out = {
      network: networkName,
      chainId: Number(chainId),
      exportedAt: new Date().toISOString(),
      PROVToken: {
        address: token.address,
        abi: PROVToken.abi,
      },
      ContentRegistry: {
        address: registry.address,
        abi: ContentRegistry.abi,
        params: {
          provToken: token.address,
          burnFeeBps: burnFeeBps.toString(),
          challengePeriod: challengePeriod.toString(),
        },
      },
    };

    const dir = path.resolve(__dirname, "..", "..", "deployments");
    fs.mkdirSync(dir, { recursive: true });
    const file = path.join(dir, `${networkName}.json`);
    fs.writeFileSync(file, JSON.stringify(out, null, 2) + "\n");

    console.log(`Deployment exported -> ${path.relative(process.cwd(), file)}`);
    console.log(`  chainId:          ${out.chainId}`);
    console.log(`  PROVToken:        ${token.address}`);
    console.log(`  ContentRegistry:  ${registry.address}`);
    console.log(`  burnFeeBps:       ${burnFeeBps.toString()}`);
    console.log(`  challengePeriod:  ${challengePeriod.toString()} s`);

    callback();
  } catch (err) {
    callback(err);
  }
};
