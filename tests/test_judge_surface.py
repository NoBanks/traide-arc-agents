"""
Tests for the judge-facing surface added 2026-09-10: the public ledger export,
the single-receipt route, the dashboard status line, and the offline parts of
scripts/verify_receipt.py. No network is touched here; the chain and Graph
checks are exercised by running the verifier itself.

    python3.11 -m pytest tests -q
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arc_agents import config, receipts  # noqa: E402
from arc_agents import dashboard  # noqa: E402
from scripts import verify_receipt  # noqa: E402

BALANCES = {"usdc_units_6": 1_000_000, "link_wei_18": 2_000 * 10**18, "native_wei_18": 10**18}
RESERVES = {"usdc_units_6": 2_000_000, "link_wei_18": 16_534 * 10**18}
GRAPH_CALL = {
    "product": "thegraph-token-api", "provider": "thegraph-token-api",
    "endpoint": "https://api.pinax.network/v1/evm/dexes", "params": {"network": "base"},
    "authenticated": False, "status": 200, "response_sha256": "ab" * 32,
    "response_bytes": 1927, "fetched_at": "2026-09-10T10:00:00Z", "ok": True,
}


def _ledger(tmp_path: Path, n: int = 4) -> Path:
    """A small hash chained ledger. Even rows traded (with a fake swap hash)."""
    path = tmp_path / "receipts.jsonl"
    for i in range(n):
        swap = {"hash": "0x" + f"{i:064x}", "block": 100 + i, "status": 1} if i % 2 == 0 else None
        r = receipts.build_receipt(
            agent=["PASSIVE", "AGGRESSIVE", "REBALANCE"][i % 3], agent_address="0x" + "3" * 40,
            action="BUY_LINK" if swap else "HOLD", reason=f"row {i}", graph_tier="activity",
            graph_calls=[GRAPH_CALL], graph_signal={"activity_score": 0.3},
            pool_reserves=RESERVES, balances=BALANCES, swap=swap, cycle=i,
        )
        anchor = {"hash": "0x" + f"{i + 1000:064x}", "anchor_contract": "0x" + "4" * 40} if swap else {}
        receipts.append(r, anchor, path)
    return path


@pytest.fixture
def client(tmp_path, monkeypatch):
    path = _ledger(tmp_path)
    monkeypatch.setattr(config, "RECEIPTS_PATH", path)
    monkeypatch.setattr(config, "STATE_PATH", tmp_path / "state.json")
    (tmp_path / "state.json").write_text(json.dumps({"cycle": 4, "agents": {}, "started_at": "2026-09-07T20:48:57Z", "graph": {}}))
    return TestClient(dashboard.app)


def test_ledger_json_is_the_raw_ledger_with_totals(client):
    body = client.get("/ledger.json").json()
    assert body["chain_id"] == config.CHAIN_ID
    assert body["totals"] == {"receipts": 4, "swaps": 2, "anchors": 2, "last_decision_at": body["rows"][-1]["receipt"]["timestamp"]}
    assert body["count"] == 4
    # Every exported row re-hashes to its own receipt_hash: the export is byte-true.
    for row in body["rows"]:
        assert receipts.receipt_hash(row["receipt"]) == row["receipt_hash"]
    assert "canonical_rule" in body and "verify_one" in body


def test_ledger_json_filters(client):
    assert client.get("/ledger.json?limit=1").json()["count"] == 1
    traded = client.get("/ledger.json?traded=1").json()
    assert traded["count"] == 2 and all(r["receipt"]["swap"]["hash"] for r in traded["rows"])
    # totals describe the whole ledger even when the rows are filtered
    assert traded["totals"]["receipts"] == 4
    by_agent = client.get("/ledger.json?agent=passive").json()
    assert by_agent["count"] == 2 and {r["receipt"]["agent"] for r in by_agent["rows"]} == {"PASSIVE"}


def test_receipt_route_by_hash(client):
    rows = client.get("/ledger.json").json()["rows"]
    h = rows[1]["receipt_hash"]
    assert client.get(f"/receipt/{h}.json").json() == rows[1]
    assert client.get(f"/receipt/0x{h}.json").status_code == 200
    assert client.get("/receipt/" + "a" * 64 + ".json").status_code == 404


def test_dashboard_status_line(client):
    html = client.get("/", headers={"host": "arc-agents.nohumannearby.com", "x-forwarded-proto": "https"}).text
    assert '<div class="status">' in html
    assert "<b>4</b> receipts" in html and "<b>2</b> real swaps" in html and "<b>2</b> anchored on Arc" in html
    assert "ledger running since" in html and "2026-09-07T20:48:57Z" in html
    assert "--ledger https://arc-agents.nohumannearby.com/ledger.json" in html


def test_ledger_export_never_carries_a_credential(client, monkeypatch):
    monkeypatch.setenv("GRAPH_GATEWAY_API_KEY", "not-a-real-key-just-a-canary-value")
    text = client.get("/ledger.json").text
    assert "not-a-real-key-just-a-canary-value" not in text


# --------------------------------------------------- verify_receipt, offline


def test_verifier_resolves_a_hash_from_a_local_ledger(tmp_path):
    path = _ledger(tmp_path)
    rows = receipts.read_all(path)
    row, source = verify_receipt.load_target(rows[2]["receipt_hash"], str(path))
    assert row == rows[2] and source == str(path)
    row0, _ = verify_receipt.load_target("0x" + rows[0]["receipt_hash"], str(path))
    assert row0 == rows[0]
    with pytest.raises(SystemExit):
        verify_receipt.load_target("f" * 64, str(path))
    with pytest.raises(SystemExit):
        verify_receipt.load_target("not-a-hash", str(path))


def test_verifier_accepts_a_row_file_or_a_bare_receipt(tmp_path):
    path = _ledger(tmp_path)
    row = receipts.read_all(path)[0]
    f = tmp_path / "row.json"
    f.write_text(json.dumps(row))
    assert verify_receipt.load_target(str(f), str(path))[0] == row
    bare = tmp_path / "bare.json"
    bare.write_text(json.dumps(row["receipt"]))
    wrapped, _ = verify_receipt.load_target(str(bare), str(path))
    assert wrapped["receipt"] == row["receipt"] and wrapped["receipt_hash"] == ""


def test_verifier_hash_check_catches_tampering(tmp_path, capsys):
    path = _ledger(tmp_path)
    row = receipts.read_all(path)[0]
    rep = verify_receipt.Report()
    assert verify_receipt.check_hash(rep, row, row["receipt_hash"]) == row["receipt_hash"]
    assert rep.passed == 1 and rep.failed == 0
    row["receipt"]["reason"] = "edited after the fact"
    rep2 = verify_receipt.Report()
    verify_receipt.check_hash(rep2, row, "")
    assert rep2.failed == 1
    assert "[FAIL] hash" in capsys.readouterr().out


def test_verifier_graph_check_rejects_a_non_graph_host(tmp_path, capsys):
    path = _ledger(tmp_path)
    row = receipts.read_all(path)[0]
    row["receipt"]["graph"]["calls"] = [dict(GRAPH_CALL, endpoint="https://api.dexscreener.com/latest")]
    rep = verify_receipt.Report()
    verify_receipt.check_graph(rep, row, rerun=False)
    out = capsys.readouterr().out
    assert rep.failed == 1 and "is not a Graph host" in out


def test_verifier_guard_fails_a_trade_made_on_tier_none(tmp_path, capsys):
    path = _ledger(tmp_path)
    row = receipts.read_all(path)[0]
    row["receipt"]["graph"]["tier"] = "none"
    rep = verify_receipt.Report()
    verify_receipt.check_graph(rep, row, rerun=False)
    assert rep.failed >= 1 and "TRADED with Graph tier none" in capsys.readouterr().out


def test_verifier_graph_check_passes_offline_with_no_graph(tmp_path, capsys):
    path = _ledger(tmp_path)
    row = receipts.read_all(path)[0]
    rep = verify_receipt.Report()
    verify_receipt.check_graph(rep, row, rerun=False)
    out = capsys.readouterr().out
    assert rep.failed == 0 and "re-run disabled with --no-graph" in out and "[PASS] guard" in out
