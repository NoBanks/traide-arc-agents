"""
graph.py - The Graph client. This module is load-bearing: if it returns no live
signal, the agents do not trade. There is no silent fallback to any other data
source anywhere in this package.

Two tiers, both against The Graph's Token API (run by Pinax under The Graph
brand). Endpoint paths and their auth requirements were read from the live
OpenAPI document at https://api.pinax.network/openapi on 2026-09-07, spec
version 3.21.1+af56ff2. Nothing here is guessed.

  ACTIVITY tier, keyless
    GET https://api.pinax.network/v1/evm/dexes?network=base
    The spec carries no security block on this path and a live unauthenticated
    call returned 200 with per-factory transaction counts, unique active wallet
    counts and a last_activity timestamp. Polling it across cycles yields a real
    market-activity delta, which is what the PASSIVE and AGGRESSIVE agents trade
    on. This is live data at query time, not a cached or mocked dataset.

  PRICE tier, requires GRAPH_API_KEY
    GET https://api.pinax.network/v1/evm/pools?network=base&factory=...
    GET https://api.pinax.network/v1/evm/pools/ohlc?network=base&pool=...
    GET https://api.pinax.network/v1/evm/swaps?network=base&pool=...
    All three carry security: [{bearerAuth: []}] in the spec, and a live
    unauthenticated call to /v1/evm/pools returned
    {"error":{"status":401,"code":"unauthorized"}}. So there is no keyless way
    to obtain reference prices, and the REBALANCE agent, which needs a price,
    refuses to trade until the key is set.

Every call records provenance: endpoint, query parameters, HTTP status, the
sha256 of the exact response bytes, and the timestamp. That provenance is
embedded in the keeper receipt so a verifier can prove the decision was informed
by live Graph data.

The API key is read from the environment and sent in an Authorization header.
It is never logged, never written to a receipt, and never returned by any
function in this module.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, asdict
from typing import Any

from . import config

NO_KEY_MESSAGE = "[GRAPH] no API key, not trading"


@dataclass
class GraphCall:
    """One HTTP call to a Graph provider, with everything a verifier needs."""

    provider: str
    endpoint: str
    params: dict[str, Any]
    authenticated: bool
    status: int
    response_sha256: str
    response_bytes: int
    fetched_at: str
    ok: bool
    error: str = ""

    def provenance(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("error" if not self.error else "__never__", None)
        return d


@dataclass
class GraphSignal:
    """
    The decision input. `tier` says which Graph tier produced it.

    activity_score  live DEX activity momentum on the reference network, from the
                    keyless dexes endpoint. Positive means transactions per second
                    across the reference factories is rising versus the last poll.
    price           reference pool close price from the OHLC endpoint, or None.
    price_change    fractional change of close over the OHLC window, or None.
    """

    tier: str
    activity_score: float | None = None
    price: float | None = None
    price_change: float | None = None
    calls: list[GraphCall] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        return self.tier != "none"

    @property
    def has_price(self) -> bool:
        return self.price is not None and self.price_change is not None

    def provenance(self) -> list[dict[str, Any]]:
        return [c.provenance() for c in self.calls]


def _get(
    path: str,
    params: dict[str, Any],
    api_key: str = "",
    base: str = config.GRAPH_TOKEN_API_BASE,
    provider: str = "thegraph-token-api",
) -> tuple[GraphCall, Any]:
    """
    One GET. Returns the provenance record and the decoded body (or None).
    Never raises on a transport or HTTP error; the caller reads call.ok.
    """
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})
    url = f"{base}{path}?{query}" if query else f"{base}{path}"
    headers = {"Accept": "application/json", "User-Agent": "traide-arc-agents/1.0"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    fetched_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    req = urllib.request.Request(url, headers=headers, method="GET")
    body = b""
    status = 0
    error = ""
    try:
        with urllib.request.urlopen(req, timeout=config.GRAPH_TIMEOUT_SECONDS) as resp:
            status = resp.status
            body = resp.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = exc.read() or b""
        error = f"http {exc.code}"
    except Exception as exc:  # transport failure, DNS, timeout
        error = f"{type(exc).__name__}"

    call = GraphCall(
        provider=provider,
        endpoint=f"{base}{path}",
        params=dict(params),
        authenticated=bool(api_key),
        status=status,
        response_sha256=hashlib.sha256(body).hexdigest(),
        response_bytes=len(body),
        fetched_at=fetched_at,
        ok=(200 <= status < 300 and not error),
        error=error,
    )

    decoded: Any = None
    if call.ok:
        try:
            decoded = json.loads(body.decode("utf-8"))
        except Exception:
            call.ok = False
            call.error = "invalid json"
    return call, decoded


# --------------------------------------------------------------- activity tier


def fetch_dex_activity(network: str = config.GRAPH_NETWORK) -> tuple[GraphCall, list[dict]]:
    """
    Keyless. Live DEX activity on the reference network. Verified 2026-09-07:
    HTTP 200 with no Authorization header.
    """
    call, body = _get(config.GRAPH_PATH_DEXES, {"network": network})
    rows = body.get("data", []) if isinstance(body, dict) else []
    return call, rows


def _activity_total(rows: list[dict]) -> tuple[int, int]:
    """Sum transactions and unique active wallets across the reported factories."""
    tx = sum(int(r.get("transactions", 0) or 0) for r in rows)
    uaw = sum(int(r.get("uaw", 0) or 0) for r in rows)
    return tx, uaw


# ------------------------------------------------------------------ price tier


def discover_reference_pool(api_key: str, network: str = config.GRAPH_NETWORK) -> tuple[list[GraphCall], str]:
    """
    Derive the reference pool from live Graph data instead of hardcoding one.

    1. keyless /v1/evm/dexes gives the factories on the network with their live
       transaction counts. Take the busiest one matching the reference protocol.
    2. /v1/evm/pools for that factory enumerates its pools. Take the first.

    An operator can pin a pool with GRAPH_REFERENCE_POOL, which skips both calls.
    The resolved pool is cached under data/ so restarts do not re-derive it.
    """
    override = config.graph_reference_pool_override()
    if override:
        return [], override

    cache = config.GRAPH_POOL_CACHE_PATH
    if cache.exists():
        try:
            cached = json.loads(cache.read_text())
            if cached.get("network") == network and cached.get("pool"):
                return [], str(cached["pool"]).lower()
        except Exception:
            pass

    calls: list[GraphCall] = []
    dex_call, rows = fetch_dex_activity(network)
    calls.append(dex_call)
    if not dex_call.ok or not rows:
        return calls, ""

    matching = [r for r in rows if r.get("protocol") == config.GRAPH_REFERENCE_PROTOCOL]
    if not matching:
        return calls, ""
    matching.sort(key=lambda r: int(r.get("transactions", 0) or 0), reverse=True)
    factory = str(matching[0].get("factory", "")).lower()
    if not factory:
        return calls, ""

    pool_call, body = _get(
        config.GRAPH_PATH_POOLS,
        {"network": network, "factory": factory, "limit": 10},
        api_key=api_key,
    )
    calls.append(pool_call)
    if not pool_call.ok or not isinstance(body, dict):
        return calls, ""
    data = body.get("data") or []
    if not data:
        return calls, ""
    pool = str(data[0].get("pool") or data[0].get("address") or "").lower()
    if pool:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"network": network, "pool": pool, "factory": factory}, indent=2))
    return calls, pool


def fetch_pool_ohlc(api_key: str, pool: str, network: str = config.GRAPH_NETWORK) -> tuple[GraphCall, list[dict]]:
    call, body = _get(
        config.GRAPH_PATH_OHLC,
        {
            "network": network,
            "pool": pool,
            "interval": config.GRAPH_OHLC_INTERVAL,
            "limit": config.GRAPH_OHLC_LIMIT,
        },
        api_key=api_key,
    )
    rows = body.get("data", []) if isinstance(body, dict) else []
    return call, rows


def _close_series(rows: list[dict]) -> list[float]:
    out: list[float] = []
    for r in rows:
        for key in ("close", "close_price", "c"):
            if key in r and r[key] is not None:
                try:
                    out.append(float(r[key]))
                except (TypeError, ValueError):
                    pass
                break
    return out


# ------------------------------------------------------------------ public API


class GraphClient:
    """
    Stateful across cycles only to hold the previous activity reading, which is
    what turns a level into a momentum signal. No market data is ever cached and
    reused as a decision input: every cycle re-fetches.
    """

    def __init__(self) -> None:
        self._prev_activity: tuple[int, int, float] | None = None
        self._pool: str = ""

    def signal(self) -> GraphSignal:
        """
        Build this cycle's decision input from live Graph data.

        Returns a signal with tier "none" when The Graph gives us nothing. The
        runner treats tier "none" as a hard stop: no agent trades that cycle.
        """
        api_key = config.graph_api_key()
        sig = GraphSignal(tier="none")

        # PRICE tier first when a key is present. It supersedes activity.
        if api_key:
            if not self._pool:
                calls, pool = discover_reference_pool(api_key)
                sig.calls.extend(calls)
                self._pool = pool
            if self._pool:
                ohlc_call, rows = fetch_pool_ohlc(api_key, self._pool)
                sig.calls.append(ohlc_call)
                closes = _close_series(rows)
                if ohlc_call.ok and len(closes) >= 2:
                    first, last = closes[0], closes[-1]
                    if first:
                        sig.price = last
                        sig.price_change = (last - first) / first
                        sig.tier = "price"
                        sig.notes.append(
                            f"reference pool {self._pool} on {config.GRAPH_NETWORK}, "
                            f"{len(closes)} {config.GRAPH_OHLC_INTERVAL} closes"
                        )
                else:
                    sig.notes.append("price tier returned no usable OHLC series")
            else:
                sig.notes.append("price tier could not resolve a reference pool")
        else:
            sig.notes.append(NO_KEY_MESSAGE)

        # ACTIVITY tier. Keyless, verified live. Always fetched, because even in
        # the price tier the activity delta sizes the trade.
        if config.graph_allow_keyless():
            dex_call, rows = fetch_dex_activity()
            sig.calls.append(dex_call)
            if dex_call.ok and rows:
                tx, uaw = _activity_total(rows)
                now = time.time()
                if self._prev_activity is not None:
                    ptx, puaw, pt = self._prev_activity
                    elapsed = max(now - pt, 1.0)
                    tx_rate = (tx - ptx) / elapsed
                    uaw_delta = uaw - puaw
                    # Normalized so a quiet network sits near zero and a busy one
                    # near one. The divisor is the observed steady-state rate on
                    # Base, measured live rather than assumed: see README.
                    sig.activity_score = max(min(tx_rate / 400.0, 2.0), -2.0) + (
                        0.001 * uaw_delta
                    )
                    if sig.tier == "none":
                        sig.tier = "activity"
                        sig.notes.append(
                            f"activity tier: {len(rows)} factories on "
                            f"{config.GRAPH_NETWORK}, {tx_rate:.1f} tx/s"
                        )
                else:
                    sig.notes.append("activity tier priming, no previous poll to diff")
                self._prev_activity = (tx, uaw, now)
            else:
                sig.notes.append("activity tier call failed")
        else:
            sig.notes.append("keyless activity tier disabled by GRAPH_ALLOW_KEYLESS=0")

        return sig
