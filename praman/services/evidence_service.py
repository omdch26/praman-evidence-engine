"""
Assembly of independently-verifiable evidence bundles.

Responsibility
    Fetch a tenant's events, compute the canonical JSON and Merkle root,
    sign it, and shape the result into the bundle format an offline
    verifier (browser or standalone script) can check without further
    calls back to us.

Must not
    Perform hashing, canonicalisation, or signing itself — call domain/
    functions for all of it. This file sequences calls; it does not
    compute anything.
    Write raw SQL (use the injected db.Session's ORM query interface, as
    every other service in this codebase does).
"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from praman.domain.canonical import canonicalise
from praman.domain.merkle import compute_root_hex
from praman.domain.signing import sign_root_hex
from praman.persistence.models import Event as EventModel
from praman.ports.key_custody import KeyCustody

# STUB: same fixed demo HMAC key as api/routers/events.py and
# services/event_logger.py. Disclosed in docs/LIMITATIONS.md. A bundle
# assembled for a tenant using a real per-tenant key would need that
# tenant's key here instead — which by design this service would not hold,
# meaning bundle-based verification for a real key-custody deployment is a
# capability that does not exist yet. See docs/VERIFICATION.md.
_DEMO_HMAC_KEY = b"\x00" * 32

_BUNDLE_VERSION = "1.0"


def build_evidence_bundle(db: Session, tenant_id: str, key_custody: KeyCustody) -> dict[str, Any]:
    """
    Assemble a complete, independently-verifiable evidence bundle for one
    tenant's full event history.

    Args:
        db: Database session (injected).
        tenant_id: Tenant to assemble the bundle for.
        key_custody: Provides the signing key and key_id (see ADR 0014).

    Returns:
        A dict matching the evidence bundle schema documented in
        docs/VERIFICATION.md and echoed in the CLAUDE_CODE_PROMPT brief:
        bundle_version, tenant_id, generated_at, algorithms, events (with
        exact canonical_json bytes per event), merkle_root, signature,
        key_id, and a link to human-readable verification instructions.

    Raises:
        ValueError: If the tenant has no events (nothing to bundle).
    """
    events = (
        db.query(EventModel)
        .filter(EventModel.tenant_id == tenant_id)
        .order_by(EventModel.id)
        .all()
    )

    if not events:
        raise ValueError(f"No events found for tenant {tenant_id!r}; nothing to bundle.")

    bundle_events = [
        {
            "sequence": index,
            # Recomputed fresh from the stored (JSONB) canonical_event, not
            # read back as a stored string — JSONB does not preserve the
            # original byte serialisation, but re-canonicalising the
            # retrieved dict reproduces identical bytes because
            # canonicalise() is content-deterministic (sorted keys,
            # compact separators), not order-dependent on the source.
            # Verified in tests/services/test_evidence_service.py.
            "canonical_json": canonicalise(event.canonical_event).decode("utf-8"),
            "hmac_value": event.hmac_value,
        }
        for index, event in enumerate(events)
    ]

    hmac_values = [event.hmac_value for event in events]
    merkle_root_hex = compute_root_hex(hmac_values)
    signature_hex = sign_root_hex(merkle_root_hex, key_custody.signing_key())

    return {
        "bundle_version": _BUNDLE_VERSION,
        "tenant_id": tenant_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "algorithms": {
            "canonicalisation": "RFC 8785-style JCS (sorted keys, compact separators, NFC unicode)",
            "leaf_hash": "SHA-256 with 0x00 domain-separation prefix",
            "node_hash": "SHA-256 with 0x01 domain-separation prefix",
            "signature": "Ed25519",
            "hmac_chain_key": (
                "STUB: fixed 32-byte all-zero key, disclosed in docs/LIMITATIONS.md. "
                "A production per-tenant-key deployment would not publish this."
            ),
        },
        "events": bundle_events,
        "merkle_root": merkle_root_hex,
        "signature": signature_hex,
        "key_id": key_custody.key_id(),
        "verification_instructions_url": (
            "https://github.com/omdch26/praman-evidence-engine/blob/main/docs/VERIFICATION.md"
        ),
    }
