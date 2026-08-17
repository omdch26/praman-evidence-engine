"""
Tests for domain/verification.py.

These tests prove the central claims of Layer 3: an independently
recomputed root matches what the server claims, a signature verifies
against a LOCALLY recomputed root (not the server's claimed one), and
tampering any event is detected with the correct divergent sequence
number named.

Run with: pytest tests/domain/test_verification.py -v
"""

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from praman.domain.canonical import canonicalise
from praman.domain.hashing import compute_hmac_hex
from praman.domain.merkle import compute_root_hex
from praman.domain.signing import sign_root_hex
from praman.domain.verification import (
    recompute_root_from_bundle,
    verify_bundle,
    verify_bundle_signature,
    verify_hmac_chain_continuity,
)

_HMAC_KEY = b"\x00" * 32


def _build_test_bundle(event_payloads: list[dict], private_key: Ed25519PrivateKey) -> dict:
    """Build a bundle exactly the way evidence_service.py does, for testing."""
    events = []
    previous_hmac_hex = None

    for index, payload in enumerate(event_payloads):
        canonical_bytes = canonicalise(payload)
        hmac_hex = compute_hmac_hex(canonical_bytes, _HMAC_KEY, previous_hmac_hex)
        events.append(
            {
                "sequence": index,
                "canonical_json": canonical_bytes.decode("utf-8"),
                "hmac_value": hmac_hex,
            }
        )
        previous_hmac_hex = hmac_hex

    hmac_values = [e["hmac_value"] for e in events]
    root_hex = compute_root_hex(hmac_values)
    signature_hex = sign_root_hex(root_hex, private_key)

    return {"events": events, "merkle_root": root_hex, "signature": signature_hex}


class TestIndependentlyRecomputedRootMatchesServerRoot:
    def test_independently_recomputed_root_matches_server_root(self):
        """
        The core claim: recomputing the root from nothing but the bundle's
        event data produces the exact same root the server claimed.
        """
        private_key = Ed25519PrivateKey.generate()
        payloads = [{"seq": i, "event": f"event_{i}"} for i in range(5)]
        bundle = _build_test_bundle(payloads, private_key)

        recomputed_root = recompute_root_from_bundle(bundle["events"])

        assert recomputed_root.hex() == bundle["merkle_root"]


class TestSignatureVerifiesAgainstPublishedPublicKey:
    def test_signature_verifies_against_published_public_key(self):
        """The signature verifies against the LOCALLY recomputed root, not the bundle's claimed root."""
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        payloads = [{"seq": i, "event": f"event_{i}"} for i in range(3)]
        bundle = _build_test_bundle(payloads, private_key)

        recomputed_root = recompute_root_from_bundle(bundle["events"])

        assert verify_bundle_signature(recomputed_root, bundle["signature"], public_key) is True

    def test_signature_fails_when_any_event_is_altered(self):
        """
        Altering one event's hmac_value changes the recomputed root, which
        the original signature no longer matches.
        """
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        payloads = [{"seq": i, "event": f"event_{i}"} for i in range(4)]
        bundle = _build_test_bundle(payloads, private_key)

        tampered_events = [dict(e) for e in bundle["events"]]
        tampered_events[1]["hmac_value"] = "f" * 64

        recomputed_root = recompute_root_from_bundle(tampered_events)

        assert verify_bundle_signature(recomputed_root, bundle["signature"], public_key) is False


class TestHmacChainContinuity:
    def test_valid_chain_passes(self):
        private_key = Ed25519PrivateKey.generate()
        payloads = [{"seq": i} for i in range(4)]
        bundle = _build_test_bundle(payloads, private_key)

        passed, divergence = verify_hmac_chain_continuity(bundle["events"], _HMAC_KEY)

        assert passed is True
        assert divergence is None

    def test_altered_canonical_json_is_detected_at_correct_sequence(self):
        private_key = Ed25519PrivateKey.generate()
        payloads = [{"seq": i} for i in range(5)]
        bundle = _build_test_bundle(payloads, private_key)

        tampered_events = [dict(e) for e in bundle["events"]]
        tampered_events[3]["canonical_json"] = '{"seq":3,"tampered":true}'

        passed, divergence = verify_hmac_chain_continuity(tampered_events, _HMAC_KEY)

        assert passed is False
        assert divergence == 3


class TestVerifyBundleFullReport:
    def test_untampered_bundle_passes_every_check(self):
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        payloads = [{"seq": i, "event": f"e{i}"} for i in range(6)]
        bundle = _build_test_bundle(payloads, private_key)

        report = verify_bundle(
            events=bundle["events"],
            claimed_root_hex=bundle["merkle_root"],
            signature_hex=bundle["signature"],
            public_key=public_key,
            hmac_key=_HMAC_KEY,
        )

        assert report.overall_passed is True
        assert all(check.passed for check in report.checks)
        assert report.first_divergent_sequence is None

    def test_tampered_hmac_value_fails_report_and_names_sequence(self):
        """
        Tampering hmac_value directly (simulating a row edited in the
        database, not just its displayed payload) must fail the HMAC
        chain, root, AND signature checks together, and name the correct
        first divergent sequence.
        """
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        payloads = [{"seq": i, "event": f"e{i}"} for i in range(5)]
        bundle = _build_test_bundle(payloads, private_key)

        tampered_events = [dict(e) for e in bundle["events"]]
        tampered_events[2]["hmac_value"] = "a" * 64

        report = verify_bundle(
            events=tampered_events,
            claimed_root_hex=bundle["merkle_root"],
            signature_hex=bundle["signature"],
            public_key=public_key,
            hmac_key=_HMAC_KEY,
        )

        assert report.overall_passed is False
        assert report.first_divergent_sequence == 2

        checks_by_name = {c.name: c for c in report.checks}
        assert checks_by_name["hmac_chain_continuity"].passed is False
        assert checks_by_name["merkle_root_matches"].passed is False
        assert checks_by_name["signature_valid"].passed is False

    def test_wrong_public_key_fails_signature_check_only(self):
        """A signature from a different key entirely must fail verification."""
        private_key = Ed25519PrivateKey.generate()
        wrong_public_key = Ed25519PrivateKey.generate().public_key()
        payloads = [{"seq": i} for i in range(3)]
        bundle = _build_test_bundle(payloads, private_key)

        report = verify_bundle(
            events=bundle["events"],
            claimed_root_hex=bundle["merkle_root"],
            signature_hex=bundle["signature"],
            public_key=wrong_public_key,
            hmac_key=_HMAC_KEY,
        )

        checks_by_name = {c.name: c for c in report.checks}
        assert checks_by_name["hmac_chain_continuity"].passed is True
        assert checks_by_name["merkle_root_matches"].passed is True
        assert checks_by_name["signature_valid"].passed is False
        assert report.overall_passed is False
