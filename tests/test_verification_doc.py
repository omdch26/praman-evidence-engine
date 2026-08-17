"""
Tests that docs/VERIFICATION.md's worked example is actually correct.

This exists because a hand-transcribed hex value in a doc is exactly the
kind of thing that silently drifts from reality — caught once already
during authoring (see git history) by manually re-deriving these numbers
and finding a one-character transcription error in every value. This
test makes that class of bug fail CI instead of waiting for a reader to
notice their hand-computation doesn't match the doc.

Run with: pytest tests/test_verification_doc.py -v
"""

from praman.domain.canonical import canonicalise
from praman.domain.hashing import compute_hmac_hex
from praman.domain.merkle import compute_root_hex, hash_leaf, hash_node

_HMAC_KEY = b"\x00" * 32

# The exact two events docs/VERIFICATION.md's worked example uses.
_EVENT_1 = {
    "action": None,
    "event_type": "consent_granted",
    "module": "privacy",
    "payload": {},
    "principal_id_hash": "sha256:abc123",
    "timestamp": "2026-08-16T14:30:00",
}
_EVENT_2 = {
    "action": None,
    "event_type": "consent_withdrawn",
    "module": "privacy",
    "payload": {},
    "principal_id_hash": "sha256:abc123",
    "timestamp": "2026-08-16T14:35:00",
}

# The exact values currently published in docs/VERIFICATION.md. If you
# change the worked example in that doc, update these to match — and
# vice versa: if this test fails, the doc is wrong, not this test.
_DOC_EVENT_1_HMAC = "bb5fc137d94d13cf41dd1808ba87f90a926f22e44bb2cae84b200c63b67d6007"
_DOC_EVENT_2_HMAC = "17ec0053e84eb4d33c8c33daf22e10261fe8343a49e48d6b367431f89816b250"
_DOC_LEAF_1 = "73e3f4bbcd05112fcc9fb3592e7e2f00bb03f5da5d10fc7032d2a108313119a2"
_DOC_LEAF_2 = "bf6279ecc9f5838b5087b56f33b9af74b20c5848239b017716338a18458bc061"
_DOC_ROOT = "887e6816b035be9def1ba330b6b7f78e0a36a8ae5f119d7749905dc7cd80d7ae"


class TestVerificationDocWorkedExample:
    def test_event_hmacs_match_documented_values(self):
        canonical_1 = canonicalise(_EVENT_1)
        hmac_1 = compute_hmac_hex(canonical_1, _HMAC_KEY, None)

        canonical_2 = canonicalise(_EVENT_2)
        hmac_2 = compute_hmac_hex(canonical_2, _HMAC_KEY, hmac_1)

        assert hmac_1 == _DOC_EVENT_1_HMAC, "docs/VERIFICATION.md's event 1 HMAC is stale"
        assert hmac_2 == _DOC_EVENT_2_HMAC, "docs/VERIFICATION.md's event 2 HMAC is stale"

    def test_leaf_hashes_match_documented_values(self):
        leaf_1 = hash_leaf(_DOC_EVENT_1_HMAC).hex()
        leaf_2 = hash_leaf(_DOC_EVENT_2_HMAC).hex()

        assert leaf_1 == _DOC_LEAF_1, "docs/VERIFICATION.md's leaf_1 is stale"
        assert leaf_2 == _DOC_LEAF_2, "docs/VERIFICATION.md's leaf_2 is stale"

    def test_root_matches_documented_value(self):
        node_via_hash_node = hash_node(
            hash_leaf(_DOC_EVENT_1_HMAC), hash_leaf(_DOC_EVENT_2_HMAC)
        ).hex()
        root_via_compute_root_hex = compute_root_hex([_DOC_EVENT_1_HMAC, _DOC_EVENT_2_HMAC])

        assert node_via_hash_node == _DOC_ROOT, "docs/VERIFICATION.md's root is stale"
        assert root_via_compute_root_hex == _DOC_ROOT
        assert node_via_hash_node == root_via_compute_root_hex, (
            "hash_node() and compute_root_hex() disagree with each other, which is a "
            "real bug independent of the doc"
        )

    def test_all_hex_values_are_64_characters(self):
        """Every value in the worked example must be a full 32-byte hash, hex-encoded."""
        for name, value in [
            ("event_1_hmac", _DOC_EVENT_1_HMAC),
            ("event_2_hmac", _DOC_EVENT_2_HMAC),
            ("leaf_1", _DOC_LEAF_1),
            ("leaf_2", _DOC_LEAF_2),
            ("root", _DOC_ROOT),
        ]:
            assert len(value) == 64, f"{name} is {len(value)} chars, expected 64: {value}"
