# ADR 0016: Verification runs in the visitor's browser, not just on our server

**Status:** Accepted
**Date:** 2026-08-16

## Context

Every claim Praman makes about tamper-evidence — the root, the signature,
the "this would fail" demonstration — was, before this ADR, something the
server told the visitor. A technical reviewer's correct objection: *"You
are the one making the claim. Why would I believe your server's own
assertion about your server's own integrity?"*

No amount of additional server-side assertion answers that objection,
because every additional assertion is still us talking. The only answer is
moving the actual check into code the visitor runs themselves, using
inputs (a public key, a bundle of canonical event data) they can inspect
before trusting.

## Decision

Two complementary things ship:

1. **`domain/verification.py`** — pure verification logic, importable and
   testable server-side, that recomputes a Merkle root from raw event data
   and checks a signature against the *recomputed* root (never the
   server's claimed root — see that module's docstring on why that
   distinction is the entire point).
2. **Client-side verification in the browser**, using native WebCrypto
   (`crypto.subtle`), reimplementing the same algorithm in JavaScript so
   it runs entirely in the visitor's own browser, with no call back to us
   required to reach a verdict.

The two implementations are not the same code — the browser cannot import
Python. They are the same *specification*, checked against the same
worked examples (see `docs/VERIFICATION.md`), so drift between them would
show up as a test failure, not a silent divergence a reviewer discovers
independently.

## Options considered

| Option | Pros | Cons | Chosen? |
|---|---|---|---|
| Server-side verification only, exposed as an API a visitor can call | Simpler; one implementation | Still requires trusting our server to run the check honestly — a malicious or compromised server could report "verified: true" regardless of the actual data | No |
| **Client-side (WebCrypto) verification, server-side domain logic for reuse (chosen)** | The visitor's own browser reaches the verdict; nothing to trust beyond the crypto primitives and their own eyes on the network tab | Two implementations of the same algorithm to keep in sync | Yes |
| Ship a compiled WASM verifier instead of hand-written JS | One implementation, not two | Opaque to a reviewer who wants to read the actual verification code — "trust our WASM blob" is not meaningfully different from "trust our server" for a non-expert reviewer, and worse for an expert one who can read JS but not disassemble WASM at a glance | No |

The rejected option that matters most: **server-side-only verification is
weaker for a structural reason, not a stylistic one.** It still requires
trusting us — the same trust boundary the whole rest of this brief exists
to eliminate. A verification feature that itself asks to be trusted has
not solved the problem it was built to solve.

## Rationale

1. **Ed25519 is natively supported.** Chrome 137+, Firefox 129+, Safari
   17+ implement Ed25519 in `crypto.subtle` directly — no external crypto
   library, no supply-chain trust question about a third-party JS package
   doing the actual verification.
2. **The demo must degrade honestly, not silently.** Older browsers
   without native Ed25519 support can still run SHA-256 (universal) for
   the HMAC-chain and Merkle-root checks — steps 1 through 4 of 5. The
   signature step must say plainly "not supported in this browser," never
   silently skip and leave the panel looking fully green. A green panel
   that secretly checked less than it claims to would be worse than the
   original CSS-only button this whole brief exists to replace.
3. **The two tamper modes must share one verifier function.** "Try to
   edit the database" (Layer 2) and "assume an attacker got past the
   database" (client-side bundle mutation) call the *identical*
   JavaScript verification function — not a real check for one button and
   a hand-rolled "make it fail" routine for the other. A parallel
   failure-only code path is exactly the kind of thing that quietly drifts
   from the real check over time and becomes unriggable in appearance
   only. This is stated as a comment at the call site in `demo.html` so a
   future refactor does not split them apart without noticing why they
   were joined.

## Consequences

**Easy:**
- A reviewer can View Source on the verification panel and read exactly
  what it does — no build step, no bundler, no minification obscuring the
  logic.
- The offline standalone verifier (`scripts/verify_bundle.py`, see ADR
  0017... [not yet written; Layer 4]) checks against the same worked
  example as the browser panel, so the three implementations (Python
  domain logic, browser JS, standalone script) all agree on one ground
  truth.

**Hard:**
- Any change to `domain/merkle.py`'s or `domain/canonical.py`'s algorithm
  must be mirrored in the browser JavaScript by hand — there is no shared
  compilation target. This is a real maintenance cost, accepted
  deliberately in exchange for the browser code being human-readable.

## Revisit when

- Ed25519 WebCrypto support becomes universal enough that the fallback
  path (SHA-256-only, no signature check) can be retired — track browser
  support before removing it, not before.
- If a customer's compliance team specifically requires WASM or a
  different verification delivery mechanism for their own audit tooling.
