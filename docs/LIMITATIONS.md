# Praman — Known Limitations and Stubs

**Last updated:** 16 Aug 2026  
**Status:** Disclosed; see ADRs for context. Reviewed 16 Aug 2026 — all three stubs below (drift detection, HMAC key, RFC 3161) are unchanged and still accurate.

This document lists every stub, shortcut, and untested assumption. Read this before claiming anything is production-ready.

---

## Stubs (Disclosed Twice: Code + This Doc)

### Drift Detection — Deterministic Stub

**Location:** `adapters/drift/deterministic_stub.py`

**What it does:**
Returns a fixed, reproducible drift score for every call. Score is deterministic based on input hash (same input → same score always). This makes demos reproducible, but it measures nothing real.

**Why it is stubbed:**
Production drift detection requires either:
1. Population Stability Index (PSI) — needs reference distribution and multiple observations
2. Semantic entropy — needs multiple sampled generations and semantic embedding
3. Behavioural distribution shift — needs historical decision rate baseline

Each method requires operational data (sampling, labelling, re-inference) that makes the demo costly. The stub proves the circuit-breaker mechanism works; the detection logic is separate.

**Production approach:**
See `adapters/drift/psi.py` (documented, not implemented) for PSI. The interface (`DriftScorer`) is swappable; swapping adapters is one line in `factories.py`.

**Implication:**
Do not use Module 2 drift detection in production without implementing a real detector. The stub will never trigger. Use this as a policy-only governance layer until you have operational data to instrument with real drift.

---

### HMAC Chaining Key — Fixed Demo Key

**Location:** `api/routers/events.py` (`hmac_key`), `services/event_logger.py` (`_HMAC_KEY`)

**What it does:**
Every event — whether posted directly to `POST /events` or logged internally by Module 2 (policy decisions, circuit-breaker halts, drift scores) — is HMAC-chained using the same fixed 32-byte all-zero key, rather than a tenant-specific key.

**Why it is stubbed:**
Per-tenant key management (generation, storage, rotation, and safe injection into both the API layer and the internal event logger) is a real key-management design decision, not a one-line fix. Using one fixed key keeps the demo's HMAC chain internally consistent — Module 1 and Module 2 events must chain with the *same* key or the chain breaks at the module boundary — without deciding the production key-custody model prematurely.

**Production approach:**
Load a per-tenant HMAC key (client-held, per `config.py`'s `hmac_key` setting) and thread it through both `api/routers/events.py` and `services/event_logger.py` so every write path uses the same tenant-scoped key.

**Implication:**
Do not use this build to make evidentiary claims across tenants or in production — the shared fixed key means any two tenants' events are technically chained with the same secret. Fine for demonstrating the chaining mechanism; not fine for real evidentiary separation.

---

### RFC 3161 Timestamping — Local-Only Fallback

**Location:** `adapters/anchor/local_only.py` (ships now), `adapters/anchor/rfc3161_freetsa.py` (documented, not implemented)

**What it does (local-only):**
Merkle root is signed and stored locally. Timestamp is the system clock at signing time.

**Why local-only ships:**
RFC 3161 integration requires:
1. Choice of a Timestamping Authority (TSA)
2. TLS connectivity to the TSA
3. TSA certificate validation
4. Retry/circuit-breaker logic for TSA outages

This is operational overhead for a demo. The local-only version proves the signing and certificate-generation logic works.

**Production approach:**
See `adapters/anchor/rfc3161_freetsa.py` (documented) for the FreeTSA integration. It:
1. POSTs the Merkle root to the TSA
2. Gets back a signed timestamp token
3. Embeds the token in the certificate
4. Verification uses TSA's public key (no ongoing trust in TSA)

**Implication:**
Local timestamps are self-asserted (the bank asserts when the root existed). Under adversarial scrutiny, this is weak. Use RFC 3161 for any production deployment. Implement it by end of Month 2.

---

### Certificate Rendering — ReportLab, BSA §63 Format

**Location:** `adapters/certificate/reportlab_bsa63.py` (shipped with placeholders)

**What it does:**
Renders a PDF modelled on the BSA §63 Schedule certificate format. Part A: description of the electronic record and how it was produced (includes hash value and algorithm). Part B: person responsible for the system attesting it was operating properly.

**Why Part B is a stub:**
The Schedule requires Part B to be completed by "the person responsible for the electronic record generating system." In practice:
- This is typically the CTO or Chief Information Officer
- They must personally attest the system was operating properly on the specific date
- Praman generates Part A automatically (hash value, algorithm, timestamp)
- Part B is a legally-binding statement; it must be reviewed by the customer's legal team before signing

**Current implementation:**
Praman generates a **template** for Part B. It reads:

> *[Company Name], represented by [Officer Name], hereby attests that the electronic record generating system (Praman Evidence Engine, version 0.1.0) was operating properly, in accordance with the specified procedures, on [date]. Signature: [Officer Name], [Title].*

This is **not yet signed**. The customer must:
1. Review with their legal team
2. Print, sign, and scan OR use a digital signature service
3. Embed the scanned/signed image in the certificate

**Implication:**
The certificate is modelled on the Schedule format and includes the required hash value and algorithm. It is legally sufficient only after Part B is reviewed and signed by the customer's responsible officer. Praman does not make that claim; you (the customer) do.

**Production approach:**
Implement e-signature integration (eSignature service, DocuSign, etc.) so Part B can be signed digitally without print/scan cycles. This is Month 3 work.

---

## Untested Assumptions

### Multi-tenant Isolation (Row Level Security)

**Assumption:** PostgreSQL RLS policies enforce tenant isolation.

**Status:** Policy is written; not yet load-tested.

**What could go wrong:**
- RLS bypass via prepared statements (unlikely; modern PostgreSQL prevents this)
- RLS bypass via privilege escalation (requires application to have admin role; we use a restricted role)
- RLS policy logic error (allows one tenant to see another's events)

**Mitigation:**
Write integration tests that verify:
1. User A cannot read User B's events (even if they guess the event ID)
2. Attempting to UPDATE another tenant's event raises an error
3. RLS audit trail shows which tenant accessed what

**Timeline:** Month 2, as part of hardening.

---

### Cryptographic Key Management

**Assumption:** Client-held HMAC keys are generated and stored securely on the client's side.

**Status:** Praman does not generate or manage the key; client does.

**What could go wrong:**
- Client generates a weak key (too short, predictable)
- Client loses the key (loss of auditability)
- Client's key storage is compromised (all historical HMACs are forgeable)
- Key rotation is not implemented

**Mitigation:**
1. Document a key-generation procedure for clients (256-bit random from a cryptographic RNG)
2. Provide a key-rotation mechanism (new key is stored with an effective-date in the ledger)
3. Old entries use old key; new entries use new key
4. Audit trail shows when a key rotation happened

**Timeline:** Month 1; ship key-rotation logic with Module 1.

---

### Ed25519 Key Persistence

**Assumption:** Praman's Ed25519 private key is stored encrypted at rest and never leaves the process.

**Status:** Key is loaded from a file at startup; stored in memory during runtime.

**What could go wrong:**
- Private key file is readable by other processes (file permissions)
- Private key is dumped to disk in core dumps
- Private key is logged in debug output
- HSM/KMS integration is not available (single point of failure)

**Mitigation:**
1. Restrict key file to 0600 permissions (readable by app user only)
2. Disable core dumps in production (OS-level: `ulimit -c 0`)
3. Never log the key or any key-derived values
4. Document HSM integration path (use `cryptography.hazmat.backends` with PKCS11 support)

**Timeline:** Month 1; implement file permissions and core-dump disabling before first deployment.

---

### Merkle Tree Unbounded Growth

**Assumption:** Merkle tree can grow indefinitely without performance degradation.

**Status:** Tree is computed from all events since the beginning of time; not optimised.

**Scaling concern:**
After 1 million events, recomputing the tree takes milliseconds (acceptable). After 100 million events, it might take seconds (still acceptable, but slow down is O(n)).

**Production approach:**
Implement Merkle Mountain Range (MMR) for incremental proof updates. Instead of recomputing from scratch, append new events to a growing tree structure. This is a Month 4 optimisation, not critical for launch.

**Implication:**
Do not run this in production with >1 billion events without profiling first. For most use cases (2–5 million events/year), unbounded growth is fine for 5+ years.

---

### No audit trail of administrative actions

**Assumption:** Praman writes no audit trail of who accessed what. RLS prevents inter-tenant access, but it does not log access attempts.

**Status:** Audit logging is not implemented.

**What this means:**
If a Praman administrator queries the `events` table, that query is not logged. This violates many compliance frameworks (ISO 27001, SOC 2).

**Mitigation:**
1. Enable PostgreSQL query logging (`log_statement='all'` in production)
2. Implement application-level audit trails (every API call logs: who, what, when, result)
3. Send audit logs to a separate, append-only table or external service

**Timeline:** Month 1; audit logging is required before first customer access.

---

## Not Yet Implemented (Documented, No Stub)

These are on the roadmap but not shipped. They are not stubs because we have not attempted to build them.

| Feature | Why not shipped | Timeline |
|---|---|---|
| **Multi-factor deletion** | Requires key ceremony; needs customer consent | Month 2 |
| **Policy-as-code (OPA/Rego)** | JSON rules ship; Rego integration is an adapter swap | Month 2 |
| **HSM/KMS integration** | Adds operational overhead; not needed for launch | Month 3 |
| **Dashboard gauges (real-time)** | UI exists; wiring to drift detector needs OTel | Month 2 |
| **LLM-as-judge policy evaluation** | Requires LLM API key; adds latency; JSON rules are synchronous for now | Month 3 |
| **Semantic entropy drift detector** | Requires LLM integration; complex; PSI is simpler | Month 4 |

---

## Testing Gaps

### Load Testing

No load tests yet. Unknown:
- How many requests/second can Render Free tier handle?
- Merkle tree computation time at 10k events? 100k?
- Database query time with 1M events?

**Mitigation:** Write load tests in Month 2; profile bottlenecks; optimise before scaling.

### Security Testing

No penetration testing. Unknown:
- Can an attacker craft a malformed event to crash the parser?
- Can an attacker forge an HMAC without the key?
- Can an attacker escalate from tenant isolation bypass to data exfiltration?

**Mitigation:** Contract a security firm for a penetration test before first customer. Budget: ₹5–10L.

### Regulatory Testing

No legal review. Unknown:
- Does the certificate actually satisfy BSA §63 requirements?
- Are there gaps between the Schedule format and what Praman generates?
- Is the DPDP §12 erasure paradox actually resolved?

**Mitigation:** Engage an IP/evidence law firm to review the implementation. Budget: ₹10–20L. Timeline: Month 2, before any customer pitch.

---

## Caveat Emptor

This is a demonstrator built in 7 days. It is production-grade in its architecture, but it has not been stress-tested, security-audited, or legally reviewed. Use it for:

✅ Understanding the problem space  
✅ Demos to CROs and DPOs  
✅ Reference implementations for policy engines and drift detectors  
❌ Storing production customer data  
❌ Claiming legal sufficiency in court  
❌ Meeting SOC 2 or ISO 27001 requirements yet  

---

## How to Use This Document

**For internal readers (before customer pitch):**
- Read it all. It is the reality check.

**For customer readers (under NDA):**
- Read the Stubs section. Everything else is internal.

**For legal review:**
- Read the "Regulatory Testing" gap. You need this addressed before any legal claim.

**For operations:**
- Read "Untested Assumptions" and "Testing Gaps". These are your hardening roadmap.

---

## Reporting New Limitations

If you find a stub, untested assumption, or gap while building or deploying, add it here **in the same commit**. Never ship undisclosed limitations.

Format:
```
### [Feature Name] — [Stub Type]

**Location:** path/to/code.py or "architecture-level"

**What it does/doesn't do:** One paragraph

**Why it is stubbed:** One paragraph

**Production approach:** One paragraph or link to ADR

**Implication:** One sentence for customers
```

---

## Related

- `ARCHITECTURE.md` — System design
- `ADR/0012-module-two-build-gate.md` — Why Module 2 has a commercial gate
