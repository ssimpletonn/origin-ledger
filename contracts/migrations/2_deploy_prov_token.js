const PROVToken = artifacts.require("PROVToken");

module.exports = async function (deployer, network, accounts) {
  // Начальный supply: 100,000,000 PROV (18 decimals)
  const initialSupply = web3.utils.toWei("100000000", "ether");
  const treasury = accounts[0]; // казна проекта — в проде заменить на мультисиг/DAO

  await deployer.deploy(PROVToken, initialSupply, treasury);
};
