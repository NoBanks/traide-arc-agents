"""
Tests for the parts that must never regress: the Graph refusal guard, the
canonicalization rule matching traide-keeper, and the ledger hash chain.

    python3.11 -m pytest tests -q
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arc_agents import agents, receipts  # noqa: E402
from arc_agents.graph import (  # noqa: E402
    GraphSignal,
    NO_KEY_MESSAGE,
    PRICE_UNAVAILABLE_KEY_REJECTED,
    PRICE_UNAVAILABLE_NO_KEY,
)

BALANCES = {"usdc_units_6": 1_000_000, "link_wei_18": 2_000 * 10**18, "native_wei_18": 10**18}
RESERVES = {"usdc_units_6": 2_000_000, "link_wei_18": 16_534 * 10**18}


def test_no_graph_signal_means_no_trade():
    """The load-bearing rule. Every agent holds when The Graph gives nothing."""
    signal = GraphSignal(tier="none", notes=[NO_KEY_MESSAGE])
    for name in ("PASSIVE", "AGGRESSIVE", "REBALANCE"):
        d = agents.decide(name, signal, BALANCES, RESERVES)
        assert d.action == "HOLD"
        assert not d.trades
        assert NO_KEY_MESSAGE in d.reason


def test_rebalance_refuses_without_the_price_tier():
    """REBALANCE cannot act on the keyless activity tier alone."""
    signal = GraphSignal(tier="activity", activity_score=0.9)
    d = agents.decide("REBALANCE", signal, BALANCES, RESERVES)
    assert d.action == "HOLD"
    assert "price tier" in d.reason


def test_rebalance_reason_names_the_actual_cause():
    """
    Regression guard. The refusal line used to say "no API key" even when a key
    was present and the gateway had refused it, which points at the wrong fix.
    Whatever the Graph client determined must reach the log verbatim.
    """
    rejected = GraphSignal(
        tier="activity", activity_score=0.9,
        price_unavailable_reason=PRICE_UNAVAILABLE_KEY_REJECTED,
    )
    d = agents.decide("REBALANCE", rejected, BALANCES, RESERVES)
    assert d.action == "HOLD"
    assert "rejected the key" in d.reason
    assert NO_KEY_MESSAGE not in d.reason

    absent = GraphSignal(
        tier="activity", activity_score=0.9,
        price_unavailable_reason=PRICE_UNAVAILABLE_NO_KEY,
    )
    d2 = agents.decide("REBALANCE", absent, BALANCES, RESERVES)
    assert "no credential set" in d2.reason


def test_rebalance_trades_once_the_price_tier_is_live():
    """The moment a price arrives, REBALANCE acts. It is underweight LINK here."""
    live = GraphSignal(tier="price", activity_score=0.0, price=23.5, price_change=0.01)
    d = agents.decide("REBALANCE", live, BALANCES, RESERVES)
    assert d.action == "BUY_LINK"
    assert d.size_usdc_units > 0


def test_activity_tier_drives_opposite_sides():
    """PASSIVE is contrarian, AGGRESSIVE follows. A hot market splits them."""
    hot = GraphSignal(tier="activity", activity_score=0.4)
    assert agents.decide("AGGRESSIVE", hot, BALANCES, RESERVES).action == "BUY_LINK"
    assert agents.decide("PASSIVE", hot, BALANCES, RESERVES).action == "SELL_LINK"

    cold = GraphSignal(tier="activity", activity_score=-0.4)
    assert agents.decide("AGGRESSIVE", cold, BALANCES, RESERVES).action == "SELL_LINK"
    assert agents.decide("PASSIVE", cold, BALANCES, RESERVES).action == "BUY_LINK"


def test_dead_band_holds():
    flat = GraphSignal(tier="activity", activity_score=0.01)
    for name in ("PASSIVE", "AGGRESSIVE"):
        assert agents.decide(name, flat, BALANCES, RESERVES).action == "HOLD"


def test_swap_sizes_stay_inside_the_configured_bounds():
    from arc_agents import config

    hot = GraphSignal(tier="activity", activity_score=1.5)
    d = agents.decide("AGGRESSIVE", hot, BALANCES, RESERVES)
    assert config.SWAP_MIN_USDC_UNITS <= d.size_usdc_units <= config.SWAP_MAX_USDC_UNITS


def test_canonicalization_matches_traide_keeper():
    """
    The hashing rule is the pre-existing traide-keeper rule, not a fork. This
    reproduces the exact byte string and hash from a traide-keeper example
    receipt using THIS module's functions.
    """
    keeper_example = {
        "balances": {"100k": 97663.31, "10k": 16983.89, "1k": 3570.23, "1m": 995049.99},
        "day": "2026-08-02",
        "day_start": {"100k": 97830.93, "10k": 16848.97, "1k": 3428.26, "1m": 995428.5},
        "engine": "TRAIDE-4lane-benchmark",
        "peaks": {"100k": 100090.97, "10k": 16989.17, "1k": 3570.6, "1m": 1000045.88},
        "type": "lane_state_attestation",
    }
    expected = (
        '{"balances":{"100k":97663.31,"10k":16983.89,"1k":3570.23,"1m":995049.99},'
        '"day":"2026-08-02","day_start":{"100k":97830.93,"10k":16848.97,"1k":3428.26,'
        '"1m":995428.5},"engine":"TRAIDE-4lane-benchmark","peaks":{"100k":100090.97,'
        '"10k":16989.17,"1k":3570.6,"1m":1000045.88},"type":"lane_state_attestation"}'
    )
    assert receipts.canonical_bytes(keeper_example).decode() == expected
    # Deterministic: key order in the input must not change the hash.
    shuffled = dict(reversed(list(keeper_example.items())))
    assert receipts.receipt_hash(shuffled) == receipts.receipt_hash(keeper_example)


def test_receipt_carries_graph_provenance():
    call = {
        "provider": "thegraph-token-api",
        "endpoint": "https://api.pinax.network/v1/evm/dexes",
        "params": {"network": "base"},
        "authenticated": False,
        "status": 200,
        "response_sha256": "0" * 64,
        "response_bytes": 2010,
        "fetched_at": "2026-09-07T20:50:26Z",
        "ok": True,
    }
    r = receipts.build_receipt(
        agent="AGGRESSIVE", agent_address="0x" + "1" * 40, action="BUY_LINK",
        reason="test", graph_tier="activity", graph_calls=[call],
        graph_signal={"activity_score": 0.4, "price": None, "price_change": None},
        pool_reserves=RESERVES, balances=BALANCES, swap=None, cycle=1,
    )
    assert r["type"] == "arc_agent_decision"
    assert r["graph"]["calls"][0]["response_sha256"] == "0" * 64
    assert r["graph"]["calls"][0]["endpoint"].startswith("https://api.pinax.network")
    assert len(receipts.receipt_hash(r)) == 64


def test_ledger_chain_and_tamper_detection(tmp_path):
    path = tmp_path / "receipts.jsonl"
    hashes = []
    for i in range(3):
        r = receipts.build_receipt(
            agent="PASSIVE", agent_address="0x" + "2" * 40, action="HOLD",
            reason=f"cycle {i}", graph_tier="activity", graph_calls=[],
            graph_signal={}, pool_reserves=RESERVES, balances=BALANCES,
            swap=None, cycle=i,
        )
        hashes.append(receipts.append(r, None, path))
    report = receipts.verify_ledger(path)
    assert report["ok"] and report["rows"] == 3

    # Tamper with one receipt body; the recomputed hash must no longer match.
    lines = path.read_text().splitlines()
    row = json.loads(lines[1])
    row["receipt"]["reason"] = "edited after the fact"
    lines[1] = json.dumps(row, sort_keys=True, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n")
    assert receipts.verify_ledger(path)["hash_mismatches"] == [1]


def test_no_dexscreener_anywhere_in_the_decision_path():
    """
    The Graph must be the only data source. Guard against a future edit quietly
    reintroducing the paper agent's price feed.
    """
    root = Path(__file__).resolve().parent.parent / "arc_agents"
    for py in root.glob("*.py"):
        text = py.read_text().lower()
        assert "dexscreener.com" not in text, f"{py.name} reaches a non-Graph data source"
        assert "api.dexscreener" not in text, f"{py.name} reaches a non-Graph data source"
