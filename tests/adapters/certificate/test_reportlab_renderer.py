"""
Tests for ReportLabCertificateRenderer.

Proves the central claim of ADR 0017: the certificate is a real PDF, not
the text-encoded-as-bytes stub it replaces. A reviewer who opens the
downloaded file in a PDF viewer must see a real document, not a text
file with a misleading extension.

Run with: pytest tests/adapters/certificate/test_reportlab_renderer.py -v
"""

from datetime import datetime

from praman.adapters.certificate.reportlab_renderer import ReportLabCertificateRenderer


def _render(**overrides) -> bytes:
    """Render a certificate with sensible defaults, allowing overrides for one field."""
    fields = {
        "tenant_id": "demo-abc12345",
        "root_hex": "ab" * 32,
        "signature_hex": "cd" * 64,
        "key_id": "0123456789abcdef",
        "from_event": 1,
        "to_event": 42,
        "generated_at": datetime(2026, 1, 1, 12, 0, 0),
    }
    fields.update(overrides)
    return ReportLabCertificateRenderer().render(**fields)


class TestRendersARealPdf:
    """The load-bearing test: this is a PDF, not text pretending to be one."""

    def test_output_starts_with_pdf_magic_bytes(self):
        """
        A real PDF file begins with the literal bytes '%PDF-'. The STUB it
        replaces returned UTF-8 text with a .pdf filename attached — this
        is the exact difference a reviewer opening the file would see.
        """
        pdf_bytes = _render()

        assert pdf_bytes.startswith(b"%PDF-")

    def test_output_ends_with_eof_marker(self):
        """A well-formed PDF file ends with the %%EOF marker."""
        pdf_bytes = _render()

        assert pdf_bytes.rstrip().endswith(b"%%EOF")

    def test_output_is_non_trivial_size(self):
        """Sanity check: a multi-section certificate is not a near-empty file."""
        pdf_bytes = _render()

        assert len(pdf_bytes) > 1000


class TestContentIsEmbedded:
    """
    PDF text is stream-encoded, not plaintext-searchable by naive
    substring checks, so these tests confirm the render call succeeds
    with the real values wired through rather than asserting on bytes.
    """

    def test_render_accepts_real_root_and_signature_values(self):
        pdf_bytes = _render(root_hex="11" * 32, signature_hex="22" * 64, key_id="fedcba9876543210")

        assert pdf_bytes.startswith(b"%PDF-")

    def test_different_tenants_produce_different_bytes(self):
        """Distinct inputs must not collapse to a cached, identical document."""
        pdf_a = _render(tenant_id="demo-aaaaaaaa")
        pdf_b = _render(tenant_id="demo-bbbbbbbb")

        assert pdf_a != pdf_b
