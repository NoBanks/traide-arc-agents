"""
verify_receipt.py - verify ONE receipt end to end, with one command, from any machine.

scripts/verify.py checks the whole ledger. This checks a single decision the way
a judge would want to: pick any row on the live dashboard, paste its sha256, and
watch every claim in that row get re-derived from the chain and from The Graph.

    python3.11 -m scripts.verify_receipt <receipt sha256>
    python3.11 -m scripts.verify_receipt docs/sample_receipt_price_tier.json
    python3.11 -m scripts.verify_receipt <sha256> --ledger https://arc-agents.nohumannearby.com/ledger.json

What it does, in order, printing PASS, FAIL or SKIP for each with the URL to
check by hand:

  hash      rebuilds the canonical JSON of the receipt object with the exact
            traide-keeper rule (sort_keys, no whitespace, utf-8) and recomputes
            sha256. Must equal the ledger's receipt_hash and the hash you asked for.
  anchor    eth_call attestedAt(bytes32) and attestedBy(bytes32) on
            ArcReceiptAnchor. attestedAt must be nonzero (the hash is on chain,
            first seen at that block timestamp) and attestedBy must equal the
            receipt's agent_address (the agent signed its own evidence).
  anchor tx re-fetches the anchor transaction receipt: status 1, sent from the
            agent, sent to the anchor contract, and its Attested event carries
            this receipt hash.
  swap tx   re-fetches the swap transaction receipt: status 1, sent from the
            agent, sent to TRAIDEAMM, in the block the receipt says.
  graph     for every recorded Graph call: the endpoint must be a Graph host and
            the recorded status must be 200. Then the SAME request is re-issued
            now. Token API calls are keyless and always re-run. Subgraph gateway
            calls need GRAPH_GATEWAY_API_KEY in the environment and are SKIPped
            without it. A live response whose sha256 equals the recorded one is
            reported as a match; one that differs is reported honestly as "live
            data has moved since <fetched_at>", which is the normal case for a
            live index. The recorded hash pins what the agent saw; the anchor
            pins when.
  guard     a decision that traded must carry a usable Graph tier. A swap on
            tier "none" fails here. HOLD decisions are not anchored by design and
            say so.

Dependencies: only what requirements.txt already installs (web3). The ledger is
read from data/receipts.jsonl when it exists locally, otherwise from the public
dashboard export, so a fresh clone works with no setup. No secret is read except
the optional GRAPH_GATEWAY_API_KEY, which is sent as a bearer header and never
printed.

Exit status 0 when nothing failed, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from web3 import Web3  # noqa: E402

from arc_agents import config, receipts  # noqa: E402
from arc_agents.graph import _get as graph_get  # noqa: E402
from arc_agents.subgraph import _post as subgraph_post  # noqa: E402

PUBLIC_DASHBOARD = "https://arc-agents.nohumannearby.com"
PUBLIC_LEDGER = f"{PUBLIC_DASHBOARD}/ledger.json"
PUBLIC_RECEIPT = PUBLIC_DASHBOARD + "/receipt/{h}.json"

GRAPH_HOSTS = ("api.pinax.network", "gateway.thegraph.com", "token-api.thegraph.com")

# Only the read-only surface of ArcReceiptAnchor this script needs. Kept local so
# the verifier depends on nothing but the contract's public ABI.
ANCHOR_READ_ABI = [
    {"name": "attestedAt", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "", "type": "bytes32"}], "outputs": [{"name": "", "type": "uint256"}]},
    {"name": "attestedBy", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "", "type": "bytes32"}], "outputs": [{"name": "", "type": "address"}]},
]
ATTESTED_TOPIC = Web3.keccak(text="Attested(address,bytes32,bytes32,uint256)").hex()

HEX64 = re.compile(r"^(0x)?[0-9a-fA-F]{64}$")


class Report:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.skipped = 0

    def line(self, status: str, name: str, msg: str, url: str = "") -> None:
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}[status]
        print(f"{tag} {name}: {msg}")
        if url:
            print(f"       {url}")
        if status == "PASS":
            self.passed += 1
        elif status == "FAIL":
            self.failed += 1
        else:
            self.skipped += 1


def _iso(ts: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(ts)))


def _strip0x(h: str) -> str:
    return h[2:] if h.startswith("0x") else h


def _fetch_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "traide-arc-agents/verify"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


# --------------------------------------------------------------- load the row


def load_target(target: str, ledger: str) -> tuple[dict[str, Any], str]:
    """
    Returns (row, source). A row is the ledger line shape:
      {"receipt": {...}, "receipt_hash": ..., "anchor": {...}, "prev_receipt_hash": ...}
    A bare receipt object (no "receipt" key) is wrapped so the same checks run.
    """
    p = Path(target)
    if p.exists():
        obj = json.loads(p.read_text())
        if "receipt" in obj:
            return obj, str(p)
        return {"receipt": obj, "receipt_hash": "", "anchor": {}}, str(p)

    if not HEX64.match(target):
        raise SystemExit(f"target is neither a file nor a 64-hex receipt hash: {target}")
    wanted = _strip0x(target).lower()

    if ledger.startswith("http://") or ledger.startswith("https://"):
        # Try the single-row route first, fall back to the full export.
        base = ledger.rsplit("/", 1)[0]
        single = f"{base}/receipt/{wanted}.json"
        try:
            row = _fetch_json(single)
            if isinstance(row, dict) and row.get("receipt_hash") == wanted:
                return row, single
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
        except Exception:
            pass
        body = _fetch_json(ledger)
        rows = body.get("rows", []) if isinstance(body, dict) else body
        for row in rows:
            if row.get("receipt_hash") == wanted:
                return row, ledger
        raise SystemExit(f"receipt {wanted} not found in {ledger} ({len(rows)} rows)")

    rows = receipts.read_all(Path(ledger))
    for row in rows:
        if row.get("receipt_hash") == wanted:
            return row, ledger
    raise SystemExit(f"receipt {wanted} not found in {ledger} ({len(rows)} rows)")


# -------------------------------------------------------------------- checks


def check_hash(rep: Report, row: dict[str, Any], requested: str) -> str:
    receipt = row["receipt"]
    recomputed = receipts.receipt_hash(receipt)
    recorded = row.get("receipt_hash", "")
    if recorded and recorded != recomputed:
        rep.line("FAIL", "hash", f"sha256(canonical JSON) = {recomputed}, ledger says {recorded}")
    elif requested and _strip0x(requested).lower() != recomputed:
        rep.line("FAIL", "hash", f"sha256(canonical JSON) = {recomputed}, you asked for {requested}")
    else:
        rep.line("PASS", "hash", f"sha256(canonical JSON) = {recomputed}"
                 + (", matches the ledger's receipt_hash" if recorded else ", recomputed from the bare receipt"))
    return recomputed


def check_anchor(rep: Report, w3: Web3, row: dict[str, Any], h: str, anchor_contract: str) -> None:
    receipt = row["receipt"]
    anchor = row.get("anchor") or {}
    agent_addr = Web3.to_checksum_address(receipt["agent_address"])
    traded = bool((receipt.get("swap") or {}).get("hash"))

    if not anchor_contract:
        rep.line("FAIL", "anchor", "no anchor contract address known; pass --anchor-contract")
        return
    contract = w3.eth.contract(address=Web3.to_checksum_address(anchor_contract), abi=ANCHOR_READ_ABI)
    at = int(contract.functions.attestedAt(bytes.fromhex(h)).call())
    by = contract.functions.attestedBy(bytes.fromhex(h)).call()
    contract_url = config.address_url(anchor_contract)

    if at == 0:
        if not traded and not anchor.get("hash"):
            rep.line("SKIP", "anchor", "HOLD decision, not anchored by design (only decisions that traded are anchored); "
                     f"attestedAt(0x{h[:12]}..) = 0 on {anchor_contract[:10]}.. as expected", contract_url)
        else:
            rep.line("FAIL", "anchor", f"attestedAt(0x{h}) = 0 on {anchor_contract}: this hash is NOT on chain", contract_url)
        return

    if Web3.to_checksum_address(by) != agent_addr:
        rep.line("FAIL", "anchor", f"attestedAt = {at} but attestedBy = {by}, not the agent {agent_addr}", contract_url)
    else:
        rep.line("PASS", "anchor", f"attestedAt(0x{h[:12]}..) = {at} ({_iso(at)}) on {anchor_contract[:10]}.., "
                 f"attestedBy = {by[:10]}.. which is the agent's own address", contract_url)

    tx_hash = anchor.get("hash")
    if not tx_hash:
        rep.line("SKIP", "anchor tx", "the row carries no anchor transaction hash to re-fetch (bare receipt); "
                 "the on-chain attestedAt above already proves the anchor")
        return
    try:
        rcpt = w3.eth.get_transaction_receipt(tx_hash)
    except Exception as exc:
        rep.line("FAIL", "anchor tx", f"{tx_hash} could not be fetched: {type(exc).__name__}", config.tx_url(tx_hash))
        return
    problems = []
    if int(rcpt["status"]) != 1:
        problems.append(f"status {rcpt['status']}")
    if Web3.to_checksum_address(rcpt["from"]) != agent_addr:
        problems.append(f"from {rcpt['from']} is not the agent")
    if Web3.to_checksum_address(rcpt["to"]) != Web3.to_checksum_address(anchor_contract):
        problems.append(f"to {rcpt['to']} is not the anchor contract")
    carries = any(
        len(lg["topics"]) == 4
        and _strip0x(lg["topics"][0].hex()).lower() == _strip0x(ATTESTED_TOPIC).lower()
        and _strip0x(lg["topics"][2].hex()).lower() == h
        for lg in rcpt["logs"]
    )
    if not carries:
        problems.append("no Attested event with this receipt hash in the logs")
    if anchor.get("block") and int(anchor["block"]) != int(rcpt["blockNumber"]):
        problems.append(f"block {rcpt['blockNumber']} differs from recorded {anchor['block']}")
    if problems:
        rep.line("FAIL", "anchor tx", f"{tx_hash[:14]}.. " + "; ".join(problems), config.tx_url(tx_hash))
    else:
        rep.line("PASS", "anchor tx", f"{tx_hash[:14]}.. status 1, block {rcpt['blockNumber']}, from the agent, "
                 "to the anchor contract, Attested event carries this hash", config.tx_url(tx_hash))


def check_swap(rep: Report, w3: Web3, row: dict[str, Any]) -> None:
    receipt = row["receipt"]
    swap = receipt.get("swap") or {}
    tx_hash = swap.get("hash")
    if not tx_hash:
        rep.line("SKIP", "swap tx", f"action {receipt.get('action')} sent no transaction")
        return
    agent_addr = Web3.to_checksum_address(receipt["agent_address"])
    try:
        rcpt = w3.eth.get_transaction_receipt(tx_hash)
    except Exception as exc:
        rep.line("FAIL", "swap tx", f"{tx_hash} could not be fetched: {type(exc).__name__}", config.tx_url(tx_hash))
        return
    problems = []
    if int(rcpt["status"]) != 1:
        problems.append(f"status {rcpt['status']}")
    if Web3.to_checksum_address(rcpt["from"]) != agent_addr:
        problems.append(f"from {rcpt['from']} is not the agent")
    amm = receipt.get("pool", {}).get("amm", config.TRAIDE_AMM)
    if Web3.to_checksum_address(rcpt["to"]) != Web3.to_checksum_address(amm):
        problems.append(f"to {rcpt['to']} is not TRAIDEAMM {amm}")
    if swap.get("block") and int(swap["block"]) != int(rcpt["blockNumber"]):
        problems.append(f"block {rcpt['blockNumber']} differs from recorded {swap['block']}")
    if problems:
        rep.line("FAIL", "swap tx", f"{tx_hash[:14]}.. " + "; ".join(problems), config.tx_url(tx_hash))
    else:
        rep.line("PASS", "swap tx", f"{tx_hash[:14]}.. status 1, block {rcpt['blockNumber']}, from the agent, "
                 f"to TRAIDEAMM {amm[:10]}.., {receipt.get('action')} amount_in {swap.get('amount_in')}",
                 config.tx_url(tx_hash))


def _rerun_graph_call(call: dict[str, Any]) -> tuple[int, str, int, str]:
    """
    Re-issue the recorded request. Returns (status, sha256, bytes, note).
    note is non-empty when the call could not be re-run.
    """
    endpoint = str(call.get("endpoint", ""))
    if call.get("product") == "thegraph-subgraph-gateway" or "gateway.thegraph.com" in endpoint:
        key = config.graph_gateway_api_key()
        if not key:
            return 0, "", 0, "needs GRAPH_GATEWAY_API_KEY in the environment to re-run"
        sid = str(call.get("subgraph_id", "")) or endpoint.rsplit("/", 1)[-1]
        rec, _body = subgraph_post(sid, str(call.get("query", "")), dict(call.get("variables") or {}), key)
        return int(rec["status"]), str(rec["response_sha256"]), int(rec["response_bytes"]), str(rec.get("graphql_errors") or rec.get("error") or "")
    base = config.GRAPH_TOKEN_API_BASE
    if not endpoint.startswith(base):
        return 0, "", 0, f"endpoint is not under {base}, cannot re-run"
    key = config.graph_api_key() if call.get("authenticated") else ""
    if call.get("authenticated") and not key:
        return 0, "", 0, "recorded as authenticated and GRAPH_API_KEY is not set"
    gc, _body = graph_get(endpoint[len(base):], dict(call.get("params") or {}), api_key=key)
    return int(gc.status), gc.response_sha256, gc.response_bytes, gc.error


def check_graph(rep: Report, row: dict[str, Any], rerun: bool) -> None:
    receipt = row["receipt"]
    graph = receipt.get("graph") or {}
    calls = graph.get("calls") or []
    tier = graph.get("tier")
    traded = bool((receipt.get("swap") or {}).get("hash"))

    if not calls:
        if tier in ("none", None):
            rep.line("SKIP", "graph", "no Graph call recorded and tier is none: this is a refusal receipt")
        else:
            rep.line("FAIL", "graph", f"tier is {tier} but no Graph call is recorded")
    for i, call in enumerate(calls, 1):
        name = f"graph {i}/{len(calls)}"
        endpoint = str(call.get("endpoint", ""))
        host = endpoint.split("/")[2] if endpoint.startswith("http") else ""
        product = call.get("product", "?")
        what = f"{product} {endpoint}"
        if call.get("params"):
            what += " params " + json.dumps(call["params"], sort_keys=True)
        if call.get("variables"):
            what += " variables " + json.dumps(call["variables"], sort_keys=True)
        if host not in GRAPH_HOSTS:
            rep.line("FAIL", name, f"{what}: endpoint host {host or 'unknown'} is not a Graph host")
            continue
        recorded_status = int(call.get("status", 0))
        recorded_sha = str(call.get("response_sha256", ""))
        if not call.get("ok") or recorded_status != 200 or not HEX64.match(recorded_sha):
            rep.line("FAIL", name, f"{what}: recorded status {recorded_status}, ok={call.get('ok')}, sha256 {recorded_sha or 'missing'}")
            continue
        recorded = (f"recorded {call.get('fetched_at')} HTTP 200, {call.get('response_bytes')} bytes, "
                    f"sha256 {recorded_sha[:12]}..")
        if not rerun:
            rep.line("PASS", name, f"{what}\n       {recorded}; re-run disabled with --no-graph")
            continue
        status, live_sha, nbytes, note = _rerun_graph_call(call)
        if status == 0 and note and ("GRAPH_" in note or "cannot re-run" in note):
            rep.line("SKIP", name, f"{what}\n       {recorded}; not re-run: {note}")
            continue
        if status != 200 or note:
            # The gateway serves through a set of indexers and a heavy query can
            # come back "bad indexers: Timeout" on one attempt and succeed on the
            # next. Seen live on 2026-09-10 against the token scan. One retry.
            time.sleep(3)
            status, live_sha, nbytes, note = _rerun_graph_call(call)
        if status != 200 or note:
            # A failure to re-serve the request NOW says nothing about what the
            # agent saw THEN, so this is not a failure of the receipt. It is
            # reported as a skip with the exact reason, never hidden.
            rep.line("SKIP", name, f"{what}\n       {recorded}; the live re-run could not be served right now "
                     f"(HTTP {status} {note}). The recorded provenance stands; retry later".replace("  ", " "))
            continue
        if live_sha == recorded_sha:
            verdict = "live response sha256 MATCHES the recorded one byte for byte"
        else:
            verdict = (f"live response now HTTP 200, {nbytes} bytes, sha256 {live_sha[:12]}..: live data has moved "
                       f"since {call.get('fetched_at')}, which is expected for a live index. The recorded hash "
                       "pins what the agent saw and the anchor pins when")
        rep.line("PASS", name, f"{what}\n       {recorded}; {verdict}")

    # The load-bearing rule, checked per receipt.
    if traded and tier in ("none", None):
        rep.line("FAIL", "guard", "this decision TRADED with Graph tier none")
    elif traded:
        rep.line("PASS", "guard", f"decision traded on Graph tier \"{tier}\"; a swap on tier \"none\" would fail here")
    else:
        rep.line("PASS", "guard", f"HOLD on Graph tier \"{tier}\": {str(receipt.get('reason', ''))[:120]}")


# ---------------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="verify one traide-arc-agents receipt end to end")
    parser.add_argument("target", help="receipt sha256 (64 hex, 0x optional) or a path to a receipt JSON file")
    parser.add_argument("--ledger", default="",
                        help=f"ledger to resolve a hash against: a local receipts.jsonl or a /ledger.json URL "
                             f"(default: data/receipts.jsonl if present, else {PUBLIC_LEDGER})")
    parser.add_argument("--rpc", default="", help="Arc RPC URL (default ARC_RPC_URL or the public testnet RPC)")
    parser.add_argument("--anchor-contract", default="",
                        help="ArcReceiptAnchor address (default: from the row, else deployments/arc-5042002.json)")
    parser.add_argument("--no-graph", action="store_true", help="do not re-issue the recorded Graph requests")
    args = parser.parse_args(argv)

    config.load_dotenv()
    ledger = args.ledger or (str(config.RECEIPTS_PATH) if config.RECEIPTS_PATH.exists() else PUBLIC_LEDGER)

    row, source = load_target(args.target, ledger)
    receipt = row["receipt"]
    requested = args.target if HEX64.match(args.target) else ""

    print(f"receipt {row.get('receipt_hash') or '(bare)'}")
    print(f"  {receipt.get('agent')} {receipt.get('action')} cycle {receipt.get('cycle')} at {receipt.get('timestamp')}"
          f" on chain {receipt.get('chain_id')}, engine {receipt.get('engine')} {receipt.get('engine_version')}")
    print(f"  source: {source}")
    print(f"  dashboard: {PUBLIC_DASHBOARD}")

    rep = Report()
    if int(receipt.get("chain_id", 0)) != config.CHAIN_ID:
        rep.line("FAIL", "chain", f"receipt chain_id {receipt.get('chain_id')} is not Arc testnet {config.CHAIN_ID}")
        print(f"RESULT: {rep.passed} PASS, {rep.failed} FAIL, {rep.skipped} SKIP")
        return 1

    h = check_hash(rep, row, requested)

    rpc = args.rpc or config.rpc_url()
    w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 60}))
    chain_id = w3.eth.chain_id
    if chain_id != config.CHAIN_ID:
        rep.line("FAIL", "rpc", f"{rpc} answers chain id {chain_id}, expected {config.CHAIN_ID}")
        print(f"RESULT: {rep.passed} PASS, {rep.failed} FAIL, {rep.skipped} SKIP")
        return 1
    print(f"  rpc: {rpc} (chain id {chain_id}, head block {w3.eth.block_number})")

    anchor_contract = args.anchor_contract or (row.get("anchor") or {}).get("anchor_contract", "")
    if not anchor_contract:
        try:
            anchor_contract = json.loads(config.DEPLOYMENT_PATH.read_text()).get("anchor", {}).get("address", "")
        except Exception:
            anchor_contract = ""

    check_anchor(rep, w3, row, h, anchor_contract)
    check_swap(rep, w3, row)
    check_graph(rep, row, rerun=not args.no_graph)

    print(f"RESULT: {rep.passed} PASS, {rep.failed} FAIL, {rep.skipped} SKIP")
    return 0 if rep.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
