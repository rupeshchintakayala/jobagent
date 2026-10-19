"""BYOK key vault: Fernet encryption at rest. Master key comes from env JOBAGENT_MASTER_KEY."""
from __future__ import annotations
import os
from cryptography.fernet import Fernet, InvalidToken


class KeyVaultError(Exception): ...


class KeyVault:
    def __init__(self, master_key: str | bytes | None = None):
        mk = master_key or os.environ.get("JOBAGENT_MASTER_KEY")
        if not mk:
            raise KeyVaultError("JOBAGENT_MASTER_KEY is not set. Generate one with KeyVault.generate_master_key().")
        try:
            self._f = Fernet(mk if isinstance(mk, bytes) else mk.encode())
        except Exception:
            raise KeyVaultError("Invalid master key format") from None

    @staticmethod
    def generate_master_key() -> str:
        return Fernet.generate_key().decode()

    def encrypt(self, api_key: str) -> bytes:
        return self._f.encrypt(api_key.encode())

    def decrypt(self, token: bytes) -> str:
        try:
            return self._f.decrypt(token).decode()
        except InvalidToken:
            raise KeyVaultError("Cannot decrypt key (wrong master key or corrupted data)") from None


def mask(api_key: str) -> str:
    """Safe display form for logs/UI."""
    return "****" + api_key[-4:] if len(api_key) > 8 else "****"
