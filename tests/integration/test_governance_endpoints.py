"""
Tests for governance endpoints (/governance/evaluate and /governance/status).

These tests prove:
1. POST /governance/evaluate accepts policy evaluation requests
2. Rejects requests with missing headers or invalid tiers
3. Returns PolicyDecision with allowed/denied + reason
4. GET /governance/status returns current governance state
5. Both endpoints require X-Tenant-ID header

Run with: pytest tests/integration/test_governance_endpoints.py -v
"""

import pytest
import json
from datetime import datetime
from fastapi.testclient import TestClient

from praman.main import app
from praman.persistence.models import Event as EventModel
from praman.persistence.database import SessionLocal


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def db():
    """Database session."""
    return SessionLocal()


@pytest.fixture
def cleanup(db):
    """Clean up test data."""
    yield
    # Cleanup (optional for these tests)


class TestGovernanceEvaluateEndpoint:
    """Tests for POST /governance/evaluate."""

    def test_evaluate_governance_requires_tenant_id(self, client):
        """Request without X-Tenant-ID header fails."""
        payload = {
            "agent_name": "TestAgent",
            "autonomy_tier": "OBSERVE",
            "tool_name": "read",
        }

        response = client.post("/governance/evaluate", json=payload)

        assert response.status_code == 422  # Missing required header

    def test_evaluate_governance_invalid_tier(self, client):
        """Request with invalid autonomy tier fails."""
        payload = {
            "agent_name": "TestAgent",
            "autonomy_tier": "INVALID_TIER",  # Not a valid tier
            "tool_name": "read",
        }

        response = client.post(
            "/governance/evaluate",
            json=payload,
            headers={"X-Tenant-ID": "tenant-123"},
        )

        assert response.status_code == 400
        assert "Invalid autonomy tier" in response.text

    def test_evaluate_governance_observe_tool_allowed(self, client, db):
        """OBSERVE tier allows read-only tools."""
        payload = {
            "agent_name": "GatheringAgent",
            "autonomy_tier": "OBSERVE",
            "tool_name": "read",
        }

        response = client.post(
            "/governance/evaluate",
            json=payload,
            headers={"X-Tenant-ID": "tenant-123"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["allowed"] is True
        assert data["autonomy_tier"] == "OBSERVE"
        assert data["tool_name"] == "read"

    def test_evaluate_governance_observe_tool_denied(self, client):
        """OBSERVE tier denies write tools."""
        payload = {
            "agent_name": "GatheringAgent",
            "autonomy_tier": "OBSERVE",
            "tool_name": "write",  # Not allowed for OBSERVE
        }

        response = client.post(
            "/governance/evaluate",
            json=payload,
            headers={"X-Tenant-ID": "tenant-123"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["allowed"] is False
        assert "not allowed for tier OBSERVE" in data["reason"]

    def test_evaluate_governance_propose_allows_draft(self, client):
        """PROPOSE tier allows draft tool."""
        payload = {
            "agent_name": "ApprovalAgent",
            "autonomy_tier": "PROPOSE",
            "tool_name": "draft",
        }

        response = client.post(
            "/governance/evaluate",
            json=payload,
            headers={"X-Tenant-ID": "tenant-123"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["allowed"] is True

    def test_evaluate_governance_act_bounded_allows_write(self, client):
        """ACT_BOUNDED tier allows write tool."""
        payload = {
            "agent_name": "RiskScoreAgent",
            "autonomy_tier": "ACT_BOUNDED",
            "tool_name": "write",
        }

        response = client.post(
            "/governance/evaluate",
            json=payload,
            headers={"X-Tenant-ID": "tenant-123"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["allowed"] is True

    def test_evaluate_governance_act_full_allows_transfer(self, client):
        """ACT_FULL tier allows transfer tool."""
        payload = {
            "agent_name": "FullAgent",
            "autonomy_tier": "ACT_FULL",
            "tool_name": "transfer",
        }

        response = client.post(
            "/governance/evaluate",
            json=payload,
            headers={"X-Tenant-ID": "tenant-123"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["allowed"] is True

    def test_evaluate_governance_returns_drift_status(self, client):
        """Response includes drift_status field."""
        payload = {
            "agent_name": "TestAgent",
            "autonomy_tier": "OBSERVE",
            "tool_name": "read",
        }

        response = client.post(
            "/governance/evaluate",
            json=payload,
            headers={"X-Tenant-ID": "tenant-123"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "drift_status" in data
        assert data["drift_status"] in ["nominal", "elevated"]


class TestGovernanceStatusEndpoint:
    """Tests for GET /governance/status."""

    def test_status_requires_tenant_id(self, client):
        """Request without X-Tenant-ID header fails."""
        response = client.get("/governance/status")

        assert response.status_code == 422  # Missing required header

    def test_status_returns_full_governance_state(self, client):
        """GET /governance/status returns dashboard data."""
        response = client.get(
            "/governance/status",
            headers={"X-Tenant-ID": "tenant-123"},
        )

        assert response.status_code == 200
        data = response.json()

        # Check all required fields
        assert data["tenant_id"] == "tenant-123"
        assert "autonomy_tiers" in data
        assert "circuit_breaker_open" in data
        assert "drift_scores" in data
        assert "last_evaluated_at" in data

    def test_status_autonomy_tiers_structure(self, client):
        """autonomy_tiers is a dict of agent → tier."""
        response = client.get(
            "/governance/status",
            headers={"X-Tenant-ID": "tenant-123"},
        )

        assert response.status_code == 200
        data = response.json()

        # Should have a dictionary of agent → tier
        assert isinstance(data["autonomy_tiers"], dict)
        assert len(data["autonomy_tiers"]) > 0

        # Check that values are valid tier names
        for agent_name, tier in data["autonomy_tiers"].items():
            assert tier in ["OBSERVE", "PROPOSE", "ACT_BOUNDED", "ACT_FULL"]

    def test_status_drift_scores_structure(self, client):
        """drift_scores is a list with detector info."""
        response = client.get(
            "/governance/status",
            headers={"X-Tenant-ID": "tenant-123"},
        )

        assert response.status_code == 200
        data = response.json()

        # Should have at least one drift score
        assert isinstance(data["drift_scores"], list)
        assert len(data["drift_scores"]) > 0

        for score in data["drift_scores"]:
            assert "detector" in score
            assert "score" in score
            assert "threshold" in score
            assert "triggered" in score

            # Validate ranges
            assert 0.0 <= score["score"] <= 1.0
            assert 0.0 <= score["threshold"] <= 1.0
            assert isinstance(score["triggered"], bool)

    def test_status_circuit_breaker_state(self, client):
        """circuit_breaker_open reflects breaker state."""
        response = client.get(
            "/governance/status",
            headers={"X-Tenant-ID": "tenant-123"},
        )

        assert response.status_code == 200
        data = response.json()

        assert isinstance(data["circuit_breaker_open"], bool)
        # If open, should have a reason
        if data["circuit_breaker_open"]:
            assert data["circuit_breaker_reason"] is not None
        else:
            # May or may not have a reason when closed
            pass

    def test_status_timestamp(self, client):
        """last_evaluated_at is a recent timestamp."""
        before = datetime.utcnow()

        response = client.get(
            "/governance/status",
            headers={"X-Tenant-ID": "tenant-123"},
        )

        after = datetime.utcnow()

        assert response.status_code == 200
        data = response.json()

        # Parse the timestamp
        evaluated_at = datetime.fromisoformat(data["last_evaluated_at"].replace("Z", "+00:00"))

        # Timestamp should be between request time and now
        assert before <= evaluated_at <= after


class TestGovernanceIntegration:
    """Integration tests: governance endpoints working together."""

    def test_evaluate_then_status_flow(self, client):
        """Typical flow: evaluate a decision, then check status."""
        tenant_id = "tenant-999"
        headers = {"X-Tenant-ID": tenant_id}

        # 1. Evaluate governance
        eval_payload = {
            "agent_name": "TestAgent",
            "autonomy_tier": "ACT_BOUNDED",
            "tool_name": "write",
        }

        eval_response = client.post(
            "/governance/evaluate",
            json=eval_payload,
            headers=headers,
        )

        assert eval_response.status_code == 200
        eval_data = eval_response.json()
        assert "allowed" in eval_data

        # 2. Check status
        status_response = client.get(
            "/governance/status",
            headers=headers,
        )

        assert status_response.status_code == 200
        status_data = status_response.json()

        # Status should show the tenant
        assert status_data["tenant_id"] == tenant_id

    def test_multiple_tenants_isolated(self, client):
        """Different tenants have isolated governance state."""
        headers_1 = {"X-Tenant-ID": "tenant-001"}
        headers_2 = {"X-Tenant-ID": "tenant-002"}

        # Get status for tenant 1
        response_1 = client.get("/governance/status", headers=headers_1)
        data_1 = response_1.json()

        # Get status for tenant 2
        response_2 = client.get("/governance/status", headers=headers_2)
        data_2 = response_2.json()

        # Both should succeed
        assert response_1.status_code == 200
        assert response_2.status_code == 200

        # Both should show their respective tenant IDs
        assert data_1["tenant_id"] == "tenant-001"
        assert data_2["tenant_id"] == "tenant-002"
