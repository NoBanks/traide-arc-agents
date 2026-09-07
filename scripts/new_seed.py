"""
new_seed.py - print a fresh BIP-39 mnemonic for the agent wallets.

Run this ONCE, on the operator's own machine, and paste the phrase into the
gitignored dotenv file at the repo root as AGENT_SEED_MNEMONIC. The phrase is
printed to stdout and nowhere else: it is not written to disk, not logged, and
not sent anywhere. Do not run this on a shared screen.

    python3.11 -m scripts.new_seed
"""

from eth_account import Account

Account.enable_unaudited_hdwallet_features()


def main() -> int:
    _acct, mnemonic = Account.create_with_mnemonic(num_words=12)
    print(mnemonic)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
