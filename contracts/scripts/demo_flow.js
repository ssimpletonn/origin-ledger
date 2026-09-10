/* eslint-disable no-console */
// Полный сценарий без кошелька: все действия шлются от аккаунтов ganache.
// Запуск (нода + migrate + export уже сделаны):
//   npx truffle exec scripts/demo_flow.js --network development
//
// После прогона проверяйте backend:
//   curl localhost:8000/api/stats
//   curl localhost:8000/api/contents | python3 -m json.tool

const PROVToken = artifacts.require("PROVToken");
const ContentRegistry = artifacts.require("ContentRegistry");

const advanceTime = (seconds) =>
  new Promise((resolve, reject) =>
    web3.currentProvider.send(
      { jsonrpc: "2.0", method: "evm_increaseTime", params: [seconds], id: Date.now() },
      (e1) =>
        e1
          ? reject(e1)
          : web3.currentProvider.send(
              { jsonrpc: "2.0", method: "evm_mine", params: [], id: Date.now() + 1 },
              (e2, r) => (e2 ? reject(e2) : resolve(r)),
            ),
    ),
  );

module.exports = async function (cb) {
  try {
    const { toWei, keccak256, fromWei } = web3.utils;
    const accounts = await web3.eth.getAccounts();
    const [treasury, author, verifier] = accounts;

    const token = await PROVToken.deployed();
    const registry = await ContentRegistry.deployed();
    const challengePeriod = Number(await registry.challengePeriod());

    console.log("treasury:", treasury);
    console.log("author:  ", author);
    console.log("verifier:", verifier);

    // выдаём автору PROV на bond'ы
    await token.transfer(author, toWei("1000", "ether"), { from: treasury });
    await registry.setVerifier(verifier, true, { from: treasury });

    const bond = toWei("10", "ether");

    // 1) чистая регистрация -> потом withdraw
    await token.approve(registry.address, bond, { from: author });
    const h1 = keccak256("demo-clean-" + Date.now());
    const r1 = await registry.registerContent(h1, "ipfs://license/clean", bond, { from: author });
    const id1 = r1.logs[0].args.contentId.toString();
    console.log(`\n[1] registered #${id1}  hash=${h1}`);

    // 2) регистрация -> challenge -> подтверждённый дубликат (Revoked)
    await token.approve(registry.address, bond, { from: author });
    const h2 = keccak256("demo-dupe-" + Date.now());
    const r2 = await registry.registerContent(h2, "ipfs://license/dupe", bond, { from: author });
    const id2 = r2.logs[0].args.contentId.toString();
    console.log(`[2] registered #${id2}  hash=${h2}`);

    await registry.raiseChallenge(id2, { from: verifier });
    console.log(`[2] challenge raised by verifier`);

    const supplyBefore = BigInt((await token.totalSupply()).toString());
    await registry.resolveChallenge(id2, true, { from: treasury });
    const supplyAfter = BigInt((await token.totalSupply()).toString());
    console.log(`[2] resolved as duplicate -> Revoked, burned ${fromWei((supplyBefore - supplyAfter).toString())} PROV`);

    // 3) перематываем время и забираем bond по #1 (сгорает 5%)
    await advanceTime(challengePeriod + 60);
    const balBefore = BigInt((await token.balanceOf(author)).toString());
    const w = await registry.withdrawBond(id1, { from: author });
    const balAfter = BigInt((await token.balanceOf(author)).toString());
    console.log(`\n[1] withdrawBond -> event amount=${fromWei(w.logs[0].args.amount.toString())} PROV, ` +
                `balance +${fromWei((balAfter - balBefore).toString())} PROV`);

    console.log("\nГотово. Индексатор подхватит события за пару секунд:");
    console.log("  curl -s localhost:8000/api/stats");
    console.log(`  curl -s localhost:8000/api/contents/by-hash/${h1}`);
    cb();
  } catch (err) {
    cb(err);
  }
};
