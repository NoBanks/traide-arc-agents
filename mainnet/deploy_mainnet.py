"""
deploy_mainnet.py - stand up the minimal TRAIDE footprint on Arc mainnet (chain 5042).

Deploys exactly three contracts, replaying the byte-exact deploy calldata of the
testnet transactions (mainnet/testnet_initcode.json, extracted from the Arc testnet
explorer and re-verified against the testnet CREATE2 addresses):

  TRAIDEToken  CREATE2, salt TRAIDE_TOKEN_V1   same address as testnet. Owner and
               the whole supply end up at the stateless CREATE2 proxy: nothing can
               mint, pause or move it. Present only because TRAIDEAMM reads fee tiers.
  TRAIDEAMM    CREATE2, salt TRAIDE_AMM_V1     same address as testnet.
  ArcReceiptAnchor  plain CREATE, same bytecode as testnet, new address.

Nothing else from the 11-contract suite goes to mainnet.
    ARC_NETWORK=mainnet python3.11 -m mainnet.deploy_mainnet [--plan]
"""
from __future__ import annotations
import argparse, json, time
from eth_utils import keccak, to_checksum_address
from web3 import Web3
from arc_agents import config
from arc_agents.chain import ArcClient
from arc_agents.wallets import deployer_account

PROXY = "0x4e59b44847b379578588920cA78FbF26c0B4956C"

def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--plan", action="store_true"); a = ap.parse_args()
    assert config.IS_MAINNET, "run with ARC_NETWORK=mainnet"
    config.load_dotenv()
    client = ArcClient(); acct = deployer_account()
    init = json.loads((config.REPO_ROOT / "mainnet" / "testnet_initcode.json").read_text())
    rec = json.loads(config.DEPLOYMENT_PATH.read_text()) if config.DEPLOYMENT_PATH.exists() else {}
    rec.update({"chain_id": config.CHAIN_ID, "deployer": acct.address, "usdc": config.USDC, "eurc": config.LINKMOCK})
    rec.setdefault("txs", {})
    def save(): config.DEPLOYMENT_PATH.write_text(json.dumps(rec, indent=2, sort_keys=True))
    print("deployer USDC (native 18dp):", client.w3.eth.get_balance(acct.address) / 1e18)
    assert len(client.w3.eth.get_code(PROXY)) == 69, "CREATE2 proxy missing"

    for name in ("token", "amm"):
        data = bytes.fromhex(init[name]["data"][2:])
        addr = to_checksum_address(keccak(b"\xff" + bytes.fromhex(PROXY[2:]) + data[:32] + keccak(data[32:]))[12:])
        assert addr.lower() == init[name]["testnet_address"].lower(), f"{name} predicted address drifted"
        if client.w3.eth.get_code(addr):
            print(f"= {name} already at {addr}")
        elif a.plan:
            print(f"would deploy {name} at {addr}")
        else:
            r = client.send(acct, {"to": PROXY, "data": "0x" + data.hex(), "value": 0}, f"deploy_{name}")
            for _ in range(6):
                if client.w3.eth.get_code(addr): break
                time.sleep(5)
            assert client.w3.eth.get_code(addr), f"no code at {addr}"
            rec["txs"][f"deploy_{name}"] = r; print(f"+ {name} {addr} {r['hash']}")
        rec[name] = {"address": addr, "explorer": config.address_url(addr), "salt_version": "V1"}
        save()

    if rec.get("anchor", {}).get("address") and client.w3.eth.get_code(rec["anchor"]["address"]):
        print("= anchor already at", rec["anchor"]["address"])
    elif a.plan:
        print("would deploy anchor (plain CREATE)")
    else:
        r = client.send(acct, {"data": init["anchor"]["data"], "value": 0}, "deploy_anchor")
        rc = client.w3.eth.get_transaction_receipt(r["hash"])
        addr = Web3.to_checksum_address(rc["contractAddress"])
        assert client.w3.eth.get_code(addr), "anchor has no code"
        rec["anchor"] = {"address": addr, "deploy_tx": r, "explorer": config.address_url(addr)}
        print("+ anchor", addr, r["hash"]); save()

    tok = client.contract(rec["token"]["address"], [{"name":"owner","outputs":[{"type":"address"}],"inputs":[],"stateMutability":"view","type":"function"},{"name":"balanceOf","outputs":[{"type":"uint256"}],"inputs":[{"type":"address"}],"stateMutability":"view","type":"function"},{"name":"totalSupply","outputs":[{"type":"uint256"}],"inputs":[],"stateMutability":"view","type":"function"}]) if not a.plan or client.w3.eth.get_code(rec["token"]["address"]) else None
    if tok:
        owner = tok.functions.owner().call(); sup = tok.functions.totalSupply().call(); held = tok.functions.balanceOf(PROXY).call()
        rec["token"]["inert_check"] = {"owner": owner, "total_supply": str(sup), "held_by_create2_proxy": str(held), "circulating": str(sup - held)}
        print("token owner", owner, "supply", sup, "held by proxy", held, "circulating", sup - held); save()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
