const PROVToken = artifacts.require("PROVToken");
const ContentRegistry = artifacts.require("ContentRegistry");

module.exports = async function (deployer) {
  const token = await PROVToken.deployed();

  const burnFeeBps = 500;               // 5% от bond сжигается сразу как anti-spam fee
  const challengePeriod = 7 * 24 * 3600; // 7 дней на оспаривание

  await deployer.deploy(ContentRegistry, token.address, burnFeeBps, challengePeriod);
  const registry = await ContentRegistry.deployed();

  // Разрешаем ContentRegistry сжигать токены (bond при revoke/withdraw)
  await token.setPlatformContract(registry.address, true);
};
