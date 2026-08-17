"""
Certificate generation and retrieval routes — GET /certificates.

Responsibility
    Generate BSA §63 certificates on demand.
    Return certificates as PDF (Part A: hash and algorithm, Part B: template).
    Include Merkle root, signature, and verification instructions.

Must not
    Perform cryptography here (call domain/ functions).
    Store PDFs on disk (stream from memory).
    Return personal data (only tenant_id and hashes).

Certificate structure (modelled on BSA §63 Schedule):
    Part A: Description of the record and how it was produced
        - Hash value (Merkle root)
        - Hash algorithm used (SHA-256)
        - Date and time
        - Sequence range
    Part B: Attestation by the person in charge
        - Name of person
        - Signature (to be added by customer)
        - Date of attestation
"""

from fastapi import APIRouter, Depends, HTTPException, Header, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Dict, Any
from datetime import datetime

from praman.dependencies import get_certificate_renderer, get_key_custody
from praman.persistence.database import get_db
from praman.persistence.models import Event as EventModel
from praman.domain.merkle import compute_root_hex
from praman.domain.signing import sign_root_hex
from praman.ports.certificate_renderer import CertificateRenderer
from praman.ports.key_custody import KeyCustody

router = APIRouter()


@router.get("/latest")
async def get_latest_certificate(
    db: Session = Depends(get_db),
    key_custody: KeyCustody = Depends(get_key_custody),
    tenant_id: str = Header(..., alias="X-Tenant-ID"),
) -> Dict[str, Any]:
    """
    Get the latest Merkle root and certificate metadata.

    Computes the root from all events and returns proof it exists.

    Headers:
        X-Tenant-ID: Unique customer identifier (required)

    Returns:
        JSON with root, signature, key_id, sequence range, timestamp.
    """
    # Get all events for this tenant
    events = (
        db.query(EventModel)
        .filter(EventModel.tenant_id == tenant_id)
        .order_by(EventModel.id)
        .all()
    )

    if not events:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No events found for this tenant",
        )

    # Compute root from HMACs
    hmacs = [e.hmac_value for e in events]
    root_hex = compute_root_hex(hmacs)

    # Sign with the process's stable key (see ADR 0014 — this used to call
    # generate_keypair() per request, producing a signature nobody could
    # ever verify because the public key was thrown away with the private
    # key on every call).
    signature_hex = sign_root_hex(root_hex, key_custody.signing_key())

    return {
        "tenant_id": tenant_id,
        "merkle_root": root_hex,
        "signature": signature_hex,
        "key_id": key_custody.key_id(),
        "from_event": events[0].id,
        "to_event": events[-1].id,
        "total_events": len(events),
        "computed_at": datetime.utcnow().isoformat(),
    }


@router.get("/{certificate_id}")
async def get_certificate_pdf(
    certificate_id: int,
    db: Session = Depends(get_db),
    key_custody: KeyCustody = Depends(get_key_custody),
    certificate_renderer: CertificateRenderer = Depends(get_certificate_renderer),
    tenant_id: str = Header(..., alias="X-Tenant-ID"),
) -> StreamingResponse:
    """
    Retrieve a certificate as PDF.

    Generates a BSA §63 certificate on demand (not stored).
    Part A is populated automatically and signed. Part B is a template.

    Headers:
        X-Tenant-ID: Unique customer identifier (required)

    Args:
        certificate_id: Certificate ID (or use 'latest')

    Returns:
        PDF file (application/pdf)
    """
    events = (
        db.query(EventModel)
        .filter(EventModel.tenant_id == tenant_id)
        .order_by(EventModel.id)
        .all()
    )

    if not events:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No events found",
        )

    hmacs = [e.hmac_value for e in events]
    root_hex = compute_root_hex(hmacs)
    signature_hex = sign_root_hex(root_hex, key_custody.signing_key())

    pdf_content = certificate_renderer.render(
        tenant_id=tenant_id,
        root_hex=root_hex,
        signature_hex=signature_hex,
        key_id=key_custody.key_id(),
        from_event=events[0].id,
        to_event=events[-1].id,
        generated_at=datetime.utcnow(),
    )

    return StreamingResponse(
        iter([pdf_content]),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=certificate_{certificate_id}.pdf"},
    )


@router.post("/generate")
async def generate_certificate_for_range(
    from_event: int,
    to_event: int,
    db: Session = Depends(get_db),
    key_custody: KeyCustody = Depends(get_key_custody),
    tenant_id: str = Header(..., alias="X-Tenant-ID"),
) -> Dict[str, Any]:
    """
    Generate a certificate for a specific range of events.

    Args:
        from_event: First event ID
        to_event: Last event ID

    Returns:
        JSON with certificate metadata, root, and key_id.
    """
    # Get events in range
    events = (
        db.query(EventModel)
        .filter(
            EventModel.tenant_id == tenant_id,
            EventModel.id >= from_event,
            EventModel.id <= to_event,
        )
        .order_by(EventModel.id)
        .all()
    )

    if not events:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No events found for range [{from_event}, {to_event}]",
        )

    # Compute root
    hmacs = [e.hmac_value for e in events]
    root_hex = compute_root_hex(hmacs)

    # Sign with the process's stable key (see ADR 0014).
    signature_hex = sign_root_hex(root_hex, key_custody.signing_key())

    return {
        "certificate_id": 1,  # STUB: would be persisted
        "tenant_id": tenant_id,
        "merkle_root": root_hex,
        "signature": signature_hex,
        "key_id": key_custody.key_id(),
        "from_event": from_event,
        "to_event": to_event,
        "total_events": len(events),
        "generated_at": datetime.utcnow().isoformat(),
    }
