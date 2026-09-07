"""
runner.py - the loop. One cycle does this, in order:

  1. Ask The Graph for a live signal. One fetch per cycle, never cached.
  2. Read the TRAIDEAMM pair reserves and each agent's balances from Arc.
  3. Each agent decides. No usable Graph signal means every agent HOLDs.
  4. A trading decision executes a real swap on TRAIDEAMM and the receipt is
     re-read from chain with status 1 before anything is claimed.
  5. A keeper receipt is built for EVERY decision, trade or hold, carrying the
     Graph provenance, and its sha256 is written to the hash chained ledger.
  6. Receipts for decisions that traded are anchored on Arc through
     ArcReceiptAnchor, signed by the agent that made the decision.

Run one cycle:   python3.11 -m arc_agents.runner --once
Dry run:         python3.11 -m arc_agents.runner --once --dry-run
Forever:         python3.11 -m arc_agents.runner
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

from . import agents, anchor, config, receipts
from .chain import ArcClient
from .graph import GraphClient
from .wallets import AgentWallet, derive_agents


def log(msg: str) -> None:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def _load_state() -> dict[str, Any]:
    if config.STATE_PATH.exists():
        try:
            return json.loads(config.STATE_PATH.read_text())
        except Exception:
            pass
    return {"cycle": 0, "agents": {}, "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def _save_state(state: dict[str, Any]) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True))


def _pnl_vs_hold(client: ArcClient, wallet: AgentWallet, state: dict[str, Any]) -> dict[str, float]:
    """
    Mark the agent to market against the do nothing benchmark.

    opening_* is the inventory the agent was funded with. Both the live and the
    hold portfolio are valued at the SAME live pool rate, so the difference is
    purely the effect of trading, not of the pool moving.
    """
    entry = state["agents"].setdefault(wallet.name, {})
    bal = client.balances(wallet.address)
    r = client.reserves()
    if r["link_wei_18"] == 0:
        return {}
    # USDC units per 1e18 LINK wei, from live reserves.
    rate = r["usdc_units_6"] / r["link_wei_18"]

    if "opening_usdc_units_6" not in entry:
        entry["opening_usdc_units_6"] = bal["usdc_units_6"]
        entry["opening_link_wei_18"] = bal["link_wei_18"]

    live_value = bal["usdc_units_6"] + bal["link_wei_18"] * rate
    hold_value = entry["opening_usdc_units_6"] + entry["opening_link_wei_18"] * rate
    entry["live_value_usdc"] = live_value / 10**config.USDC_DECIMALS
    entry["hold_value_usdc"] = hold_value / 10**config.USDC_DECIMALS
    entry["pnl_vs_hold_usdc"] = (live_value - hold_value) / 10**config.USDC_DECIMALS
    entry["balances"] = bal
    entry["address"] = wallet.address
    entry["explorer"] = wallet.explorer_url()
    return entry


def run_cycle(
    client: ArcClient,
    graph_client: GraphClient,
    wallets: list[AgentWallet],
    state: dict[str, Any],
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    state["cycle"] = int(state.get("cycle", 0)) + 1
    cycle = state["cycle"]

    signal = graph_client.signal()
    log(f"cycle {cycle}: Graph tier={signal.tier} calls={len(signal.calls)}")
    for note in signal.notes:
        log(f"  {note}")
    if not signal.usable:
        log("  no usable Graph signal, every agent holds this cycle")

    reserves = client.reserves()
    state["pool"] = {
        "reserves": reserves,
        "amm": config.TRAIDE_AMM,
        "link_per_usdc": client.pool_price_link_per_usdc(),
    }
    state["graph_activity_carry"] = graph_client.export_activity()
    state["graph"] = {
        "tier": signal.tier,
        "activity_score": signal.activity_score,
        "price": signal.price,
        "price_change": signal.price_change,
        "notes": signal.notes,
        "products": signal.products,
        "price_unavailable_reason": signal.price_unavailable_reason,
        "last_calls": signal.provenance(),
    }

    results: list[dict[str, Any]] = []
    for wallet in wallets:
        balances = client.balances(wallet.address)
        decision = agents.decide(wallet.name, signal, balances, reserves)
        log(f"  {wallet.name}: {decision.action} - {decision.reason}")

        swap_record: dict[str, Any] | None = None
        if decision.trades and not dry_run:
            try:
                swap_record = _execute(client, wallet, decision)
                log(f"    swap {swap_record['hash']} block {swap_record['block']}")
            except Exception as exc:
                log(f"    swap failed: {type(exc).__name__}: {exc}")
                decision = agents.Decision("HOLD", f"swap attempt failed: {type(exc).__name__}")
        elif decision.trades and dry_run:
            log("    dry run, no transaction sent")

        receipt = receipts.build_receipt(
            agent=wallet.name,
            agent_address=wallet.address,
            action=decision.action,
            reason=decision.reason,
            graph_tier=signal.tier,
            graph_calls=signal.provenance(),
            graph_signal={
                "activity_score": signal.activity_score,
                "price": signal.price,
                "price_change": signal.price_change,
            },
            pool_reserves=reserves,
            balances=balances,
            swap=swap_record,
            cycle=cycle,
        )
        h = receipts.receipt_hash(receipt)

        anchor_record: dict[str, Any] = {}
        if swap_record and not dry_run:
            try:
                anchor_record = anchor.attest(client, wallet, h, wallet.name)
                log(f"    anchored {h[:16]} in {anchor_record['hash']}")
            except Exception as exc:
                log(f"    anchor failed: {type(exc).__name__}: {exc}")

        receipts.append(receipt, anchor_record)
        _pnl_vs_hold(client, wallet, state)
        results.append({"agent": wallet.name, "action": decision.action, "receipt_hash": h,
                        "swap": swap_record, "anchor": anchor_record})

    _save_state(state)
    return results


def _execute(client: ArcClient, wallet: AgentWallet, decision: agents.Decision) -> dict[str, Any]:
    """Approve if needed, quote, then swap with a 2 percent slippage floor."""
    if decision.action == "BUY_LINK":
        token_in, token_out, amount = config.USDC, config.LINKMOCK, decision.size_usdc_units
    else:
        token_in, token_out, amount = config.LINKMOCK, config.USDC, decision.size_link_wei

    client.ensure_allowance(wallet, token_in, config.TRAIDE_AMM, amount)
    quoted = client.quote(token_in, token_out, amount, wallet.address)
    if quoted <= 0:
        raise RuntimeError("pool quoted zero output")
    min_out = quoted * 98 // 100

    record = client.swap(wallet, token_in, token_out, amount, min_out)
    record.update({
        "token_in": token_in,
        "token_out": token_out,
        "amount_in": str(amount),
        "quoted_out": str(quoted),
        "min_out": str(min_out),
        "venue": config.SWAP_VENUE,
    })
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TRAIDE agents on Arc testnet")
    parser.add_argument("--once", action="store_true", help="run a single cycle and exit")
    parser.add_argument("--dry-run", action="store_true", help="decide and write receipts, send no transactions")
    parser.add_argument("--cycles", type=int, default=0, help="stop after N cycles (0 means forever)")
    parser.add_argument("--interval", type=int, default=config.CYCLE_SECONDS)
    args = parser.parse_args(argv)

    config.load_dotenv()
    client = ArcClient()
    graph_client = GraphClient()
    wallets = derive_agents()
    state = _load_state()

    # Carry the last activity reading across the restart so the first cycle is
    # not wasted priming. Anything older than three intervals is discarded.
    if graph_client.restore_activity(state.get("graph_activity_carry"), args.interval * 3):
        log("restored the previous activity reading, no priming cycle needed")

    log(f"chain {client.chain_id}, AMM {config.TRAIDE_AMM}, anchor {anchor.anchor_address() or 'not deployed'}")
    for w in wallets:
        log(f"agent {w.name} {w.address} ({w.derivation_path})")
    if not config.graph_api_key() and not config.graph_gateway_api_key():
        log("WARNING no Graph credential set, the price tier cannot run and REBALANCE will hold")

    limit = 1 if args.once else args.cycles
    n = 0
    while True:
        try:
            run_cycle(client, graph_client, wallets, state, dry_run=args.dry_run)
        except KeyboardInterrupt:
            return 0
        except Exception as exc:
            log(f"cycle error: {type(exc).__name__}: {exc}")
        n += 1
        if limit and n >= limit:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
