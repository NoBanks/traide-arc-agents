<!--
# CITATION: prize requirement text is quoted from https://ethglobal.com/events/ethonline2026/prizes
as captured verbatim in Clawdbot/ETHONLINE_2026_SCOUT_ARC_2026-09-07.md and
Clawdbot/ETHONLINE_2026_SCOUT_GRAPH_UNISWAP_WORLD_LEDGER_2026-09-07.md on 2026-09-07. Every tx
hash, address and count below was read live from https://rpc.testnet.arc.io and is checkable on
https://testnet.arcscan.app. Counts are a snapshot; the agents are still running, so the live
figures at judging time will be higher, never lower.
-->

# Prize evidence map

One section per target prize. Each requirement is quoted from the ETHOnline 2026 prizes page,
then mapped to concrete evidence: a file path, an address, a transaction hash, or a URL.

Nothing in this document is aspirational. If something is not done, it says so.

## Quick reference

| Thing | Value |
|---|---|
| Repo | https://github.com/NoBanks/traide-arc-agents (public, MIT) |
| Live dashboard | https://arc-agents.nohumannearby.com |
| Chain | Arc testnet, id 5042002 |
| Explorer | https://testnet.arcscan.app |
| Swap venue, TRAIDEAMM | [0x4b6781AfC7e91D65acdD37a424D7A43f170f9120](https://testnet.arcscan.app/address/0x4b6781AfC7e91D65acdD37a424D7A43f170f9120) |
| Anchor, ArcReceiptAnchor | [0x107B82c61E006A962a6C4ec1E9379667B6fa3f09](https://testnet.arcscan.app/address/0x107B82c61E006A962a6C4ec1E9379667B6fa3f09) |
| PASSIVE | [0x537F486eAEc5e564f3F9d8d010f8A5992cda2544](https://testnet.arcscan.app/address/0x537F486eAEc5e564f3F9d8d010f8A5992cda2544) |
| AGGRESSIVE | [0x5C33e8ec0087522F883a32A76D486D8ab2282701](https://testnet.arcscan.app/address/0x5C33e8ec0087522F883a32A76D486D8ab2282701) |
| REBALANCE | [0x27e13BC4CB091E7696D66c30887E3EE85f477c3B](https://testnet.arcscan.app/address/0x27e13BC4CB091E7696D66c30887E3EE85f477c3B) |
| Architecture diagram | [docs/architecture.png](architecture.png) |
| Uniswap feedback | [FEEDBACK.md](../FEEDBACK.md) |
| Public ledger export | https://arc-agents.nohumannearby.com/ledger.json (whole hash-chained ledger, byte-true per row; `?traded=1&limit=N`, `?agent=NAME`) |
| One receipt as JSON | `https://arc-agents.nohumannearby.com/receipt/<sha256>.json` |
| One-command verifier, per receipt | [`scripts/verify_receipt.py`](../scripts/verify_receipt.py): hash, `attestedAt` + `attestedBy`, anchor tx, swap tx, live Graph re-run. JUDGE QUICKSTART in [README.md](../README.md) |
| Whole-ledger verifier | [`scripts/verify.py`](../scripts/verify.py), falls back to the public export on a clone with no `data/` |

Snapshot at the time of writing, all reproducible with `python3.11 -m scripts.verify`:

```
[PASS] ledger: 51 receipts, 0 hash mismatches, 0 chain breaks
[PASS] swaps: 24 refetched from Arc, 0 not status 1
[PASS] anchors: 24 anchored, contract total() 24, 0 hashes absent on chain
[PASS] graph: 0 receipts with a tier but no provenance, 0 swaps made without a Graph tier
ALL CHECKS PASSED
```

24 real swaps: PASSIVE 11, AGGRESSIVE 11, REBALANCE 2. Six of those were decided by the Subgraph
price tier. REBALANCE also holds 15 recorded refusals, which is evidence in its own right and is
explained under The Graph section below.

**Re-run 2026-09-10** from a fresh clone with no dotenv and no `data/`, so the rows came from the
public `/ledger.json` export and every swap and anchor was refetched from Arc:

```
$ python3.11 -m scripts.verify
ledger: https://arc-agents.nohumannearby.com/ledger.json
[PASS] ledger: 2196 receipts, 0 hash mismatches, 0 chain breaks
[PASS] swaps: 589 refetched from Arc, 0 not status 1, 0 could not be fetched after 3 attempts
[PASS] anchors: 589 anchored, contract total() 589, 0 hashes absent on chain
[PASS] graph: 0 receipts with a tier but no provenance, 0 swaps made without a Graph tier

Graph endpoints that actually decided these trades:
  https://api.pinax.network/v1/evm/dexes
  https://api.pinax.network/v1/evm/pools
  https://gateway.thegraph.com/api/subgraphs/id/5zvR82QoaXYFyDEKLZ9t6v9adgnptxYpKpSbxtgVENFV

anchor contract: https://testnet.arcscan.app/address/0x107B82c61E006A962a6C4ec1E9379667B6fa3f09
ALL CHECKS PASSED
```

Three days unattended under PM2: 2196 decisions, 589 real swaps, 589 anchors, contract `total()`
589, zero mismatches. The ledger is still growing while this file sits still, so a judge's own
run will show larger numbers than these, never smaller.

---

## PRE-EXISTING versus NEW, the Continuity disclosure

Required by the Continuity policy: disclose pre-existing work in writing, and show what was built
during the event. Quoted policy: a Continuity project "brings an existing open-source repository
or extends an existing private/commercial product," the judged work must include "new features or
functionality developed during the hackathon," and "submissions with large single commits or
missing histories may be disqualified."

**PRE-EXISTING, not claimed as event work**

| Thing | What it is |
|---|---|
| TRAIDE AMM contract fleet | Uniswap-v2-style AMM, deployed on 26 chains. The Arc testnet deploy of this fleet is LANE 1, done 2026-09-07 immediately before this repo existed |
| TRAIDEAMM at `0x4b6781Af...` | The venue the agents trade on. Deployed and source-verified before this repo was created |
| traide-keeper | Receipt canonicalization and attestation. This repo reuses its hashing rule byte for byte and does not fork it |
| clip_sim.py paper agents | Four paper agents priced from DexScreener. They never touch a chain, and their data source is deliberately absent from this repo |
| x402 paid intelligence API | Paid endpoints on Base. Mentioned for completeness; this repo serves free routes only |

**NEW, built during the event.** Everything in this repository. Full statement in
[README.md](../README.md) under "NEW, built during ETHOnline 2026".

**Commit history**, incremental as the policy requires, no single squashed drop:

| Commit | What |
|---|---|
| `e2696c2` | scaffold: MIT license, ignore rules, env template, requirements |
| `a85bbdc` | core: Arc client, Graph client, keeper receipts, anchor contract, three agents |
| `b5c2c24` | dashboard, PM2 config, tests, README, architecture diagram |
| `79495ca` | verify CLI, and carry the activity reading across a restart |
| `bd2a70d` | graph: refuse a rate computed over too short a window |
| `182fad9` | compose a second Graph product: Subgraph price tier via the network gateway |
| `955524c` | subgraph price tier is live: REBALANCE made its first real trade |
| `f9a4438` | readme: live price tier receipts and the three gateway lessons |
| `f1fa108` | docs: Arc mainnet readiness, config-only path plus preflight |

**Still Ryan's action, not a build task:** registering the project as a Continuity Project with
ETHGlobal and sending the written pre-existing-work disclosure. Track C's requirement line is
explicit: "Be registered as a Continuity Project, under the Continuity Track." That registration
has not been confirmed done, and this document does not claim it has.

---

## Arc, Track C: Best DeFi or Agentic Application (Continuity), 1,666 USD

Track C "combines Tracks A and B's requirements for Continuity-track participants," so both are
mapped below.

> Track B: "Build AI agents that hold wallets, make payments, manage risk, settle jobs or
> transact with other agents using USDC." Agents need clear decision logic and autonomous
> spending flows.

| Requirement | Evidence |
|---|---|
| Agents that **hold wallets** | Three, each with its own key, derived deterministically in [`arc_agents/wallets.py`](../arc_agents/wallets.py) from one gitignored BIP-39 seed at paths `m/44'/60'/0'/0/1..3`. Addresses in the Quick reference table above, all funded on chain |
| **Make payments using USDC** | 24 real swaps against TRAIDEAMM, quote asset is Arc's native USDC `0x3600000000000000000000000000000000000000`. First: [0x8a3c6944...](https://testnet.arcscan.app/tx/0x8a3c694454c088a3c36aaba289e241fdc5d1db14a5a13699adc424e745e0e90d). Full table in `ETHONLINE_2026_BUILD_LOG.md` |
| **Manage risk** | Per-swap size capped at 0.001 to 0.010 USDC (`SWAP_MIN/MAX_USDC_UNITS`); every swap quoted first and sent with a 2 percent slippage floor (`runner._execute`); each agent keeps 0.2 USDC back for gas, since on Arc gas and the traded asset are the same thing; the deployer is never drawn below a 10 USDC floor |
| **Clear decision logic** | [`arc_agents/agents.py`](../arc_agents/agents.py), three named strategies with explicit thresholds. Every decision records a human-readable reason, for example "REBALANCE: LINK share 0.190, target 0.406 from the Graph price tier (-1.87 percent), drift -0.216" |
| **Autonomous spending flows** | No human in the loop. PM2 app `arc-agents-runner` decides, approves, swaps and anchors on a 300 second cycle. By 2026-09-10, three days after launch: 589 real swaps and 589 anchors, unattended, all re-verified from a clean clone (see the 2026-09-10 re-run under Quick reference) |
| Track A: "stablecoin-native DeFi on Arc... swaps, liquidity provision" | Swaps by the agents; liquidity provision by the deployer, which deepened the pool from 0.05 to 2.00 USDC a side in [0x671aef83...](https://testnet.arcscan.app/tx/0x671aef8352d4b5c8bfdd1e630ae91403852aa591e0ab17763a9141f94ad3cdec) |
| "functional MVP with a diagram showing working frontend and backend" | Backend: the runner and the fleet on Arc. Frontend: https://arc-agents.nohumannearby.com, with the ledger exported whole at `/ledger.json` and per row at `/receipt/<sha256>.json`. Diagram: [docs/architecture.png](architecture.png), generated from code by [`scripts/make_architecture_png.py`](../scripts/make_architecture_png.py) |
| "GitHub/Replit repo link" | https://github.com/NoBanks/traide-arc-agents |
| "video demo + presentation" | **NOT DONE.** A 2 to 4 minute demo video is required by the submission form and does not exist yet. This is the single largest open item |
| "Be registered as a Continuity Project" | **NOT CONFIRMED.** Ryan's action, see the disclosure section above |

**Beyond the minimum**, the part that is actually distinctive: every decision produces a
canonical receipt whose sha256 is anchored on Arc in the same flow, signed by the agent that made
the decision. An auditor can prove what an autonomous agent knew, when it knew it, and that it
acted on it. Sample: [docs/sample_receipt_price_tier.json](sample_receipt_price_tier.json).

---

## Arc, Track E: Launch on Arc Testnet and Push to Mainnet (Continuity), 1,500 USD

> "Add working Arc integration to existing products" covering "USDC/EURC payment flows,
> crosschain transfers, agentic payments, stablecoin settlement, or treasury features."

> "Projects must be deployed or deployment-ready on Arc mainnet by September 30."

| Requirement | Evidence |
|---|---|
| "existing product" | TRAIDE, a 26-chain AMM that predates the event. Disclosed above |
| "working Arc integration" | Not a stub. An 11-contract fleet deployed by CREATE2, all source-verified on Blockscout, a funded pair, and 24 agent swaps. LANE 1 section of `ETHONLINE_2026_BUILD_LOG.md` |
| "agentic payments" | Three autonomous agents paying each other's counterparty, the pool, in USDC, unattended under PM2 |
| "stablecoin settlement" | Arc's gas token is USDC, so both the settlement asset and the gas are USDC. Handled explicitly: `eth_getBalance` reports 18 decimals and `balanceOf` reports 6 for the same balance, differing by exactly `10**12`, and [`arc_agents/chain.py`](../arc_agents/chain.py) names every quantity by its scale so the two can never be mixed |
| "deployed **or** deployment-ready on Arc mainnet by September 30" | Deployed on testnet, deployment-ready for mainnet. The config-only path, what must not change, the gas budget and a preflight checklist are in [docs/MAINNET_READY.md](MAINNET_READY.md) |
| Launched on Arc testnet | Yes. Chain 5042002, addresses in `deployments/arc-5042002.json` and the LANE 1 build log |

**Stated plainly:** there is no Arc mainnet deployment and none is claimed. Arc mainnet goes live
September 16, three days after the September 13 submission deadline, and Arc's own connect-to-arc
reference still documented testnet only when re-fetched on 2026-09-07. The prize language says
"deployed **or** deployment-ready" precisely for this window. The third-party mainnet chain id
`5042` is deliberately not written into any config file in either repo, because it is not
confirmed against Arc's own docs.

**Findings from actually exercising Arc**, which is the difference between an integration and a
deployment that was never used:

1. The 6-versus-18 decimal question on native USDC, settled empirically rather than argued.
2. `deposit()` and `withdraw(uint256)` on the native USDC view both revert, so the Router's
   ETH-specific paths cannot work on Arc and the token-token paths are the supported route.
3. TRAIDE pairs cannot take first liquidity on **any** chain, because `TRAIDEPair.sol:126` mints
   `MINIMUM_LIQUIDITY` to `address(0)` and OpenZeppelin 5 reverts `ERC20InvalidReceiver`. Found by
   pushing past deployment into a funded pair, which had never been done on any of the 26 chains.
   Deliberately not patched, because patching changes the Factory's CREATE2 address everywhere.
   Routed around through TRAIDEAMM instead, and the empty Factory pair is left on chain as the
   evidence trail rather than hidden.

---

## The Graph, Best AI Tooling or AI Use Case (Continuity), 5,000 USD pool

> "Use The Graph as a load-bearing part of the project... Consume live data from a Graph
> provider... Do meaningful work with the data: reasoning, decisions, automation, or a natural-
> language interface, not just printing a raw query result... Open-source the code with a clear
> README or SKILL.md... Select the pool that matches how you built."

| Requirement | Evidence |
|---|---|
| **"load-bearing"** | If the Graph call fails, no agent trades. Enforced in one place, `agents.decide`, before any strategy runs. There is no fallback source in the package, and `tests/test_agents.py::test_no_dexscreener_anywhere_in_the_decision_path` fails the build if one is reintroduced |
| load-bearing, **proved by a run** | `GRAPH_ALLOW_KEYLESS=0 python3.11 -m arc_agents.runner --once --dry-run` makes all three agents refuse. Transcript in [README.md](../README.md) |
| load-bearing, **proved by the ledger** | REBALANCE needs a price, so it held on **15 recorded cycles** while the price tier was down, then traded on the first cycle that carried a price. Refusals are receipts too, and they are in `data/receipts.jsonl` |
| **"Consume live data from a Graph provider"** | Two providers, refetched every cycle, never cached as a decision input |
| **"compose two or more of The Graph's products"** (the separate composability track, noted because this build satisfies it) | Token API **and** Subgraph gateway answering in the same cycle. Logged as "composed two Graph products: thegraph-subgraph-gateway, thegraph-token-api" and recorded per call as a `product` field in every receipt |
| **"meaningful work... not just printing a raw query result"** | The activity rate is differenced across cycles and compared to a **measured** steady state of 9.64 tx/s (raw windows in [docs/graph_activity_baseline.json](graph_activity_baseline.json)); the price series sets REBALANCE's target allocation. Both change what the agents do, then the decision is hashed and anchored on chain |
| **"Open-source the code with a clear README"** | MIT, public, [README.md](../README.md) has a dedicated "How The Graph is used" section with the exact queries |
| **Correct pool** | Continuity. Disclosure above |

### Product 1, Token API, keyless activity tier

```
GET https://api.pinax.network/v1/evm/dexes?network=base
```

No `security` block on that path in the live OpenAPI document
(`https://api.pinax.network/openapi`, spec 3.21.1+af56ff2, read 2026-09-07), and an
unauthenticated call returns HTTP 200. Implementation: [`arc_agents/graph.py`](../arc_agents/graph.py).

### Product 2, Subgraph through the decentralized network gateway

```
POST https://gateway.thegraph.com/api/subgraphs/id/5zvR82QoaXYFyDEKLZ9t6v9adgnptxYpKpSbxtgVENFV
Authorization: Bearer <GRAPH_GATEWAY_API_KEY>
```

```graphql
query ReferencePrice($tid: String!, $n: Int!) {
  bundles(first: 1) { ethPriceUSD }
  tokenHourDatas(where: {token: $tid}, orderBy: periodStartUnix,
                 orderDirection: desc, first: $n) {
    periodStartUnix open high low close priceUSD
  }
  _meta { block { number } hasIndexingErrors }
}
```

Implementation: [`arc_agents/subgraph.py`](../arc_agents/subgraph.py). Live response returned 24
hourly closes for LINK with ETH at 2490.675326884083227389169746640452 at block 25928106.

Nothing here is a guessed identifier. The subgraph id came from its Graph Explorer page and was
chosen by probing four candidates live; the reference token was resolved **by symbol** from live
subgraph data, which matters because the live response returns several tokens calling themselves
LINK; and every field was checked against `Uniswap/v3-subgraph` `schema.graphql` before being
wired.

### Provenance, which is the actual AI-tooling contribution

Every Graph call is recorded in the receipt that gets hashed and anchored: product, endpoint,
subgraph id, the exact query and variables, whether it was authenticated, HTTP status, **the
sha256 of the exact response bytes**, byte count and timestamp. So a verifier can prove which
Graph response an autonomous agent acted on, and the on-chain anchor pins when.

The API key never appears in a URL, a log line or a receipt. Verified by searching a full receipt
for the key value: not present.

**Worked example, REBALANCE's first price-tier trade:**

| Item | Value |
|---|---|
| Decision | BUY_LINK, "LINK share 0.190, target 0.406 from the Graph price tier (-1.87 percent)" |
| Swap tx | [0x92ee6657...](https://testnet.arcscan.app/tx/0x92ee66575f8700dc46f156b9041a8d6cef80d8ec78f2d0af1b38b54a562d1b09), status 1, block 60969449 |
| Receipt sha256 | `2d51c783230fe76de2b59fc2d3548840ebb41586a8c9cf23a4b5f985a5f120ee` |
| Anchor tx | [0x0311a0f9...](https://testnet.arcscan.app/tx/0x0311a0f9e7b1fc78a31cac92ce0b372718c0736f622a42eeb9b6a5b6312e54d3) |
| `attestedAt` on chain | 1788815904, nonzero |
| Full receipt | [docs/sample_receipt_price_tier.json](sample_receipt_price_tier.json) |

Anyone can re-run the whole chain of custody with `python3.11 -m scripts.verify`, which also
prints the Graph endpoints that actually decided the trades.

**And one receipt at a time, with the Graph calls re-issued live.** This is the check that makes
the provenance claim falsifiable rather than rhetorical. `scripts/verify_receipt.py` takes a hash
from the dashboard, recomputes the sha256, reads `attestedAt` and `attestedBy` from the anchor
contract, refetches the anchor and swap transactions, then re-issues every recorded Graph request
and compares response hashes. The keyless Token API call is always re-run; the gateway calls are
re-run when `GRAPH_GATEWAY_API_KEY` is set and skipped, saying so, when it is not. Output of the
worked example above, run 2026-09-10 from a clone with no dotenv and no `data/`:

```
$ python3.11 -m scripts.verify_receipt 2d51c783230fe76de2b59fc2d3548840ebb41586a8c9cf23a4b5f985a5f120ee
receipt 2d51c783230fe76de2b59fc2d3548840ebb41586a8c9cf23a4b5f985a5f120ee
  REBALANCE BUY_LINK cycle 16 at 2026-09-07T21:18:23Z on chain 5042002, engine traide-arc-agents 1.0.0
  source: https://arc-agents.nohumannearby.com/receipt/2d51c783230fe76de2b59fc2d3548840ebb41586a8c9cf23a4b5f985a5f120ee.json
  dashboard: https://arc-agents.nohumannearby.com
[PASS] hash: sha256(canonical JSON) = 2d51c783230fe76de2b59fc2d3548840ebb41586a8c9cf23a4b5f985a5f120ee, matches the ledger's receipt_hash
  rpc: https://rpc.testnet.arc.io (chain id 5042002, head block 61387822)
[PASS] anchor: attestedAt(0x2d51c783230f..) = 1788815904 (2026-09-07T21:18:24Z) on 0x107B82c6.., attestedBy = 0x27e13BC4.. which is the agent's own address
       https://testnet.arcscan.app/address/0x107B82c61E006A962a6C4ec1E9379667B6fa3f09
[PASS] anchor tx: 0x0311a0f9e7b1.. status 1, block 60969453, from the agent, to the anchor contract, Attested event carries this hash
       https://testnet.arcscan.app/tx/0x0311a0f9e7b1fc78a31cac92ce0b372718c0736f622a42eeb9b6a5b6312e54d3
[PASS] swap tx: 0x92ee66575f87.. status 1, block 60969449, from the agent, to TRAIDEAMM 0x4b6781Af.., BUY_LINK amount_in 10000
       https://testnet.arcscan.app/tx/0x92ee66575f8700dc46f156b9041a8d6cef80d8ec78f2d0af1b38b54a562d1b09
[PASS] graph 1/3: thegraph-token-api https://api.pinax.network/v1/evm/dexes params {"network": "base"}
       recorded 2026-09-07T21:18:05Z HTTP 200, 1927 bytes, sha256 570bb047e39d..; live response now HTTP 200, 1927 bytes, sha256 91a25ab61741..: live data has moved since 2026-09-07T21:18:05Z, which is expected for a live index. The recorded hash pins what the agent saw and the anchor pins when
[SKIP] graph 2/3: thegraph-subgraph-gateway https://gateway.thegraph.com/api/subgraphs/id/5zvR82QoaXYFyDEKLZ9t6v9adgnptxYpKpSbxtgVENFV variables {"sym": "LINK"}
       recorded 2026-09-07T21:17:41Z HTTP 200, 846 bytes, sha256 7e7e1952e7ef..; not re-run: needs GRAPH_GATEWAY_API_KEY in the environment to re-run
[SKIP] graph 3/3: thegraph-subgraph-gateway https://gateway.thegraph.com/api/subgraphs/id/5zvR82QoaXYFyDEKLZ9t6v9adgnptxYpKpSbxtgVENFV variables {"n": 24, "tid": "0x514910771af9ca656af840dff83e8264ecf986ca"}
       recorded 2026-09-07T21:18:04Z HTTP 200, 6376 bytes, sha256 3914ec12e70d..; not re-run: needs GRAPH_GATEWAY_API_KEY in the environment to re-run
[PASS] guard: decision traded on Graph tier "price"; a swap on tier "none" would fail here
RESULT: 6 PASS, 0 FAIL, 2 SKIP
```

The live Token API hash differs from the recorded one, and the verifier says so plainly instead
of pretending a live index stands still. What is provable is exactly what the receipt claims:
this agent saw a response with sha256 `570bb047..` at 21:18:05Z, decided on it, and anchored that
decision on chain 19 seconds later, signed by its own key.

---

## Uniswap Foundation: Best Uniswap Stack Contribution (Continuity), 2,000 USD, 2 winners

> "Build on or integrate any part of the Uniswap stack, including the Uniswap API, the Uniswap
> AMM (v2, v3, or v4), CCA, or any other Uniswap protocol... A public GitHub repository with
> open-source code, a FEEDBACK.md file, and a completed submission to the Uniswap Developer
> Feedback Form."

### Scope, stated honestly first

TRAIDE is an independent Uniswap-v2-**style** AMM that predates the event. It is not a deployment
of Uniswap Labs' contracts and is not affiliated with Uniswap. **This submission does not claim
that building TRAIDE counts as building on the Uniswap stack.** Calling an independent v2-style
implementation "the Uniswap AMM" would be a stretch and we are not making it.

The claim is narrower and unambiguous: the event work **consumes the official Uniswap v3 subgraph**
as the agents' live price signal, with that provenance written into on-chain-anchored receipts.
Plus a v2-fork finding reported back in `FEEDBACK.md`.

| Requirement | Evidence |
|---|---|
| "integrate any part of the Uniswap stack" | Official Uniswap v3 subgraph, queried per decision cycle through The Graph gateway. [`arc_agents/subgraph.py`](../arc_agents/subgraph.py) |
| "A public GitHub repository with open-source code" | https://github.com/NoBanks/traide-arc-agents, MIT, public |
| "a FEEDBACK.md file" | [FEEDBACK.md](../FEEDBACK.md) at the repo root, linked from the README |
| "a completed submission to the Uniswap Developer Feedback Form" | **SUBMITTED by Ryan 2026-09-07 ~15:45 PT (form at developers.uniswap.org/hackathon-feedback, filled from docs/UNISWAP_FEEDBACK_FORM_ANSWERS.md).** Form verified live at https://developers.uniswap.org/hackathon-feedback (HTTP 200, 2026-09-07). Every field captured with drafted answers in [docs/UNISWAP_FEEDBACK_FORM_ANSWERS.md](UNISWAP_FEEDBACK_FORM_ANSWERS.md). Ryan submits it in the browser |
| Continuity pool | Disclosure at the top of this document |

### Uniswap stack usage, file and line pointers

| What | Where |
|---|---|
| Price query: `bundles { ethPriceUSD }` plus `tokenHourDatas { periodStartUnix open high low close priceUSD }` | `arc_agents/subgraph.py:101-119` (`PRICE_QUERY`) |
| The `bundles(first: 1) { ethPriceUSD }` line | `arc_agents/subgraph.py:103` |
| The `tokenHourDatas` selection | `arc_agents/subgraph.py:104-116` |
| Token resolution by symbol, ordered by `volumeUSD` | `arc_agents/subgraph.py:89-99` (`TOKEN_QUERY`) |
| Candidate subgraph ids and their sources | `arc_agents/subgraph.py:70-79` (`CANDIDATE_SUBGRAPHS`) |
| Resolver that validates with the real query, not `_meta` | `arc_agents/subgraph.py:251-296` (`resolve`) |
| Impostor-token guard: highest `volumeUSD` whose name matches | `arc_agents/subgraph.py:315-330` (`_adopt_token`) |
| Gateway POST, provenance record, bearer auth so the key never enters a URL | `arc_agents/subgraph.py:122-199` (`_post`) |
| Guard for HTTP-200-with-GraphQL-error auth failures | `arc_agents/subgraph.py:201-210` (`auth_error`) |
| Timeout raised to 60s after measuring a 10.9s token scan | `arc_agents/subgraph.py:64` (`SUBGRAPH_TIMEOUT_SECONDS`) |
| Close series extracted, newest-last | `arc_agents/subgraph.py:332-380` (`price_series`) |
| Where the Uniswap price enters the Graph signal | `arc_agents/graph.py:364-371` |
| Price tier declared live | `arc_agents/graph.py:398` |
| Where the price drives a decision | `arc_agents/agents.py:93-101` (`decide`), `arc_agents/agents.py:185+` (`_rebalance`) |
| Price threshold | `arc_agents/agents.py:42` (`PRICE_MOVE`) |

### Load-bearing, demonstrated rather than asserted

REBALANCE's entire strategy is a target allocation by value, so without a Uniswap price it cannot
compute a target and refuses to trade. In the committed ledger it held on **15 consecutive
cycles** while the price tier was down, then traded on the first cycle that carried a price.

| Item | Value |
|---|---|
| First Uniswap-price-driven trade | [0x92ee6657...](https://testnet.arcscan.app/tx/0x92ee66575f8700dc46f156b9041a8d6cef80d8ec78f2d0af1b38b54a562d1b09), status 1, block 60969449 |
| Decision reason | "LINK share 0.190, target 0.406 from the Graph price tier (-1.87 percent), drift -0.216" |
| Receipt sha256 | `2d51c783230fe76de2b59fc2d3548840ebb41586a8c9cf23a4b5f985a5f120ee` |
| Anchor tx | [0x0311a0f9...](https://testnet.arcscan.app/tx/0x0311a0f9e7b1fc78a31cac92ce0b372718c0736f622a42eeb9b6a5b6312e54d3) |
| Receipt carrying the Uniswap subgraph provenance | [docs/sample_receipt_price_tier.json](sample_receipt_price_tier.json) |

### The contribution back to the ecosystem

Taking a v2-style fork past deployment into a funded pair surfaced a real hazard for every v2 fork
on modern OpenZeppelin: `UniswapV2Pair`'s `_mint(address(0), MINIMUM_LIQUIDITY)` reverts under
OpenZeppelin 5, whose `ERC20._mint` rejects the zero address with `ERC20InvalidReceiver`. Deploy,
pair creation and verification all succeed; it only fires on the **first** `addLiquidity`, so a
fork can ship to many chains and look healthy until someone funds a pool. Evidence, suggested
docs fix, and three further subgraph findings are written up in [FEEDBACK.md](../FEEDBACK.md).

---

## Open items

Honest list, so nothing here reads better than it is.

1. **Demo video, 2 to 4 minutes. NOT DONE.** Required by the submission form, which rejects
   anything under 2 or over 4 minutes. Any render must be 24fps.
2. **Continuity registration and the written pre-existing-work disclosure. NOT CONFIRMED.**
   Ryan's action. Track C names it as an explicit requirement.
3. **Prize selection.** The form allows up to 3 partner prizes, and all three are now chosen:
   Arc Track C, Arc Track E, The Graph AI Continuity, plus Uniswap Foundation Continuity mapped
   above. This document is the argument for each.
4. **Uniswap Developer Feedback Form. SUBMITTED by Ryan 2026-09-07 ~15:45 PT (form at developers.uniswap.org/hackathon-feedback, filled from docs/UNISWAP_FEEDBACK_FORM_ANSWERS.md).** Required by the Uniswap prize line.
   Answers drafted in [docs/UNISWAP_FEEDBACK_FORM_ANSWERS.md](UNISWAP_FEEDBACK_FORM_ANSWERS.md);
   Ryan submits it in the browser. Note the five dropdowns are JavaScript-populated, so their
   exact options must be read on the page rather than guessed.
5. **Arc mainnet.** Not deployed, correctly, and not claimed. See
   [docs/MAINNET_READY.md](MAINNET_READY.md).
6. **P and L is negative**, roughly 0.03 USDC per trading agent against holding, which is the 0.3
   percent AMM fee plus slippage on small swaps. It is on the dashboard as measured rather than
   hidden. These agents are a provenance demonstration, not a profitable strategy, and the repo
   does not claim otherwise.
