"""
Demo-only routes that prove the ledger's append-only guarantee live.

Responsibility
    Let a visitor issue a real UPDATE against the events table and see
    PostgreSQL's own rejection, so the tamper-evidence claim does not rest
    on trusting anything our application code says about it.

Must not
    Ever commit a mutation. The UPDATE this router issues is always rolled
    back, in a finally block, regardless of whether it raised.
    Accept a request outside the demo tenant namespace (see
    _require_demo_tenant below) — a real customer's ledger is never a
    target for this endpoint, under any configuration.
    Run at all unless settings.demo_mode_enabled is explicitly True.

Why this file is separate from events.py
    Everything here exists to be deleted or disabled without touching a
    single line of the real ledger-write path. Mixing "endpoint that
    proves tampering fails" into "endpoint that writes real evidence"
    would make it one accidental refactor away from the two blurring
    together.

See also
    docs/ADR/0015-demo-tamper-endpoint.md — the safety design and the
    rejected alternative (faking the error message client-side).
"""

import re

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from praman.config import settings
from praman.persistence.database import get_db

router = APIRouter()

# Demo tenant ids are always of this shape (see frontend/demo.html's
# per-session tenant generator). Anything else is rejected outright —
# this is the second, independent line of defense alongside the query's
# own tenant scoping below.
_DEMO_TENANT_PATTERN = re.compile(r"^demo-[a-z0-9]{8}$")


class TamperAttemptRequest(BaseModel):
    """What the visitor wants to (fail to) change."""

    event_id: int = Field(..., description="The event row to attempt to alter")
    new_payload: str = Field(
        ...,
        max_length=1000,
        description="Arbitrary replacement text for event_type, to prove even "
        "a trivial edit is rejected",
    )


def _require_demo_mode_enabled() -> None:
    """
    Raise 404 (not 403) when demo mode is off.

    404, not 403: an endpoint that is disabled should not confirm its own
    existence to a caller probing for it. A customer deployment running
    with demo_mode_enabled=False should look, from the outside, like this
    route was never registered.
    """
    if not settings.demo_mode_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)


def _require_demo_tenant(tenant_id: str) -> str:
    """
    Reject any tenant id that is not a demo tenant.

    This is deliberately a hard 403, not a soft filter — a real customer's
    tenant_id must never reach the tamper-attempt code path, regardless of
    what demo_mode_enabled is set to.
    """
    if not _DEMO_TENANT_PATTERN.match(tenant_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint only operates on demo tenants (tenant_id "
            "matching 'demo-<8 lowercase alphanumeric chars>').",
        )
    return tenant_id


@router.post("/tamper-attempt")
async def tamper_attempt(
    body: TamperAttemptRequest,
    db: Session = Depends(get_db),
    tenant_id: str = Header(..., alias="X-Tenant-ID"),
    _demo_mode: None = Depends(_require_demo_mode_enabled),
) -> dict:
    """
    Attempt to UPDATE one event's row, then roll the attempt back.

    Issues a genuine UPDATE — not a simulated one — against the events
    table. The database's own append-only trigger rejects it; this
    handler's only job is to report exactly what PostgreSQL said, inside
    a SAVEPOINT that is unconditionally rolled back.

    Safety, all four independent and all required (see ADR 0015):
        1. 404 when settings.demo_mode_enabled is False.
        2. tenant_id must match the demo tenant pattern (403 otherwise).
        3. The UPDATE's WHERE clause is scoped to (tenant_id, event_id)
           together — not event_id alone — so this endpoint cannot reach
           a row belonging to a different tenant even if the trigger were
           somehow absent. A caller passing another tenant's event_id
           gets 404 (no row matched), never a write attempt against it.
        4. The UPDATE runs inside an explicit SAVEPOINT, rolled back in a
           finally block whether the statement raised or not.

    Args:
        body: event_id to target and a replacement payload string.
        db: Database session (injected).
        tenant_id: Caller's tenant, from X-Tenant-ID header. Must be a
            demo tenant.

    Returns:
        The raw outcome of the attempt: whether it succeeded (it must
        not), PostgreSQL's own error text and SQLSTATE, and a plain-word
        explanation of the mechanism.

    Raises:
        HTTPException 404: demo mode disabled, or event_id does not
            belong to this tenant.
        HTTPException 403: tenant_id is not a demo tenant.
    """
    _require_demo_tenant(tenant_id)

    savepoint = db.begin_nested()
    try:
        # Tenant-scoped: this WHERE clause is the structural guarantee that
        # this endpoint can never touch a row outside the caller's own
        # tenant, independent of the append-only trigger. If the trigger
        # were ever dropped, this scoping is what stands between "the
        # demo's tamper button" and "a real cross-tenant write."
        result = db.execute(
            text(
                "UPDATE events SET event_type = :new_payload "
                "WHERE tenant_id = :tenant_id AND id = :event_id"
            ),
            {
                "new_payload": body.new_payload,
                "tenant_id": tenant_id,
                "event_id": body.event_id,
            },
        )

        if result.rowcount == 0:
            # Not a trigger rejection — there was simply no row for this
            # tenant at this id. Conflating the two would misrepresent
            # what happened: "we tried and Postgres blocked it" is a
            # different claim from "there was nothing here to try."
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No event {body.event_id} found for this demo tenant.",
            )

        # If we reach here, the UPDATE was NOT rejected. That is the
        # append-only trigger failing to do its job — report it plainly
        # rather than let the finally-block rollback hide the failure.
        return {
            "attempted": True,
            "succeeded": True,
            "database_error": None,
            "sql_state": None,
            "explanation": (
                "The UPDATE was not rejected by the database. This means "
                "the append-only trigger is missing or misconfigured — "
                "this is a real finding, not expected demo behaviour."
            ),
        }

    except DBAPIError as exc:
        original = exc.orig
        sql_state = getattr(original, "pgcode", None)
        database_error = str(original).strip()

        return {
            "attempted": True,
            "succeeded": False,
            "database_error": database_error,
            "sql_state": sql_state,
            "explanation": (
                "The ledger table has a BEFORE UPDATE OR DELETE trigger that "
                "raises an exception. This is enforced by PostgreSQL, not by "
                "application code, so it holds even for a caller with direct "
                "database access."
            ),
        }
    finally:
        # Unconditional: whether the UPDATE raised, returned 0 rows, or
        # (should the trigger ever be absent) actually succeeded, this
        # attempt is never allowed to become a committed change.
        savepoint.rollback()
