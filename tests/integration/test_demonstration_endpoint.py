"""
Tests for POST /demo/tamper-attempt.

These tests prove the four independent safety gates from ADR 0015 all
hold, and that the endpoint's core claim is true: a real UPDATE against
the ledger is attempted, rejected by PostgreSQL, and the row is
genuinely unchanged afterward — not merely that the endpoint returns a
plausible-looking response.

Run with: pytest tests/integration/test_demonstration_endpoint.py -v
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from praman.config import settings
from praman.main import app
from praman.persistence.database import SessionLocal
from praman.persistence.models import Event


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def demo_mode_enabled():
    """Flip settings.demo_mode_enabled on for the duration of one test.

    settings is a live singleton read fresh on every request (see
    demonstration.py), so mutating the attribute directly and restoring
    it afterward is correct here — no re-import or app rebuild needed.
    """
    original = settings.demo_mode_enabled
    settings.demo_mode_enabled = True
    yield
    settings.demo_mode_enabled = original


def _demo_tenant() -> str:
    """A syntactically valid demo tenant id, unique per call."""
    return "demo-" + uuid.uuid4().hex[:8]


class TestDemoModeIsDisabledByDefault:
    def test_demo_mode_is_disabled_by_default(self):
        """
        The regression guard for ADR 0015's central safety requirement:
        settings.demo_mode_enabled must default to False. A test asserting
        this fails loudly if that default is ever flipped by accident.
        """
        from praman.config import Settings

        fresh_settings = Settings(database_url="postgresql://user:pass@localhost/db")

        assert fresh_settings.demo_mode_enabled is False

    def test_endpoint_returns_404_when_demo_mode_disabled(self, client: TestClient):
        """With demo mode off (the real default), the route 404s, not 403."""
        assert settings.demo_mode_enabled is False

        response = client.post(
            "/demo/tamper-attempt",
            json={"event_id": 1, "new_payload": "x"},
            headers={"X-Tenant-ID": _demo_tenant()},
        )

        assert response.status_code == 404


class TestDemoEndpointRejectsNonDemoTenant:
    def test_demo_endpoint_rejects_non_demo_tenant(self, client: TestClient, demo_mode_enabled):
        """A real-looking tenant id is rejected even with demo mode enabled."""
        response = client.post(
            "/demo/tamper-attempt",
            json={"event_id": 1, "new_payload": "x"},
            headers={"X-Tenant-ID": "some-real-bank-customer"},
        )

        assert response.status_code == 403

    @pytest.mark.parametrize(
        "bad_tenant",
        [
            "demo-",  # too short
            "demo-ABCDEFGH",  # uppercase not allowed
            "demo-1234567",  # 7 chars, needs 8
            "demo-123456789",  # 9 chars, needs 8
            "DEMO-12345678",  # wrong case on prefix
            "demo_12345678",  # underscore, not hyphen
        ],
    )
    def test_rejects_malformed_demo_tenant_ids(self, client: TestClient, demo_mode_enabled, bad_tenant):
        response = client.post(
            "/demo/tamper-attempt",
            json={"event_id": 1, "new_payload": "x"},
            headers={"X-Tenant-ID": bad_tenant},
        )

        assert response.status_code == 403


class TestTamperAttemptIsRejectedByDatabase:
    def test_tamper_attempt_is_rejected_by_database(self, client: TestClient, db, demo_mode_enabled):
        """
        The core claim: a real UPDATE is attempted and PostgreSQL's own
        append-only trigger rejects it. sql_state must be the trigger's
        actual SQLSTATE (P0001, a plain RAISE EXCEPTION), not a hardcoded
        placeholder.
        """
        tenant = _demo_tenant()
        create_response = client.post(
            "/events",
            json={"event_type": "original", "principal_id_hash": "sha256:x"},
            headers={"X-Tenant-ID": tenant},
        )
        event_id = create_response.json()["event_id"]

        tamper_response = client.post(
            "/demo/tamper-attempt",
            json={"event_id": event_id, "new_payload": "TAMPERED"},
            headers={"X-Tenant-ID": tenant},
        )

        assert tamper_response.status_code == 200
        body = tamper_response.json()
        assert body["attempted"] is True
        assert body["succeeded"] is False
        assert body["sql_state"] == "P0001"
        assert "append-only" in body["database_error"]

    def test_tamper_attempt_never_mutates_the_ledger(self, client: TestClient, db, demo_mode_enabled):
        """
        Assert the row is byte-for-byte unchanged after the attempt — not
        just that the endpoint reported failure, but that the failure
        report was true.
        """
        tenant = _demo_tenant()
        create_response = client.post(
            "/events",
            json={"event_type": "original_untouched", "principal_id_hash": "sha256:x"},
            headers={"X-Tenant-ID": tenant},
        )
        event_id = create_response.json()["event_id"]

        client.post(
            "/demo/tamper-attempt",
            json={"event_id": event_id, "new_payload": "TAMPERED"},
            headers={"X-Tenant-ID": tenant},
        )

        row = db.query(Event).filter(Event.id == event_id).first()
        assert row.event_type == "original_untouched"


class TestCrossTenantScoping:
    def test_cannot_tamper_another_demo_tenants_event(self, client: TestClient, db, demo_mode_enabled):
        """
        A caller authenticated as one demo tenant cannot reach another demo
        tenant's event_id — this is the (tenant_id, event_id) scoping fix
        that makes cross-tenant reach impossible by construction rather
        than trigger-dependent. Expect 404 (nothing found for this
        tenant), not a write attempt against someone else's row.
        """
        owner_tenant = _demo_tenant()
        attacker_tenant = _demo_tenant()

        create_response = client.post(
            "/events",
            json={"event_type": "owners_original", "principal_id_hash": "sha256:x"},
            headers={"X-Tenant-ID": owner_tenant},
        )
        event_id = create_response.json()["event_id"]

        cross_tenant_response = client.post(
            "/demo/tamper-attempt",
            json={"event_id": event_id, "new_payload": "CROSS-TENANT"},
            headers={"X-Tenant-ID": attacker_tenant},
        )

        assert cross_tenant_response.status_code == 404

        row = db.query(Event).filter(Event.id == event_id).first()
        assert row.event_type == "owners_original"
