"""
BSA §63 certificate rendering via ReportLab — produces a real PDF.

Responsibility
    Implement CertificateRenderer.render() by laying out Part A (record
    description, hash value, algorithm, sequence range, key ID — all
    populated from real data) and Part B (an unsigned attestation
    template for the customer's authorised officer) as an actual PDF
    document.

Must not
    Sign or hash anything — the caller already computed the root and
    signature; this file only lays out bytes on a page.
    Write to disk. render() returns bytes; the caller decides whether
    those bytes are streamed, cached, or discarded.

Why ReportLab
    Already a pinned dependency (requirements.txt) with no other adapter
    using it until now. Produces standards-compliant PDF/A-adjacent output
    without a browser or headless-Chromium dependency, which matters for a
    process running on Render's free tier.
"""

from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


class ReportLabCertificateRenderer:
    """Implements CertificateRenderer using ReportLab's platypus layout engine."""

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
        Build the certificate PDF and return its bytes.

        Layout mirrors the wording of the text this replaces (see git
        history on api/routers/certificates.py's former
        generate_certificate_pdf STUB) — the content was already correct;
        only the format was fake. Part B is deliberately left with blank
        attestation lines; nothing here should ever pre-fill a signatory's
        name or claim an attestation happened that did not.
        """
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            topMargin=20 * mm,
            bottomMargin=20 * mm,
            leftMargin=20 * mm,
            rightMargin=20 * mm,
        )

        styles = getSampleStyleSheet()
        heading_style = ParagraphStyle(
            "CertHeading",
            parent=styles["Heading1"],
            fontSize=14,
            spaceAfter=6 * mm,
        )
        section_style = ParagraphStyle(
            "CertSection",
            parent=styles["Heading2"],
            fontSize=11,
            spaceBefore=6 * mm,
            spaceAfter=3 * mm,
        )
        body_style = ParagraphStyle(
            "CertBody",
            parent=styles["Normal"],
            fontSize=9.5,
            leading=13,
        )
        mono_style = ParagraphStyle(
            "CertMono",
            parent=styles["Normal"],
            fontName="Courier",
            fontSize=8,
            leading=11,
        )

        elements = []

        elements.append(Paragraph("BSA §63 CERTIFICATE OF ELECTRONIC RECORD", heading_style))
        elements.append(Paragraph(f"Generated: {generated_at.isoformat()}", body_style))
        elements.append(Spacer(1, 6 * mm))

        elements.append(Paragraph("PART A: DESCRIPTION OF THE RECORD", section_style))
        part_a_rows = [
            ["Tenant ID", tenant_id],
            ["Record Type", "Merkle Hash Tree (Digital Evidence)"],
            ["Hash Algorithm", "SHA-256"],
            ["Hash Value (Root)", root_hex],
            ["Ed25519 Signature", signature_hex],
            ["Signing Key ID", key_id],
            ["Sequence Range", f"Events {from_event} to {to_event}"],
        ]
        part_a_table = Table(part_a_rows, colWidths=[45 * mm, 120 * mm])
        part_a_table.setStyle(
            TableStyle(
                [
                    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                    ("FONTNAME", (1, 0), (1, -1), "Courier"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#e5e7eb")),
                ]
            )
        )
        elements.append(part_a_table)
        elements.append(Spacer(1, 4 * mm))

        elements.append(
            Paragraph(
                "This certificate attests that the above hash value was computed from a "
                "Merkle tree constructed over event records in the ledger, as follows:",
                body_style,
            )
        )
        elements.append(
            Paragraph(
                "Each event was canonicalised to deterministic JSON, hashed with HMAC-SHA256 "
                "using a client-held key, and chained (each event's HMAC depends on the "
                "previous event's HMAC).",
                body_style,
            )
        )
        elements.append(
            Paragraph(
                "The Merkle root computed from this chain uniquely commits to all events in "
                "the range. Any alteration to any event will change the root, making tampering "
                "detectable.",
                body_style,
            )
        )
        elements.append(Spacer(1, 6 * mm))

        elements.append(Paragraph("PART B: ATTESTATION BY PERSON IN CHARGE (TEMPLATE)", section_style))
        elements.append(
            Paragraph(
                "To be completed by the customer's authorised representative:",
                body_style,
            )
        )
        elements.append(Spacer(1, 3 * mm))
        elements.append(
            Paragraph(
                f"I, {'_' * 30} (Name), holding the position of {'_' * 25} "
                f"at {tenant_id}, do hereby attest that:",
                body_style,
            )
        )
        elements.append(Spacer(1, 2 * mm))
        for point in (
            "1. The electronic record system described in Part A was operating properly "
            "on the date this certificate was generated.",
            "2. The record has not been altered since generation of this certificate.",
            "3. I have authority to make this attestation on behalf of the organisation.",
        ):
            elements.append(Paragraph(point, body_style))
        elements.append(Spacer(1, 8 * mm))
        elements.append(Paragraph(f"Signature: {'_' * 40}", body_style))
        elements.append(Paragraph(f"Date: {'_' * 40}", body_style))
        elements.append(Spacer(1, 6 * mm))

        elements.append(Paragraph("VERIFICATION INSTRUCTIONS", section_style))
        for step in (
            f"1. Obtain the Merkle root: {root_hex}",
            "2. Retrieve the event records from the ledger",
            "3. Recompute the canonical form of each event",
            "4. Recompute the Merkle tree",
            "5. Verify the root matches the value in this certificate",
            f"6. Fetch the public key for key_id {key_id} from GET /keys/public and verify "
            "the signature against the recomputed root",
        ):
            elements.append(Paragraph(step, mono_style))
        elements.append(Spacer(1, 3 * mm))
        elements.append(
            Paragraph(
                "If the root matches and the signature verifies, no events have been altered. "
                "If either check fails, at least one event has been changed since this "
                "certificate was generated. See docs/VERIFICATION.md for the full worked "
                "example.",
                body_style,
            )
        )
        elements.append(Spacer(1, 6 * mm))

        elements.append(Paragraph("DISCLOSED LIMITATIONS", section_style))
        elements.append(
            Paragraph(
                "This certificate's timestamp is self-asserted from the issuing system's "
                "clock, not an independent Timestamping Authority (RFC 3161 anchoring is "
                "designed but not implemented — see docs/LIMITATIONS.md). Part B is an "
                "unsigned template; it becomes an attestation only once the named officer "
                "signs it after their own legal review.",
                body_style,
            )
        )

        doc.build(elements)
        return buffer.getvalue()
