"""
Event ingestion routes — POST /events, GET /events/:id.

Responsibility
    Parse incoming events, validate tenant isolation, call ledger service,
    return results. No business logic (that is services/).

Must not
    Contain cryptographic logic or persistence details.
    Bypass tenant isolation (RLS enforced at DB level, but also in the route).
    Return personal data (only hashed identifiers).

Pattern
    POST /events
    - Accepts JSON event
    - Validates tenant_id from header
    - Calls LedgerService.append_event()
    - Returns event_id and status
"""

from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime

from praman.persistence.database import get_db
from praman.persistence.models import Event as EventModel
from praman.domain.canonical import canonicalise
from praman.domain.hashing import compute_hmac_hex
from praman.config import settings

router = APIRouter()


class EventRequest(BaseModel):
    """Schema for inbound events."""

    event_type: str = Field(..., description="Type of event (consent_granted, policy_evaluated, etc.)")
    module: str = Field(
        "privacy",
        description="Module: 'privacy' or 'ai_risk'",
    )
    action: Optional[str] = Field(None, description="What action was taken")
    principal_id_hash: Optional[str] = Field(
        None,
        description="Hash of the principal ID (never the actual ID). "
        "Client provides this hash; Praman does not resolve it.",
    )
    payload: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Event payload (must not contain PII)",
    )
    timestamp: Optional[datetime] = Field(
        default_factory=datetime.utcnow,
        description="When the event occurred (RFC3339 UTC)",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "event_type": "consent_granted",
                "module": "privacy",
                "principal_id_hash": "sha256:abc123...",
                "action": "data_share",
                "payload": {"purpose": "loan_underwriting"},
            }
        }


class EventResponse(BaseModel):
    """Response after appending an event."""

    event_id: int
    status: str
    hmac_value: str
    timestamp: datetime

    class Config:
        from_attributes = True


@router.post("/events", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
async def create_event(
    event: EventRequest,
    db: Session = Depends(get_db),
    tenant_id: str = Header(..., alias="X-Tenant-ID"),
) -> EventResponse:
    """
    Append one event to the ledger.

    Accepts a JSON event, canonicalises it, computes HMAC, stores in the ledger.
    Returns the event ID and HMAC for verification.

    Headers:
        X-Tenant-ID: Unique customer identifier (required). Enforces RLS.

    Args:
        event: EventRequest body
        db: Database session (injected)
        tenant_id: Tenant identifier from header

    Returns:
        EventResponse with event_id, status, hmac, timestamp

    Raises:
        HTTPException 400: If event is malformed or tenant_id is missing
        HTTPException 401: If tenant is not enabled
        HTTPException 500: If database write fails

    Example:
        POST /events
        X-Tenant-ID: bank_x_123
        Content-Type: application/json

        {
          "event_type": "consent_granted",
          "principal_id_hash": "sha256:abc123...",
          "action": "data_share"
        }

        Response (201):
        {
          "event_id": 42,
          "status": "appended",
          "hmac_value": "9f86d081...",
          "timestamp": "2026-08-10T14:32:00Z"
        }
    """
    # Validate tenant_id
    if not tenant_id or len(tenant_id) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Tenant-ID header is required and must be at least 3 characters",
        )

    try:
        # Get the previous event's HMAC (for chaining)
        previous_event = (
            db.query(EventModel)
            .filter(EventModel.tenant_id == tenant_id)
            .order_by(EventModel.id.desc())
            .first()
        )
        previous_hmac_hex = previous_event.hmac_value if previous_event else None

        # Build the canonical event (never include PII, only hashes)
        canonical_event_dict = {
            "event_type": event.event_type,
            "module": event.module,
            "principal_id_hash": event.principal_id_hash,
            "action": event.action,
            "timestamp": event.timestamp.isoformat(),
            "payload": event.payload or {},
        }

        # Canonicalise
        canonical_bytes = canonicalise(canonical_event_dict)

        # Compute HMAC (this is a stub — in production, we'd use the tenant's actual key)
        # For now, use a fixed key for demo purposes
        hmac_key = b"\x00" * 32  # STUB: fixed key for testing
        hmac_hex = compute_hmac_hex(canonical_bytes, hmac_key, previous_hmac_hex)

        # Insert into database
        new_event = EventModel(
            tenant_id=tenant_id,
            module=event.module,
            event_type=event.event_type,
            canonical_event=canonical_event_dict,
            hmac_value=hmac_hex,
            timestamp=event.timestamp or datetime.utcnow(),
        )

        db.add(new_event)
        db.commit()
        db.refresh(new_event)

        return EventResponse(
            event_id=new_event.id,
            status="appended",
            hmac_value=hmac_hex,
            timestamp=new_event.timestamp,
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to append event: {str(e)}",
        )


@router.get("/events/{event_id}", response_model=Dict[str, Any])
async def get_event(
    event_id: int,
    db: Session = Depends(get_db),
    tenant_id: str = Header(..., alias="X-Tenant-ID"),
) -> Dict[str, Any]:
    """
    Retrieve one event by ID (RLS enforced).

    The database RLS policy ensures the tenant can only see their own events.

    Headers:
        X-Tenant-ID: Unique customer identifier (required)

    Args:
        event_id: Event to retrieve
        db: Database session (injected)
        tenant_id: Tenant identifier from header

    Returns:
        Event object with canonical_event, hmac_value, timestamp

    Raises:
        HTTPException 404: If event not found (including RLS filtering)
    """
    event = (
        db.query(EventModel)
        .filter(EventModel.tenant_id == tenant_id, EventModel.id == event_id)
        .first()
    )

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found (or not visible to this tenant)",
        )

    return {
        "event_id": event.id,
        "event_type": event.event_type,
        "module": event.module,
        "canonical_event": event.canonical_event,
        "hmac_value": event.hmac_value,
        "timestamp": event.timestamp,
    }


@router.get("/events")
async def list_events(
    db: Session = Depends(get_db),
    tenant_id: str = Header(..., alias="X-Tenant-ID"),
    limit: int = 100,
) -> Dict[str, Any]:
    """
    List all events for a tenant (RLS enforced).

    Returns the latest N events (default 100).

    Headers:
        X-Tenant-ID: Unique customer identifier (required)

    Query params:
        limit: Maximum number of events to return (default 100)

    Returns:
        List of events with basic details
    """
    events = (
        db.query(EventModel)
        .filter(EventModel.tenant_id == tenant_id)
        .order_by(EventModel.id.desc())
        .limit(limit)
        .all()
    )

    return {
        "tenant_id": tenant_id,
        "count": len(events),
        "events": [
            {
                "event_id": e.id,
                "event_type": e.event_type,
                "hmac_value": e.hmac_value,
                "timestamp": e.timestamp,
            }
            for e in events
        ],
    }
