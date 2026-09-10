const PROVToken = artifacts.require("PROVToken");
const ContentRegistry = artifacts.require("ContentRegistry");

const { toBN, toWei, keccak256 } = web3.utils;

contract("OriginLedger", (accounts) => {
  const [treasury, author, verifier, buyer] = accounts;

  let token;
  let registry;

  const initialSupply = toWei("100000000", "ether");
  const burnFeeBps = 500; // 5%
  const challengePeriod = 7 * 24 * 3600;

  beforeEach(async () => {
    token = await PROVToken.new(initialSupply, treasury);
    registry = await ContentRegistry.new(token.address, burnFeeBps, challengePeriod);
    await token.setPlatformContract(registry.address, true, { from: treasury });

    // выдаём автору немного PROV для bond'а
    await token.transfer(author, toWei("1000", "ether"), { from: treasury });
  });

  it("деплоит токен с фиксированным supply на казну", async () => {
    const supply = await token.totalSupply();
    assert.equal(supply.toString(), initialSupply);

    const treasuryBalance = await token.balanceOf(treasury);
    assert.equal(treasuryBalance.toString(), toBN(initialSupply).sub(toBN(toWei("1000", "ether"))).toString());
  });

  it("регистрирует контент с bond и не даёт зарегистрировать тот же hash дважды", async () => {
    const bond = toWei("10", "ether");
    const contentHash = keccak256("some-unique-content-bytes");

    await token.approve(registry.address, bond, { from: author });
    const tx = await registry.registerContent(contentHash, "ipfs://license/1", bond, { from: author });

    assert.equal(tx.logs[0].event, "ContentRegistered");
    const contentId = tx.logs[0].args.contentId.toString();
    assert.equal(contentId, "1");

    // повторная регистрация того же hash должна упасть
    await token.approve(registry.address, bond, { from: author });
    try {
      await registry.registerContent(contentHash, "ipfs://license/1", bond, { from: author });
      assert.fail("expected revert");
    } catch (err) {
      assert.include(err.message, "already registered");
    }
  });

  it("после challenge period автор может забрать bond за вычетом anti-spam fee", async () => {
    const bond = toWei("10", "ether");
    const contentHash = keccak256("another-content");

    await token.approve(registry.address, bond, { from: author });
    const tx = await registry.registerContent(contentHash, "ipfs://license/2", bond, { from: author });
    const contentId = tx.logs[0].args.contentId;

    // мотаем время вперёд за пределы challenge period
    await advanceTime(challengePeriod + 1);

    const balanceBefore = toBN(await token.balanceOf(author));
    await registry.withdrawBond(contentId, { from: author });
    const balanceAfter = toBN(await token.balanceOf(author));

    const expectedRefund = toBN(bond).mul(toBN(10000 - burnFeeBps)).div(toBN(10000));
    assert.equal(balanceAfter.sub(balanceBefore).toString(), expectedRefund.toString());
  });

  it("подтверждённый дубликат сжигает bond полностью", async () => {
    const bond = toWei("10", "ether");
    const contentHash = keccak256("disputed-content");

    await token.approve(registry.address, bond, { from: author });
    const tx = await registry.registerContent(contentHash, "ipfs://license/3", bond, { from: author });
    const contentId = tx.logs[0].args.contentId;

    await registry.setVerifier(verifier, true, { from: treasury });
    await registry.raiseChallenge(contentId, { from: verifier });

    const supplyBefore = toBN(await token.totalSupply());
    await registry.resolveChallenge(contentId, true, { from: treasury });
    const supplyAfter = toBN(await token.totalSupply());

    assert.equal(supplyBefore.sub(supplyAfter).toString(), bond);
  });
});

// Ganache-совместимый helper для перемотки времени (evm_increaseTime + evm_mine)
function advanceTime(seconds) {
  return new Promise((resolve, reject) => {
    web3.currentProvider.send(
      { jsonrpc: "2.0", method: "evm_increaseTime", params: [seconds], id: new Date().getTime() },
      (err1) => {
        if (err1) return reject(err1);
        web3.currentProvider.send(
          { jsonrpc: "2.0", method: "evm_mine", params: [], id: new Date().getTime() + 1 },
          (err2, res) => (err2 ? reject(err2) : resolve(res))
        );
      }
    );
  });
}
