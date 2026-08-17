"""
Evidence bundle retrieval — GET /evidence/bundle.

Responsibility
    Return everything an offline verifier needs to independently confirm
    a tenant's ledger is tamper-evident, in one response.

Must not
    Contain assembly logic itself (that is services/evidence_service.py).
    Require the caller to trust anything beyond what is in the response
    plus GET /keys/public — no follow-up call to us should be necessary
    to verify what this endpoint returns.
"""

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from praman.dependencies import get_key_custody
from praman.persistence.database import get_db
from praman.ports.key_custody import KeyCustody
from praman.services.evidence_service import build_evidence_bundle

router = APIRouter()


@router.get("/bundle")
async def get_evidence_bundle(
    db: Session = Depends(get_db),
    key_custody: KeyCustody = Depends(get_key_custody),
    tenant_id: str = Header(..., alias="X-Tenant-ID"),
) -> dict:
    """
    Return the full, independently-verifiable evidence bundle for one tenant.

    Headers:
        X-Tenant-ID: Which tenant's ledger to bundle.

    Returns:
        See services/evidence_service.py's build_evidence_bundle() for the
        exact schema. Includes exact canonical JSON bytes per event, the
        Merkle root, the Ed25519 signature over it, and the key_id needed
        to fetch the matching public key from GET /keys/public.

    Raises:
        HTTPException 404: The tenant has no events to bundle.
    """
    try:
        return build_evidence_bundle(db, tenant_id, key_custody)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
