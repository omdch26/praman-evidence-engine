"""
Governance evaluation and dashboard routes.

Responsibility
    Evaluate policies + check drift + decide on agent action.
    Return governance status and real-time drift metrics.
    Provide dashboard data (autonomy tiers, breaker state, drift scores).

Must not
    Contain business logic (call services/).
    Perform cryptography (call domain/).
    Directly modify the ledger (call persistence/).

Routes
    POST /governance/evaluate — Evaluate a policy decision
    GET /governance/status — Dashboard: current governance state
"""

from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
from datetime import datetime

from praman.persistence.database import get_db
from praman.persistence.models import Event as EventModel
from praman.domain.governance import AutonomyTier, apply_delegation_ceiling
from praman.domain.drift import (
    compute_deterministic_drift_score,
    evaluate_circuit_breaker,
    DriftReport,
)

router = APIRouter()


class PolicyEvaluationRequest(BaseModel):
    """Request to evaluate a policy."""

    agent_name: str = Field(..., description="Name of the agent")
    autonomy_tier: str = Field(..., description="Autonomy tier: OBSERVE, PROPOSE, ACT_BOUNDED, ACT_FULL")
    tool_name: str = Field(..., description="Tool the agent is trying to call")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Tool parameters")


class PolicyDecision(BaseModel):
    """Decision on whether to allow a tool call."""

    allowed: bool
    reason: str
    autonomy_tier: str
    tool_name: str
    drift_status: str


class GovernanceStatus(BaseModel):
    """Current governance status (dashboard data)."""

    tenant_id: str
    autonomy_tiers: Dict[str, str]  # agent_name → tier
    circuit_breaker_open: bool
    circuit_breaker_reason: Optional[str]
    drift_scores: List[Dict[str, Any]]
    last_evaluated_at: datetime


@router.post("/evaluate", response_model=PolicyDecision)
async def evaluate_governance(
    request: PolicyEvaluationRequest,
    db: Session = Depends(get_db),
    tenant_id: str = Header(..., alias="X-Tenant-ID"),
) -> PolicyDecision:
    """
    Evaluate a policy decision: should this agent be allowed to call this tool?

    Checks:
    1. Autonomy tier permits the action
    2. Drift detection (is the agent in a safe state?)
    3. Tool allowlist (is this tool allowed for this tier?)

    Args:
        request: PolicyEvaluationRequest
        db: Database session
        tenant_id: Tenant identifier

    Returns:
        PolicyDecision: allowed/denied + reason
    """
    # Parse autonomy tier
    try:
        tier = AutonomyTier[request.autonomy_tier.upper()]
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid autonomy tier: {request.autonomy_tier}",
        )

    # Tool allowlist by tier (simplified)
    # Keys by tier value to avoid unhashable type issues
    allowlist_by_tier = {
        0: {"read", "query"},  # OBSERVE
        1: {"read", "query", "draft"},  # PROPOSE
        2: {"read", "query", "write", "decision"},  # ACT_BOUNDED
        3: {"read", "query", "write", "decision", "transfer"},  # ACT_FULL
    }

    allowed_tools = allowlist_by_tier.get(int(tier), set())

    # Check if tool is in allowlist
    tool_allowed = request.tool_name.lower() in allowed_tools

    # Compute drift (stub for now)
    event_count = db.query(EventModel).filter(EventModel.tenant_id == tenant_id).count()
    drift_score = compute_deterministic_drift_score(event_count, threshold=0.25)

    # Evaluate breaker
    breaker = evaluate_circuit_breaker([drift_score])

    # Decision logic
    if breaker.is_open:
        allowed = False
        reason = f"Circuit breaker open: {breaker.reason}"
    elif not tool_allowed:
        allowed = False
        reason = f"Tool '{request.tool_name}' not allowed for tier {tier.name}"
    else:
        allowed = True
        reason = f"Allowed for tier {tier.name}"

    return PolicyDecision(
        allowed=allowed,
        reason=reason,
        autonomy_tier=tier.name,
        tool_name=request.tool_name,
        drift_status="nominal" if not drift_score.triggered else "elevated",
    )


@router.get("/status", response_model=GovernanceStatus)
async def governance_status(
    db: Session = Depends(get_db),
    tenant_id: str = Header(..., alias="X-Tenant-ID"),
) -> GovernanceStatus:
    """
    Get current governance status for the dashboard.

    Returns autonomy tier assignments, circuit breaker state, and drift metrics.

    Args:
        db: Database session
        tenant_id: Tenant identifier

    Returns:
        GovernanceStatus with all metrics
    """
    # Get events for this tenant
    events = (
        db.query(EventModel)
        .filter(EventModel.tenant_id == tenant_id)
        .order_by(EventModel.id.desc())
        .limit(100)
        .all()
    )

    # Mock agent tiers (in production, would read from database)
    agent_tiers = {
        "GatheringAgent": "OBSERVE",
        "RiskScoreAgent": "ACT_BOUNDED",
        "ApprovalAgent": "PROPOSE",
    }

    # Compute drift score
    event_count = len(events)
    drift_score = compute_deterministic_drift_score(event_count, threshold=0.25)

    # Evaluate breaker
    breaker = evaluate_circuit_breaker([drift_score])

    return GovernanceStatus(
        tenant_id=tenant_id,
        autonomy_tiers=agent_tiers,
        circuit_breaker_open=breaker.is_open,
        circuit_breaker_reason=breaker.reason,
        drift_scores=[
            {
                "detector": drift_score.detector_type.value,
                "score": drift_score.score,
                "threshold": drift_score.threshold,
                "triggered": drift_score.triggered,
            }
        ],
        last_evaluated_at=datetime.utcnow(),
    )
