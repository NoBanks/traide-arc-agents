"""
dashboard.py - read only FastAPI view of what the agents are actually doing.

Free routes only. Nothing here writes to the chain, signs anything, or exposes a
key. It reads two files the runner produces (data/state.json and the hash chained
data/receipts.jsonl) plus a small number of eth_calls, and renders them.

    python3.11 -m arc_agents.dashboard
    http://127.0.0.1:17360/

Routes
    GET /                 HTML overview
    GET /api/state        agents, balances, pool, latest Graph signal
    GET /api/receipts     receipt ledger with anchor transactions (last N)
    GET /api/verify       recompute every receipt hash and check the chain
    GET /ledger.json      the WHOLE hash chained ledger as one JSON document,
                          for verifiers and judges. Read only, no secrets.
                          ?limit=N returns the last N rows, ?agent=NAME filters,
                          ?traded=1 keeps only rows with a swap.
    GET /receipt/<sha256>.json   one ledger row by receipt hash
    GET /healthz          liveness
"""

from __future__ import annotations

import html
import json
import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

from . import config, receipts
from .anchor import anchor_address

app = FastAPI(title="TRAIDE agents on Arc", docs_url=None, redoc_url=None)

_STARTED = time.time()


def _state() -> dict[str, Any]:
    if config.STATE_PATH.exists():
        try:
            return json.loads(config.STATE_PATH.read_text())
        except Exception:
            return {}
    return {}


def _deployment() -> dict[str, Any]:
    if config.DEPLOYMENT_PATH.exists():
        try:
            return json.loads(config.DEPLOYMENT_PATH.read_text())
        except Exception:
            return {}
    return {}


@app.get("/healthz")
def healthz() -> JSONResponse:
    return JSONResponse({"ok": True, "uptime_seconds": round(time.time() - _STARTED, 1)})


@app.get("/api/state")
def api_state() -> JSONResponse:
    state = _state()
    dep = _deployment()
    return JSONResponse(
        {
            "chain_id": config.CHAIN_ID,
            "explorer": config.EXPLORER_BASE,
            "amm": config.TRAIDE_AMM,
            "anchor": anchor_address(),
            "usdc": config.USDC,
            "linkmock": config.LINKMOCK,
            "agents": dep.get("agents", []),
            "state": state,
            "graph_key_configured": bool(config.graph_api_key()),
        }
    )


@app.get("/api/receipts")
def api_receipts(limit: int = 100) -> JSONResponse:
    rows = receipts.read_all()
    return JSONResponse({"count": len(rows), "rows": rows[-limit:]})


@app.get("/api/verify")
def api_verify() -> JSONResponse:
    return JSONResponse(receipts.verify_ledger())


def _ledger_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The counts every view of the ledger agrees on, computed in one place."""
    swaps = sum(1 for r in rows if (r.get("receipt", {}).get("swap") or {}).get("hash"))
    anchors = sum(1 for r in rows if (r.get("anchor") or {}).get("hash"))
    last = rows[-1].get("receipt", {}).get("timestamp", "") if rows else ""
    return {"receipts": len(rows), "swaps": swaps, "anchors": anchors, "last_decision_at": last}


@app.get("/ledger.json")
def ledger_json(limit: int = 0, agent: str = "", traded: bool = False) -> JSONResponse:
    """
    Public, read-only export of data/receipts.jsonl. Every row is exactly the
    line the runner wrote: the canonical receipt object, its sha256, the previous
    row's sha256 and the anchor transaction. Nothing is added or reshaped, so
    scripts/verify_receipt.py can recompute each hash from this document alone.
    No credential is ever written to a receipt, so there is nothing to redact.
    """
    rows = receipts.read_all()
    summary = _ledger_summary(rows)
    if agent:
        rows = [r for r in rows if r.get("receipt", {}).get("agent") == agent.upper()]
    if traded:
        rows = [r for r in rows if (r.get("receipt", {}).get("swap") or {}).get("hash")]
    if limit > 0:
        rows = rows[-limit:]
    return JSONResponse({
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "chain_id": config.CHAIN_ID,
        "explorer": config.EXPLORER_BASE,
        "amm": config.TRAIDE_AMM,
        "anchor_contract": anchor_address(),
        "canonical_rule": "sha256(json.dumps(receipt, sort_keys=True, separators=(',',':')).encode('utf-8'))",
        "verify_one": "python3.11 -m scripts.verify_receipt <receipt_hash> --ledger <this URL>",
        "totals": summary,
        "count": len(rows),
        "rows": rows,
    })


@app.get("/receipt/{receipt_hash}.json")
def receipt_json(receipt_hash: str) -> JSONResponse:
    """One ledger row by receipt sha256, so a verifier need not pull the whole ledger."""
    wanted = receipt_hash[2:] if receipt_hash.startswith("0x") else receipt_hash
    wanted = wanted.lower()
    for row in receipts.read_all():
        if row.get("receipt_hash") == wanted:
            return JSONResponse(row)
    return JSONResponse({"error": "receipt not found", "receipt_hash": wanted}, status_code=404)


CSS = """
:root{color-scheme:dark;--bg:#0d1117;--panel:#161b22;--line:#30363d;--fg:#e6edf3;
--dim:#8b949e;--ok:#3fb950;--warn:#d29922;--accent:#7c8cff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.6 -apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif}
.wrap{max-width:1100px;margin:0 auto;padding:28px 20px 60px}
h1{font-size:22px;margin:0 0 4px}
h2{font-size:15px;text-transform:uppercase;letter-spacing:.08em;color:var(--dim);margin:32px 0 10px}
.sub{color:var(--dim);margin:0 0 20px}
.grid{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(250px,1fr))}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.card h3{margin:0 0 8px;font-size:14px}
.kv{display:flex;justify-content:space-between;gap:12px;padding:3px 0;border-bottom:1px solid rgba(255,255,255,.04)}
.kv:last-child{border-bottom:0}
.kv span:first-child{color:var(--dim)}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--dim);font-weight:600;text-transform:uppercase;letter-spacing:.05em;font-size:11px}
.scroll{overflow-x:auto;border:1px solid var(--line);border-radius:10px;background:var(--panel)}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
.tag{display:inline-block;padding:1px 7px;border-radius:20px;font-size:11px;border:1px solid var(--line)}
.buy{color:var(--ok);border-color:var(--ok)}
.sell{color:var(--warn);border-color:var(--warn)}
.hold{color:var(--dim)}
.note{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--warn);
border-radius:8px;padding:12px 16px;margin:14px 0;color:var(--dim)}
.status{display:flex;flex-wrap:wrap;gap:6px 18px;margin:0 0 18px;padding:8px 12px;border:1px solid var(--line);
border-radius:8px;background:var(--panel);font-size:12.5px;color:var(--dim)}
.status b{color:var(--fg);font-weight:600}
.status .mono{font-size:12px}
"""


def _fmt_usdc(units: Any) -> str:
    try:
        return f"{int(units) / 10**config.USDC_DECIMALS:.6f}"
    except Exception:
        return "-"


def _fmt_link(wei: Any) -> str:
    try:
        return f"{int(wei) / 10**config.LINKMOCK_DECIMALS:,.4f}"
    except Exception:
        return "-"


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    forwarded = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    scheme = request.headers.get("x-forwarded-proto") or request.url.scheme
    request_base = f"{scheme}://{forwarded}" if forwarded else ""
    state = _state()
    dep = _deployment()
    rows = receipts.read_all()
    verify = receipts.verify_ledger()
    g = state.get("graph", {})
    pool = state.get("pool", {}).get("reserves", {})
    anchor = anchor_address()

    # The banner must describe the ACTUAL state, not just whether a key string
    # exists. A key that is set but refused by the gateway is a different problem
    # with a different fix, and saying "not set" would send the reader the wrong way.
    key_set = bool(config.graph_api_key() or config.graph_gateway_api_key())
    price_live = g.get("price") is not None
    price_reason = ""
    for note in g.get("notes", []):
        if note.startswith("[GRAPH] price tier unavailable"):
            price_reason = note
            break

    banner = ""
    if not price_live:
        if not key_set:
            detail = (
                "No Graph credential is set. Neither GRAPH_API_KEY (Token API JWT) "
                "nor GRAPH_GATEWAY_API_KEY (Subgraph Studio query key) is present."
            )
        else:
            detail = html.escape(price_reason) if price_reason else (
                "A Graph credential is set but the price tier returned no usable series."
            )
        banner = (
            '<div class="note"><strong>Price tier is down, so REBALANCE is not trading.</strong> '
            + detail
            + " PASSIVE and AGGRESSIVE continue on the keyless Token API activity tier. "
            "No data source outside The Graph is used anywhere in this program.</div>"
        )

    cards = []
    for agent in dep.get("agents", []):
        entry = state.get("agents", {}).get(agent["name"], {})
        bal = entry.get("balances", {})
        pnl = entry.get("pnl_vs_hold_usdc")
        cards.append(
            f"""<div class="card"><h3>{html.escape(agent['name'])}</h3>
<div class="kv"><span>address</span><a class="mono" href="{agent['explorer']}">{agent['address'][:10]}...{agent['address'][-6:]}</a></div>
<div class="kv"><span>path</span><span class="mono">{html.escape(agent['derivation_path'])}</span></div>
<div class="kv"><span>USDC</span><span class="mono">{_fmt_usdc(bal.get('usdc_units_6'))}</span></div>
<div class="kv"><span>LINKMock</span><span class="mono">{_fmt_link(bal.get('link_wei_18'))}</span></div>
<div class="kv"><span>value now</span><span class="mono">{entry.get('live_value_usdc', 0):.6f}</span></div>
<div class="kv"><span>value if held</span><span class="mono">{entry.get('hold_value_usdc', 0):.6f}</span></div>
<div class="kv"><span>P and L vs hold</span><span class="mono">{(pnl if pnl is not None else 0):+.6f} USDC</span></div>
</div>"""
        )

    trs = []
    for row in reversed(rows[-60:]):
        r = row.get("receipt", {})
        swap = r.get("swap") or {}
        anch = row.get("anchor") or {}
        action = r.get("action", "")
        cls = {"BUY_LINK": "buy", "SELL_LINK": "sell"}.get(action, "hold")
        swap_cell = (
            f'<a class="mono" href="{swap["explorer"]}">{swap["hash"][:12]}...</a>'
            if swap.get("explorer") else '<span class="mono hold">none</span>'
        )
        anchor_cell = (
            f'<a class="mono" href="{anch["explorer"]}">{anch["hash"][:12]}...</a>'
            if anch.get("explorer") else '<span class="mono hold">not anchored</span>'
        )
        trs.append(
            f"""<tr><td class="mono">{r.get('cycle','')}</td>
<td>{html.escape(str(r.get('agent','')))}</td>
<td><span class="tag {cls}">{html.escape(action)}</span></td>
<td class="mono">{html.escape(str(r.get('graph',{}).get('tier','')))}</td>
<td>{html.escape(str(r.get('reason','')))[:150]}</td>
<td class="mono">{row.get('receipt_hash','')[:16]}</td>
<td>{swap_cell}</td><td>{anchor_cell}</td></tr>"""
        )

    summary = _ledger_summary(rows)
    swaps = summary["swaps"]
    anchors = summary["anchors"]
    started = str(state.get("started_at", "")) or "-"
    last_decision = summary["last_decision_at"] or "-"
    status_line = (
        '<div class="status">'
        f'<span><b>{len(rows)}</b> receipts</span>'
        f'<span><b>{swaps}</b> real swaps</span>'
        f'<span><b>{anchors}</b> anchored on Arc</span>'
        f'<span>last decision <b class="mono">{html.escape(last_decision)}</b></span>'
        f'<span>ledger running since <b class="mono">{html.escape(started)}</b></span>'
        f'<span>integrity <b>{"verified" if verify.get("ok") else "BROKEN"}</b></span>'
        '</div>'
    )

    body = f"""<title>TRAIDE agents on Arc</title><style>{CSS}</style>
<div class="wrap">
<h1>TRAIDE agents on Arc testnet</h1>
<p class="sub">Three autonomous agents, each with its own wallet, trading a real
TRAIDEAMM pair on Arc testnet {config.CHAIN_ID}. Every decision is driven by live
data from The Graph and recorded as a keeper receipt anchored on chain.</p>
{status_line}
{banner}
<h2>Agents</h2>
<div class="grid">{''.join(cards) or '<div class="card">no agent record yet</div>'}</div>

<h2>Graph signal, last cycle</h2>
<div class="grid">
<div class="card"><h3>Signal</h3>
<div class="kv"><span>tier</span><span class="mono">{html.escape(str(g.get('tier','-')))}</span></div>
<div class="kv"><span>activity score</span><span class="mono">{g.get('activity_score') if g.get('activity_score') is not None else '-'}</span></div>
<div class="kv"><span>reference price</span><span class="mono">{g.get('price') if g.get('price') is not None else '-'}</span></div>
<div class="kv"><span>price change</span><span class="mono">{g.get('price_change') if g.get('price_change') is not None else '-'}</span></div>
<div class="kv"><span>credential set</span><span class="mono">{'yes' if key_set else 'no'}</span></div>
<div class="kv"><span>graph products</span><span class="mono">{html.escape(', '.join(state.get('graph', {}).get('products', [])) or 'none this cycle')}</span></div>
</div>
<div class="card"><h3>Pool, TRAIDEAMM</h3>
<div class="kv"><span>USDC reserve</span><span class="mono">{_fmt_usdc(pool.get('usdc_units_6'))}</span></div>
<div class="kv"><span>LINKMock reserve</span><span class="mono">{_fmt_link(pool.get('link_wei_18'))}</span></div>
<div class="kv"><span>AMM</span><a class="mono" href="{config.address_url(config.TRAIDE_AMM)}">{config.TRAIDE_AMM[:10]}...</a></div>
<div class="kv"><span>cycle</span><span class="mono">{state.get('cycle','-')}</span></div>
</div>
<div class="card"><h3>Receipts</h3>
<div class="kv"><span>decisions</span><span class="mono">{len(rows)}</span></div>
<div class="kv"><span>real swaps</span><span class="mono">{swaps}</span></div>
<div class="kv"><span>anchored</span><span class="mono">{anchors}</span></div>
<div class="kv"><span>ledger integrity</span><span class="mono">{'verified' if verify.get('ok') else 'BROKEN'}</span></div>
<div class="kv"><span>anchor contract</span><a class="mono" href="{config.address_url(anchor) if anchor else '#'}">{(anchor[:10] + '...') if anchor else 'not deployed'}</a></div>
</div>
</div>

<h2>Decision ledger</h2>
<div class="scroll"><table>
<tr><th>cycle</th><th>agent</th><th>action</th><th>graph tier</th><th>reason</th>
<th>receipt sha256</th><th>swap tx</th><th>anchor tx</th></tr>
{''.join(trs) or '<tr><td colspan="8">no decisions yet</td></tr>'}
</table></div>

<p class="sub" style="margin-top:24px">JSON:
<a href="/api/state">/api/state</a> &middot;
<a href="/api/receipts">/api/receipts</a> &middot;
<a href="/api/verify">/api/verify</a> &middot;
<a href="/ledger.json?limit=50">/ledger.json</a> (full export, <code>?limit=N</code>, <code>?traded=1</code>, <code>?agent=NAME</code>) &middot;
<code>/receipt/&lt;sha256&gt;.json</code> &middot;
<a href="/healthz">/healthz</a></p>
<p class="sub">Verify any row yourself: <code class="mono">python3.11 -m scripts.verify_receipt &lt;receipt sha256&gt; --ledger {html.escape(request_base)}/ledger.json</code></p>
</div>"""
    return HTMLResponse(body)


def main() -> None:
    import uvicorn

    config.load_dotenv()
    uvicorn.run(app, host="127.0.0.1", port=config.dashboard_port(), log_level="info")


if __name__ == "__main__":
    main()
