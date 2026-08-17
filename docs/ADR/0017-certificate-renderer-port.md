# ADR 0017: Certificate rendering behind a port, real PDF via ReportLab

**Status:** Accepted
**Date:** 2026-08-17

## Context

`api/routers/certificates.py`'s `GET /certificates/{certificate_id}` called an
inline `generate_certificate_pdf()` function that was, despite its name, not
a PDF generator. It built an f-string of certificate text, encoded it as
UTF-8 bytes, and streamed it back with `media_type="application/pdf"` and a
`.pdf` filename. A reviewer who downloaded the file and opened it in a PDF
viewer would find a document that fails to open, or opens as garbled text
depending on the viewer's tolerance for mislabeled content — either way, the
first thing a technical reviewer checks about a "certificate" fails.

The content itself (Part A record description, Part B attestation template,
verification instructions) was already correct — this was a format problem,
not a content problem. `reportlab` was already a pinned dependency
(`requirements.txt`), unused anywhere in the codebase before this change.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Fix `generate_certificate_pdf()` in place to call ReportLab directly | Smallest diff | Hardcodes the rendering choice inside a router — the exact anti-pattern CLAUDE.md §4 exists to prevent, and forecloses HTML output for a future customer whose tooling parses HTML rather than PDF |
| **Port + adapter (chosen)** | Matches the `KeyCustody` precedent (ADR 0014); swapping to an HTML renderer later is a new adapter file plus one `factories.py` branch | More files up front for what is currently a single-adapter concern |

## Decision

`CertificateRenderer` is a `Protocol` in `ports/certificate_renderer.py` with
one method: `render(tenant_id, root_hex, signature_hex, key_id, from_event,
to_event, generated_at) -> bytes`. `ReportLabCertificateRenderer`
(`adapters/certificate/reportlab_renderer.py`) implements it using
`reportlab.platypus` (`SimpleDocTemplate`, `Paragraph`, `Table`), producing a
real PDF starting with the `%PDF-` magic bytes.

`config.py` adds `certificate_renderer_provider: str = "reportlab"`.
`factories.py`'s `build_certificate_renderer(settings)` selects the adapter
by that string, raising `ValueError` on an unknown provider — the same
fail-loudly contract `build_key_custody` already uses. `dependencies.py`
constructs one `ReportLabCertificateRenderer` at import time and exposes it
via `get_certificate_renderer()`.

The router now injects both `KeyCustody` and `CertificateRenderer`, signs the
root itself (previously `get_certificate_pdf` never signed anything — Part A
lacked a signature entirely), and passes the real `signature_hex` and
`key_id` into the renderer so a reader can fetch the matching public key
from `GET /keys/public` and verify the certificate independently.

## Rationale

1. **The format was the whole defect.** No cryptography changed — the
   Merkle root and signature were already computed correctly elsewhere in
   the router. This ADR is scoped to rendering only, which is why it does
   not touch `domain/merkle.py` or `domain/signing.py`.
2. **The signature was missing from the PDF before this change**, which
   this ADR also fixes as a side effect of routing real values through the
   renderer's signature. A certificate that describes a hash but omits the
   signature over it cannot be independently verified — that gap closes
   here, not as a separate change, because the renderer's `render()`
   signature requires `signature_hex` as an argument.
3. **One adapter ships, matching CLAUDE.md's Strategy table**, which already
   named "HTML/PDF, other jurisdictions" as the documented future variation
   before this port existed. Nothing here anticipates a jurisdiction this
   product does not yet serve; it only stops hardcoding the one that ships.

## Consequences

**Easy:**
- `GET /certificates/{id}` now returns a real, openable PDF with an
  embedded signature and key ID.
- Adding an HTML renderer later is one new adapter file and one
  `factories.py` branch.

**Hard:**
- `certificate_id` in `POST /certificates/generate` remains a hardcoded
  stub (`1`) — this ADR did not touch persistence, and bundling that fix in
  here would have mixed an unrelated change into a format fix. Tracked
  separately in `docs/LIMITATIONS.md`.

## Revisit when

- A customer's internal tooling requires HTML instead of PDF (implement a
  new adapter; the port already supports it).
- Certificate generations need to be queryable after the fact (requires the
  `certificate_id` persistence fix noted above — a `services/` and
  `persistence/` change, not a rendering change).
