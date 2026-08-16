"""
Integration tests: end-to-end event ingestion and verification.

Tests the full flow:
1. POST /events with canonical event
2. Database appends (append-only trigger enforced)
3. HMAC is computed and stored
4. GET /events retrieves the event
5. Verify HMAC chain is unbroken

Run with: pytest tests/integration/test_ledger_flow.py -v
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from datetime import datetime

from praman.main import app
from praman.persistence.database import get_db
from praman.persistence.models import Base, Event
from praman.domain.canonical import canonicalise
from praman.domain.hashing import verify_hmac_chain


# Setup test database (in-memory SQLite)
@pytest.fixture
def test_db():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield SessionLocal()
    app.dependency_overrides.clear()


@pytest.fixture
def client(test_db):
    """FastAPI test client."""
    return TestClient(app)


class TestEventIngestion:
    """Test event ingestion via POST /events."""

    def test_post_event_returns_201(self, client):
        """POST /events returns 201 Created."""
        event_data = {
            "event_type": "consent_granted",
            "module": "privacy",
            "principal_id_hash": "sha256:abc123",
            "action": "data_share",
        }

        response = client.post(
            "/events/events",
            json=event_data,
            headers={"X-Tenant-ID": "test_tenant_1"},
        )

        assert response.status_code == 201
        assert response.json()["status"] == "appended"
        assert "event_id" in response.json()

    def test_post_event_requires_tenant_id(self, client):
        """POST /events requires X-Tenant-ID header."""
        event_data = {
            "event_type": "consent_granted",
            "principal_id_hash": "sha256:abc123",
        }

        response = client.post("/events/events", json=event_data)

        assert response.status_code == 422  # Validation error (missing header)

    def test_post_event_returns_hmac(self, client):
        """POST /events response includes computed HMAC."""
        event_data = {
            "event_type": "consent_granted",
            "principal_id_hash": "sha256:abc123",
        }

        response = client.post(
            "/events/events",
            json=event_data,
            headers={"X-Tenant-ID": "test_tenant_1"},
        )

        assert response.status_code == 201
        hmac_value = response.json()["hmac_value"]
        assert hmac_value is not None
        assert len(hmac_value) == 64  # HMAC-SHA256 hex is 64 characters

    def test_post_multiple_events_appends_in_order(self, client):
        """Multiple POST /events append in order (append-only)."""
        tenant = "test_tenant_1"

        event1 = {"event_type": "consent_granted", "principal_id_hash": "sha256:abc"}
        response1 = client.post(
            "/events/events",
            json=event1,
            headers={"X-Tenant-ID": tenant},
        )
        assert response1.status_code == 201
        event1_id = response1.json()["event_id"]
        hmac1 = response1.json()["hmac_value"]

        event2 = {"event_type": "consent_withdrawn", "principal_id_hash": "sha256:abc"}
        response2 = client.post(
            "/events/events",
            json=event2,
            headers={"X-Tenant-ID": tenant},
        )
        assert response2.status_code == 201
        event2_id = response2.json()["event_id"]
        hmac2 = response2.json()["hmac_value"]

        # Verify order and IDs
        assert event2_id > event1_id, "Events must be appended in order"

        # Verify HMACs are different (chained, so event 2's HMAC includes event 1's)
        assert hmac1 != hmac2, "Chained events must have different HMACs"


class TestEventRetrieval:
    """Test event retrieval via GET /events."""

    def test_get_event_by_id(self, client):
        """GET /events/{id} retrieves an event."""
        # First, append an event
        event_data = {"event_type": "consent_granted", "principal_id_hash": "sha256:abc"}
        post_response = client.post(
            "/events/events",
            json=event_data,
            headers={"X-Tenant-ID": "test_tenant_1"},
        )
        event_id = post_response.json()["event_id"]

        # Then, retrieve it
        get_response = client.get(
            f"/events/events/{event_id}",
            headers={"X-Tenant-ID": "test_tenant_1"},
        )

        assert get_response.status_code == 200
        event = get_response.json()
        assert event["event_id"] == event_id
        assert event["event_type"] == "consent_granted"

    def test_get_event_respects_tenant_isolation(self, client):
        """GET /events respects tenant isolation (RLS)."""
        # Append event for tenant 1
        event_data = {"event_type": "consent_granted", "principal_id_hash": "sha256:abc"}
        post_response = client.post(
            "/events/events",
            json=event_data,
            headers={"X-Tenant-ID": "tenant_1"},
        )
        event_id = post_response.json()["event_id"]

        # Try to retrieve as tenant 2
        get_response = client.get(
            f"/events/events/{event_id}",
            headers={"X-Tenant-ID": "tenant_2"},
        )

        # Should not be able to see tenant 1's events
        assert get_response.status_code == 404

    def test_list_events(self, client):
        """GET /events lists events for a tenant."""
        tenant = "test_tenant_1"

        # Append 3 events
        for i in range(3):
            event_data = {"event_type": f"event_{i}", "principal_id_hash": "sha256:abc"}
            client.post(
                "/events/events",
                json=event_data,
                headers={"X-Tenant-ID": tenant},
            )

        # List events
        list_response = client.get(
            "/events/events",
            headers={"X-Tenant-ID": tenant},
        )

        assert list_response.status_code == 200
        data = list_response.json()
        assert data["count"] == 3
        assert len(data["events"]) == 3


class TestHMACChaining:
    """Test that HMAC chaining works end-to-end."""

    def test_hmac_chain_is_verifiable(self, client, test_db):
        """HMAC chain stored in database is verifiable."""
        tenant = "test_tenant_1"
        hmac_key = b"\x00" * 32  # Same key used in the endpoint

        # Append event 1
        event1_data = {"event_type": "consent_granted", "principal_id_hash": "sha256:abc"}
        response1 = client.post(
            "/events/events",
            json=event1_data,
            headers={"X-Tenant-ID": tenant},
        )
        assert response1.status_code == 201

        # Append event 2
        event2_data = {"event_type": "consent_withdrawn", "principal_id_hash": "sha256:abc"}
        response2 = client.post(
            "/events/events",
            json=event2_data,
            headers={"X-Tenant-ID": tenant},
        )
        assert response2.status_code == 201

        # Retrieve events from database
        events = test_db.query(Event).filter(Event.tenant_id == tenant).order_by(Event.id).all()

        assert len(events) == 2

        # Verify the HMAC chain
        events_to_verify = [
            (canonicalise(e.canonical_event), e.hmac_value)
            for e in events
        ]

        # The chain should verify
        assert verify_hmac_chain(events_to_verify, hmac_key) is True

    def test_tampering_would_break_chain(self, test_db):
        """If an event is tampered with, the chain breaks (demonstrates integrity)."""
        # This is a direct test, not via API
        hmac_key = b"\x00" * 32

        # Create two events with canonical forms
        event1_canonical = canonicalise({"type": "consent", "action": "share"})
        event2_canonical = canonicalise({"type": "consent_withdrawn", "action": "withdraw"})

        # Compute their HMACs
        from praman.domain.hashing import compute_hmac_hex

        hmac1_hex = compute_hmac_hex(event1_canonical, hmac_key)
        hmac2_hex = compute_hmac_hex(event2_canonical, hmac_key, previous_hmac_hex=hmac1_hex)

        # Verify the chain (should work)
        events = [(event1_canonical, hmac1_hex), (event2_canonical, hmac2_hex)]
        assert verify_hmac_chain(events, hmac_key) is True

        # Now tamper: change event 1's canonical form
        event1_tampered = canonicalise({"type": "consent", "action": "TAMPERED"})
        hmac1_tampered = compute_hmac_hex(event1_tampered, hmac_key)

        # Verify the tampered chain (should fail, because event 2's HMAC was based on event 1's original HMAC)
        tampered_events = [(event1_tampered, hmac1_tampered), (event2_canonical, hmac2_hex)]
        assert verify_hmac_chain(tampered_events, hmac_key) is False
