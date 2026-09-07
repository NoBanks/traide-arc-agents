"""
chain.py - everything that touches Arc testnet 5042002.

Rules this module enforces so no claim in this repo can outrun the chain:
  - Every transaction is waited on and its receipt is re-read. status != 1 raises.
  - Every returned tx record carries the hash, block, gas used, effective gas
    price and an explorer URL, so a reader can check it.
  - Swaps go through TRAIDEAMM, never the Factory/Router/Pair path. See the note
    in config.SWAP_VENUE for why.
  - Legacy type-0 transactions with an explicit gasPrice. Arc's mempool enforces
    a 20 gwei maxFeePerGas floor, so the price is clamped up, never down.
"""

from __future__ import annotations

import time
from typing import Any

from eth_account.signers.local import LocalAccount
from web3 import Web3

from . import config
from .wallets import AgentWallet

ERC20_ABI = [
    {"name": "approve", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "spender", "type": "address"}, {"name": "amount", "type": "uint256"}],
     "outputs": [{"name": "", "type": "bool"}]},
    {"name": "transfer", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "to", "type": "address"}, {"name": "amount", "type": "uint256"}],
     "outputs": [{"name": "", "type": "bool"}]},
    {"name": "balanceOf", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "account", "type": "address"}],
     "outputs": [{"name": "", "type": "uint256"}]},
    {"name": "allowance", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "owner", "type": "address"}, {"name": "spender", "type": "address"}],
     "outputs": [{"name": "", "type": "uint256"}]},
    {"name": "decimals", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "uint8"}]},
]

# Only the four TRAIDEAMM functions this package uses, transcribed from
# TRAIDE/contracts/TRAIDEAMM.sol at the bytecode deployed on Arc.
TRAIDE_AMM_ABI = [
    {"name": "swap", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "tokenIn", "type": "address"}, {"name": "tokenOut", "type": "address"},
                {"name": "amountIn", "type": "uint256"}, {"name": "minAmountOut", "type": "uint256"}],
     "outputs": [{"name": "amountOut", "type": "uint256"}]},
    {"name": "addLiquidity", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "tokenA", "type": "address"}, {"name": "tokenB", "type": "address"},
                {"name": "amountA", "type": "uint256"}, {"name": "amountB", "type": "uint256"},
                {"name": "minAmountA", "type": "uint256"}, {"name": "minAmountB", "type": "uint256"}],
     "outputs": [{"name": "shares", "type": "uint256"}]},
    {"name": "getReserves", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "tokenA", "type": "address"}, {"name": "tokenB", "type": "address"}],
     "outputs": [{"name": "reserveA", "type": "uint256"}, {"name": "reserveB", "type": "uint256"}]},
    {"name": "getSwapQuote", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "tokenIn", "type": "address"}, {"name": "tokenOut", "type": "address"},
                {"name": "amountIn", "type": "uint256"}, {"name": "user", "type": "address"}],
     "outputs": [{"name": "amountOut", "type": "uint256"}, {"name": "feeAmount", "type": "uint256"}]},
    {"name": "pairExists", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "", "type": "address"}, {"name": "", "type": "address"}],
     "outputs": [{"name": "", "type": "bool"}]},
]

ANCHOR_ABI = [
    {"name": "attest", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "receiptHash", "type": "bytes32"}, {"name": "agent", "type": "bytes32"}],
     "outputs": []},
    {"name": "total", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "uint256"}]},
    {"name": "attestedAt", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "", "type": "bytes32"}], "outputs": [{"name": "", "type": "uint256"}]},
    {"anonymous": False, "name": "Attested", "type": "event",
     "inputs": [{"indexed": True, "name": "attester", "type": "address"},
                {"indexed": True, "name": "receiptHash", "type": "bytes32"},
                {"indexed": True, "name": "agent", "type": "bytes32"},
                {"indexed": False, "name": "timestamp", "type": "uint256"}]},
]


class ArcClient:
    def __init__(self, rpc_url: str | None = None) -> None:
        self.w3 = Web3(Web3.HTTPProvider(rpc_url or config.rpc_url(), request_kwargs={"timeout": 45}))
        chain_id = self.w3.eth.chain_id
        if chain_id != config.CHAIN_ID:
            raise RuntimeError(f"wrong chain: {chain_id}, expected Arc testnet {config.CHAIN_ID}")
        self.chain_id = chain_id
        self.usdc = self.contract(config.USDC, ERC20_ABI)
        self.link = self.contract(config.LINKMOCK, ERC20_ABI)
        self.amm = self.contract(config.TRAIDE_AMM, TRAIDE_AMM_ABI)

    # ------------------------------------------------------------- primitives

    def contract(self, address: str, abi: list[dict]) -> Any:
        return self.w3.eth.contract(address=Web3.to_checksum_address(address), abi=abi)

    def gas_price(self) -> int:
        price = int(self.w3.eth.gas_price)
        bumped = price * config.GAS_PRICE_BUMP_NUMERATOR // config.GAS_PRICE_BUMP_DENOMINATOR
        return max(bumped, config.MIN_GAS_PRICE_WEI)

    def send(self, account: LocalAccount, tx: dict, label: str) -> dict:
        """
        Sign, send, wait, re-read the receipt, and refuse anything but status 1.
        Returns a record that is safe to publish.
        """
        tx = dict(tx)
        # web3's build_transaction fills EIP-1559 fields. Arc's RPC rejects a
        # transaction that carries both those and gasPrice, so drop them and
        # send a legacy type-0 transaction, which is what the fleet deploy used.
        tx.pop("maxFeePerGas", None)
        tx.pop("maxPriorityFeePerGas", None)
        tx.setdefault("from", account.address)
        tx.setdefault("chainId", self.chain_id)
        tx.setdefault("nonce", self.w3.eth.get_transaction_count(account.address))
        tx.setdefault("gasPrice", self.gas_price())
        if "gas" not in tx:
            estimate = self.w3.eth.estimate_gas(tx)
            tx["gas"] = int(estimate * 13 // 10)
        signed = account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=240)
        # Re-read rather than trusting the object we were handed.
        confirmed = self.w3.eth.get_transaction_receipt(tx_hash)
        if int(confirmed["status"]) != 1:
            raise RuntimeError(f"{label} reverted: {tx_hash.hex()}")
        h = confirmed["transactionHash"].hex()
        if not h.startswith("0x"):
            h = "0x" + h
        return {
            "label": label,
            "hash": h,
            "block": int(confirmed["blockNumber"]),
            "gas_used": int(confirmed["gasUsed"]),
            "effective_gas_price": int(confirmed.get("effectiveGasPrice", receipt.get("effectiveGasPrice", 0))),
            "status": 1,
            "explorer": config.tx_url(h),
        }

    # ---------------------------------------------------------------- reading

    def balances(self, address: str) -> dict[str, int]:
        addr = Web3.to_checksum_address(address)
        return {
            "native_wei_18": int(self.w3.eth.get_balance(addr)),
            "usdc_units_6": int(self.usdc.functions.balanceOf(addr).call()),
            "link_wei_18": int(self.link.functions.balanceOf(addr).call()),
        }

    def reserves(self) -> dict[str, int]:
        a, b = self.amm.functions.getReserves(
            Web3.to_checksum_address(config.USDC), Web3.to_checksum_address(config.LINKMOCK)
        ).call()
        return {"usdc_units_6": int(a), "link_wei_18": int(b)}

    def pool_price_link_per_usdc(self) -> float:
        """LINK per whole USDC, from live reserves. Used for the hold benchmark."""
        r = self.reserves()
        if r["usdc_units_6"] == 0:
            return 0.0
        usdc = r["usdc_units_6"] / 10**config.USDC_DECIMALS
        link = r["link_wei_18"] / 10**config.LINKMOCK_DECIMALS
        return link / usdc if usdc else 0.0

    def quote(self, token_in: str, token_out: str, amount_in: int, user: str) -> int:
        out, _fee = self.amm.functions.getSwapQuote(
            Web3.to_checksum_address(token_in),
            Web3.to_checksum_address(token_out),
            int(amount_in),
            Web3.to_checksum_address(user),
        ).call()
        return int(out)

    # ---------------------------------------------------------------- writing

    def ensure_allowance(self, wallet: AgentWallet, token: str, spender: str, needed: int) -> dict | None:
        token_c = self.contract(token, ERC20_ABI)
        current = int(
            token_c.functions.allowance(
                Web3.to_checksum_address(wallet.address), Web3.to_checksum_address(spender)
            ).call()
        )
        if current >= needed:
            return None
        # Approve a generous but bounded amount so an agent does not pay for an
        # approve on every cycle, and never an unbounded allowance.
        amount = needed * 500
        tx = token_c.functions.approve(
            Web3.to_checksum_address(spender), amount
        ).build_transaction({"from": wallet.address})
        tx.pop("gas", None)
        return self.send(wallet._account, tx, f"approve_{token[:8]}")

    def swap(self, wallet: AgentWallet, token_in: str, token_out: str, amount_in: int, min_out: int) -> dict:
        tx = self.amm.functions.swap(
            Web3.to_checksum_address(token_in),
            Web3.to_checksum_address(token_out),
            int(amount_in),
            int(min_out),
        ).build_transaction({"from": wallet.address})
        tx.pop("gas", None)
        return self.send(wallet._account, tx, "swap")

    def transfer_native(self, account: LocalAccount, to: str, amount_wei_18: int, label: str) -> dict:
        """
        Move Arc's gas token. On Arc the gas token IS USDC, so a plain value
        transfer credits the recipient's gas balance directly. Amount is in the
        18-decimal native view; multiply the 6-decimal USDC view by 10**12.
        """
        tx = {
            "to": Web3.to_checksum_address(to),
            "value": int(amount_wei_18),
            "gas": 21000,
        }
        return self.send(account, tx, label)

    def transfer_erc20(self, account: LocalAccount, token: str, to: str, amount: int, label: str) -> dict:
        token_c = self.contract(token, ERC20_ABI)
        tx = token_c.functions.transfer(
            Web3.to_checksum_address(to), int(amount)
        ).build_transaction({"from": account.address})
        tx.pop("gas", None)
        return self.send(account, tx, label)

    def wait_for_nonce(self, address: str, target: int, timeout: int = 120) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.w3.eth.get_transaction_count(Web3.to_checksum_address(address)) >= target:
                return
            time.sleep(2)
