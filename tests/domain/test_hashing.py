"""
Tests for HMAC-SHA256 computation and chaining.

These tests prove:
1. HMAC prevents forgery (vendor cannot forge without the key)
2. HMAC chaining detects tampering (edit any event, break all subsequent HMACs)
3. Key validation works (weak keys are rejected)

Run with: pytest tests/domain/test_hashing.py -v
"""

import pytest
from praman.domain.hashing import (
    compute_hmac,
    compute_hmac_hex,
    verify_hmac_chain,
    validate_hmac_key,
)


class TestHMACComputation:
    """Basic HMAC computation tests."""

    def test_hmac_is_deterministic(self):
        """
        Same input + same key → same HMAC, every time.
        """
        key = b"\x00" * 32  # 256-bit key (all zeros, for testing)
        message = b"event_data"

        hmac1 = compute_hmac(message, key)
        hmac2 = compute_hmac(message, key)

        assert hmac1 == hmac2, "HMAC must be deterministic"

    def test_hmac_changes_with_key(self):
        """
        Different key → different HMAC.

        This proves the key matters (HMAC is not just a hash of the message).
        """
        message = b"event_data"
        key1 = b"\x00" * 32
        key2 = b"\x01" * 32

        hmac1 = compute_hmac(message, key1)
        hmac2 = compute_hmac(message, key2)

        assert hmac1 != hmac2, "HMAC must differ with different keys"

    def test_hmac_changes_with_message(self):
        """
        Different message → different HMAC.
        """
        key = b"\x00" * 32
        message1 = b"event_data_1"
        message2 = b"event_data_2"

        hmac1 = compute_hmac(message1, key)
        hmac2 = compute_hmac(message2, key)

        assert hmac1 != hmac2, "HMAC must differ with different messages"

    def test_hmac_is_32_bytes(self):
        """
        HMAC-SHA256 always produces 32 bytes (256 bits).
        """
        key = b"\x00" * 32
        message = b"event_data"

        hmac_result = compute_hmac(message, key)

        assert len(hmac_result) == 32, "HMAC-SHA256 must be 32 bytes"

    def test_hmac_hex_is_64_chars(self):
        """
        compute_hmac_hex() returns 64 hex characters (32 bytes × 2).
        """
        key = b"\x00" * 32
        message = b"event_data"

        hmac_hex = compute_hmac_hex(message, key)

        assert len(hmac_hex) == 64, "HMAC hex must be 64 characters"
        assert all(c in "0123456789abcdef" for c in hmac_hex), "Must be valid hex"


class TestHMACChaining:
    """HMAC chaining tests — proving the chain detects tampering."""

    def test_hmac_chain_includes_previous(self):
        """
        Event 2's HMAC depends on Event 1's HMAC.

        If Event 1 changes, Event 2's HMAC becomes invalid.
        """
        key = b"\x00" * 32
        event1 = b'{"type":"consent"}'
        event2 = b'{"type":"consent_withdraw"}'

        # Event 1 (no chaining, first event)
        hmac1 = compute_hmac(event1, key)

        # Event 2 (chained: includes event1's HMAC in the computation)
        hmac2_chained = compute_hmac(event2, key, previous_hmac=hmac1)

        # Event 2 without chaining (hypothetically)
        hmac2_unchained = compute_hmac(event2, key, previous_hmac=None)

        # The two must be different (proof that chaining affects the HMAC)
        assert hmac2_chained != hmac2_unchained, "Chaining must affect the HMAC"

    def test_tampering_breaks_chain(self):
        """
        Edit Event 1 → Event 1's HMAC changes → Event 2's HMAC is now wrong.

        This is the core security property: tampering is visible throughout the chain.
        """
        key = b"\x00" * 32
        event1_original = b'{"type":"consent"}'
        event1_tampered = b'{"type":"consent_TAMPERED"}'
        event2 = b'{"type":"consent_withdraw"}'

        # Original chain
        hmac1_original = compute_hmac(event1_original, key)
        hmac2_original = compute_hmac(event2, key, previous_hmac=hmac1_original)

        # Tampered chain (Event 1 is modified)
        hmac1_tampered = compute_hmac(event1_tampered, key)
        hmac2_with_original = compute_hmac(
            event2, key, previous_hmac=hmac1_original
        )  # Event 2 still references original
        hmac2_recalculated = compute_hmac(event2, key, previous_hmac=hmac1_tampered)

        # Proof: hmac2_original != hmac2_recalculated (because the chain was broken)
        assert hmac2_original != hmac2_recalculated, "Tampering must break the chain"

    def test_chain_order_matters(self):
        """
        The order of events in the chain matters (HMAC2 includes HMAC1, not vice versa).
        """
        key = b"\x00" * 32
        event1 = b'{"type":"consent"}'
        event2 = b'{"type":"consent_withdraw"}'

        hmac1 = compute_hmac(event1, key)

        # Event 2 chained after Event 1
        hmac2_after_1 = compute_hmac(event2, key, previous_hmac=hmac1)

        # Event 1 (hypothetically) chained after Event 2
        hmac1_after_2 = compute_hmac(event1, key, previous_hmac=hmac2_after_1)

        # These must be different (proof that order affects chaining)
        assert hmac2_after_1 != hmac1_after_2, "Chain order must affect HMACs"


class TestHMACChainVerification:
    """Tests for verify_hmac_chain()."""

    def test_verify_chain_all_valid(self):
        """
        verify_hmac_chain() returns True when all HMACs are correct.
        """
        key = b"\x00" * 32
        event1 = b'{"type":"consent"}'
        event2 = b'{"type":"consent_withdraw"}'

        hmac1_hex = compute_hmac_hex(event1, key)
        hmac2_hex = compute_hmac_hex(event2, key, previous_hmac_hex=hmac1_hex)

        events = [(event1, hmac1_hex), (event2, hmac2_hex)]

        assert verify_hmac_chain(events, key) is True

    def test_verify_chain_detects_tampering(self):
        """
        verify_hmac_chain() returns False if any HMAC is wrong.
        """
        key = b"\x00" * 32
        event1 = b'{"type":"consent"}'
        event2 = b'{"type":"consent_withdraw"}'

        hmac1_hex = compute_hmac_hex(event1, key)
        hmac2_hex = compute_hmac_hex(event2, key, previous_hmac_hex=hmac1_hex)

        # Tamper with Event 2's HMAC
        tampered_hmac2 = "0" * 64  # Wrong HMAC

        events = [(event1, hmac1_hex), (event2, tampered_hmac2)]

        assert verify_hmac_chain(events, key) is False

    def test_verify_chain_empty(self):
        """
        verify_hmac_chain() returns True for an empty chain (no events).
        """
        key = b"\x00" * 32
        events = []

        assert verify_hmac_chain(events, key) is True


class TestKeyValidation:
    """Tests for validate_hmac_key()."""

    def test_valid_key_256_bits(self):
        """
        A 32-byte (256-bit) key is valid.
        """
        key = b"\x00" * 32
        # Should not raise
        validate_hmac_key(key)

    def test_valid_key_larger(self):
        """
        Keys larger than 256 bits are valid (redundant but not harmful).
        """
        key = b"\x00" * 64  # 512 bits
        # Should not raise
        validate_hmac_key(key)

    def test_invalid_key_too_short(self):
        """
        Keys shorter than 32 bytes are rejected.
        """
        key = b"\x00" * 16  # 128 bits (too short)

        with pytest.raises(ValueError, match="at least 32 bytes"):
            validate_hmac_key(key)

    def test_invalid_key_not_bytes(self):
        """
        Non-bytes keys are rejected.
        """
        key = "not_bytes"

        with pytest.raises(TypeError, match="must be bytes"):
            validate_hmac_key(key)

    def test_invalid_key_empty(self):
        """
        Empty keys are rejected.
        """
        key = b""

        with pytest.raises(ValueError, match="at least 32 bytes"):
            validate_hmac_key(key)


class TestIntegration:
    """Integration tests: canonicalisation + HMAC together."""

    def test_hmac_chain_with_real_events(self):
        """
        Full end-to-end: canonicalise events, HMAC them, chain them, verify.
        """
        from praman.domain.canonical import canonicalise

        key = b"\x00" * 32
        event1 = {"type": "consent", "principal_id": "hash:abc123", "action": "data_share"}
        event2 = {"type": "consent_withdrawn", "principal_id": "hash:abc123", "reason": "user_request"}

        canonical1 = canonicalise(event1)
        canonical2 = canonicalise(event2)

        hmac1_hex = compute_hmac_hex(canonical1, key)
        hmac2_hex = compute_hmac_hex(canonical2, key, previous_hmac_hex=hmac1_hex)

        events_to_verify = [(canonical1, hmac1_hex), (canonical2, hmac2_hex)]

        assert verify_hmac_chain(events_to_verify, key) is True

    def test_tampering_detected_end_to_end(self):
        """
        Full end-to-end: tamper with an event, verification fails.
        """
        from praman.domain.canonical import canonicalise

        key = b"\x00" * 32
        event1_original = {"type": "consent", "principal_id": "hash:abc123", "action": "data_share"}
        event2 = {"type": "consent_withdrawn", "principal_id": "hash:abc123"}

        canonical1_original = canonicalise(event1_original)
        canonical2 = canonicalise(event2)

        hmac1_original_hex = compute_hmac_hex(canonical1_original, key)
        hmac2_original_hex = compute_hmac_hex(canonical2, key, previous_hmac_hex=hmac1_original_hex)

        # Tamper with event 1
        event1_tampered = {"type": "consent", "principal_id": "hash:abc123", "action": "TAMPERED"}
        canonical1_tampered = canonicalise(event1_tampered)
        hmac1_tampered_hex = compute_hmac_hex(canonical1_tampered, key)

        # Event 2's HMAC would now be different if we recalculated it
        hmac2_new = compute_hmac_hex(canonical2, key, previous_hmac_hex=hmac1_tampered_hex)

        # But we kept the original hmac2, so verification fails
        tampered_events = [(canonical1_tampered, hmac1_tampered_hex), (canonical2, hmac2_original_hex)]

        assert verify_hmac_chain(tampered_events, key) is False
