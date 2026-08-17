"""
Integration tests for GET /keys/public and GET /evidence/bundle.

Proves the two endpoints together give an independent verifier everything
needed: a public key that matches the bundle's key_id, and a bundle whose
signature verifies against that key over an independently recomputed root.

Run with: pytest tests/integration/test_evidence_endpoints.py -v
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from praman.domain.signing import public_key_from_pem
from praman.domain.verification import verify_bundle
from praman.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _tenant() -> str:
    return "demo-" + uuid.uuid4().hex[:8]


class TestPublicKeyEndpoint:
    def test_get_public_key_returns_ed25519_key(self, client: TestClient):
        response = client.get("/keys/public")

        assert response.status_code == 200
        body = response.json()
        assert body["algorithm"] == "Ed25519"
        assert body["public_key_pem"].startswith("-----BEGIN PUBLIC KEY-----")
        assert len(body["public_key_raw_hex"]) == 64  # 32 bytes, hex-encoded

    def test_public_key_is_stable_across_calls(self, client: TestClient):
        """Regression guard: same key_id every call (ADR 0014's central claim, via HTTP)."""
        first = client.get("/keys/public").json()
        second = client.get("/keys/public").json()

        assert first["key_id"] == second["key_id"]
        assert first["public_key_pem"] == second["public_key_pem"]


class TestEvidenceBundleEndpoint:
    def test_bundle_returns_404_for_tenant_with_no_events(self, client: TestClient):
        response = client.get("/evidence/bundle", headers={"X-Tenant-ID": _tenant()})

        assert response.status_code == 404

    def test_bundle_key_id_matches_public_key_endpoint(self, client: TestClient):
        tenant = _tenant()
        client.post(
            "/events",
            json={"event_type": "key_id_check", "principal_id_hash": "sha256:x"},
            headers={"X-Tenant-ID": tenant},
        )

        bundle = client.get("/evidence/bundle", headers={"X-Tenant-ID": tenant}).json()
        public_key_data = client.get("/keys/public").json()

        assert bundle["key_id"] == public_key_data["key_id"]

    def test_full_bundle_verifies_end_to_end(self, client: TestClient):
        """
        The complete story: create events, fetch the bundle and the public
        key over separate HTTP calls (as a real independent verifier
        would), and confirm domain/verification.py's full report passes
        every check.
        """
        tenant = _tenant()
        for i in range(5):
            response = client.post(
                "/events",
                json={"event_type": f"e2e_event_{i}", "principal_id_hash": "sha256:x"},
                headers={"X-Tenant-ID": tenant},
            )
            assert response.status_code == 201

        bundle = client.get("/evidence/bundle", headers={"X-Tenant-ID": tenant}).json()
        public_key_data = client.get("/keys/public").json()
        public_key = public_key_from_pem(public_key_data["public_key_pem"].encode())

        report = verify_bundle(
            events=bundle["events"],
            claimed_root_hex=bundle["merkle_root"],
            signature_hex=bundle["signature"],
            public_key=public_key,
            hmac_key=b"\x00" * 32,
        )

        assert report.overall_passed is True
        assert len(bundle["events"]) == 5

    def test_tampered_bundle_event_fails_verification_with_correct_sequence(self, client: TestClient):
        """
        The negative-path companion to the full round trip: mutating one
        event's hmac_value in a fetched bundle (simulating "assume an
        attacker got past the database") must fail verification and name
        the correct sequence — using the SAME verify_bundle function the
        happy path uses, not a parallel check.
        """
        tenant = _tenant()
        for i in range(4):
            client.post(
                "/events",
                json={"event_type": f"tamper_check_{i}", "principal_id_hash": "sha256:x"},
                headers={"X-Tenant-ID": tenant},
            )

        bundle = client.get("/evidence/bundle", headers={"X-Tenant-ID": tenant}).json()
        public_key_data = client.get("/keys/public").json()
        public_key = public_key_from_pem(public_key_data["public_key_pem"].encode())

        tampered_events = [dict(e) for e in bundle["events"]]
        tampered_events[2]["hmac_value"] = "b" * 64

        report = verify_bundle(
            events=tampered_events,
            claimed_root_hex=bundle["merkle_root"],
            signature_hex=bundle["signature"],
            public_key=public_key,
            hmac_key=b"\x00" * 32,
        )

        assert report.overall_passed is False
        assert report.first_divergent_sequence == 2
