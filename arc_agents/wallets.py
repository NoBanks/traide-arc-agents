"""
wallets.py - deterministic agent wallet derivation.

The three agent wallets are BIP-44 children of one BIP-39 mnemonic held in the
gitignored dotenv file at the repo root. Anyone with that mnemonic reproduces the
exact same three addresses; nobody without it can. The derivation paths are in
config.AGENT_DERIVATION_PATHS and are part of the public record, because a path
is not a secret. The mnemonic and the derived private keys never leave this
module: no function here returns, prints or logs a key, and only addresses cross
the module boundary. Signing happens inside sign_and_send in chain.py, which
takes an AgentWallet and reads its key through a private attribute.
"""

from __future__ import annotations

from dataclasses import dataclass

from eth_account import Account
from eth_account.signers.local import LocalAccount

from . import config

Account.enable_unaudited_hdwallet_features()


@dataclass
class AgentWallet:
    name: str
    address: str
    derivation_path: str
    _account: LocalAccount

    def explorer_url(self) -> str:
        return config.address_url(self.address)

    def public(self) -> dict[str, str]:
        """The only shape that is ever serialized or served."""
        return {
            "name": self.name,
            "address": self.address,
            "derivation_path": self.derivation_path,
            "explorer": self.explorer_url(),
        }


def derive_agents(mnemonic: str | None = None) -> list[AgentWallet]:
    phrase = mnemonic or config.agent_seed_mnemonic()
    wallets: list[AgentWallet] = []
    for name, path in config.AGENT_DERIVATION_PATHS.items():
        acct = Account.from_mnemonic(phrase, account_path=path)
        wallets.append(
            AgentWallet(name=name, address=acct.address, derivation_path=path, _account=acct)
        )
    return wallets


def deployer_account() -> LocalAccount:
    return Account.from_key(config.deployer_private_key())
