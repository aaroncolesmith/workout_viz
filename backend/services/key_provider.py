"""
key_provider.py — Master-key custody seam (DATA-2 / Appendix C).

All key material flows through get_master().  Swapping the backing store
(env → KMS) requires changing only this module.

Master key: 32 raw bytes read from DB_ENCRYPTION_MASTER_KEY (hex-encoded env var).
Per-user DEKs: 32 random bytes, stored AES-GCM-wrapped by the master in the
identity DB.  Rotation re-wraps DEK rows without touching per-user DB files.
"""
import os
import hashlib
import secrets
import logging
from functools import lru_cache
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

# 12-byte nonce is the GCM standard; prepended to ciphertext in storage.
_NONCE_LEN = 12


@lru_cache(maxsize=1)
def get_master() -> bytes:
    """
    Return the 32-byte master key.  Cached for the process lifetime.
    Raises at startup if the env var is missing or malformed — fail fast.
    """
    raw = os.environ.get("DB_ENCRYPTION_MASTER_KEY", "")
    if not raw:
        raise RuntimeError(
            "DB_ENCRYPTION_MASTER_KEY is not set. "
            "Generate one with: openssl rand -hex 32"
        )
    try:
        key = bytes.fromhex(raw)
    except ValueError:
        raise RuntimeError("DB_ENCRYPTION_MASTER_KEY must be a hex-encoded string")
    if len(key) != 32:
        raise RuntimeError(
            f"DB_ENCRYPTION_MASTER_KEY must decode to exactly 32 bytes, got {len(key)}"
        )
    return key


def generate_dek() -> bytes:
    """Generate a fresh random 32-byte Data Encryption Key."""
    return secrets.token_bytes(32)


def wrap_dek(dek: bytes, master: Optional[bytes] = None) -> bytes:
    """AES-GCM encrypt dek under the master key.  Returns nonce+ciphertext.

    master defaults to the process master key; the rotation script passes
    an explicit key so old/new envelopes share this exact format.
    """
    master = master if master is not None else get_master()
    nonce = secrets.token_bytes(_NONCE_LEN)
    ct = AESGCM(master).encrypt(nonce, dek, None)
    return nonce + ct


def unwrap_dek(wrapped: bytes, master: Optional[bytes] = None) -> bytes:
    """Decrypt a wrapped DEK produced by wrap_dek()."""
    master = master if master is not None else get_master()
    nonce, ct = wrapped[:_NONCE_LEN], wrapped[_NONCE_LEN:]
    return AESGCM(master).decrypt(nonce, ct, None)


def identity_db_key(master: Optional[bytes] = None) -> bytes:
    """
    Derive the key for the central identity DB directly from the master
    (no per-row DEK needed — there is only one identity DB).
    Uses a fixed label so the derivation is deterministic across restarts.
    """
    master = master if master is not None else get_master()
    return hashlib.blake2b(master, person=b"identity-db\x00\x00\x00\x00\x00", digest_size=32).digest()
