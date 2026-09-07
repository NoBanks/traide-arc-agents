<!--
# CITATION: every market number in this repo is live at query time from The Graph Token API
(https://api.pinax.network; endpoints and their auth requirements read from the live OpenAPI
document at https://api.pinax.network/openapi, spec 3.21.1+af56ff2, on 2026-09-07). Every
chain number is read live from https://rpc.testnet.arc.io and checkable on
https://testnet.arcscan.app. No simulated, projected or cached dataset is used anywhere in
the demo path.
-->

# traide-arc-agents

Three autonomous agents, each with its own funded wallet, trading a real pair on
Arc testnet. Every trade is decided by data pulled from The Graph at decision
time, recorded as a canonical keeper receipt, and anchored on Arc.

Built for ETHOnline 2026, Continuity track. TRAIDE is pre-existing work and this
repo is the event work. The split is spelled out below, line by line.

![architecture](docs/architecture.png)

## The one rule that matters

The Graph is load bearing. If the Graph call fails, the agents do not trade. They
log the refusal and skip the cycle. There is no fallback data source anywhere in
this program. DexScreener, which the pre-existing paper agent uses, is not
imported, not called, and not reachable from this code path.

The refusal is not a claim, it is a run:

```
$ GRAPH_ALLOW_KEYLESS=0 python3.11 -m arc_agents.runner --once --dry-run
cycle 1: Graph tier=none calls=0
  [GRAPH] no API key, not trading
  keyless activity tier disabled by GRAPH_ALLOW_KEYLESS=0
  no usable Graph signal, every agent holds this cycle
  PASSIVE: HOLD - [GRAPH] no API key, not trading
  AGGRESSIVE: HOLD - [GRAPH] no API key, not trading
  REBALANCE: HOLD - [GRAPH] no API key, not trading
```

## PRE-EXISTING, not event work

Documented here because the Continuity track requires it. None of this was built
during ETHOnline 2026 and none of it is claimed as event work.

| Thing | Where | What it is |
|---|---|---|
| TRAIDE AMM contract fleet | TRAIDE monorepo, deployed on 26 chains | Uniswap-v2-style AMM. The Arc testnet deploy of this fleet happened on 2026-09-07, immediately before this repo existed. |
| TRAIDEAMM on Arc | `0x4b6781AfC7e91D65acdD37a424D7A43f170f9120` | The venue these agents trade on. Deployed and source-verified before this repo was created. |
| traide-keeper | separate repo | Receipt canonicalization and on-chain attestation. This repo reuses its hashing rule exactly, and does not fork it. |
| clip_sim.py paper agents | TRAIDE agent backend | Four paper-trading agents priced from DexScreener. Referenced only to say what this is not: those agents do not touch a chain, and their data source is deliberately absent here. |
| x402 paid intelligence API | TRAIDE agent backend | Paid endpoints on Base. Mentioned for completeness. This repo serves free routes only. |

## NEW, built during ETHOnline 2026

Everything in this repository. Specifically:

- `arc_agents/graph.py`, the Graph client, its two tiers, its provenance record
  and the refusal guard.
- `arc_agents/agents.py`, three strategies whose decision input is a Graph signal.
- `arc_agents/wallets.py`, deterministic per-agent wallets from one gitignored seed.
- `arc_agents/chain.py`, the Arc client that refuses to report a transaction it
  has not re-read with status 1.
- `arc_agents/receipts.py`, a NEW receipt shape, `arc_agent_decision`, carrying
  Graph provenance. The canonicalization rule is the pre-existing traide-keeper
  rule, unchanged.
- `contracts/ArcReceiptAnchor.sol` and `arc_agents/anchor.py`, on-chain anchoring.
- `arc_agents/dashboard.py`, the read-only FastAPI view.
- `scripts/`, the setup, seed and diagram tooling.

## How The Graph is used

Both tiers hit The Graph's Token API, which runs at `api.pinax.network` under The
Graph brand. Every path below and its authentication requirement was read from
the live OpenAPI document at `https://api.pinax.network/openapi` on 2026-09-07
(spec version 3.21.1+af56ff2). Nothing is guessed.

### Tier 1, activity. Keyless, verified against the running service.

```
GET https://api.pinax.network/v1/evm/dexes?network=base
Accept: application/json
```

The OpenAPI spec carries no `security` block on this path, and an unauthenticated
call returns HTTP 200:

```
$ curl -s -o /dev/null -w "%{http_code}\n" "https://api.pinax.network/v1/evm/dexes?network=base"
200
```

The response gives, per DEX factory on the network, a cumulative `transactions`
count, a `uaw` unique-active-wallet count, and a `last_activity` timestamp.
Polling it once per cycle and differencing gives a transaction rate as of that
moment. The agents trade the deviation of that rate from a measured steady state,
not the level.

The steady state was measured, not assumed. Four unauthenticated polls sixty
seconds apart on 2026-09-07 gave 10.83, 8.24 and 9.85 transactions per second
across the three windows, mean 9.64. The raw windows are committed at
`docs/graph_activity_baseline.json` and the constant lives at
`graph.BASE_ACTIVITY_TX_PER_SECOND`.

### Tier 2, price. Requires GRAPH_API_KEY.

```
GET https://api.pinax.network/v1/evm/pools?network=base&factory=<factory>&limit=10
GET https://api.pinax.network/v1/evm/pools/ohlc?network=base&pool=<pool>&interval=1h&limit=24
Authorization: Bearer <GRAPH_API_KEY>
```

All three of `/v1/evm/pools`, `/v1/evm/pools/ohlc` and `/v1/evm/swaps` carry
`security: [{bearerAuth: []}]` in the spec, and an unauthenticated call is
refused:

```
$ curl -s "https://api.pinax.network/v1/evm/pools?network=base&limit=1"
{"error":{"status":401,"code":"unauthorized"}}
```

So there is no keyless route to reference prices. That is why the REBALANCE
agent, whose whole strategy is a value split and therefore needs a price, stands
down and logs `[GRAPH] no API key, not trading` until the key is set. One agent
that literally cannot act without The Graph is the clearest demonstration of
load-bearing this repo can offer.

The reference pool is not hardcoded. It is derived at runtime: the keyless dexes
call names the busiest Uniswap v3 factory on the reference network, and the pools
call enumerates that factory's pools. An operator can pin one with
`GRAPH_REFERENCE_POOL`.

### Provenance in every receipt

Every Graph call records the endpoint, the exact query parameters, whether it was
authenticated, the HTTP status, the sha256 of the exact response bytes, the byte
count, and the fetch timestamp. That block is embedded in the receipt that is
hashed and anchored, so a verifier can prove which Graph response the decision
was made from. The API key itself is never logged, never written to a receipt,
and never returned by any function.

A real receipt from a real cycle is committed at `docs/sample_receipt.json`, with
its swap transaction and its anchor transaction beside it. The running ledger is
at `data/receipts.jsonl` and is served at `/api/receipts`.

## The agents

| Agent | Derivation path | Strategy | Graph tier it needs |
|---|---|---|---|
| PASSIVE | `m/44'/60'/0'/0/1` | Contrarian. Buys weakness, sells strength, always the smallest size. | activity or price |
| AGGRESSIVE | `m/44'/60'/0'/0/2` | Trend follower. Size scales with signal strength. | activity or price |
| REBALANCE | `m/44'/60'/0'/0/3` | Holds a target split by pool value, leaning with the reference price. | price only, so it is flat without the key |

Wallets are BIP-44 children of one BIP-39 mnemonic held only in the gitignored
dotenv file. The paths are public because a path is not a secret; the mnemonic
never leaves the operator's machine and no private key is printed, logged or
serialized anywhere in this repo.

## Chain facts

| Fact | Value |
|---|---|
| Chain | Arc testnet, id 5042002 |
| RPC | `https://rpc.testnet.arc.io` |
| Explorer | `https://testnet.arcscan.app` |
| Gas token | USDC. Gas and the quote asset are the same asset. |
| Native USDC ERC-20 view | `0x3600000000000000000000000000000000000000`, 6 decimals |
| Second leg | LINKMock `0x4A8ac01265a030Aad32fb9B7bD5f89Be18f21858`, 18 decimals |
| Swap venue | TRAIDEAMM `0x4b6781AfC7e91D65acdD37a424D7A43f170f9120` |
| Anchor | ArcReceiptAnchor, address in `deployments/arc-5042002.json` |

Two Arc-specific facts this code is built around, both found by exercising the
chain rather than reading docs:

1. `eth_getBalance` reports the USDC balance at 18 decimals while `balanceOf`
   reports the same balance at 6. They differ by exactly `10**12`. Mixing them
   is an off-by-a-trillion bug, so `chain.py` names every quantity by its scale.
2. Swaps go through TRAIDEAMM, not the Factory/Router/Pair path. `TRAIDEPair`
   mints `MINIMUM_LIQUIDITY` to `address(0)`, which OpenZeppelin 5 reverts with
   `ERC20InvalidReceiver`, so a TRAIDE pair cannot take first liquidity on any
   chain. TRAIDEAMM keeps LP shares in its own mapping and never touches the
   zero address. The Factory pair exists on Arc and is left in place as the
   evidence trail rather than hidden.

## Anchoring, and why a contract instead of a memo

Both options were on the table. A self transfer carrying the receipt hash as
calldata is cheaper, but it leaves nothing queryable: a verifier would have to
scan every transaction the agent ever sent to find the anchors.
`ArcReceiptAnchor` costs a little more gas and gives three things a memo cannot:

- an indexed `Attested(attester, receiptHash, agent, timestamp)` event a verifier
  can filter, per agent, with one `eth_getLogs`
- a first-seen block per hash, so a receipt cannot be backdated
- a running `total()` the dashboard reads with one `eth_call`

At 25 gwei on Arc an anchor costs roughly 0.0015 USDC, so the extra cost is not a
real constraint. The contract has no owner, no admin and no upgrade path. Anyone
may attest. The agent that made the decision is the address that signs its own
anchor, so the evidence does not come from a shared operator account.

## Running it

```bash
python3.11 -m pip install -r requirements.txt

cp .env.example .env             # then fill it in, it is gitignored
python3.11 -m scripts.new_seed   # prints a fresh mnemonic, paste it into the dotenv

python3.11 -m scripts.setup_arc --plan   # show what it would do, send nothing
python3.11 -m scripts.setup_arc          # liquidity, funding, anchor deploy

python3.11 -m arc_agents.runner --once --dry-run   # decide, send nothing
python3.11 -m arc_agents.runner --once             # one real cycle
python3.11 -m arc_agents.runner                    # forever

python3.11 -m arc_agents.dashboard   # http://127.0.0.1:17360/
```

Unattended, under PM2, with the crash-loop guards this house requires
(`max_restarts`, `min_uptime`, exponential backoff, logs in `~/.pm2/logs`):

```bash
pm2 start ecosystem.config.js && pm2 save
pm2 logs arc-agents-runner --lines 50 --nostream
```

## Verifying the receipts yourself

```bash
curl -s http://127.0.0.1:17360/api/verify
```

That recomputes every receipt hash from its own canonical bytes and walks the
prev-hash chain. To check an anchor independently, call `attestedAt(bytes32)` on
the anchor contract with the receipt hash from the ledger; a nonzero result is
the block timestamp at which that exact receipt was first anchored on Arc.

## Deployment ready on Arc mainnet

Everything that differs between testnet and mainnet is configuration, not code:

- [ ] `ARC_RPC_URL` and `config.CHAIN_ID` point at Arc mainnet. Public launch is
      2026-09-16. The mainnet chain id circulating third hand is 5042 and it is
      NOT confirmed against Arc's own docs, so this repo does not configure it.
- [ ] `config.USDC` is Arc mainnet's native USDC address, read from chain, not
      assumed to be the same predeploy.
- [ ] `config.TRAIDE_AMM` is the mainnet fleet's AMM. The fleet deploys to the
      same CREATE2 addresses on every chain, so this is a lookup, not a rewrite.
- [ ] The second leg is a real asset, not a mock.
- [ ] `ArcReceiptAnchor` redeployed on mainnet and `deployments/` updated.
- [ ] Swap sizes revisited. Mainnet gas is real USDC.

No contract change and no code change is required for any of the above.

## License

MIT. See LICENSE.
