<!--
# CITATION: field list captured by fetching https://developers.uniswap.org/hackathon-feedback live
on 2026-09-07 (HTTP 200, 81969 bytes). Question wording is quoted from that page. Answers are
drafted from this repo's code, its git history, and transactions on Arc testnet.
-->

# Uniswap Developer Feedback Form, drafted answers

Form URL, verified live 2026-09-07, HTTP 200:
**https://developers.uniswap.org/hackathon-feedback**

Required by the prize line: "a completed submission to the Uniswap Developer Feedback Form."

## How to use this document

**This form has NOT been submitted.** These are drafts for Ryan to paste and send in the browser.

Two things to know before filling it:

1. **The five dropdowns are JavaScript-populated.** The page ships five empty `<select>` elements
   whose options are injected at runtime, so the exact option strings could not be captured by
   fetching the HTML and are deliberately not guessed here. For each dropdown below there is an
   "intent" line saying what to pick. Read the actual options in the browser and choose the
   closest one.
2. **Fields are plain text.** No markdown. No asterisks, no pipe tables, no leading hashes. The
   answers below are already written as plain text and can be pasted as-is.

## Identity fields

| Field | Type | Required | Answer |
|---|---|---|---|
| First name | Short text | Yes | Ryan |
| Last name | Short text | No | Hammer |
| Email | Short text | Yes | Ryan's own address, his call which one |
| Telegram handle | Short text | Yes | nobanksnearby |
| Which hackathon did you participate in? | Short text | Yes | ETHOnline 2026 |

## Dropdown fields

### "Did you complete a project during the hackathon?"
Type: multiple choice, required. Options are JS-populated.
**Intent: yes, completed.** The project is deployed, running unattended, and publicly viewable.

### "Are you building an AI-powered or agentic project?"
Type: multiple choice, required. Options are JS-populated.
**Intent: yes.** Three autonomous agents, each with its own wallet, deciding and executing without
a human in the loop.

### "Were you able to successfully integrate Uniswap into your project?"
Type: multiple choice, required. Options are JS-populated.
**Intent: yes, successfully.** The Uniswap v3 subgraph is the live price signal driving real
on-chain trades.

### "How long did it take to get your first successful integration working?"
Type: multiple choice, required. Options are JS-populated.
**Intent: the shortest available bucket, well under an hour.** Measured from git history: about 13
minutes from the first line of the subgraph client to REBALANCE's first live trade off Uniswap
data. If the options start at something like "less than 1 hour," pick that.

### "Do you plan to continue building the project you started at this hackathon?"
Type: multiple choice, required. Options are JS-populated.
**Intent: yes.**

## Long text fields

### "What did you build?"
Required. Paste as plain text:

```
Three autonomous trading agents on Arc testnet, each with its own funded wallet, whose price
signal is the official Uniswap v3 subgraph.

Every decision cycle the agents query the Uniswap v3 subgraph through The Graph gateway for
bundles.ethPriceUSD and a 24 point tokenHourDatas series (open, high, low, close, priceUSD) for a
reference token, then decide, then execute a real swap on chain. One of the three agents,
REBALANCE, holds a target allocation by value, so without a Uniswap price it cannot compute a
target at all and refuses to trade. That is visible in the ledger: it held on 15 consecutive
cycles while the price tier was down, then traded on the first cycle that carried a price.

The part we think is novel is provability. Every decision produces a canonical JSON receipt that
records the endpoint, the subgraph id, the exact query and variables, the HTTP status and the
sha256 of the exact response bytes. The receipt is hashed and that hash is anchored on chain in
the same flow, signed by the agent that made the decision. So anyone can prove afterwards which
Uniswap subgraph response drove a specific trade, and when.

There is deliberately no fallback data source. If the query fails, the agents log the refusal and
hold. A test fails the build if any non Graph data source is reintroduced, because a silent
fallback would destroy the provenance guarantee.

Disclosure on scope: our own AMM, TRAIDE, is a Uniswap v2 style implementation that predates the
event and is not affiliated with Uniswap. We are not claiming that building it counts as building
on the Uniswap stack. The event work is the Uniswap v3 subgraph integration described above, plus
a v2 fork finding reported in the blocker field.

Repo: https://github.com/NoBanks/traide-arc-agents
Live dashboard: https://arc-agents.nohumannearby.com
```

### "What was the biggest blocker you faced?"
Optional, but answer it. Paste as plain text:

```
Finding a subgraph id we could trust. There was no canonical, per chain, machine readable list of
current Uniswap subgraph ids that we could fetch, so we collected four candidates from Graph
Explorer pages and the Uniswap developer docs and probed all four live.

Two of the four were dead and returned "subgraph not found". A third,
A3Np3RQbaBA6oKJgiwDJeo5T3zrYfGHPWFYayMwtNDum, was reachable but carried an incompatible schema: it
answers a _meta health check happily and then fails the real query with "Type Token has no field
volumeUSD". That is the dangerous case, because a health check based on _meta will select a
subgraph that cannot answer the query you actually need. We had exactly that bug and had to change
our resolver to validate using the real query instead.

Suggestion: publish a versioned, machine readable mapping of chain to current canonical subgraph
id in a Uniswap owned repo, so it can be fetched in CI, with dead deployments explicitly marked
deprecated rather than silently returning not found.

Two smaller blockers. First, the token lookup ordering by volumeUSD took 10.9 seconds against a
cold gateway, which tripped our 15 second timeout and surfaced as a confusing "no token found"
rather than as a timeout. Second, token symbol is not unique: querying symbol LINK returns several
tokens and only one is Chainlink, so a naive first result pick will eventually select an impostor
token, which for a trading agent is a real safety issue. We disambiguate by highest volumeUSD plus
a name check. A short "resolving a token safely" note in the docs would cover both.

Separately, and we think this is the most useful thing we can hand back: the Uniswap v2 pattern of
locking MINIMUM_LIQUIDITY with _mint(address(0), ...) reverts under OpenZeppelin 5, whose
ERC20._mint rejects the zero address with ERC20InvalidReceiver. Every v2 fork we have seen copies
that line verbatim. The failure is nasty because of when it fires: deploy succeeds, pair creation
succeeds, verification succeeds, and it only breaks on the first addLiquidity into a pair, so a
fork can ship to many chains and look healthy until someone actually funds a pool. We hit it on
our own v2 style fork across all 26 of its chains at once, and only found it because this was the
first chain we pushed past deployment into a funded pair. Static call evidence: revert selector
0xec442f05 with the zero address as the argument. The common fix is sending MINIMUM_LIQUIDITY to a
dead address such as 0x000000000000000000000000000000000000dEaD.

Suggestion: one sentence in the v2 docs, or a comment in the reference UniswapV2Pair source,
noting the OpenZeppelin 5 incompatibility and the dead address workaround. This is not a bug in
v2, which predates OZ 5, but it is a real hazard for anyone deriving from it today.
```

### "If applicable: what was the hardest part of building an agentic app on Uniswap?"
Optional, but this is the question the prize actually cares about. Paste as plain text:

```
Provability, not the query. The query was the easy part.

An autonomous agent trading on Uniswap data raises an obvious question: how does anyone verify,
afterwards, what the agent actually saw? "The subgraph said the price was X" is unfalsifiable once
the block moves on, and an agent that cannot prove its inputs cannot really be audited.

Our answer was to record, per decision, the endpoint, the subgraph id, the exact query and
variables, the HTTP status and the sha256 of the exact response bytes, then hash the whole decision
receipt and anchor that hash on chain in the same transaction flow. That makes the Uniswap sourced
input to an autonomous trade checkable by a third party.

The second hard part was refusing to trade. It is easy, and tempting, to fall back to another
price source when the subgraph is unavailable. That quietly destroys the provenance story, because
the receipt no longer proves what informed the decision. Making the agent hold rather than degrade
was a deliberate design constraint, enforced in one place and covered by a test that fails the
build if a non Graph data source is reintroduced.

A practical gotcha specific to agentic use: through the gateway, both an unknown API key and a
dead subgraph id come back as HTTP 200 with a GraphQL error body. Any client treating response.ok
as success will silently read zero rows, and a trading agent will then act on an empty price
series. Showing the error checking path in the docs examples, not just the happy path, would
prevent a whole class of silent failure.
```

### "What support was missing, or could have been better?"
Optional. Paste as plain text:

```
Everything we needed was in the schema and the docs; what was missing was a trustworthy pointer to
which deployment to query. Concretely, in priority order:

1. A machine readable, versioned chain to subgraph id mapping in a Uniswap owned repo, with dead
   deployments marked deprecated.
2. An OpenZeppelin 5 note on the v2 MINIMUM_LIQUIDITY zero address mint.
3. Error checking shown in the subgraph query examples, since gateway failures return HTTP 200.
4. A short note that token symbol is not unique and that ordering by volumeUSD is the safe
   disambiguator.

We did not use office hours, Discord or mentorship, so we cannot rate those. The schema repo was
the single most useful resource: verifying every field against
github.com/Uniswap/v3-subgraph schema.graphql before writing any client code is the reason the
price query worked on its first live attempt.
```

### "Any additional feedback?"
Optional. Paste as plain text:

```
The v3 subgraph schema is genuinely well designed for agent consumption. tokenHourDatas exposing
open, high, low, close and priceUSD in one entity means a price series an agent can reason about
is a single query rather than a reconstruction from swap events, and Bundle.ethPriceUSD alongside
Token.derivedETH is a clean separation. That design choice is why this integration took minutes
rather than hours.

Worth crediting too: the v2 constant product design is simple enough to reimplement correctly and
reason about, which is why independent implementations of it exist at all. That is a real
contribution that rarely gets acknowledged.

Full written feedback, with evidence and transaction hashes, is in FEEDBACK.md at the repo root:
https://github.com/NoBanks/traide-arc-agents/blob/main/FEEDBACK.md
```

## Rating fields

| Field | Scale | Suggested | Why |
|---|---|---|---|
| "How helpful was the Uniswap documentation for your use case?" | 1 to 5, required | **4** | The schema repo was authoritative and complete, and verifying against it up front is why the integration worked first try. Held back from 5 only by the missing canonical subgraph id mapping and the absent OZ 5 note, both of which cost real time |
| "How would you rate the support Uniswap provided overall?" | 1 to 5, required | Ryan's call | We did not use office hours, Discord or mentorship, so a low score would be misleading and a high score unearned. If the scale allows a neutral middle, 3 is the honest answer, and the reason is stated in the support-missing field |

## Checkbox fields

### "What type of support did you use?"
Checkboxes, optional. Options: Developer office hours, Mentorship, Technical docs, Discord
support, Code examples / templates, Other.

**Tick: Technical docs only.** That is the truth. Do not tick office hours, mentorship or Discord,
none of which were used.

### "Can we follow up with you about your feedback?"
Yes/No, optional. **Suggested: Yes.** The OpenZeppelin 5 v2 fork finding is worth a conversation.

### Terms and Privacy agreement
Checkbox, required. Ryan ticks it himself.

## Before submitting

- [ ] The five dropdowns actually read in the browser and the closest option chosen, since the
      option strings are not captured here.
- [ ] Every long answer pasted as plain text. No asterisks, no pipe tables, no leading hashes.
- [ ] Email and Telegram confirmed correct.
- [ ] The repo is public and FEEDBACK.md is visible at the URL quoted in the answers.
- [ ] Submitted by Ryan in the browser. This document is a draft, not a submission.
