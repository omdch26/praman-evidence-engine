"""
Contract for rendering a BSA §63 certificate as a downloadable document.

Responsibility
    Turn a signed Merkle root and its supporting metadata into bytes a
    customer can download, print, and attach to a court filing or
    regulatory submission.

Must not
    Perform cryptography (hashing, signing) — the caller supplies an
    already-computed root, signature, and key_id; this port only renders
    them into a document.
    Touch the database or the network. Rendering is a pure transform from
    structured data to bytes.

Why this is an interface
    The concrete format is not a settled question. ReportLab-generated PDF
    ships first because it is the format a bank's legal and compliance
    teams expect for a court exhibit. A customer in a different
    jurisdiction, or one whose internal tooling parses HTML rather than
    PDF, is a foreseeable variation — not a hypothetical one, per CLAUDE.md
    §4's Strategy table, which already named "HTML/PDF, other
    jurisdictions" as the documented alternative before this port existed.
    Keeping rendering behind a Protocol means adding that alternative is a
    new adapter file plus one factories.py branch, not a rewrite of the
    route that calls it.
"""

from datetime import datetime
from typing import Protocol


class CertificateRenderer(Protocol):
    """Renders certificate data into a downloadable document's bytes."""

    def render(
        self,
        tenant_id: str,
        root_hex: str,
        signature_hex: str,
        key_id: str,
        from_event: int,
        to_event: int,
        generated_at: datetime,
    ) -> bytes:
        """
        Render one certificate.

        Args:
            tenant_id: Which customer this certificate is for.
            root_hex: The Merkle root this certificate attests to (hex).
            signature_hex: Ed25519 signature over the root (hex).
            key_id: Identifies which public key verifies the signature —
                see ports/key_custody.py. Included so a reader can fetch
                the matching key from GET /keys/public independently.
            from_event: First event ID in the range this root commits to.
            to_event: Last event ID in the range this root commits to.
            generated_at: When this certificate was produced. Self-asserted
                from the system clock — see docs/LIMITATIONS.md's RFC 3161
                disclosure; this port does not change that limitation, it
                only renders whatever timestamp it is given.

        Returns:
            The rendered document's bytes (PDF for the adapter that ships
            now; a future adapter could return HTML bytes instead — the
            caller only needs to know the content-type that adapter emits,
            which is not this Protocol's concern).
        """
        ...
