"""
anchor.py - compile, deploy and call ArcReceiptAnchor on Arc testnet.

Why a contract and not a calldata memo: both were on the table and the choice is
documented in ArcReceiptAnchor.sol. A self transfer with the hash in calldata is
cheaper, but it is not queryable. The contract gives an indexed event a verifier
can filter, a first-seen timestamp per hash so a receipt cannot be backdated,
and a total the dashboard reads with a single eth_call. On Arc a 60k gas anchor
costs about 0.0015 USDC at 25 gwei, so the extra cost is not a real constraint.

The contract is compiled with solc 0.8.25, the same compiler the TRAIDE fleet on
Arc was built and verified with.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import solcx
from eth_account.signers.local import LocalAccount
from web3 import Web3

from . import config
from .chain import ANCHOR_ABI, ArcClient

SOLC_VERSION = "0.8.25"
SOURCE_PATH = config.REPO_ROOT / "contracts" / "ArcReceiptAnchor.sol"
BUILD_PATH = config.REPO_ROOT / "build" / "ArcReceiptAnchor.json"
DEPLOYMENT_PATH = config.REPO_ROOT / "deployments" / "arc-5042002.json"


def compile_anchor() -> dict[str, Any]:
    if SOLC_VERSION not in [str(v) for v in solcx.get_installed_solc_versions()]:
        solcx.install_solc(SOLC_VERSION)
    compiled = solcx.compile_files(
        [str(SOURCE_PATH)],
        output_values=["abi", "bin"],
        solc_version=SOLC_VERSION,
        optimize=True,
        optimize_runs=200,
    )
    key = next(k for k in compiled if k.endswith(":ArcReceiptAnchor"))
    artifact = {
        "contract": "ArcReceiptAnchor",
        "solc": SOLC_VERSION,
        "optimizer": {"enabled": True, "runs": 200},
        "abi": compiled[key]["abi"],
        "bytecode": compiled[key]["bin"],
    }
    BUILD_PATH.parent.mkdir(parents=True, exist_ok=True)
    BUILD_PATH.write_text(json.dumps(artifact, indent=2))
    return artifact


def load_deployment(path: Path | None = None) -> dict[str, Any]:
    target = path or DEPLOYMENT_PATH
    if not target.exists():
        return {}
    return json.loads(target.read_text())


def anchor_address() -> str:
    return str(load_deployment().get("anchor", {}).get("address", ""))


def deploy(client: ArcClient, account: LocalAccount) -> dict[str, Any]:
    """Deploy once. Re-running returns the recorded deployment untouched."""
    existing = load_deployment()
    recorded = existing.get("anchor", {}).get("address", "")
    if recorded:
        code = client.w3.eth.get_code(Web3.to_checksum_address(recorded))
        if len(code) > 2:
            return existing["anchor"]

    artifact = compile_anchor()
    factory = client.w3.eth.contract(abi=artifact["abi"], bytecode=artifact["bytecode"])
    tx = factory.constructor().build_transaction({"from": account.address})
    tx.pop("gas", None)
    record = client.send(account, tx, "deploy_anchor")

    receipt = client.w3.eth.get_transaction_receipt(record["hash"])
    address = Web3.to_checksum_address(receipt["contractAddress"])
    code = client.w3.eth.get_code(address)
    if len(code) <= 2:
        raise RuntimeError(f"anchor deployed but has no code at {address}")

    entry = {
        "address": address,
        "code_bytes": len(code),
        "deploy_tx": record,
        "explorer": config.address_url(address),
        "solc": SOLC_VERSION,
    }
    existing.setdefault("chain_id", config.CHAIN_ID)
    existing["anchor"] = entry
    DEPLOYMENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEPLOYMENT_PATH.write_text(json.dumps(existing, indent=2, sort_keys=True))
    return entry


def _agent_bytes32(name: str) -> bytes:
    raw = name.encode("utf-8")[:32]
    return raw + b"\x00" * (32 - len(raw))


def attest(client: ArcClient, wallet: Any, receipt_hash_hex: str, agent_name: str) -> dict[str, Any]:
    """
    Anchor one receipt hash. `wallet` is an AgentWallet, so the agent that made
    the decision is the address that signs the anchor. That matters: the anchor
    is evidence about that agent, so it should not come from a shared operator.
    """
    address = anchor_address()
    if not address:
        raise RuntimeError("anchor contract is not deployed; run scripts/deploy_anchor.py")
    contract = client.contract(address, ANCHOR_ABI)
    h = receipt_hash_hex[2:] if receipt_hash_hex.startswith("0x") else receipt_hash_hex
    tx = contract.functions.attest(
        bytes.fromhex(h), _agent_bytes32(agent_name)
    ).build_transaction({"from": wallet.address})
    tx.pop("gas", None)
    record = client.send(wallet._account, tx, "anchor")
    record["receipt_hash"] = h
    record["anchor_contract"] = address
    return record


def anchored_total(client: ArcClient) -> int:
    address = anchor_address()
    if not address:
        return 0
    return int(client.contract(address, ANCHOR_ABI).functions.total().call())
