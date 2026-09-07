<!--
# CITATION: chain facts below were read live from https://rpc.testnet.arc.io and
https://docs.arc.io/arc/references/connect-to-arc.md on 2026-09-07. Prize text is quoted from
https://ethglobal.com/events/ethonline2026/prizes as captured in
Clawdbot/ETHONLINE_2026_SCOUT_ARC_2026-09-07.md. Mainnet values that Arc has not published are
marked NOT PUBLISHED rather than filled in.
-->

# Arc mainnet readiness

For the Arc prize line, quoted from the ETHOnline 2026 prizes page:

> "Projects must be deployed or deployment-ready on Arc mainnet by September 30."

## Honest status, stated first

**This has not been verified on Arc mainnet, because Arc mainnet is not live yet.**

Arc's public mainnet launch is **September 16, 2026**
(https://www.arc.io/blog/arc-mainnet-goes-live-on-september-16-2026, and Circle's press room
"ahead of September 16 mainnet launch"). The ETHOnline submission deadline is **September 13,
2026 at 12:00 pm EDT**, three days earlier. So at submission time, testnet-only is the honest
and expected state for every team in this track, and the prize language says "deployed **or**
deployment-ready" for exactly that reason.

What is claimed here is the second half of that sentence: deployment-ready. What is **not**
claimed is a mainnet deployment, a mainnet transaction hash, or a measured mainnet gas cost.
There are none, and none are shown anywhere in this repo.

## What Arc has and has not published

Checked live on 2026-09-07 against `https://docs.arc.io/arc/references/connect-to-arc.md`. That
page documents **only testnet**. Every mainnet row below is therefore unfilled on purpose.

| Value | Testnet, verified | Mainnet |
|---|---|---|
| Chain id | `5042002` (`0x4cef52`), confirmed by `eth_chainId` | **NOT PUBLISHED by Arc** |
| RPC | `https://rpc.testnet.arc.io` | **NOT PUBLISHED** |
| Explorer | `https://testnet.arcscan.app` (Blockscout) | **NOT PUBLISHED** |
| Native USDC ERC-20 view | `0x3600000000000000000000000000000000000000`, `decimals()` 6 | **NOT PUBLISHED, do not assume the same predeploy** |
| CREATE2 proxy | `0x4e59b44847b379578588920cA78FbF26c0B4956C`, 69 bytes of code | expected identical, must be confirmed with `eth_getCode` |
| Gas token | USDC | expected USDC, must be confirmed |

### About the chain id 5042

A third-party aggregator lists Arc mainnet chain id as `5042` (`0x13b2`). That number does
**not** come from `docs.arc.io`, and a live fetch of Arc's own connect-to-arc reference on
2026-09-07 still documents testnet only.

**It is deliberately not written into any config file in this repo.** Guessing a chain id is how
a deploy lands on the wrong network or a signed transaction gets replayed somewhere unintended.
Pull it fresh from Arc's own docs on or after September 16 and paste the verified value.

## What must NOT change

This is the part that is easy to break and expensive to undo.

1. **The CREATE2 salts.** `create2-salts-manifest.json` in the TRAIDE repo, salts V1. Ten of the
   eleven fleet addresses are chain-invariant precisely because the salts and the init code are
   identical everywhere. Change a salt and Arc mainnet gets different addresses from the other
   26 chains, and the whole address-invariance property is gone.
2. **The canonical CREATE2 proxy** `0x4e59b44847b379578588920cA78FbF26c0B4956C`. Confirm it has
   code on mainnet, do not deploy a different one.
3. **`TRAIDEPair` / `TRAIDEFactory` bytecode.** `TRAIDEFactory` embeds
   `type(TRAIDEPair).creationCode`, so touching the Pair changes the Factory's bytecode, which
   changes the Factory's CREATE2 address **on all 26 chains**. The known first-liquidity bug
   (`_mint(address(0), MINIMUM_LIQUIDITY)` reverting under OpenZeppelin 5) is still unpatched for
   this reason. That is Ryan's call, not a deploy-time decision. See the LANE 1 section of
   `ETHONLINE_2026_BUILD_LOG.md`.
4. **The deployer** `0xcEDdA90b60748e04Ff9C4123c5f49544611748e5`. The fleet's constructor
   arguments hardcode it, so a different signer produces different addresses.
5. **The agent derivation paths** in `arc_agents/config.py`. Changing them changes every agent
   address and orphans the existing receipt history.
6. **The receipt canonicalization rule.** It is the traide-keeper rule and a test pins it. Change
   it and every previously anchored hash becomes unverifiable.

## What actually changes, and it is config only

No contract change and no code change is required. Every item below is a value, not logic.

### The agents, in this repo

`arc_agents/config.py`:

| Constant | Testnet value | Mainnet action |
|---|---|---|
| `CHAIN_ID` | `5042002` | set to Arc's published mainnet id |
| `DEFAULT_RPC_URL` | `https://rpc.testnet.arc.io` | set to Arc's published mainnet RPC |
| `EXPLORER_BASE` | `https://testnet.arcscan.app` | set to Arc's published mainnet explorer |
| `USDC` | `0x3600...0000` | read the mainnet address from Arc's docs and confirm `decimals()` on chain |
| `LINKMOCK` | `0x4A8ac012...` | replace with a real asset. A mock has no business on mainnet |
| `TRAIDE_AMM` | `0x4b6781Af...` | the mainnet fleet's AMM. Chain-invariant, so this is a lookup, not a rewrite |
| `MIN_GAS_PRICE_WEI` | `20_000_000_000` | re-measure with `eth_gasPrice`, do not assume the testnet floor |
| `SWAP_MIN/MAX_USDC_UNITS` | 0.001 to 0.010 USDC | revisit. Mainnet gas is real money |
| `AGENT_FUND_USDC_UNITS` | 1.0 USDC | revisit against a real funding budget |

Environment variables, all in the gitignored dotenv file:

| Variable | Changes |
|---|---|
| `ARC_RPC_URL` | yes, to the mainnet RPC |
| `ARC_DEPLOYER_PRIVATE_KEY` | same key, but the wallet now needs **real** USDC |
| `AGENT_SEED_MNEMONIC` | unchanged. Same three agents, same addresses |
| `GRAPH_API_KEY` / `GRAPH_GATEWAY_API_KEY` | unchanged. The Graph tiers are chain-independent |
| `DASHBOARD_PORT` | unchanged |

### The fleet, in the TRAIDE repo

Branch `ethonline-arc-2026`. One new network entry, the same shape as the Arc testnet entry
already committed there:

- `hardhat.config.js`: an `arcMainnet` network block plus its Blockscout custom-chain entry.
- `create2-wrapped-native.js`: a `WRAPPED_NATIVE[<mainnet chain id>]` row. On a USDC-gas chain
  this slot holds the native USDC ERC-20 view, the same pattern Celo already uses with its
  native-as-ERC-20 GoldToken.
- `verify-fleet-blockscout.js`: the mainnet explorer entry.

Then the identical four commands used on testnet, with no edits:

```bash
npx hardhat run create2-predict-fleet.js --network arcMainnet   # predict BEFORE spending gas
npx hardhat run create2-deploy-fleet.js  --network arcMainnet
cd ~/Documents/traide-celo && node verify-fleet-blockscout.js <mainnet chain id>
```

Predicting before funding is the point. If the ten chain-invariant addresses do not match the
other 26 chains, stop: something changed that should not have.

## Gas funding

Testnet gas came from `https://faucet.circle.com`, about 20 USDC, and the whole LANE 1 fleet plus
LANE 2 agents cost about 0.68 USDC of gas. **There is no mainnet faucet.** Mainnet gas is real
USDC and must be bridged or purchased into the deployer.

Budget, extrapolated from measured testnet gas and clearly labelled as an extrapolation, not a
mainnet measurement:

| Item | Measured on testnet | Note |
|---|---|---|
| 11-contract fleet | 0.5175 USDC at 25 gwei | scales linearly with the mainnet gas price |
| Anchor contract | about 0.0015 USDC | one deploy |
| Pair, liquidity, first swap | about 0.15 USDC | excluding the liquidity itself |
| Per agent cycle | about 0.005 USDC | roughly two swaps plus two anchors |

At the testnet gas price this is under 1 USDC for a full stand-up. Mainnet gas price is unknown
until mainnet exists, so multiply by the real ratio once `eth_gasPrice` answers.

## Preflight checklist

Nothing here is optional, and every item is a command whose output you should read.

**Before spending any gas**

- [ ] Pull the mainnet chain id, RPC and USDC address from `docs.arc.io` directly. Do not use the
      third-party `5042` figure without confirming it there.
- [ ] `eth_chainId` on the mainnet RPC returns exactly the documented id.
- [ ] `eth_getCode` on `0x4e59b44847b379578588920cA78FbF26c0B4956C` returns 69 bytes. No code
      means no CREATE2 proxy and the whole address-invariance plan stops here.
- [ ] `eth_getCode` on the mainnet USDC address returns non-empty, and `decimals()` returns 6.
- [ ] Confirm whether `deposit()` and `withdraw(uint256)` revert, as they do on testnet. If they
      do, the Router's ETH-specific paths remain unusable and the token-token paths are the route.
- [ ] `eth_gasPrice`, recorded, and `MIN_GAS_PRICE_WEI` set from it rather than from testnet.
- [ ] Deployer funded with real USDC, balance read back both ways (18-decimal `eth_getBalance`
      and 6-decimal `balanceOf`) and confirmed to agree.
- [ ] Check whether mainnet has a deploy allowlist. Testnet has none documented; Arc is an
      institutional network and mainnet rules may differ. Do not assume.

**Deploy**

- [ ] `create2-predict-fleet.js` run first, and the ten chain-invariant addresses match the other
      26 chains exactly. If not, stop.
- [ ] Fleet deployed, `eth_getCode` non-empty at all eleven addresses.
- [ ] All eleven source-verified on the mainnet explorer.
- [ ] `ArcReceiptAnchor` deployed, `total()` reads 0, `deployments/arc-<chain id>.json` written.

**Agents**

- [ ] Real second asset chosen. The LINKMock does not go to mainnet.
- [ ] Pool created and funded through `TRAIDEAMM`, not through the Factory/Router/Pair path.
- [ ] Agent wallets funded, tx hashes recorded, deployer left above its floor.
- [ ] `python3.11 -m arc_agents.runner --once --dry-run` shows the Graph tiers resolving.
- [ ] `GRAPH_ALLOW_KEYLESS=0` dry run still shows all three agents refusing. The load-bearing
      guard must survive the chain switch.
- [ ] One real cycle, then `python3.11 -m scripts.verify` returns ALL CHECKS PASSED.
- [ ] PM2 apps restarted with the mainnet env, crash-loop guards intact.

**After**

- [ ] Receipts appended to `ETHONLINE_2026_BUILD_LOG.md` with real mainnet hashes.
- [ ] This file updated: replace the NOT PUBLISHED rows with the real values and replace the
      honest-status paragraph at the top with the actual deployment receipts.

## Why this is genuinely config-only

The claim is testable rather than rhetorical. Nothing in `arc_agents/` branches on a chain id
other than the single guard in `ArcClient.__init__` that refuses to run on the wrong chain:

```python
if chain_id != config.CHAIN_ID:
    raise RuntimeError(f"wrong chain: {chain_id}, expected Arc testnet {config.CHAIN_ID}")
```

Addresses come from `config.py`, the RPC from an environment variable, the Graph tiers do not
know what chain the agents trade on, and the receipt and anchoring code is chain-agnostic. The
fleet side is already parameterized by network because 26 chains share one deploy script.

The one thing that is not config is the choice of a real second asset for the pair, which is a
founder decision about what the agents should actually trade, not an engineering task.
