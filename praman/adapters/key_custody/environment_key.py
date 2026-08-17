"""
Ed25519 key custody backed by a single environment variable.

Responsibility
    Load one stable Ed25519 private key at construction time and hold it
    for the life of the process.

Must not
    Generate a key if one is missing or malformed (see "Why fail loudly"
    below). Re-read the environment on every call — the key is loaded
    once, in __init__, and never again.

Why fail loudly
    The bug this whole port exists to fix (see ADR 0013) was
    certificates.py calling generate_keypair() per request: every
    signature verified against a public key nobody had, because a fresh
    key was thrown away after each call. Silently falling back to a
    freshly generated key on missing configuration would reproduce that
    exact bug under a different trigger (misconfiguration instead of
    per-call generation) with the same result — signatures nobody can
    check. A demo that signs with a key nobody can verify is worse than a
    demo that visibly refuses to start, because the first one looks like
    it is proving something and is not.

Production note
    This adapter is a legitimate choice for a demo or a customer who
    accepts environment-variable key storage. It is not what a bank's
    security team will sign off on for real evidentiary signing — see
    adapters/key_custody/hsm_kms.py for the documented alternative.
"""

import base64
import hashlib

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from praman.domain.signing import private_key_from_pem, public_key_to_pem


class ConfigurationError(Exception):
    """Raised when required configuration is missing or malformed.

    Deliberately not a ValueError: a missing env var is an operator
    mistake, not a caller passing a bad argument, and the two should be
    catchable separately by anything that wraps this adapter.
    """


class EnvironmentKeyCustody:
    """
    Loads an Ed25519 private key from a base64-encoded PEM environment
    variable, once, at construction.

    Implements the KeyCustody protocol (ports/key_custody.py).
    """

    def __init__(self, private_key_pem_base64: str) -> None:
        """
        Decode and load the signing key immediately.

        Loading here — not lazily on first use — means a misconfigured
        deployment fails at startup, not on the first certificate request
        a customer happens to make.

        Args:
            private_key_pem_base64: The Ed25519 private key, PEM-encoded,
                then base64-encoded so it survives being passed through an
                environment variable without newline-mangling.

        Raises:
            ConfigurationError: If the value is empty, not valid base64,
                or the decoded PEM does not parse as an Ed25519 private key.
        """
        if not private_key_pem_base64:
            raise ConfigurationError(
                "ED25519_PRIVATE_KEY_PEM is not set. Generate one with "
                "`python -c \"from cryptography.hazmat.primitives.asymmetric.ed25519 "
                "import Ed25519PrivateKey; from cryptography.hazmat.primitives import "
                "serialization; import base64; k = Ed25519PrivateKey.generate(); "
                "print(base64.b64encode(k.private_bytes(serialization.Encoding.PEM, "
                "serialization.PrivateFormat.PKCS8, serialization.NoEncryption())).decode())\"` "
                "and set the output as ED25519_PRIVATE_KEY_PEM. See docs/DEPLOYMENT.md."
            )

        try:
            pem_bytes = base64.b64decode(private_key_pem_base64, validate=True)
        except Exception as exc:
            raise ConfigurationError(
                f"ED25519_PRIVATE_KEY_PEM is not valid base64: {exc}"
            ) from exc

        try:
            key = private_key_from_pem(pem_bytes)
        except Exception as exc:
            raise ConfigurationError(
                f"ED25519_PRIVATE_KEY_PEM did not decode to a valid PEM private key: {exc}"
            ) from exc

        if not isinstance(key, Ed25519PrivateKey):
            raise ConfigurationError(
                f"ED25519_PRIVATE_KEY_PEM decoded to {type(key).__name__}, "
                "not an Ed25519 private key."
            )

        self._key = key
        self._public_key_pem = public_key_to_pem(key.public_key())
        self._key_id = self._compute_key_id(key)

    def signing_key(self) -> Ed25519PrivateKey:
        """Return the key loaded at construction. Same object, every call."""
        return self._key

    def public_key_pem(self) -> bytes:
        """Return the PEM-encoded public key, computed once at construction."""
        return self._public_key_pem

    def key_id(self) -> str:
        """Return the stable id computed at construction."""
        return self._key_id

    @staticmethod
    def _compute_key_id(key: Ed25519PrivateKey) -> str:
        """
        First 16 hex chars of SHA-256 over the public key's DER encoding.

        DER (not PEM) because DER has no formatting variance — PEM line
        wrapping or header casing could theoretically differ between
        encoders without the key itself differing, which would make the
        id less stable than the key it identifies.
        """
        public_der = key.public_key().public_bytes(
            encoding=Encoding.DER,
            format=PublicFormat.SubjectPublicKeyInfo,
        )
        return hashlib.sha256(public_der).hexdigest()[:16]
