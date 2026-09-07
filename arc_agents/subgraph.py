"""
subgraph.py - the Subgraph price tier, queried through The Graph's decentralized
network gateway with a Subgraph Studio API key.

This is the SECOND Graph product this package consumes. The first is the Token
API activity tier in graph.py. Together they are a composition of two Graph
products, and every receipt records which product produced which number.

Why a subgraph and not the Token API for price: the Token API is a separate
service with a separate credential. Verified on 2026-09-07, token-api.thegraph.com
is a CNAME to token-api.service.pinax.network, and api.pinax.network returns
HTTP 401 for /v1/evm/pools and /v1/evm/pools/ohlc when presented with a Subgraph
Studio key. A Studio key is a gateway credential, not a Pinax JWT. So the honest
route to a reference price with the credential we actually have is a subgraph.

Gateway URL format, per
https://thegraph.com/docs/en/subgraphs/querying/from-an-application/ :

    https://gateway.thegraph.com/api/<API_KEY>/subgraphs/id/<SUBGRAPH_ID>

The newer bearer form is also accepted and is what this module sends, because it
keeps the key out of the URL and therefore out of any log line that records a URL:

    POST https://gateway.thegraph.com/api/subgraphs/id/<SUBGRAPH_ID>
    Authorization: Bearer <API_KEY>

Two transport details learned by probing the live gateway on 2026-09-07:
  - A request without a browser-shaped User-Agent is refused by Cloudflare with
    "error code: 1010" before it ever reaches the gateway. urllib's default
    User-Agent triggers this. This module always sends an explicit one.
  - A key the gateway does not recognize comes back HTTP 200 with a GraphQL body
    {"errors":[{"message":"auth error: API key not found"}]}, NOT a 401. So HTTP
    status alone is not a success test; the body must be inspected. auth_error()
    below is what the guard actually keys on.

Subgraph ids are NOT guessed. Each candidate below was taken from a Graph
Explorer subgraph page or from Uniswap's own developer docs, and the resolver
probes them live and keeps the first that actually answers with data.

Query fields were verified against the authoritative Uniswap v3 schema at
github.com/Uniswap/v3-subgraph (branch dev, schema.graphql, 657 lines, fetched
2026-09-07): Bundle.ethPriceUSD, Token.id/symbol/name/derivedETH/volumeUSD, and
TokenHourData.periodStartUnix/open/high/low/close/priceUSD all exist as used.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from typing import Any

from . import config

GATEWAY_BEARER_URL = "https://gateway.thegraph.com/api/subgraphs/id/{sid}"
GATEWAY_PATH_URL = "https://gateway.thegraph.com/api/{key}/subgraphs/id/{sid}"

USER_AGENT = "traide-arc-agents/1.0"
PRODUCT = "thegraph-subgraph-gateway"

# Candidate Uniswap v3 subgraphs, each with the page it came from. The resolver
# probes them in order and keeps the first that answers with data, so a dead or
# renamed deployment degrades to the next rather than breaking the agent.
CANDIDATE_SUBGRAPHS: list[tuple[str, str]] = [
    ("5zvR82QoaXYFyDEKLZ9t6v9adgnptxYpKpSbxtgVENFV",
     "thegraph.com/explorer/subgraphs/5zvR82QoaXYFyDEKLZ9t6v9adgnptxYpKpSbxtgVENFV"),
    ("ELUcwgpm14LKPLrBRuVvPvNKHQ9HvwmtKgKSH6123cr7",
     "thegraph.com/explorer/subgraphs/ELUcwgpm14LKPLrBRuVvPvNKHQ9HvwmtKgKSH6123cr7 (Uniswap v3 Ethereum)"),
    ("EN9rjKtzNitTEb5hgt8bmiyzzhwBpJrJaRihkg8Me8Rr",
     "thegraph.com/explorer/subgraphs/EN9rjKtzNitTEb5hgt8bmiyzzhwBpJrJaRihkg8Me8Rr (Uniswap V3 Official)"),
    ("A3Np3RQbaBA6oKJgiwDJeo5T3zrYfGHPWFYayMwtNDum",
     "developers.uniswap.org subgraph overview page"),
]

# Reference asset. Resolved BY SYMBOL from live subgraph data rather than by a
# hardcoded contract address, so no address in this file can be wrong. The
# resolver prefers the highest-volume match whose name looks like Chainlink.
REFERENCE_SYMBOL = "LINK"
REFERENCE_NAME_HINT = "chainlink"

META_QUERY = "{ _meta { block { number } hasIndexingErrors } }"

TOKEN_QUERY = """
query ResolveToken($sym: String!) {
  tokens(where: {symbol: $sym}, orderBy: volumeUSD, orderDirection: desc, first: 5) {
    id
    symbol
    name
    derivedETH
    volumeUSD
  }
}
""".strip()

PRICE_QUERY = """
query ReferencePrice($tid: String!, $n: Int!) {
  bundles(first: 1) { ethPriceUSD }
  tokenHourDatas(
    where: {token: $tid}
    orderBy: periodStartUnix
    orderDirection: desc
    first: $n
  ) {
    periodStartUnix
    open
    high
    low
    close
    priceUSD
  }
  _meta { block { number } hasIndexingErrors }
}
""".strip()


def _post(sid: str, query: str, variables: dict[str, Any], api_key: str) -> tuple[dict[str, Any], Any]:
    """
    One gateway POST. Returns (provenance_record, decoded_body_or_None).

    curl is used rather than urllib because the gateway sits behind Cloudflare,
    which rejects urllib's default User-Agent with error code 1010 before the
    request reaches The Graph. The key travels in an Authorization header and is
    never placed in the recorded URL.
    """
    url = GATEWAY_BEARER_URL.format(sid=sid)
    payload = json.dumps({"query": query, "variables": variables})
    fetched_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    body = b""
    status = 0
    error = ""
    try:
        proc = subprocess.run(
            [
                "curl", "-s", "-w", "\n%{http_code}", "-X", "POST", url,
                "-H", "Content-Type: application/json",
                "-H", f"Authorization: Bearer {api_key}",
                "-A", USER_AGENT,
                "--max-time", str(config.GRAPH_TIMEOUT_SECONDS),
                "-d", payload,
            ],
            capture_output=True, timeout=config.GRAPH_TIMEOUT_SECONDS + 10,
        )
        raw = proc.stdout.decode("utf-8", "replace")
        text, _, code = raw.rpartition("\n")
        body = text.encode("utf-8")
        status = int(code) if code.strip().isdigit() else 0
    except Exception as exc:
        error = type(exc).__name__

    decoded: Any = None
    if body and not error:
        try:
            decoded = json.loads(body.decode("utf-8"))
        except Exception:
            error = "invalid json"

    gql_errors = ""
    if isinstance(decoded, dict) and decoded.get("errors"):
        gql_errors = "; ".join(
            str(e.get("message", ""))[:120] for e in decoded["errors"][:3]
        )

    ok = (200 <= status < 300) and not error and not gql_errors and isinstance(decoded, dict) \
        and isinstance(decoded.get("data"), dict)

    record = {
        "product": PRODUCT,
        "provider": "thegraph-gateway",
        "endpoint": url,
        "subgraph_id": sid,
        "query": " ".join(query.split()),
        "variables": dict(variables),
        "authenticated": True,
        "status": status,
        "response_sha256": hashlib.sha256(body).hexdigest(),
        "response_bytes": len(body),
        "fetched_at": fetched_at,
        "ok": ok,
    }
    if error:
        record["error"] = error
    if gql_errors:
        record["graphql_errors"] = gql_errors
    return record, decoded


def auth_error(record: dict[str, Any]) -> bool:
    """
    True when the gateway rejected the credential rather than the query.

    The gateway answers an unknown key with HTTP 200 and a GraphQL error body,
    so this cannot be inferred from the status code. Verified live 2026-09-07:
    {"errors":[{"message":"auth error: API key not found"}]}
    """
    return "auth error" in str(record.get("graphql_errors", "")).lower()


class SubgraphPriceClient:
    """
    Resolves a working subgraph and a reference token once, then returns an OHLC
    close series per cycle. Nothing is cached as a decision input: the price
    series is refetched every cycle. Only the subgraph id and the token id, which
    are addressing information rather than market data, are remembered.
    """

    def __init__(self) -> None:
        self._sid: str = ""
        self._sid_source: str = ""
        self._token_id: str = ""
        self._token_label: str = ""
        self._auth_rejected: bool = False

    # ------------------------------------------------------------- resolution

    def _load_cache(self) -> None:
        path = config.SUBGRAPH_CACHE_PATH
        if self._sid or not path.exists():
            return
        try:
            c = json.loads(path.read_text())
            self._sid = str(c.get("subgraph_id", ""))
            self._sid_source = str(c.get("source", ""))
            self._token_id = str(c.get("token_id", ""))
            self._token_label = str(c.get("token_label", ""))
        except Exception:
            pass

    def _save_cache(self) -> None:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        config.SUBGRAPH_CACHE_PATH.write_text(json.dumps({
            "subgraph_id": self._sid,
            "source": self._sid_source,
            "token_id": self._token_id,
            "token_label": self._token_label,
        }, indent=2))

    def resolve(self, api_key: str) -> tuple[list[dict[str, Any]], list[str]]:
        """
        Pick a subgraph that answers, then resolve the reference token by symbol
        from live data. Returns (provenance records, notes).
        """
        calls: list[dict[str, Any]] = []
        notes: list[str] = []
        self._load_cache()

        override = config.subgraph_id_override()
        if override and not self._sid:
            self._sid, self._sid_source = override, "GRAPH_SUBGRAPH_ID env override"

        if not self._sid:
            for sid, source in CANDIDATE_SUBGRAPHS:
                rec, body = _post(sid, META_QUERY, {}, api_key)
                calls.append(rec)
                if auth_error(rec):
                    self._auth_rejected = True
                    notes.append(
                        "subgraph tier: the gateway rejected the API key "
                        "(auth error: API key not found). A Subgraph Studio DEPLOY key "
                        "will not query; a query API key from the Studio API Keys tab will."
                    )
                    return calls, notes
                if rec["ok"] and (body or {}).get("data", {}).get("_meta"):
                    self._sid, self._sid_source = sid, source
                    notes.append(f"subgraph tier: resolved {sid} from {source}")
                    break
            if not self._sid:
                notes.append("subgraph tier: no candidate subgraph answered")
                return calls, notes

        if not self._token_id:
            rec, body = _post(self._sid, TOKEN_QUERY, {"sym": REFERENCE_SYMBOL}, api_key)
            calls.append(rec)
            if auth_error(rec):
                self._auth_rejected = True
                notes.append("subgraph tier: the gateway rejected the API key")
                return calls, notes
            rows = ((body or {}).get("data") or {}).get("tokens") or []
            if not rows:
                notes.append(f"subgraph tier: no token with symbol {REFERENCE_SYMBOL}")
                return calls, notes
            preferred = [r for r in rows if REFERENCE_NAME_HINT in str(r.get("name", "")).lower()]
            chosen = (preferred or rows)[0]
            self._token_id = str(chosen.get("id", "")).lower()
            self._token_label = f"{chosen.get('symbol')} ({chosen.get('name')})"
            notes.append(
                f"subgraph tier: reference token {self._token_label} resolved by symbol "
                f"from live data, address {self._token_id}"
            )
        self._save_cache()
        return calls, notes

    # ------------------------------------------------------------------ price

    def price_series(self, api_key: str) -> tuple[list[dict[str, Any]], list[float], list[str]]:
        """
        Returns (provenance records, close series newest-last, notes).
        An empty series means the price tier produced nothing this cycle, which
        the caller must treat as "do not trade on price".
        """
        calls, notes = self.resolve(api_key)
        if not self._sid or not self._token_id:
            return calls, [], notes

        rec, body = _post(
            self._sid, PRICE_QUERY,
            {"tid": self._token_id, "n": config.GRAPH_OHLC_LIMIT},
            api_key,
        )
        calls.append(rec)
        if auth_error(rec):
            self._auth_rejected = True
            notes.append("subgraph tier: the gateway rejected the API key")
            return calls, [], notes
        if not rec["ok"]:
            notes.append(
                "subgraph tier: price query failed "
                f"(status {rec['status']}{', ' + rec['graphql_errors'] if rec.get('graphql_errors') else ''})"
            )
            return calls, [], notes

        data = (body or {}).get("data") or {}
        rows = data.get("tokenHourDatas") or []
        # The gateway returns newest first; the strategy wants oldest first.
        closes: list[float] = []
        for r in reversed(rows):
            for field in ("close", "priceUSD"):
                v = r.get(field)
                if v not in (None, ""):
                    try:
                        f = float(v)
                    except (TypeError, ValueError):
                        continue
                    if f > 0:
                        closes.append(f)
                    break
        if closes:
            eth = ((data.get("bundles") or [{}])[0] or {}).get("ethPriceUSD")
            notes.append(
                f"subgraph tier: {len(closes)} hourly closes for {self._token_label} "
                f"from {self._sid[:12]}.., ETH reference {eth}"
            )
        else:
            notes.append("subgraph tier: price query returned no usable close series")
        return calls, closes, notes

    @property
    def auth_rejected(self) -> bool:
        return self._auth_rejected

    @property
    def subgraph_id(self) -> str:
        return self._sid

    @property
    def token_label(self) -> str:
        return self._token_label
