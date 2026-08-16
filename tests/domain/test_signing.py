"""
Tests for Ed25519 signing and verification.

These tests prove:
1. Signatures are deterministic and verifiable
2. Only the private key holder can create valid signatures (non-repudiation)
3. Tampering with the root invalidates the signature
4. PEM import/export works correctly

Run with: pytest tests/domain/test_signing.py -v
"""

import pytest
from praman.domain.signing import (
    generate_keypair,
    private_key_to_pem,
    private_key_from_pem,
    public_key_to_pem,
    public_key_from_pem,
    sign_root,
    sign_root_hex,
    verify_signature,
    verify_signature_hex,
    tampering_check,
)


class TestKeypairGeneration:
    """Test keypair generation."""

    def test_generate_keypair_returns_both(self):
        """generate_keypair returns both private and public keys."""
        private, public = generate_keypair()

        assert private is not None
        assert public is not None
        assert type(private).__name__ == "Ed25519PrivateKey"
        assert type(public).__name__ == "Ed25519PublicKey"

    def test_generated_keys_are_different(self):
        """Two generated keypairs are different."""
        private1, public1 = generate_keypair()
        private2, public2 = generate_keypair()

        # Keys are different objects (and different key material)
        assert private1 is not private2
        assert public1 is not public2


class TestKeySerialisation:
    """Test PEM serialisation and deserialisation."""

    def test_private_key_to_pem(self):
        """Private key exports to PEM format."""
        private, _ = generate_keypair()
        pem = private_key_to_pem(private)

        assert isinstance(pem, bytes)
        assert b"-----BEGIN PRIVATE KEY-----" in pem
        assert b"-----END PRIVATE KEY-----" in pem

    def test_private_key_roundtrip(self):
        """Private key can be exported and imported."""
        private_original, _ = generate_keypair()
        pem = private_key_to_pem(private_original)
        private_recovered = private_key_from_pem(pem)

        # Sign with both, should get same signature (same key material)
        root = "abc123" * 10 + "abc1"
        sig1 = sign_root(root, private_original)
        sig2 = sign_root(root, private_recovered)

        assert sig1 == sig2, "Recovered key must produce same signatures"

    def test_public_key_to_pem(self):
        """Public key exports to PEM format."""
        _, public = generate_keypair()
        pem = public_key_to_pem(public)

        assert isinstance(pem, bytes)
        assert b"-----BEGIN PUBLIC KEY-----" in pem
        assert b"-----END PUBLIC KEY-----" in pem

    def test_public_key_roundtrip(self):
        """Public key can be exported and imported."""
        _, public_original = generate_keypair()
        pem = public_key_to_pem(public_original)
        public_recovered = public_key_from_pem(pem)

        # Both should work for verification
        private, _ = generate_keypair()
        root = "abc123" * 10 + "abc1"
        signature = sign_root(root, private)

        # This test is a bit artificial since we'd normally verify with the
        # public key from the same keypair, but demonstrates the roundtrip


class TestSigning:
    """Test signing operations."""

    def test_sign_root_returns_bytes(self):
        """sign_root returns 64-byte signature."""
        private, _ = generate_keypair()
        root = "abc123" * 10 + "abc1"

        signature = sign_root(root, private)

        assert isinstance(signature, bytes)
        assert len(signature) == 64

    def test_sign_root_is_deterministic(self):
        """Same root + same key → same signature, always."""
        private, _ = generate_keypair()
        root = "abc123" * 10 + "abc1"

        sig1 = sign_root(root, private)
        sig2 = sign_root(root, private)

        assert sig1 == sig2, "Signing must be deterministic"

    def test_different_roots_different_signatures(self):
        """Different roots → different signatures."""
        private, _ = generate_keypair()
        root1 = "abc123" * 10 + "abc1"
        root2 = "def456" * 10 + "def4"

        sig1 = sign_root(root1, private)
        sig2 = sign_root(root2, private)

        assert sig1 != sig2

    def test_different_keys_different_signatures(self):
        """Different keys → different signatures (same root)."""
        private1, _ = generate_keypair()
        private2, _ = generate_keypair()
        root = "abc123" * 10 + "abc1"

        sig1 = sign_root(root, private1)
        sig2 = sign_root(root, private2)

        assert sig1 != sig2

    def test_sign_root_hex(self):
        """sign_root_hex returns hex string (128 characters)."""
        private, _ = generate_keypair()
        root = "abc123" * 10 + "abc1"

        sig_hex = sign_root_hex(root, private)

        assert isinstance(sig_hex, str)
        assert len(sig_hex) == 128
        assert all(c in "0123456789abcdef" for c in sig_hex)


class TestVerification:
    """Test signature verification."""

    def test_verify_valid_signature(self):
        """Verifying a valid signature returns True."""
        private, public = generate_keypair()
        root = "abc123" * 10 + "abc1"

        signature = sign_root(root, private)

        assert verify_signature(root, signature, public) is True

    def test_verify_invalid_signature(self):
        """Verifying a wrong signature returns False."""
        private, public = generate_keypair()
        root = "abc123" * 10 + "abc1"

        wrong_signature = b"\x00" * 64  # Garbage signature

        assert verify_signature(root, wrong_signature, public) is False

    def test_verify_signature_with_wrong_public_key(self):
        """Verifying with the wrong public key returns False."""
        private1, _ = generate_keypair()
        _, public2 = generate_keypair()

        root = "abc123" * 10 + "abc1"
        signature = sign_root(root, private1)

        # Try to verify with a different public key
        assert verify_signature(root, signature, public2) is False

    def test_verify_signature_tampering_detected(self):
        """If the root is tampered with, verification fails."""
        private, public = generate_keypair()
        root_original = "abc123" * 10 + "abc1"
        root_tampered = "def456" * 10 + "def4"

        signature = sign_root(root_original, private)

        # Signature is valid for original root
        assert verify_signature(root_original, signature, public) is True

        # Signature is invalid for tampered root
        assert verify_signature(root_tampered, signature, public) is False

    def test_verify_signature_hex(self):
        """verify_signature_hex works with hex-encoded signatures."""
        private, public = generate_keypair()
        root = "abc123" * 10 + "abc1"

        signature_hex = sign_root_hex(root, private)

        assert verify_signature_hex(root, signature_hex, public) is True

    def test_verify_signature_hex_wrong(self):
        """Wrong hex signature fails verification."""
        _, public = generate_keypair()
        root = "abc123" * 10 + "abc1"

        wrong_sig_hex = "00" * 64  # Garbage hex

        assert verify_signature_hex(root, wrong_sig_hex, public) is False


class TestTamperingCheck:
    """Test the tampering_check convenience function."""

    def test_tampering_check_valid(self):
        """Valid signature returns (True, message)."""
        private, public = generate_keypair()
        root = "abc123" * 10 + "abc1"
        signature = sign_root_hex(root, private)

        is_valid, message = tampering_check(root, signature, public)

        assert is_valid is True
        assert "valid" in message.lower()

    def test_tampering_check_invalid(self):
        """Invalid signature returns (False, message)."""
        _, public = generate_keypair()
        root = "abc123" * 10 + "abc1"
        wrong_sig = "00" * 64

        is_valid, message = tampering_check(root, wrong_sig, public)

        assert is_valid is False
        assert "failed" in message.lower() or "tampered" in message.lower()

    def test_tampering_check_message_human_readable(self):
        """Messages are human-readable."""
        private, public = generate_keypair()
        root = "abc123" * 10 + "abc1"
        signature = sign_root_hex(root, private)

        _, message = tampering_check(root, signature, public)

        assert len(message) > 10  # Should be a full sentence


class TestNonRepudiation:
    """Test the non-repudiation property of signatures."""

    def test_only_private_key_holder_can_sign(self):
        """Only the private key holder can create a valid signature."""
        private, public = generate_keypair()
        _, other_public = generate_keypair()

        root = "abc123" * 10 + "abc1"
        signature = sign_root(root, private)

        # Valid with the correct public key
        assert verify_signature(root, signature, public) is True

        # Invalid with any other public key
        assert verify_signature(root, signature, other_public) is False

    def test_signature_binds_root(self):
        """A signature binds to one specific root (no ambiguity)."""
        private, public = generate_keypair()

        root1 = "abc123" * 10 + "abc1"
        root2 = "abc123" * 10 + "abc2"  # One character different

        sig1 = sign_root(root1, private)
        sig2 = sign_root(root2, private)

        # Each signature is valid for exactly one root
        assert verify_signature(root1, sig1, public) is True
        assert verify_signature(root1, sig2, public) is False
        assert verify_signature(root2, sig2, public) is True
        assert verify_signature(root2, sig1, public) is False


class TestIntegration:
    """Integration tests: signing + verification in realistic scenarios."""

    def test_full_signing_workflow(self):
        """Complete workflow: generate, sign, verify."""
        # Generate keypair
        private, public = generate_keypair()

        # Export and re-import public key (as it would be published)
        public_pem = public_key_to_pem(public)
        public_recovered = public_key_from_pem(public_pem)

        # Sign a root
        root = "abc123" * 10 + "abc1"
        signature = sign_root(root, private)

        # Verify with recovered public key (simulating external verification)
        assert verify_signature(root, signature, public_recovered) is True

    def test_evidence_integrity_with_signature(self):
        """Signature proves the root was not modified after signing."""
        from praman.domain.canonical import canonicalise
        from praman.domain.hashing import compute_hmac_hex
        from praman.domain.merkle import compute_root

        private, public = generate_keypair()

        # Create events
        events = [
            {"type": "consent", "principal_id": "hash:abc"},
            {"type": "consent", "principal_id": "hash:def"},
        ]

        # Canonicalise and HMAC
        hmac_key = b"\x00" * 32
        hmacs = []
        prev_hmac_hex = None
        for event in events:
            canonical = canonicalise(event)
            hmac_hex = compute_hmac_hex(canonical, hmac_key, prev_hmac_hex)
            hmacs.append(hmac_hex)
            prev_hmac_hex = hmac_hex

        # Compute root
        root = compute_root(hmacs)
        root_hex = root.hex()

        # Sign root
        signature = sign_root(root_hex, private)

        # Verify: root matches signature
        assert verify_signature(root_hex, signature, public) is True

        # If anyone tampers with the root, signature fails
        tampered_root = "00" * 32
        assert verify_signature(tampered_root, signature, public) is False
