# ADR 0003: HMAC Over Plain Hashing for Event Chaining

**Status:** Accepted  
**Date:** 10 Aug 2026  
**Author:** Sri

---

## Context

Events are chained cryptographically to detect tampering. Hashing alone (SHA-256) or HMAC (Keyed-Hash) are the two standard approaches. The question is whether the key should be vendor-held or client-held.

---

## Options Considered

| Option | Vendor forgery possible? | Client control? | Compatibility | Proof strength |
|---|---|---|---|---|
| **HMAC, client-held key (chosen)** | No (vendor never has key) | Yes (client owns proof) | Requires key exchange | Strong: client + vendor cannot collude to forge |
| **HMAC, vendor-held key** | Yes (vendor controls key) | No | Simpler | Weak: vendor can forge retroactively |
| **Plain hash (SHA-256)** | Yes (any party can forge) | No | Simplest | Weak: only proves preimage exists, not authorship |
| **Signature only (Ed25519)** | No (vendor cannot create signature) | Yes | Requires signing | Strong but slower; verification requires public key |

---

## Decision

Use HMAC with **client-held key**.

**Implementation:**
1. Client generates a random key (256 bits)
2. Client keeps the key; shares it only with Praman (over TLS)
3. Praman stores the key in secure storage (encrypted at rest)
4. For each event:
   - Canonicalise the event (deterministic JSON serialisation)
   - Compute `HMAC-SHA256(key, canonical_event)`
   - Append both the event and its HMAC to the ledger

**Verification:**
- Only holders of the client key can compute the correct HMAC
- Any change to an event → different HMAC
- If a Praman administrator tries to forge a log entry, the HMAC will be wrong (they do not have the key)

---

## Rationale

1. **Non-repudiation.** If an event's HMAC is correct, the client's key was used. The client cannot deny they stored that event (assuming the key has not been compromised).

2. **Vendor cannot forge.** Praman administrators cannot fabricate evidence by editing the ledger — the HMAC will be wrong. This is the critical property that makes the ledger trustworthy to the client.

3. **Client retains proof.** The client holds the key. If they ever need to audit Praman's ledger, they can regenerate the HMAC for any event and verify it matches what Praman stored.

4. **Cheaper than signature.** HMAC is symmetric (same key for auth and verification). Signatures are asymmetric (need public/private key pair). HMAC is O(1) latency; signature is O(n) for RSA, O(log n) for Ed25519. HMAC is fine for chaining.

5. **BSA §63 compatible.** The Schedule contemplates a "hash value"; HMAC qualifies (it is a keyed hash). Judges are familiar with HMAC in telecom and banking auditability.

---

## Consequences

**Easy:**
- Proof is held entirely by the client; no external trust needed
- Performance is excellent (symmetric cryptography)
- Standard practice in BFSI (banks use HMAC for message authentication in Swift, ACH, etc.)

**Hard:**
- Client must manage key securely (loss of key = loss of auditability)
- Key rotation is an event in the ledger (adding complexity)
- If the key is compromised, historical entries cannot be trusted

**Mitigations:**
- Ed25519 signatures on the Merkle root provide an additional layer (proves the root was not changed *after* signing)
- RFC 3161 anchoring provides an independent time proof (even if the ledger is edited, the timestamp proves when the root existed)
- Key rotation is logged as a special event; old entries use old key, new entries use new key

---

## Revisit When

- Client security model changes (e.g., multiple approvers, distributed trust)
- Vendor trust increases enough that client-held keys are not required
- Regulatory requirements mandate vendor-held keys (unlikely)
