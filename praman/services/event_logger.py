"""
Event logger service — Log governance decisions and circuit breaker halts to Module 1.

Responsibility
    Log policy decisions (allowed/denied) as events to the ledger.
    Log circuit breaker halts as evidence (halt is now tamper-evident).
    Canonicalise and HMAC-chain the logged events.
    Ensure halts are recorded before the system falls back to HITL.

Must not
    Perform cryptography directly (call domain/ functions).
    Make policy decisions (that is PolicyEngine's job).
    Read or modify arbitrary ledger entries (append-only).

Design notes
    When Module 2 makes a decision (policy eval + drift check), that decision
    becomes Module 1's evidence. The decision event is logged to the ledger,
    which means it is canonicalised, HMAC-chained, and part of the Merkle root.

    When the circuit breaker halts, the halt event includes:
    - detector type (psi_data, semantic_entropy, behavioural)
    - drift score (what was measured)
    - threshold (what triggered the halt)
    - reason (human-readable summary)

    The halt event is logged to Module 1 before the system falls back to
    human review. This ensures the halt is part of the evidence trail.

See also
    docs/ARCHITECTURE.md (event flow, module interactions)
    praman/domain/drift.py (DriftScore, CircuitBreakerState)
"""

from typing import Optional
from datetime import datetime
from sqlalchemy.orm import Session

from praman.domain.drift import DriftScore, CircuitBreakerState
from praman.domain.canonical import canonicalise
from praman.domain.hashing import compute_hmac_hex
from praman.persistence.models import Event as EventModel

# STUB: fixed HMAC key, matching api/routers/events.py. Production requires a
# per-tenant key (see docs/LIMITATIONS.md); Module 2 events must chain with
# the same key as Module 1 or the ledger's HMAC chain breaks across modules.
_HMAC_KEY = b"\x00" * 32


def _append_event(
    db: Session,
    tenant_id: str,
    module: str,
    event_type: str,
    canonical_event: dict,
) -> EventModel:
    """
    Canonicalise, HMAC-chain, and persist an event — shared by every
    log_* function in this module so Module 2 events chain into the same
    ledger and HMAC sequence as Module 1's directly-posted events.
    """
    previous_event = (
        db.query(EventModel)
        .filter(EventModel.tenant_id == tenant_id)
        .order_by(EventModel.id.desc())
        .first()
    )
    previous_hmac_hex = previous_event.hmac_value if previous_event else None

    canonical_bytes = canonicalise(canonical_event)
    hmac_hex = compute_hmac_hex(canonical_bytes, _HMAC_KEY, previous_hmac_hex)

    event = EventModel(
        tenant_id=tenant_id,
        module=module,
        event_type=event_type,
        canonical_event=canonical_event,
        hmac_value=hmac_hex,
        created_at=datetime.utcnow(),
    )

    db.add(event)
    db.commit()
    db.refresh(event)

    return event


def log_policy_decision(
    db: Session,
    tenant_id: str,
    agent_name: str,
    autonomy_tier: str,
    policy_name: str,
    decision: str,  # "allowed" | "denied"
    reason: str,
) -> EventModel:
    """
    Log a policy decision as a Module 1 event.

    The decision becomes part of the ledger (canonicalised, HMAC-chained,
    part of the Merkle root). This proves Module 2 operated and what it decided.

    Args:
        db: Database session
        tenant_id: Tenant identifier
        agent_name: Agent being evaluated
        autonomy_tier: Tier of the agent
        policy_name: Policy that was evaluated
        decision: "allowed" or "denied"
        reason: Human-readable reason (included in event)

    Returns:
        EventModel: The logged event (appended to ledger)
    """
    canonical_event = {
        "event_type": "policy_decision",
        "agent": agent_name,
        "autonomy_tier": autonomy_tier,
        "policy": policy_name,
        "decision": decision,
        "reason": reason,
    }

    return _append_event(
        db=db,
        tenant_id=tenant_id,
        module="ai_risk",
        event_type="policy_decision",
        canonical_event=canonical_event,
    )


def log_circuit_breaker_halt(
    db: Session,
    tenant_id: str,
    drift_score: DriftScore,
) -> EventModel:
    """
    Log a circuit breaker halt as a Module 1 event (evidence).

    When drift > threshold, the agent is halted and the halt is logged.
    The halt event is tamper-evident, attributed, and time-bound:
    it is now admissible as proof the system operated correctly.

    Args:
        db: Database session
        tenant_id: Tenant identifier
        drift_score: The DriftScore that triggered the breaker

    Returns:
        EventModel: The halt event (appended to ledger)
    """
    canonical_event = {
        "event_type": "circuit_breaker_halt",
        "detector": drift_score.detector_type.value,
        "score": drift_score.score,
        "threshold": drift_score.threshold,
        "margin": drift_score.margin,
        "reason": f"Drift detected: {drift_score.detector_type.value} {drift_score.score:.3f} >= {drift_score.threshold:.3f}",
    }

    return _append_event(
        db=db,
        tenant_id=tenant_id,
        module="ai_risk",
        event_type="circuit_breaker_halt",
        canonical_event=canonical_event,
    )


def log_drift_report(
    db: Session,
    tenant_id: str,
    detector_type: str,
    score: float,
    threshold: float,
    triggered: bool,
    details: Optional[str] = None,
) -> EventModel:
    """
    Log a drift score (even if not triggered) for forensic tracing.

    Logging all drift scores (not just triggered ones) allows a reviewer
    to see the full picture: which detectors ran, what they measured, and
    why the breaker did or did not open.

    Args:
        db: Database session
        tenant_id: Tenant identifier
        detector_type: Type of detector (psi_data, semantic_entropy, etc.)
        score: Computed drift score (0–1)
        threshold: Trigger threshold (0–1)
        triggered: Whether the detector triggered
        details: Optional details about the computation

    Returns:
        EventModel: The logged event
    """
    canonical_event = {
        "event_type": "drift_score",
        "detector": detector_type,
        "score": score,
        "threshold": threshold,
        "triggered": triggered,
        "details": details,
    }

    return _append_event(
        db=db,
        tenant_id=tenant_id,
        module="ai_risk",
        event_type="drift_score",
        canonical_event=canonical_event,
    )
