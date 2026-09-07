<!--
# CITATION: every claim below is backed by code in this repo, by a transaction on Arc testnet
(https://testnet.arcscan.app), or by a live fetch on 2026-09-07 of the Uniswap v3 subgraph schema
at github.com/Uniswap/v3-subgraph and of The Graph gateway. Timings are taken from this repo's
git history, not estimated after the fact.
-->

# FEEDBACK.md

Feedback for the Uniswap Foundation, from ETHOnline 2026, Continuity track.

Written for the prize requirement quoted from the ETHOnline 2026 prizes page:

> "Build on or integrate any part of the Uniswap stack, including the Uniswap API, the Uniswap
> AMM (v2, v3, or v4), CCA, or any other Uniswap protocol... A public GitHub repository with
> open-source code, a FEEDBACK.md file, and a completed submission to the Uniswap Developer
> Feedback Form."

Project: three autonomous agents trading a real pair on Arc testnet, whose price signal comes
from the official Uniswap v3 subgraph. Repo: https://github.com/NoBanks/traide-arc-agents
Live: https://arc-agents.nohumannearby.com

## PRE-EXISTING versus NEW, stated before anything else

Being precise about this matters more than the feedback itself, because the honest scope changes
what this submission is claiming.

**PRE-EXISTING, built long before ETHOnline 2026, not claimed as event work:**

TRAIDE is an independent Uniswap-v2-style AMM deployed on 26 chains. It is an original
implementation in the v2 constant-product style. It is **not** a deployment of Uniswap Labs'
contracts, it is **not** affiliated with Uniswap, and this submission does not claim that
building TRAIDE is "building on the Uniswap stack." Calling an independent v2-style AMM "the
Uniswap AMM" would be a stretch, and we are not making it.

**NEW, built during the event, and this is what touches the Uniswap stack:**

The agents in this repo consume the **official Uniswap v3 subgraph** as their price signal, at
decision time, through The Graph's decentralized network gateway. That is an unambiguous
integration with Uniswap protocol data. Every decision informed by it is written into a canonical
receipt whose sha256 is anchored on chain, so the Uniswap-sourced data that drove an autonomous
trade is provable after the fact.

Separately, taking a v2-style fork all the way into a funded pair surfaced a real
OpenZeppelin-5 issue that we think is worth the Uniswap ecosystem's attention. It is written up
below, because it will bite anyone maintaining a v2 fork on modern OpenZeppelin.

## What we built on the Uniswap stack

The price tier lives in `arc_agents/subgraph.py`. One query per decision cycle:

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

The reference token is resolved by symbol from live subgraph data rather than by a hardcoded
address:

```graphql
query ResolveToken($sym: String!) {
  tokens(where: {symbol: $sym}, orderBy: volumeUSD, orderDirection: desc, first: 5) {
    id symbol name derivedETH volumeUSD
  }
}
```

That output changes what the agents do. It is not logged and discarded. The REBALANCE agent's
entire strategy is a value split, so without a Uniswap price it cannot compute a target and
refuses to trade. Recorded in the ledger: REBALANCE held on 15 consecutive cycles while the price
tier was down, then traded on the first cycle that carried a price. Its first price-driven trade
is transaction
`0x92ee66575f8700dc46f156b9041a8d6cef80d8ec78f2d0af1b38b54a562d1b09`, status 1, whose receipt
hash `2d51c783230fe76de2b59fc2d3548840ebb41586a8c9cf23a4b5f985a5f120ee` is anchored on Arc in
`0x0311a0f9e7b1fc78a31cac92ce0b372718c0736f622a42eeb9b6a5b6312e54d3`.

## What worked

**The v3 subgraph schema is genuinely well designed for this.** `tokenHourDatas` gives
`open`, `high`, `low`, `close` and `priceUSD` in one entity, so a price series that an agent can
reason about is a single query rather than a reconstruction from swap events. `Bundle.ethPriceUSD`
alongside `Token.derivedETH` is a clean separation. We got a usable 24-point hourly series on the
first query that ran.

**The schema is authoritative and readable.** We verified every field we intended to use against
`github.com/Uniswap/v3-subgraph`, branch `dev`, `schema.graphql`, **before** wiring anything.
Every field existed exactly as documented. That single check is the reason the price query worked
on its first live attempt, with no schema-guessing round trips.

**Response quality was excellent.** The price query returned in 0.3 seconds with 24 hourly closes
and `hasIndexingErrors: false`.

**The v2 design is still a good teacher.** TRAIDE exists because the v2 constant-product design is
simple enough to reimplement correctly and reason about. That is a real contribution of the
Uniswap stack that rarely gets credited.

## What did not work, and what we suggest

Four things cost us real time. Each has a concrete suggestion.

### 1. There is no canonical, per-chain list of subgraph ids that we could rely on

This was the single biggest time sink. We needed the Uniswap v3 subgraph id for a mainnet price
reference and there was no one authoritative page mapping chain to current subgraph id that we
could fetch and trust. We ended up collecting four candidate ids from Graph Explorer pages and the
Uniswap developer docs, then **probing all four live** and keeping whichever answered.

That probing was not wasted effort, because it surfaced two genuine problems:

- Two of the four ids are **dead**. They return `{"errors":[{"message":"subgraph not found: ..."}]}`.
- One of them, `A3Np3RQbaBA6oKJgiwDJeo5T3zrYfGHPWFYayMwtNDum`, is reachable but carries an
  **incompatible schema**: it answers `_meta` happily and then fails the real query with
  ``Type `Token` has no field `volumeUSD` ``.

That last one is the dangerous case. A naive health check that probes `_meta` will happily select
a subgraph that cannot answer the query you actually need. We had exactly that bug and had to fix
the resolver to validate using the real query instead
(`arc_agents/subgraph.py`, `resolve()`).

**Suggestion:** publish a machine-readable, versioned mapping of chain to current canonical
subgraph id, ideally a JSON file in a Uniswap-owned repo so it can be fetched in CI, with dead
deployments explicitly marked as deprecated rather than silently 404ing. A docs table that goes
stale is the current failure mode; a fetchable file with a deprecation flag would have saved us
the entire probing exercise.

### 2. The v2 fork guidance has not caught up to OpenZeppelin 5

This is the finding we would most like to hand back to the ecosystem.

`UniswapV2Pair` locks the first `MINIMUM_LIQUIDITY` by minting it to `address(0)`. Every v2 fork
we have seen copies that line verbatim. **Under OpenZeppelin 5, that reverts.** OZ 5's
`ERC20._mint` rejects the zero address with `ERC20InvalidReceiver(address(0))`.

The consequence is nasty because of *when* it fires: deployment succeeds, pair creation succeeds,
verification succeeds, and everything looks healthy. It only breaks on the **first**
`addLiquidity` into a pair. A fork can therefore ship to many chains and look completely fine
until someone actually funds a pool.

Evidence from a static call on Arc testnet:

```
router.addLiquidity(...) -> revert 0xec442f05
                            0000000000000000000000000000000000000000000000000000000000000000
   0xec442f05 = ERC20InvalidReceiver(address), argument = the zero address
pair.mint(...)           -> panic 0x11 (underflow), the expected follow-on with empty reserves
```

We hit this on our own v2-style fork across all 26 of its chains at once, and only found it
because Arc was the first chain we pushed past deployment into a funded pair. The usual fix in
post-OZ-5 forks is to send `MINIMUM_LIQUIDITY` to a dead address such as
`0x000000000000000000000000000000000000dEaD` instead.

**Suggestion:** add a short note to the v2 documentation, or a comment in the reference
`UniswapV2Pair` source, saying that the `_mint(address(0), MINIMUM_LIQUIDITY)` line is
incompatible with OpenZeppelin 5 and naming the dead-address workaround. One sentence in the docs
would save a lot of forks a silent, late-firing failure. This is not a bug in Uniswap v2, which
predates OZ 5, but it is a real hazard for everyone deriving from it today.

### 3. Gateway failures come back as HTTP 200

Not strictly Uniswap's surface, but it hits anyone consuming the Uniswap subgraphs, so it is worth
saying. Through The Graph's gateway, **both** an unknown API key and a dead subgraph id return
**HTTP 200** with a GraphQL error body:

```
{"errors":[{"message":"auth error: API key not found"}]}
{"errors":[{"message":"subgraph not found: ELUcwgpm14LKPLrBRuVvPvNKHQ9HvwmtKgKSH6123cr7"}]}
```

Any client that treats `resp.ok` as success will silently read zero rows and, in a trading agent,
happily act on an empty price series. Our guard therefore inspects response bodies, never status
codes (`arc_agents/subgraph.py`, `auth_error()`).

**Suggestion:** wherever the Uniswap docs show a subgraph query example, show the error-checking
path too, not just the happy path. A three-line "check `body.errors` before `body.data`" snippet in
the docs example would prevent a whole class of silent failure.

### 4. The token lookup is slow enough to trip a default timeout

`tokens(where: {symbol: ...}, orderBy: volumeUSD)` measured **10.9 seconds** against a cold
gateway. Our 15 second client timeout was marginal, and the failure surfaced as a confusing
"no token with symbol LINK" rather than as a timeout. We raised the subgraph timeout to 60 seconds
(`arc_agents/subgraph.py`, `SUBGRAPH_TIMEOUT_SECONDS`).

Also worth documenting: **symbol is not unique.** Querying `symbol: "LINK"` returns several
tokens, only one of which is Chainlink. We resolve by taking the highest-`volumeUSD` match whose
`name` also looks right. A naive `tokens(where: {symbol: "X"})[0]` will eventually pick an
impostor token, which for a trading agent is a genuine safety issue.

**Suggestion:** a short "resolving a token safely" note in the docs, covering both the
non-uniqueness of `symbol` and the cost of ordering by `volumeUSD`, would be useful. The
`volumeUSD` ordering is the right disambiguator, it is just not obvious that you need one.

## The hardest part of building an agentic app on Uniswap data

Not the query. The query was the easy part.

The hard part is **provability**. An autonomous agent that trades on Uniswap data creates an
obvious question: how does anyone verify, afterwards, what the agent actually saw? "The subgraph
said the price was X" is unfalsifiable once the block moves on.

Our answer is to record, per decision, the endpoint, subgraph id, the exact query and variables,
the HTTP status, and **the sha256 of the exact response bytes**, then hash the whole decision
receipt and anchor that hash on chain in the same flow. A verifier can then prove which Uniswap
subgraph response drove a specific trade, and the anchor pins when. Sample receipt:
`docs/sample_receipt_price_tier.json`.

The second hard part is **refusing to trade**. It is easy to write an agent that falls back to
another price source when the primary fails. That quietly destroys the provenance story, because
the receipt no longer proves what informed the decision. Making the agent hold instead of degrade
was a deliberate design constraint, and it is enforced in one place and covered by a test that
fails the build if any non-Graph data source is reintroduced.

## Time spent

From this repo's git history, all on 2026-09-07:

| Item | Time |
|---|---|
| Whole project, first commit to prize-evidence docs | 13:40 to 14:25, about 45 minutes |
| Uniswap subgraph price tier, first line to REBALANCE's first live trade | 14:05 to 14:18, about 13 minutes |
| Of which: finding a working subgraph id and debugging the three failures above | roughly half |

The integration itself was fast because the schema was verified up front. Essentially all of the
lost time went into the four problems above, and three of the four were about **discovering which
subgraph to trust**, not about querying it.

## Would we keep building on this

Yes. The concrete next step is replacing the `LINKMock` second leg with a real asset and using
Uniswap v3 pool data as a live benchmark for the agents' own execution quality, so the receipts
can show the price the agent got against the reference price it could have got. That is a natural
extension of the provenance work and it needs the Uniswap subgraph to be meaningful.

## Pointers

| Thing | Where |
|---|---|
| Subgraph client, queries, resolver, error handling | `arc_agents/subgraph.py` |
| Where the price enters the decision | `arc_agents/agents.py`, `decide()` and `_rebalance()` |
| Receipt with Uniswap provenance | `docs/sample_receipt_price_tier.json` |
| Prize requirement mapping | `docs/PRIZE_EVIDENCE.md` |
| Drafted answers for the feedback form | `docs/UNISWAP_FEEDBACK_FORM_ANSWERS.md` |
