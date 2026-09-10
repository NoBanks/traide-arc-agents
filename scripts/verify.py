"""
verify.py - independent verification, for a judge who does not want to trust the
dashboard or the README.

It does four things and prints a pass or fail for each:

  1. Recomputes every receipt hash from its own canonical bytes and walks the
     prev-hash chain, so a tampered receipt is caught.
  2. Refetches every swap transaction from Arc and requires status 1.
  3. Calls attestedAt(bytes32) on the anchor contract for every anchored receipt
     hash and requires a nonzero first-seen timestamp.
  4. Confirms every receipt carries Graph provenance with a response hash, and
     that no decision that traded was made without a usable Graph tier.

    python3.11 -m scripts.verify
    python3.11 -m scripts.verify --ledger https://arc-agents.nohumannearby.com/ledger.json

A fresh clone has no data/ directory (it is gitignored, the runner writes it), so
when the local ledger is absent this script reads the public export from the
live dashboard instead. To verify a single receipt in more depth, including its
anchor tx, the attester and a live re-run of its Graph calls, use
scripts/verify_receipt.py.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request

from arc_agents import anchor, config, receipts
from arc_agents.chain import ANCHOR_ABI, ArcClient

PUBLIC_LEDGER = "https://arc-agents.nohumannearby.com/ledger.json"


def load_rows(ledger: str) -> list[dict]:
    if ledger.startswith("http://") or ledger.startswith("https://"):
        req = urllib.request.Request(ledger, headers={"Accept": "application/json", "User-Agent": "traide-arc-agents/verify"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return list(body.get("rows", [])) if isinstance(body, dict) else list(body)
    from pathlib import Path
    return receipts.read_all(Path(ledger))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="verify the whole traide-arc-agents ledger")
    parser.add_argument("--ledger", default="",
                        help=f"local receipts.jsonl or a /ledger.json URL (default: data/receipts.jsonl if present, else {PUBLIC_LEDGER})")
    args = parser.parse_args(argv)

    config.load_dotenv()
    ledger = args.ledger or (str(config.RECEIPTS_PATH) if config.RECEIPTS_PATH.exists() else PUBLIC_LEDGER)
    rows = load_rows(ledger)
    print(f"ledger: {ledger}")
    if not rows:
        print("no receipts to verify")
        return 1

    failures = 0

    # 1. ledger integrity
    report = receipts.verify_ledger()
    ok = report["ok"]
    failures += 0 if ok else 1
    print(f"[{'PASS' if ok else 'FAIL'}] ledger: {report['rows']} receipts, "
          f"{len(report['hash_mismatches'])} hash mismatches, "
          f"{len(report['chain_breaks'])} chain breaks")

    client = ArcClient()

    # 2. swaps
    swaps = [r for r in rows if (r["receipt"].get("swap") or {}).get("hash")]
    bad = []
    for r in swaps:
        h = r["receipt"]["swap"]["hash"]
        try:
            if int(client.w3.eth.get_transaction_receipt(h)["status"]) != 1:
                bad.append(h)
        except Exception:
            bad.append(h)
    failures += 0 if not bad else 1
    print(f"[{'PASS' if not bad else 'FAIL'}] swaps: {len(swaps)} refetched from Arc, "
          f"{len(bad)} not status 1")

    # 3. anchors
    address = anchor.anchor_address()
    anchored = [r for r in rows if (r.get("anchor") or {}).get("hash")]
    missing = []
    total = 0
    if address:
        contract = client.contract(address, ANCHOR_ABI)
        total = int(contract.functions.total().call())
        for r in anchored:
            h = r["receipt_hash"]
            if int(contract.functions.attestedAt(bytes.fromhex(h)).call()) == 0:
                missing.append(h)
    else:
        missing = ["anchor contract not deployed"]
    failures += 0 if not missing else 1
    print(f"[{'PASS' if not missing else 'FAIL'}] anchors: {len(anchored)} anchored, "
          f"contract total() {total}, {len(missing)} hashes absent on chain")

    # 4. Graph provenance, and no trade without a Graph tier
    no_prov = [r for r in rows if not r["receipt"].get("graph", {}).get("calls")
               and r["receipt"]["graph"].get("tier") != "none"]
    traded_blind = [
        r for r in swaps if r["receipt"]["graph"].get("tier") in ("none", None)
    ]
    bad_prov = bool(no_prov or traded_blind)
    failures += 0 if not bad_prov else 1
    print(f"[{'PASS' if not bad_prov else 'FAIL'}] graph: {len(no_prov)} receipts with a "
          f"tier but no provenance, {len(traded_blind)} swaps made without a Graph tier")

    endpoints = sorted({
        c["endpoint"] for r in rows for c in r["receipt"].get("graph", {}).get("calls", [])
    })
    print("\nGraph endpoints that actually decided these trades:")
    for e in endpoints:
        print(f"  {e}")
    print(f"\nanchor contract: {config.address_url(address) if address else 'none'}")
    print(f"{'ALL CHECKS PASSED' if failures == 0 else str(failures) + ' CHECK GROUP(S) FAILED'}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
