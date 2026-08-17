"""
Tests for services/evidence_service.py.

Proves the byte-round-trip claim the CLAUDE_CODE_PROMPT brief explicitly
calls out: canonical_json in an assembled bundle must be the exact byte
sequence that was originally hashed, even after a round trip through
Postgres's JSONB storage — otherwise a verifier re-serialising the event
gets different bytes and fails for the wrong reason.

Run with: pytest tests/services/test_evidence_service.py -v
"""

import uuid

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from praman.adapters.key_custody.environment_key import EnvironmentKeyCustody
from praman.domain.canonical import canonicalise
from praman.domain.hashing import compute_hmac_hex
from praman.domain.merkle import compute_root_hex
from praman.domain.signing import public_key_to_pem, verify_signature_hex
from praman.persistence.database import SessionLocal
from praman.persistence.models import Event
from praman.services.evidence_service import build_evidence_bundle

_HMAC_KEY = b"\x00" * 32


class _FakeKeyCustody:
    """A minimal KeyCustody for tests that don't want to touch env config."""

    def __init__(self):
        self._key = Ed25519PrivateKey.generate()

    def signing_key(self):
        return self._key

    def public_key_pem(self):
        return public_key_to_pem(self._key.public_key())

    def key_id(self):
        return "test-key-id-0001"


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def key_custody():
    return _FakeKeyCustody()


def _tenant() -> str:
    return "demo-" + uuid.uuid4().hex[:8]


def _insert_event(db, tenant_id: str, event_type: str, previous_hmac_hex: str | None) -> Event:
    canonical_event_dict = {
        "event_type": event_type,
        "module": "privacy",
        "principal_id_hash": "sha256:test",
        "action": None,
        "timestamp": "2026-08-16T12:00:00",
        "payload": {"nested": {"b": 2, "a": 1}},  # deliberately unsorted insertion order
    }
    canonical_bytes = canonicalise(canonical_event_dict)
    hmac_hex = compute_hmac_hex(canonical_bytes, _HMAC_KEY, previous_hmac_hex)

    event = Event(
        tenant_id=tenant_id,
        module="privacy",
        event_type=event_type,
        canonical_event=canonical_event_dict,
        hmac_value=hmac_hex,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


class TestBundleCanonicalJsonRoundTrips:
    def test_bundle_canonical_json_round_trips_to_identical_bytes(self, db, key_custody):
        """
        The exact bytes in the bundle's canonical_json, when re-encoded to
        UTF-8, must equal the bytes that were originally canonicalised and
        hashed — even though the event went through Postgres JSONB storage
        and back, which does not preserve original serialisation order.
        """
        tenant = _tenant()
        original_canonical_dict = {
            "event_type": "byte_roundtrip_check",
            "module": "privacy",
            "principal_id_hash": "sha256:test",
            "action": None,
            "timestamp": "2026-08-16T12:00:00",
            "payload": {"z": 26, "a": 1, "nested": {"y": 2, "x": 1}},
        }
        original_bytes = canonicalise(original_canonical_dict)
        hmac_hex = compute_hmac_hex(original_bytes, _HMAC_KEY, None)

        event = Event(
            tenant_id=tenant,
            module="privacy",
            event_type="byte_roundtrip_check",
            canonical_event=original_canonical_dict,
            hmac_value=hmac_hex,
        )
        db.add(event)
        db.commit()

        bundle = build_evidence_bundle(db, tenant, key_custody)

        bundle_bytes = bundle["events"][0]["canonical_json"].encode("utf-8")
        assert bundle_bytes == original_bytes

    def test_bundle_hmac_recomputes_correctly_from_bundle_bytes(self, db, key_custody):
        """
        A stronger form of the round-trip claim: not just that bytes match,
        but that recomputing the HMAC from the bundle's canonical_json
        produces the same hmac_value the bundle claims for that event.
        """
        tenant = _tenant()
        event = _insert_event(db, tenant, "hmac_recompute_check", previous_hmac_hex=None)

        bundle = build_evidence_bundle(db, tenant, key_custody)
        bundle_event = bundle["events"][0]

        recomputed_hmac = compute_hmac_hex(
            bundle_event["canonical_json"].encode("utf-8"), _HMAC_KEY, None
        )

        assert recomputed_hmac == bundle_event["hmac_value"] == event.hmac_value


class TestBundleAssembly:
    def test_bundle_includes_all_tenant_events_in_order(self, db, key_custody):
        tenant = _tenant()
        e1 = _insert_event(db, tenant, "first", None)
        e2 = _insert_event(db, tenant, "second", e1.hmac_value)
        e3 = _insert_event(db, tenant, "third", e2.hmac_value)

        bundle = build_evidence_bundle(db, tenant, key_custody)

        assert len(bundle["events"]) == 3
        assert [e["sequence"] for e in bundle["events"]] == [0, 1, 2]
        assert bundle["events"][0]["hmac_value"] == e1.hmac_value
        assert bundle["events"][2]["hmac_value"] == e3.hmac_value

    def test_bundle_signature_verifies_against_bundle_root(self, db, key_custody):
        """Sanity check: the signature the service produces verifies against its own claimed root."""
        tenant = _tenant()
        _insert_event(db, tenant, "sig_check", None)

        bundle = build_evidence_bundle(db, tenant, key_custody)

        assert verify_signature_hex(
            bundle["merkle_root"], bundle["signature"], key_custody.signing_key().public_key()
        )

    def test_bundle_merkle_root_matches_independent_computation(self, db, key_custody):
        tenant = _tenant()
        e1 = _insert_event(db, tenant, "a", None)
        e2 = _insert_event(db, tenant, "b", e1.hmac_value)

        bundle = build_evidence_bundle(db, tenant, key_custody)

        expected_root = compute_root_hex([e1.hmac_value, e2.hmac_value])
        assert bundle["merkle_root"] == expected_root

    def test_raises_value_error_for_tenant_with_no_events(self, db, key_custody):
        with pytest.raises(ValueError, match="No events found"):
            build_evidence_bundle(db, "demo-noevents", key_custody)

    def test_bundle_discloses_the_fixed_demo_hmac_key(self, db, key_custody):
        """
        The algorithms block must disclose that this is a fixed demo key,
        not a real per-tenant key — omitting this would let a bundle imply
        stronger evidentiary independence than this build actually has.
        """
        tenant = _tenant()
        _insert_event(db, tenant, "disclosure_check", None)

        bundle = build_evidence_bundle(db, tenant, key_custody)

        assert "STUB" in bundle["algorithms"]["hmac_chain_key"]
