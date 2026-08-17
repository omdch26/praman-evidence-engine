# ADR 0014: Key custody behind a port, not a per-call keypair

**Status:** Accepted
**Date:** 2026-08-16

## Context

`api/routers/certificates.py` called `generate_keypair()` on every request to
`/certificates/latest`, `/certificates/{id}`, and `/certificates/generate`.
Each call produced a brand-new Ed25519 keypair, signed with the fresh private
key, and returned the signature — but never published the matching public
key anywhere. The public key was discarded the moment the request finished.

Consequences, all real and all present in the deployed demo before this fix:

- No signature returned by any of these endpoints could ever be verified,
  by anyone, because the public key needed to verify it no longer existed.
- Two identical requests (same root) produced two different signatures,
  which is not how signing a fixed value is supposed to behave.
- The non-repudiation claim made in `docs/ARCHITECTURE.md` and the sales
  deck — "anyone holding the public key can verify a root was not
  substituted" — was false for every certificate this service had ever
  issued.

This is not a cosmetic bug. Non-repudiation is one of the four claims
`docs/LIMITATIONS.md` and the four load-bearing tests (per CLAUDE.md §6)
exist to protect. A signature nobody can check is not evidence.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Generate once at module import, store as a module-level global | Minimal code change | No swap path for HSM/KMS later; every caller of `certificates.py` would need to change again when a real customer demands hardware custody |
| Load from a fixed file path, hardcoded | Simple | Same swap problem; also couples the app to a filesystem layout that will not survive Render/Vercel-style ephemeral deploys |
| **Port + adapter (chosen)** | Swapping to HSM/KMS custody is a new adapter + one factories.py branch, not a rewrite of every route that signs something | More files up front for a demo-stage feature |

## Decision

`KeyCustody` is a `Protocol` in `ports/key_custody.py` with three methods:
`signing_key()`, `public_key_pem()`, `key_id()`. `EnvironmentKeyCustody`
(`adapters/key_custody/environment_key.py`) loads a PEM key from the
`ED25519_PRIVATE_KEY_PEM` environment variable **once, at construction**,
and raises `ConfigurationError` — never silently generates a substitute —
if the variable is missing or malformed.

`dependencies.py` constructs one `EnvironmentKeyCustody` at module import
time and hands the same instance to every request via FastAPI's dependency
injection, so the key is stable for the life of the process.

`adapters/key_custody/hsm_kms.py` documents the HSM/KMS path and raises
`NotImplementedError` — it is designed, not built, because Ed25519 support
varies enough across HSM vendors and cloud KMS providers that committing to
one API before a real customer names their vendor would be guessing.

## Rationale

1. **Fail loudly, not silently.** The bug this ADR fixes was already a
   silent failure mode (a keypair being thrown away looks like success —
   the endpoint returns 200 with a signature). Replacing it with an
   adapter that *could* fall back to generating its own throwaway key on
   misconfiguration would reproduce the same failure under a different
   trigger. `ConfigurationError` on startup is the only acceptable failure
   mode here.
2. **The swap point is the actual commercial requirement.** Every bank
   security review this product will face asks "where does the private key
   live." "Behind an interface, currently in an environment variable,
   documented path to HSM/KMS" is an answerable question. "Generated fresh
   per request and discarded" was not survivable in that conversation.
3. **`key_id` matters more than it looks.** Once a customer rotates keys —
   and they will — a certificate that does not say which key signed it
   cannot be re-verified after rotation. Computing `key_id` from the
   public key's DER encoding (not PEM, which has formatting variance) at
   construction time means it is available on day one, before rotation is
   ever built, so no certificate issued now becomes unverifiable later.

## Consequences

**Easy:**
- `/certificates/*` responses now include `key_id`, which downstream
  verification (see ADR 0016) depends on to select the right public key.
- Adding HSM/KMS custody later is one new adapter file and one
  `factories.py` branch.

**Hard:**
- `KeyCustody.signing_key()` currently returns an `Ed25519PrivateKey`
  object directly, which assumes the private key exists in process memory.
  An HSM/KMS adapter cannot honestly return that — it can only offer a
  "sign this" call. `hsm_kms.py`'s docstring flags that the port's return
  type will likely need to narrow to a "can sign" Protocol when that
  adapter is actually built, so the next engineer isn't surprised.

## Revisit when

- A customer requires HSM or KMS-held keys (implement `hsm_kms.py`, and
  resolve the `signing_key()` return-type question above at that point).
- Key rotation is implemented (the `key_id` mechanism this ADR establishes
  is the foundation for it, but rotation itself — serving multiple valid
  public keys at once — is not built yet).
