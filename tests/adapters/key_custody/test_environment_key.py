"""
Tests for EnvironmentKeyCustody.

These tests prove the central claim of ADR 0014: the signing key is
stable across calls, and misconfiguration fails loudly rather than
silently substituting a throwaway key.

Run with: pytest tests/adapters/key_custody/test_environment_key.py -v
"""

import base64

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from praman.adapters.key_custody.environment_key import (
    ConfigurationError,
    EnvironmentKeyCustody,
)
from praman.domain.signing import sign_root_hex, verify_signature_hex


def _make_key_pem_base64() -> str:
    """Generate a fresh Ed25519 key, PEM+base64-encoded, as the env var would hold it."""
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return base64.b64encode(pem).decode()


class TestSigningKeyIsStable:
    """The regression guard for the bug ADR 0014 fixes."""

    def test_signing_key_is_stable_across_calls(self):
        """
        Two calls to signing_key() on the same instance return a key that
        produces identical signatures for identical input.

        This is the load-bearing test: before this fix, every call to the
        certificate endpoints generated a fresh keypair, so no two
        signatures over the same root were ever equal and no public key
        was ever published to check them against.
        """
        custody = EnvironmentKeyCustody(_make_key_pem_base64())
        root_hex = "ab" * 32

        sig1 = sign_root_hex(root_hex, custody.signing_key())
        sig2 = sign_root_hex(root_hex, custody.signing_key())

        assert sig1 == sig2, "Same key signing the same root must produce the same signature"

    def test_public_key_verifies_signature_from_signing_key(self):
        """The published public key actually verifies signatures from this custody's key."""
        custody = EnvironmentKeyCustody(_make_key_pem_base64())
        root_hex = "cd" * 32

        signature_hex = sign_root_hex(root_hex, custody.signing_key())

        assert verify_signature_hex(root_hex, signature_hex, custody.signing_key().public_key())

    def test_key_id_is_stable_across_calls(self):
        """key_id() returns the same value every call (not recomputed per call)."""
        custody = EnvironmentKeyCustody(_make_key_pem_base64())

        assert custody.key_id() == custody.key_id()

    def test_key_id_is_16_hex_characters(self):
        """key_id is exactly 16 hex characters (first 16 of a SHA-256 hexdigest)."""
        custody = EnvironmentKeyCustody(_make_key_pem_base64())
        key_id = custody.key_id()

        assert len(key_id) == 16
        assert all(c in "0123456789abcdef" for c in key_id)

    def test_different_keys_produce_different_key_ids(self):
        """Two different keys must not collide on key_id (sanity check, not a security proof)."""
        custody_a = EnvironmentKeyCustody(_make_key_pem_base64())
        custody_b = EnvironmentKeyCustody(_make_key_pem_base64())

        assert custody_a.key_id() != custody_b.key_id()


class TestFailsLoudlyOnMisconfiguration:
    """
    Missing or malformed configuration must raise, never fall back to a
    silently generated throwaway key — that would reproduce the exact bug
    this adapter exists to prevent, just triggered by misconfiguration
    instead of per-call generation.
    """

    def test_empty_key_raises_configuration_error(self):
        with pytest.raises(ConfigurationError):
            EnvironmentKeyCustody("")

    def test_none_key_raises_configuration_error(self):
        with pytest.raises(ConfigurationError):
            EnvironmentKeyCustody(None)

    def test_invalid_base64_raises_configuration_error(self):
        with pytest.raises(ConfigurationError):
            EnvironmentKeyCustody("not valid base64 !!! @@@")

    def test_valid_base64_but_not_pem_raises_configuration_error(self):
        garbage = base64.b64encode(b"this is not a PEM file").decode()

        with pytest.raises(ConfigurationError):
            EnvironmentKeyCustody(garbage)

    def test_rsa_key_raises_configuration_error(self):
        """A syntactically valid PEM private key that isn't Ed25519 must still be rejected."""
        from cryptography.hazmat.primitives.asymmetric import rsa

        rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = rsa_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        encoded = base64.b64encode(pem).decode()

        with pytest.raises(ConfigurationError):
            EnvironmentKeyCustody(encoded)


class TestPublicKeyPem:
    """The published public key material is well-formed."""

    def test_public_key_pem_is_pem_encoded(self):
        custody = EnvironmentKeyCustody(_make_key_pem_base64())

        assert custody.public_key_pem().startswith(b"-----BEGIN PUBLIC KEY-----")

    def test_public_key_pem_is_stable_across_calls(self):
        custody = EnvironmentKeyCustody(_make_key_pem_base64())

        assert custody.public_key_pem() == custody.public_key_pem()
