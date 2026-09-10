"""
receipts.py - keeper receipts for Arc agent decisions.

The canonicalization rule is NOT reinvented here. It is the same rule as
traide-keeper/traide_keeper/receipt.py, which was verified against a landed
attestation transaction:

    json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("utf-8")
    sha256(those bytes)

What is new is the receipt SHAPE. traide-keeper's shape is
"lane_state_attestation" for the four-lane paper benchmark. This package emits
"arc_agent_decision", which additionally carries Graph provenance so a verifier
can prove the decision was informed by live Graph data at query time:

    graph.tier              which Graph tier decided this cycle
    graph.calls[]           endpoint, params, auth flag, HTTP status,
                            sha256 of the exact response bytes, byte count,
                            and the fetch timestamp
    graph.signal            the numbers actually fed to the strategy

Rebuilding the same canonical JSON from the receipt file reproduces the same
sha256, and that sha256 is what is anchored on Arc. A verifier who re-runs the
same Graph query at the same block will not get byte-identical data (live data
moves), but the response hash pins exactly what this agent saw, and the on-chain
anchor pins when it saw it.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from . import config

RECEIPT_TYPE = "arc_agent_decision"
ENGINE_NAME = "traide-arc-agents"
ENGINE_VERSION = "1.0.0"


def canonical_bytes(receipt: dict[str, Any]) -> bytes:
    """Identical rule to traide-keeper.receipt.canonical_bytes."""
    return json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def receipt_hash(receipt: dict[str, Any]) -> str:
    """64 lower-hex characters, no 0x prefix. Same convention as traide-keeper."""
    return sha256_hex(canonical_bytes(receipt))


def build_receipt(
    *,
    agent: str,
    agent_address: str,
    action: str,
    reason: str,
    graph_tier: str,
    graph_calls: list[dict[str, Any]],
    graph_signal: dict[str, Any],
    pool_reserves: dict[str, int],
    balances: dict[str, int],
    swap: dict[str, Any] | None,
    cycle: int,
) -> dict[str, Any]:
    """
    Build the canonical decision receipt.

    Every field is either read from the chain, read from The Graph, or computed
    from those two. Nothing is a placeholder and nothing is mocked.
    """
    return {
        "action": action,
        "agent": agent,
        "agent_address": agent_address,
        "balances": balances,
        "chain_id": config.CHAIN_ID,
        "cycle": cycle,
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "graph": {
            "calls": graph_calls,
            "signal": graph_signal,
            "tier": graph_tier,
        },
        "pool": {
            "amm": config.TRAIDE_AMM,
            "reserves": pool_reserves,
            "token_a": config.USDC,
            "token_b": config.LINKMOCK,
            "venue": config.SWAP_VENUE,
        },
        "reason": reason,
        "swap": swap or {},
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "type": RECEIPT_TYPE,
    }


def append(receipt: dict[str, Any], anchor: dict[str, Any] | None = None, path: Path | None = None) -> str:
    """
    Append one receipt to the hash-chained jsonl ledger and return its hash.

    The stored line wraps the canonical receipt so the anchor transaction and
    the previous line's hash can travel with it without changing the hash that
    was anchored. Only the "receipt" object is hashed.
    """
    target = path or config.RECEIPTS_PATH
    target.parent.mkdir(parents=True, exist_ok=True)

    h = receipt_hash(receipt)
    prev = ""
    if target.exists():
        lines = [ln for ln in target.read_text().splitlines() if ln.strip()]
        if lines:
            try:
                prev = json.loads(lines[-1]).get("receipt_hash", "")
            except Exception:
                prev = ""

    line = {
        "anchor": anchor or {},
        "prev_receipt_hash": prev,
        "receipt": receipt,
        "receipt_hash": h,
    }
    with target.open("a") as f:
        f.write(json.dumps(line, sort_keys=True, separators=(",", ":")) + "\n")
    return h


def read_all(path: Path | None = None) -> list[dict[str, Any]]:
    target = path or config.RECEIPTS_PATH
    if not target.exists():
        return []
    out: list[dict[str, Any]] = []
    for ln in target.read_text().splitlines():
        if ln.strip():
            try:
                out.append(json.loads(ln))
            except Exception:
                continue
    return out


def verify_ledger(path: Path | None = None) -> dict[str, Any]:
    """
    Recompute every receipt hash from its own canonical bytes and check the
    prev-hash chain. Returns a report; never raises.
    """
    return verify_rows(read_all(path))


def verify_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """
    The same check over rows that came from anywhere: the local file, the
    dashboard's /ledger.json export, or a judge's own download. verify.py used
    to call verify_ledger() and so silently checked the LOCAL file even when
    asked to verify a URL; on a clone with no data/ that reported 0 receipts
    as a pass. Added 2026-09-10 so the rows verified are the rows named.
    """
    bad_hash: list[int] = []
    bad_chain: list[int] = []
    prev = ""
    for i, row in enumerate(rows):
        recomputed = receipt_hash(row.get("receipt", {}))
        if recomputed != row.get("receipt_hash"):
            bad_hash.append(i)
        if row.get("prev_receipt_hash", "") != prev:
            bad_chain.append(i)
        prev = row.get("receipt_hash", "")
    return {
        "rows": len(rows),
        "hash_mismatches": bad_hash,
        "chain_breaks": bad_chain,
        "ok": not bad_hash and not bad_chain,
    }
