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
from typing import Optional, Dict, Any
from datetime import datetime
import io

from praman.persistence.database import get_db
from praman.persistence.models import Event as EventModel, Certificate as CertificateModel
from praman.domain.canonical import canonicalise
from praman.domain.hashing import compute_hmac_hex
from praman.domain.merkle import compute_root_hex
from praman.domain.signing import generate_keypair, sign_root_hex

router = APIRouter()


@router.get("/latest")
async def get_latest_certificate(
    db: Session = Depends(get_db),
    tenant_id: str = Header(..., alias="X-Tenant-ID"),
) -> Dict[str, Any]:
    """
    Get the latest Merkle root and certificate metadata.

    Computes the root from all events and returns proof it exists.

    Headers:
        X-Tenant-ID: Unique customer identifier (required)

    Returns:
        JSON with root, signature, sequence range, timestamp.
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

    # Sign the root (STUB: using a fixed key for demo)
    private_key, public_key = generate_keypair()
    signature_hex = sign_root_hex(root_hex, private_key)

    return {
        "tenant_id": tenant_id,
        "merkle_root": root_hex,
        "signature": signature_hex,
        "from_event": events[0].id,
        "to_event": events[-1].id,
        "total_events": len(events),
        "computed_at": datetime.utcnow().isoformat(),
    }


@router.get("/{certificate_id}")
async def get_certificate_pdf(
    certificate_id: int,
    db: Session = Depends(get_db),
    tenant_id: str = Header(..., alias="X-Tenant-ID"),
) -> StreamingResponse:
    """
    Retrieve a certificate as PDF.

    Generates a BSA §63 certificate on demand (not stored).
    Part A is populated automatically. Part B is a template.

    Headers:
        X-Tenant-ID: Unique customer identifier (required)

    Args:
        certificate_id: Certificate ID (or use 'latest')

    Returns:
        PDF file (application/pdf)
    """
    # Get events (for this demo, just generate a new certificate)
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

    # Compute root
    hmacs = [e.hmac_value for e in events]
    root_hex = compute_root_hex(hmacs)

    # Generate PDF (STUB: for now, return a simple text representation)
    pdf_content = generate_certificate_pdf(
        tenant_id=tenant_id,
        root_hex=root_hex,
        from_event=events[0].id,
        to_event=events[-1].id,
        timestamp=datetime.utcnow(),
    )

    return StreamingResponse(
        iter([pdf_content]),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=certificate_{certificate_id}.pdf"},
    )


def generate_certificate_pdf(
    tenant_id: str,
    root_hex: str,
    from_event: int,
    to_event: int,
    timestamp: datetime,
) -> bytes:
    """
    Generate a BSA §63 certificate as PDF (STUB).

    For now, returns a simple text representation.
    In production, uses ReportLab to generate a proper PDF.

    Args:
        tenant_id: Customer identifier
        root_hex: Merkle root (32 bytes as hex)
        from_event: First event in this anchor window
        to_event: Last event in this anchor window
        timestamp: When the certificate was generated

    Returns:
        bytes: PDF content (or text for now)
    """
    # STUB: For now, return a text representation
    # In production, this would use ReportLab to generate a real PDF
    text_content = f"""
BSA §63 CERTIFICATE OF ELECTRONIC RECORD
Generated: {timestamp.isoformat()}

PART A: DESCRIPTION OF THE RECORD

Tenant ID: {tenant_id}
Record Type: Merkle Hash Tree (Digital Evidence)
Hash Algorithm: SHA-256
Hash Value (Root): {root_hex}
Sequence Range: Events {from_event} to {to_event}

This certificate attests that the above hash value was computed from a
Merkle tree constructed over event records in the ledger, as follows:

Each event was canonicalised to deterministic JSON, hashed with HMAC-SHA256
using a client-held key, and chained (each event's HMAC depends on the
previous event's HMAC).

The Merkle root computed from this chain uniquely commits to all events in
the range. Any alteration to any event will change the root, making tampering
detectable.

PART B: ATTESTATION BY PERSON IN CHARGE (TEMPLATE)

To be completed by the customer's authorised representative:

I, __________________ (Name), holding the position of __________________
at {tenant_id}, do hereby attest that:

1. The electronic record system described in Part A was operating properly
   on the date this certificate was generated.

2. The record has not been altered since generation of this certificate.

3. I have authority to make this attestation on behalf of the organisation.

Signature: ___________________________

Date: ___________________________

---

VERIFICATION INSTRUCTIONS

To verify this certificate:

1. Obtain the Merkle root: {root_hex}
2. Retrieve the event records from the ledger
3. Recompute the canonical form of each event
4. Recompute the Merkle tree
5. Verify the root matches the value in this certificate

If the root matches, no events have been altered (tamper-evident).

If the root does not match, at least one event has been changed since
this certificate was generated.

---

STUB NOTICE

This certificate is generated in demonstration mode. Before production use:
1. Obtain legal review of the certificate format
2. Implement RFC 3161 external timestamping
3. Add proper digital signature (currently placeholder)
4. Generate as PDF with proper formatting (not text)

"""
    return text_content.encode("utf-8")


@router.post("/generate")
async def generate_certificate_for_range(
    from_event: int,
    to_event: int,
    db: Session = Depends(get_db),
    tenant_id: str = Header(..., alias="X-Tenant-ID"),
) -> Dict[str, Any]:
    """
    Generate a certificate for a specific range of events.

    Args:
        from_event: First event ID
        to_event: Last event ID

    Returns:
        JSON with certificate metadata and root.
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

    # Sign (STUB: fixed key)
    private_key, public_key = generate_keypair()
    signature_hex = sign_root_hex(root_hex, private_key)

    return {
        "certificate_id": 1,  # STUB: would be persisted
        "tenant_id": tenant_id,
        "merkle_root": root_hex,
        "signature": signature_hex,
        "from_event": from_event,
        "to_event": to_event,
        "total_events": len(events),
        "generated_at": datetime.utcnow().isoformat(),
    }
