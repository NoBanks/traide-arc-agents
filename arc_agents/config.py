"""
config.py - every constant this package needs, and the env loading rules.

Chain facts here were read live from https://rpc.testnet.arc.io on 2026-09-07 and
are recorded in ETHONLINE_2026_BUILD_LOG.md. Nothing in this file is a guess.

Secrets are read from the process environment only. This module never prints,
logs or returns a private key or an API key. It only reports whether one is set.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
RECEIPTS_PATH = DATA_DIR / "receipts.jsonl"
STATE_PATH = DATA_DIR / "state.json"
DEPLOYMENT_PATH = REPO_ROOT / "deployments" / "arc-5042002.json"

# ---------------------------------------------------------------- network select

# ARC_NETWORK=mainnet switches every chain-specific value below to Arc mainnet.
# Unset (or "testnet") keeps the original testnet values byte for byte, so the
# testnet runner and its receipt history are untouched.
NETWORK = os.environ.get("ARC_NETWORK", "testnet").strip().lower()
IS_MAINNET = NETWORK == "mainnet"

# ---------------------------------------------------------------- Arc testnet

CHAIN_ID = 5042002
DEFAULT_RPC_URL = "https://rpc.testnet.arc.io"
EXPLORER_BASE = "https://testnet.arcscan.app"
NETWORK_LABEL = "Arc testnet"

# Arc's gas token is USDC. 0x3600...0000 is the same balance exposed as an
# ERC-20 with decimals() == 6, while eth_getBalance reports it at 18 decimals.
# Both readings are correct; they differ by exactly 10**12.
USDC = "0x3600000000000000000000000000000000000000"
USDC_DECIMALS = 6
NATIVE_TO_ERC20_SCALE = 10**12

# TRAIDE fleet on Arc, CREATE2 salts V1, all 11 source-verified on Blockscout.
TRAIDE_AMM = "0x4b6781AfC7e91D65acdD37a424D7A43f170f9120"
TRAIDE_FACTORY = "0xC1b443bDD37128ceB15e9b6F2c4DD3284e92259f"
TRAIDE_ROUTER = "0xa0e3D89F2e5e45D4AA9d22568F05a32b1e0f1624"
TRAIDE_TOKEN = "0x341936d89E1182c52440351B7AA1070001CEeb99"

# The second leg of the live pair. A LINKMock deployed by the fleet deployer on
# 2026-09-07, 18 decimals. The fleet's own TRAIDEToken could not be used because
# it was deployed through the stateless CREATE2 proxy, so the proxy holds the
# whole supply and cannot move it.
LINKMOCK = "0x4A8ac01265a030Aad32fb9B7bD5f89Be18f21858"
LINKMOCK_DECIMALS = 18

# Swaps run through TRAIDEAMM, not the Factory/Router/Pair path. TRAIDEPair
# cannot take first liquidity under OpenZeppelin 5, because TRAIDEPair.sol:126
# mints MINIMUM_LIQUIDITY to address(0) and OZ 5 reverts ERC20InvalidReceiver.
# TRAIDEAMM keeps LP shares in its own mapping and never touches address(0).
SWAP_VENUE = "TRAIDEAMM"

# Arc's mempool enforces a 20 gwei maxFeePerGas floor. Observed base price 25 gwei.
MIN_GAS_PRICE_WEI = 20_000_000_000
GAS_PRICE_BUMP_NUMERATOR = 12
GAS_PRICE_BUMP_DENOMINATOR = 10

# ------------------------------------------------------------------ The Graph

# Token API, run by Pinax under The Graph brand. Base URL and paths were read
# from the live OpenAPI document at https://api.pinax.network/openapi on
# 2026-09-07 (spec version 3.21.1). They are not guessed.
GRAPH_TOKEN_API_BASE = "https://api.pinax.network"
GRAPH_PATH_DEXES = "/v1/evm/dexes"          # no security block in the spec: keyless
GRAPH_PATH_POOLS = "/v1/evm/pools"          # bearerAuth
GRAPH_PATH_OHLC = "/v1/evm/pools/ohlc"      # bearerAuth
GRAPH_PATH_SWAPS = "/v1/evm/swaps"          # bearerAuth
GRAPH_PATH_NETWORKS = "/v1/networks"        # keyless

# The Graph decentralized network gateway, for the Subgraph tier.
GRAPH_GATEWAY_BASE = "https://gateway.thegraph.com/api"

# Reference market. Base is one of the networks the Token API indexes, per the
# live /v1/networks response. The reference pool is NOT hardcoded: it is
# discovered at runtime from live Graph data (keyless /v1/evm/dexes gives the
# busiest Uniswap v3 factory on Base, then /v1/evm/pools enumerates its pools),
# so no pool address in this repo is a guess. An operator may pin one with the
# GRAPH_REFERENCE_POOL env var.
GRAPH_NETWORK = "base"
GRAPH_REFERENCE_PROTOCOL = "uniswap_v3"
GRAPH_OHLC_INTERVAL = "1h"
GRAPH_OHLC_LIMIT = 24
GRAPH_POOL_CACHE_PATH = DATA_DIR / "graph_reference_pool.json"
SUBGRAPH_CACHE_PATH = DATA_DIR / "graph_subgraph_target.json"

GRAPH_TIMEOUT_SECONDS = 15

# --------------------------------------------------------------- agent wallets

# BIP-44 Ethereum path. Index 0 is reserved so an operator can keep a spare;
# the three agents take indices 1, 2 and 3. Derivation is fully deterministic
# from AGENT_SEED_MNEMONIC, which lives only in the gitignored dotenv file.
AGENT_DERIVATION_PATHS = {
    "PASSIVE": "m/44'/60'/0'/0/1",
    "AGGRESSIVE": "m/44'/60'/0'/0/2",
    "REBALANCE": "m/44'/60'/0'/0/3",
}
AGENT_NAMES = list(AGENT_DERIVATION_PATHS)

# Funding per agent, in the 6-decimal USDC view.
AGENT_FUND_USDC_UNITS = 1_000_000          # 1.0 USDC
AGENT_FUND_LINK_WEI = 2_000 * 10**18       # 2000 LINKMock, about 0.24 USDC at the
                                           # pool rate, so an agent's sell side stays
                                           # small against a 2 USDC deep pool
DEPLOYER_FLOOR_USDC_UNITS = 10_000_000     # never draw the deployer below 10 USDC

# Per-swap sizing, deliberately tiny so the pool and the gas budget outlast judging.
SWAP_MIN_USDC_UNITS = 1_000                # 0.001 USDC
SWAP_MAX_USDC_UNITS = 10_000               # 0.010 USDC

# Production cadence. At 300 seconds a full day is 288 cycles, which at roughly
# 0.0025 USDC of gas per transaction keeps the agents inside their funding for
# the whole judging window. The burn-in run used --interval 60.
CYCLE_SECONDS = int(os.environ.get("ARC_AGENT_CYCLE_SECONDS", "300"))

# ---------------------------------------------------------------- Arc mainnet
#
# Values read live on 2026-09-26 from https://docs.arc.io/arc/references/connect-to-arc.md
# and contract-addresses.md, then confirmed on chain: eth_chainId = 0x13b2 (5042),
# eth_gasPrice = 20 gwei, and 69 bytes of code at the canonical CREATE2 proxy.
#
# The second leg of the pool is Circle's EURC (6 decimals), a real asset, not a mock.
# The LINKMOCK / LINK names are kept as internal identifiers so the testnet code path
# does not change; on mainnet they hold the EURC address and decimals, and every
# human-facing label (actions, dashboard) reads SECOND_SYMBOL instead.
SECOND_SYMBOL = "LINK"

if IS_MAINNET:
    CHAIN_ID = 5042
    DEFAULT_RPC_URL = "https://rpc.mainnet.arc.io"
    EXPLORER_BASE = "https://explorer.arc.io"
    NETWORK_LABEL = "Arc mainnet"
    DATA_DIR = REPO_ROOT / "data-mainnet"
    RECEIPTS_PATH = DATA_DIR / "receipts.jsonl"
    STATE_PATH = DATA_DIR / "state.json"
    DEPLOYMENT_PATH = REPO_ROOT / "deployments" / "arc-5042.json"
    GRAPH_POOL_CACHE_PATH = DATA_DIR / "graph_reference_pool.json"
    SUBGRAPH_CACHE_PATH = DATA_DIR / "graph_subgraph_target.json"
    LINKMOCK = "0xbEf5f6d51CB62b58e6A8f77868681825C6fe21c1"   # EURC on Arc mainnet
    LINKMOCK_DECIMALS = 6
    SECOND_SYMBOL = "EURC"
    # Mainnet gas is real money: smaller funding, lower floor, slower cadence.
    AGENT_FUND_USDC_UNITS = 1_000_000          # 1.0 USDC per agent
    AGENT_FUND_LINK_WEI = 290_000              # 0.29 EURC per agent
    DEPLOYER_FLOOR_USDC_UNITS = 1_000_000      # never draw the deployer below 1 USDC
    CYCLE_SECONDS = int(os.environ.get("ARC_AGENT_CYCLE_SECONDS", "1800"))

BUY_ACTION = f"BUY_{SECOND_SYMBOL}"
SELL_ACTION = f"SELL_{SECOND_SYMBOL}"

# ------------------------------------------------------------------- env reads


def rpc_url() -> str:
    if IS_MAINNET:
        return os.environ.get("ARC_MAINNET_RPC_URL", DEFAULT_RPC_URL)
    return os.environ.get("ARC_RPC_URL", DEFAULT_RPC_URL)


def dashboard_port() -> int:
    return int(os.environ.get("DASHBOARD_PORT", "17360"))


def graph_api_key() -> str:
    """Token API bearer JWT, or empty string. The value is never logged."""
    return os.environ.get("GRAPH_API_KEY", "").strip()


def graph_gateway_api_key() -> str:
    return os.environ.get("GRAPH_GATEWAY_API_KEY", "").strip()


def graph_reference_pool_override() -> str:
    return os.environ.get("GRAPH_REFERENCE_POOL", "").strip().lower()


def subgraph_id_override() -> str:
    """Pin a specific subgraph instead of letting the resolver probe candidates."""
    return os.environ.get("GRAPH_SUBGRAPH_ID", "").strip()


def graph_allow_keyless() -> bool:
    """
    The keyless activity tier is on by default because /v1/evm/dexes was verified
    live and carries no security block in the Token API OpenAPI spec. Setting
    GRAPH_ALLOW_KEYLESS=0 turns it off, which is how the no-key refusal path is
    demonstrated end to end.
    """
    return os.environ.get("GRAPH_ALLOW_KEYLESS", "1").strip() not in ("0", "false", "no")


def deployer_private_key() -> str:
    key = os.environ.get("ARC_DEPLOYER_PRIVATE_KEY", "").strip()
    if not key:
        raise EnvironmentError(
            "ARC_DEPLOYER_PRIVATE_KEY is not set. Put it in the gitignored dotenv "
            "file at the repo root. See .env.example."
        )
    return key


def agent_seed_mnemonic() -> str:
    seed = os.environ.get("AGENT_SEED_MNEMONIC", "").strip()
    if not seed:
        raise EnvironmentError(
            "AGENT_SEED_MNEMONIC is not set. Generate one with "
            "python3.11 -m scripts.new_seed and store it in the gitignored "
            "dotenv file at the repo root."
        )
    return seed


def load_dotenv(path: Path | None = None) -> None:
    """
    Minimal dotenv loader. Reads KEY=VALUE lines into os.environ without
    overwriting anything already set. Values are never echoed.
    """
    target = path or (REPO_ROOT / ".env")
    if not target.exists():
        return
    for raw in target.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value


def tx_url(tx_hash: str) -> str:
    return f"{EXPLORER_BASE}/tx/{tx_hash}"


def address_url(address: str) -> str:
    return f"{EXPLORER_BASE}/address/{address}"
