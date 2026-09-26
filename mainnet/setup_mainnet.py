"""
setup_mainnet.py - create and seed the USDC/EURC pool on TRAIDEAMM (Arc mainnet) and
fund the three agents. Idempotent; every tx must come back status 1.
    ARC_NETWORK=mainnet python3.11 -m mainnet.setup_mainnet
"""
from __future__ import annotations
import json
from web3 import Web3
from arc_agents import config
from arc_agents.chain import ERC20_ABI, ArcClient
from arc_agents.wallets import derive_agents, deployer_account

POOL_USDC = 2_000_000   # 2.00 USDC
POOL_EURC = 1_750_000   # 1.75 EURC, about the Circle Swap rate paid on 2026-09-26 (3.00 USDC -> 2.634 EURC)
CREATE_PAIR_ABI = [{"name": "createPair", "type": "function", "stateMutability": "nonpayable",
                    "inputs": [{"type": "address"}, {"type": "address"}], "outputs": []},
                   {"name": "pairExists", "type": "function", "stateMutability": "view",
                    "inputs": [{"type": "address"}, {"type": "address"}], "outputs": [{"type": "bool"}]},
                   {"name": "addLiquidity", "type": "function", "stateMutability": "nonpayable",
                    "inputs": [{"type": "address"}] * 2 + [{"type": "uint256"}] * 4, "outputs": [{"type": "uint256"}]}]

def main() -> int:
    assert config.IS_MAINNET
    config.load_dotenv()
    c = ArcClient(); dep = deployer_account(); wallets = derive_agents()
    rec = json.loads(config.DEPLOYMENT_PATH.read_text()); rec.setdefault("txs", {})
    def save(): config.DEPLOYMENT_PATH.write_text(json.dumps(rec, indent=2, sort_keys=True))
    U, E, AMM = (Web3.to_checksum_address(x) for x in (config.USDC, config.LINKMOCK, config.TRAIDE_AMM))
    amm = c.contract(AMM, CREATE_PAIR_ABI)
    def send(fn, label):
        tx = fn.build_transaction({"from": dep.address}); tx.pop("gas", None)
        r = c.send(dep, tx, label); rec["txs"][label] = r; save(); print(label, r["hash"]); return r

    if not amm.functions.pairExists(U, E).call():
        send(amm.functions.createPair(U, E), "create_pair_usdc_eurc")
    if c.reserves()["usdc_units_6"] == 0:
        for tok, amt, label in ((U, POOL_USDC, "approve_usdc_amm"), (E, POOL_EURC, "approve_eurc_amm")):
            erc = c.contract(tok, ERC20_ABI)
            if erc.functions.allowance(dep.address, AMM).call() < amt:
                send(erc.functions.approve(AMM, amt), label)
        send(amm.functions.addLiquidity(U, E, POOL_USDC, POOL_EURC, POOL_USDC, POOL_EURC), "add_liquidity")
    print("pool reserves", c.reserves())

    for w in wallets:
        b = c.balances(w.address)
        if b["usdc_units_6"] < config.AGENT_FUND_USDC_UNITS // 2:
            d = c.balances(dep.address)["usdc_units_6"]
            assert d - config.AGENT_FUND_USDC_UNITS >= config.DEPLOYER_FLOOR_USDC_UNITS, "deployer floor"
            r = c.transfer_native(dep, w.address, config.AGENT_FUND_USDC_UNITS * config.NATIVE_TO_ERC20_SCALE, f"fund_usdc_{w.name}")
            rec["txs"][f"fund_usdc_{w.name}"] = r; save(); print("fund usdc", w.name, r["hash"])
        if b["link_wei_18"] < config.AGENT_FUND_LINK_WEI // 2:
            r = c.transfer_erc20(dep, config.LINKMOCK, w.address, config.AGENT_FUND_LINK_WEI, f"fund_eurc_{w.name}")
            rec["txs"][f"fund_eurc_{w.name}"] = r; save(); print("fund eurc", w.name, r["hash"])
    rec["agents"] = [{**w.public(), "explorer": config.address_url(w.address)} for w in wallets]
    rec["amm"] = config.TRAIDE_AMM
    save()
    print("deployer", c.balances(dep.address))
    for w in wallets: print(w.name, w.address, c.balances(w.address))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
