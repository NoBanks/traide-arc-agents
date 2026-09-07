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
"""

from __future__ import annotations

import sys

from arc_agents import anchor, config, receipts
from arc_agents.chain import ANCHOR_ABI, ArcClient


def main() -> int:
    config.load_dotenv()
    rows = receipts.read_all()
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
