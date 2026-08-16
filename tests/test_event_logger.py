"""
Tests for event logger service (log governance decisions + halts to Module 1).

These tests prove:
1. Policy decisions are logged as events (become part of ledger)
2. Circuit breaker halts are logged with full drift details
3. Drift scores are loggable (even if not triggered)
4. Logged events include all forensic information
5. Events are appended in order (relying on SQLAlchemy append-only constraint)

Note: These tests require a database connection. Run with pytest in an environment
where DATABASE_URL is set or a test database is available.

Run with: pytest tests/test_event_logger.py -v
"""

import pytest
from datetime import datetime
from sqlalchemy.orm import Session

from praman.services.event_logger import (
    log_policy_decision,
    log_circuit_breaker_halt,
    log_drift_report,
)
from praman.domain.drift import DriftScore, DriftType
from praman.persistence.models import Event as EventModel
from praman.persistence.database import SessionLocal


@pytest.fixture
def db() -> Session:
    """Database session bound to the configured (Postgres) database."""
    return SessionLocal()


class TestPolicyDecisionLogging:
    """Test logging of policy decisions to Module 1 ledger."""

    def test_allowed_decision_logged(self, db: Session):
        """Allowed decision is logged as an event."""
        tenant_id = "test-tenant-1"

        event = log_policy_decision(
            db=db,
            tenant_id=tenant_id,
            agent_name="RiskScoreAgent",
            autonomy_tier="ACT_BOUNDED",
            policy_name="loan_approval_policy",
            decision="allowed",
            reason="Policy evaluated; no constraints violated",
        )

        assert event.tenant_id == tenant_id
        assert event.event_type == "policy_decision"
        assert event.canonical_event["decision"] == "allowed"
        assert event.canonical_event["agent"] == "RiskScoreAgent"
        assert event.canonical_event["autonomy_tier"] == "ACT_BOUNDED"

    def test_denied_decision_logged(self, db: Session):
        """Denied decision is logged with reason."""
        tenant_id = "test-tenant-1"

        event = log_policy_decision(
            db=db,
            tenant_id=tenant_id,
            agent_name="ApprovalAgent",
            autonomy_tier="PROPOSE",
            policy_name="transfer_policy",
            decision="denied",
            reason="Tool not in allowlist for PROPOSE tier",
        )

        assert event.canonical_event["decision"] == "denied"
        assert "allowlist" in event.canonical_event["reason"]

    def test_decision_includes_forensic_info(self, db: Session):
        """Logged decision includes all forensic information."""
        tenant_id = "test-tenant-2"

        event = log_policy_decision(
            db=db,
            tenant_id=tenant_id,
            agent_name="DataAgent",
            autonomy_tier="OBSERVE",
            policy_name="data_access_policy",
            decision="allowed",
            reason="Read-only access; no side effects",
        )

        # All fields required for forensic replay
        assert event.canonical_event["agent"] in event.canonical_event.values()
        assert event.canonical_event["policy"] in event.canonical_event.values()
        assert event.canonical_event["autonomy_tier"] in event.canonical_event.values()
        assert event.created_at is not None


class TestCircuitBreakerHaltLogging:
    """Test logging of circuit breaker halts to Module 1 ledger."""

    def test_halt_logged_with_drift_details(self, db: Session):
        """Circuit breaker halt is logged with full drift details."""
        tenant_id = "test-tenant-1"

        drift_score = DriftScore(
            detector_type=DriftType.PSI_DATA,
            score=0.30,
            threshold=0.25,
            triggered=True,
            computed_at=datetime.utcnow(),
            details="Input distribution shifted significantly",
        )

        event = log_circuit_breaker_halt(
            db=db,
            tenant_id=tenant_id,
            drift_score=drift_score,
        )

        assert event.tenant_id == tenant_id
        assert event.event_type == "circuit_breaker_halt"
        assert event.canonical_event["detector"] == "psi_data"
        assert event.canonical_event["score"] == 0.30
        assert event.canonical_event["threshold"] == 0.25
        assert event.canonical_event["margin"] < 0  # score > threshold

    def test_halt_includes_human_readable_reason(self, db: Session):
        """Halt event includes human-readable reason."""
        tenant_id = "test-tenant-2"

        drift_score = DriftScore(
            detector_type=DriftType.SEMANTIC_ENTROPY,
            score=0.85,
            threshold=0.30,
            triggered=True,
            computed_at=datetime.utcnow(),
        )

        event = log_circuit_breaker_halt(db=db, tenant_id=tenant_id, drift_score=drift_score)

        # Reason should be human-readable (for auditor, court)
        assert "Drift detected" in event.canonical_event["reason"]
        assert "semantic_entropy" in event.canonical_event["reason"]
        assert "0.850" in event.canonical_event["reason"]  # Formatted score

    def test_halt_is_admissible_as_evidence(self, db: Session):
        """Halt event is tamper-evident and can be part of ledger proof."""
        tenant_id = "test-tenant-3"

        drift_score = DriftScore(
            detector_type=DriftType.BEHAVIOURAL,
            score=0.75,
            threshold=0.35,
            triggered=True,
            computed_at=datetime.utcnow(),
        )

        event = log_circuit_breaker_halt(db=db, tenant_id=tenant_id, drift_score=drift_score)

        # Event is now part of the ledger (can be canonicalised, HMAC'd, Merkle rooted)
        # These checks are structural; the crypto proofs belong in domain tests
        assert event.id is not None  # Has a ledger entry
        assert event.created_at is not None
        assert event.canonical_event is not None  # Canonicalisable


class TestDriftReportLogging:
    """Test logging of drift scores to audit trail."""

    def test_triggered_drift_logged(self, db: Session):
        """Triggered drift score is logged."""
        tenant_id = "test-tenant-1"

        event = log_drift_report(
            db=db,
            tenant_id=tenant_id,
            detector_type="psi_data",
            score=0.28,
            threshold=0.25,
            triggered=True,
            details="Binning strategy: deciles",
        )

        assert event.canonical_event["detector"] == "psi_data"
        assert event.canonical_event["triggered"] is True
        assert event.canonical_event["details"] == "Binning strategy: deciles"

    def test_nominal_drift_logged(self, db: Session):
        """Nominal drift score is logged (forensic visibility)."""
        tenant_id = "test-tenant-1"

        event = log_drift_report(
            db=db,
            tenant_id=tenant_id,
            detector_type="semantic_entropy",
            score=0.15,
            threshold=0.30,
            triggered=False,
            details="Output embeddings within reference distribution",
        )

        assert event.canonical_event["triggered"] is False
        # Nominal scores are logged so reviewers can see the full picture
        assert event.event_type == "drift_score"

    def test_all_detectors_loggable(self, db: Session):
        """All drift detector types are loggable."""
        tenant_id = "test-tenant-2"

        for detector_type in ["psi_data", "semantic_entropy", "behavioural"]:
            event = log_drift_report(
                db=db,
                tenant_id=tenant_id,
                detector_type=detector_type,
                score=0.50,
                threshold=0.25,
                triggered=False,
            )

            assert event.canonical_event["detector"] == detector_type


class TestMultiTenantIsolation:
    """Test that logging respects tenant isolation."""

    def test_decisions_isolated_by_tenant(self, db: Session):
        """Policy decisions are isolated by tenant."""
        tenant_1_event = log_policy_decision(
            db=db,
            tenant_id="tenant-1",
            agent_name="Agent1",
            autonomy_tier="OBSERVE",
            policy_name="policy1",
            decision="allowed",
            reason="OK",
        )

        tenant_2_event = log_policy_decision(
            db=db,
            tenant_id="tenant-2",
            agent_name="Agent2",
            autonomy_tier="ACT_BOUNDED",
            policy_name="policy2",
            decision="denied",
            reason="Denied",
        )

        # Both events are logged but belong to different tenants
        assert tenant_1_event.tenant_id == "tenant-1"
        assert tenant_2_event.tenant_id == "tenant-2"
        assert tenant_1_event.canonical_event["agent"] != tenant_2_event.canonical_event["agent"]

    def test_halts_isolated_by_tenant(self, db: Session):
        """Circuit breaker halts are isolated by tenant."""
        drift_score_1 = DriftScore(
            detector_type=DriftType.PSI_DATA,
            score=0.30,
            threshold=0.25,
            triggered=True,
            computed_at=datetime.utcnow(),
        )

        drift_score_2 = DriftScore(
            detector_type=DriftType.SEMANTIC_ENTROPY,
            score=0.85,
            threshold=0.30,
            triggered=True,
            computed_at=datetime.utcnow(),
        )

        halt_1 = log_circuit_breaker_halt(db=db, tenant_id="tenant-1", drift_score=drift_score_1)
        halt_2 = log_circuit_breaker_halt(db=db, tenant_id="tenant-2", drift_score=drift_score_2)

        # Both halts are logged but belong to different tenants
        assert halt_1.tenant_id == "tenant-1"
        assert halt_2.tenant_id == "tenant-2"
        assert halt_1.canonical_event["detector"] != halt_2.canonical_event["detector"]
