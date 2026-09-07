"""
setup_arc.py - one-time on-chain setup, idempotent.

  1. Report the deployer and the three derived agent addresses.
  2. Deepen the TRAIDEAMM USDC/LINKMock pool from the deployer, so the agents'
     tiny swaps do not move the price by double digits. Skipped once the pool is
     already at or above the target.
  3. Fund each agent with USDC (which is also Arc's gas token) and LINKMock.
  4. Deploy ArcReceiptAnchor if it is not already deployed.

Every transaction is re-read from chain and must return status 1. Nothing is
claimed that the chain did not confirm. The deployer is never drawn below
config.DEPLOYER_FLOOR_USDC_UNITS.

    python3.11 -m scripts.setup_arc            # do it
    python3.11 -m scripts.setup_arc --plan     # print the plan, send nothing
"""

from __future__ import annotations

import argparse
import json
import time

from web3 import Web3

from arc_agents import anchor, config
from arc_agents.chain import ERC20_ABI, ArcClient
from arc_agents.wallets import derive_agents, deployer_account

# Target pool depth. At 2 USDC a side, a 0.01 USDC swap moves the price about
# 0.5 percent, which leaves room for hundreds of agent trades during judging.
TARGET_POOL_USDC_UNITS = 2_000_000  # 2.0 USDC


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", action="store_true", help="print the plan and send nothing")
    args = parser.parse_args()

    config.load_dotenv()
    client = ArcClient()
    deployer = deployer_account()
    wallets = derive_agents()

    record_path = config.REPO_ROOT / "deployments" / "arc-5042002.json"
    record = json.loads(record_path.read_text()) if record_path.exists() else {}
    record["chain_id"] = config.CHAIN_ID
    record.setdefault("txs", {})
    record["agents"] = [w.public() for w in wallets]
    record["deployer"] = deployer.address
    record["amm"] = config.TRAIDE_AMM
    record["usdc"] = config.USDC
    record["linkmock"] = config.LINKMOCK

    def save() -> None:
        record_path.parent.mkdir(parents=True, exist_ok=True)
        record_path.write_text(json.dumps(record, indent=2, sort_keys=True))

    dep = client.balances(deployer.address)
    reserves = client.reserves()
    log(f"deployer {deployer.address}")
    log(f"  usdc units (6dec) {dep['usdc_units_6']}  link wei {dep['link_wei_18']}")
    log(f"pool reserves usdc {reserves['usdc_units_6']}  link {reserves['link_wei_18']}")
    for w in wallets:
        b = client.balances(w.address)
        log(f"agent {w.name:11s} {w.address}  usdc {b['usdc_units_6']}  link {b['link_wei_18']}")

    add_usdc = max(TARGET_POOL_USDC_UNITS - reserves["usdc_units_6"], 0)
    fund_needed = sum(
        1 for w in wallets if client.balances(w.address)["usdc_units_6"] < config.AGENT_FUND_USDC_UNITS // 2
    )
    log(f"plan: add {add_usdc} USDC units of liquidity, fund {fund_needed} agents, "
        f"anchor {'already deployed' if anchor.anchor_address() else 'to deploy'}")

    if args.plan:
        return 0

    # ---------------------------------------------------------------- liquidity
    if add_usdc > 0 and reserves["link_wei_18"] > 0:
        # Match the pool ratio so addLiquidity does not clamp away the USDC leg.
        need_link = add_usdc * reserves["link_wei_18"] // reserves["usdc_units_6"]
        need_link = need_link * 102 // 100  # small excess, the AMM clamps to the ratio
        if dep["link_wei_18"] < need_link:
            raise RuntimeError(f"deployer holds {dep['link_wei_18']} LINK wei, needs {need_link}")
        if dep["usdc_units_6"] - add_usdc < config.DEPLOYER_FLOOR_USDC_UNITS:
            raise RuntimeError("adding that much liquidity would breach the deployer floor")

        for token, amount, label in (
            (config.USDC, add_usdc, "approve_usdc_amm"),
            (config.LINKMOCK, need_link, "approve_link_amm"),
        ):
            c = client.contract(token, ERC20_ABI)
            allowance = int(c.functions.allowance(
                Web3.to_checksum_address(deployer.address), Web3.to_checksum_address(config.TRAIDE_AMM)
            ).call())
            if allowance < amount:
                tx = c.functions.approve(
                    Web3.to_checksum_address(config.TRAIDE_AMM), amount * 4
                ).build_transaction({"from": deployer.address})
                tx.pop("gas", None)
                r = client.send(deployer, tx, label)
                record["txs"][label] = r
                save()
                log(f"  {label} {r['hash']}")

        tx = client.amm.functions.addLiquidity(
            Web3.to_checksum_address(config.USDC),
            Web3.to_checksum_address(config.LINKMOCK),
            add_usdc, need_link, 0, 0,
        ).build_transaction({"from": deployer.address})
        tx.pop("gas", None)
        r = client.send(deployer, tx, "add_liquidity")
        record["txs"]["add_liquidity"] = r
        save()
        log(f"  add_liquidity {r['hash']}")
        reserves = client.reserves()
        log(f"  pool now usdc {reserves['usdc_units_6']} link {reserves['link_wei_18']}")

    # ------------------------------------------------------------------ funding
    for w in wallets:
        b = client.balances(w.address)
        dep = client.balances(deployer.address)
        if b["usdc_units_6"] < config.AGENT_FUND_USDC_UNITS // 2:
            if dep["usdc_units_6"] - config.AGENT_FUND_USDC_UNITS < config.DEPLOYER_FLOOR_USDC_UNITS:
                raise RuntimeError("funding this agent would breach the deployer floor")
            wei = config.AGENT_FUND_USDC_UNITS * config.NATIVE_TO_ERC20_SCALE
            r = client.transfer_native(deployer, w.address, wei, f"fund_usdc_{w.name}")
            record["txs"][f"fund_usdc_{w.name}"] = r
            save()
            log(f"  fund_usdc_{w.name} {r['hash']}")
        if b["link_wei_18"] < config.AGENT_FUND_LINK_WEI // 2:
            r = client.transfer_erc20(
                deployer, config.LINKMOCK, w.address, config.AGENT_FUND_LINK_WEI, f"fund_link_{w.name}"
            )
            record["txs"][f"fund_link_{w.name}"] = r
            save()
            log(f"  fund_link_{w.name} {r['hash']}")

    # ------------------------------------------------------------------- anchor
    save()
    entry = anchor.deploy(client, deployer)
    log(f"  anchor at {entry['address']} ({entry['code_bytes']} bytes of code)")
    record = json.loads(record_path.read_text())
    record["agents"] = [w.public() for w in wallets]
    save()

    log("final balances")
    log(f"  deployer usdc {client.balances(deployer.address)['usdc_units_6']}")
    for w in wallets:
        b = client.balances(w.address)
        log(f"  {w.name:11s} usdc {b['usdc_units_6']} link {b['link_wei_18']}")
    log(f"record written to {record_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
