# Praman — System Architecture

**Status:** Active · **Last updated:** 17 Aug 2026

---

## Overview

Praman is a dual-module platform for regulated AI in India. Both modules share a common spine (ledger, telemetry, circuit breaker) and are independently deployable.

```
┌─────────────────────────────────────┐
│  Module 1: Privacy (BSA §63)        │  Court-admissible evidence layer
│  Module 2: AI Risk (RBI FREE-AI)    │  Agent governance & drift detection
├─────────────────────────────────────┤
│  Shared Spine:                      │
│  - Event Ledger (append-only)       │
│  - HMAC Chaining                    │
│  - Merkle Trees & Roots             │
│  - OpenTelemetry instrumentation    │
│  - Circuit Breaker (HITL)           │
└─────────────────────────────────────┘
```

---

## Layered Architecture

Dependencies flow strictly inward. No layer imports outward.

```
                    ┌─────────────────────────────────────┐
                    │  api/          FastAPI routers      │  thin — parse, call, serialise
                    ├─────────────────────────────────────┤
                    │  services/     use-case orchestration│  the "what happens" layer
                    ├─────────────────────────────────────┤
                    │  ports/        abstract interfaces  │  Strategy contracts
                    ├─────────────────────────────────────┤
                    │  domain/       pure logic, no I/O   │  crypto, rules, models
                    └─────────────────────────────────────┘
                              ▲
                    adapters/ ─┘   concrete implementations of ports
                    persistence/   SQLAlchemy models + repositories
                    factories.py   builds adapters from config
```

### Dependency Rules (Binding)

| Layer | May import | Must never import |
|---|---|---|
| `domain/` | stdlib, `cryptography` | anything else in `praman/` |
| `ports/` | `domain/`, `typing` | `adapters/`, `services/`, `api/` |
| `adapters/` | `ports/`, `domain/`, third-party libs | `services/`, `api/` |
| `services/` | `ports/`, `domain/` | `adapters/` (receives them injected) |
| `api/` | `services/`, `factories.py` | `domain/` directly, `adapters/` |

**Why this matters:** The ledger's cryptographic integrity must be independently verifiable. If crypto logic is tangled with FastAPI and SQLAlchemy, no reviewer can verify the claim in isolation.

---

## Folder Structure

```
praman/
├── domain/                          # Pure logic, no I/O, no framework
│   ├── __init__.py
│   ├── models.py                    # Frozen dataclasses (events, policies, decisions)
│   ├── canonical.py                 # Event serialisation (deterministic)
│   ├── hashing.py                   # HMAC construction
│   └── merkle.py                    # Merkle tree, root, inclusion proofs
│
├── domain/                          # Pure logic, no I/O, no framework (existing files
│   │                                 # not re-listed below — see Overview section)
│   └── verification.py              # Independent bundle verification (ADR 0016)
│
├── ports/                           # Abstract interfaces (Protocols)
│   ├── __init__.py
│   └── key_custody.py               # KeyCustody protocol (ADR 0014)
│
├── adapters/                        # Concrete implementations (one file per strategy)
│   ├── __init__.py
│   ├── instrumentation/
│   │   └── otel_adapter.py          # gen_ai.* attribute mapping
│   └── key_custody/
│       ├── environment_key.py       # Loads a stable key from an env var (ships now)
│       └── hsm_kms.py                # HSM/KMS custody (documented, not implemented)
│
├── observability/
│   └── otel.py                      # OTel tracer/meter initialisation
│
├── services/                        # Orchestration — depends on ports, never on adapters
│   ├── __init__.py
│   ├── event_logger.py              # Log governance decisions + halts to Module 1
│   └── evidence_service.py          # Assemble independently-verifiable evidence bundles
│
├── persistence/                     # SQLAlchemy models + repositories
│   ├── __init__.py
│   ├── database.py                  # Engine, session factory, migration runner
│   ├── models.py                    # ORM: Event, Certificate, Tenant, Policy
│   └── migrations/
│       └── 001_initial_schema.sql   # Append-only trigger, RLS
│
├── api/                             # FastAPI routes (thin — parse, call, return)
│   ├── __init__.py
│   └── routers/
│       ├── events.py                 # POST /events, GET /events/:id
│       ├── certificates.py           # GET /certificates/latest, /generate, /:id
│       ├── governance.py             # POST /governance/evaluate, GET /governance/status
│       ├── demonstration.py          # POST /demo/tamper-attempt (ADR 0015)
│       ├── keys.py                   # GET /keys/public (ADR 0014)
│       └── evidence.py               # GET /evidence/bundle (ADR 0016)
│
├── modules/                         # Independent module registrations
│   ├── __init__.py
│   ├── privacy/__init__.py          # Module 1 registration
│   └── ai_risk/__init__.py          # Module 2 registration
│
├── main.py                          # FastAPI app initialization
├── config.py                        # Typed settings (env-driven)
├── factories.py                     # Build adapters from config (ONLY place to name them)
└── dependencies.py                  # FastAPI dependency providers (process-lifetime singletons)

tests/
├── __init__.py
├── test_architecture.py             # Import graph enforcement
├── test_factories.py                # Adapter construction fails loudly on bad config
├── test_verification_doc.py         # docs/VERIFICATION.md's worked example stays correct
├── domain/
│   ├── test_canonical.py            # Event serialisation is deterministic
│   ├── test_hashing.py              # HMAC properties
│   ├── test_merkle.py               # Tamper-evidence, inclusion proofs
│   ├── test_signing.py              # Ed25519 sign/verify
│   ├── test_governance.py           # Autonomy tiers, delegation ceilings
│   ├── test_drift.py                # Circuit breaker evaluation
│   └── test_verification.py         # Independent bundle verification (ADR 0016)
├── services/
│   └── test_evidence_service.py     # Bundle assembly, byte-round-trip through JSONB
├── adapters/
│   └── key_custody/
│       └── test_environment_key.py  # Stable key, fails loudly on bad config (ADR 0014)
├── scripts/
│   └── test_verify_bundle.py        # Standalone verifier, subprocess-tested
└── integration/
    ├── test_ledger_flow.py          # End-to-end: event → HMAC chain
    ├── test_full_flow.py            # Module 1 + Module 2 combined
    ├── test_governance_endpoints.py
    ├── test_demonstration_endpoint.py  # Tamper-attempt endpoint, all four safety gates
    └── test_evidence_endpoints.py      # /keys/public + /evidence/bundle, full verify round-trip

scripts/
└── verify_bundle.py                 # Standalone offline verifier — does NOT import praman/

frontend/
├── index.html                       # Front door served at / — positioning and three
│                                     # routes (demo, architecture, contact)
├── demo.html                        # Technical demo served at /demo — real backend
│                                     # calls, WebCrypto verification panel, no build step
└── vercel.json                      # Clean URLs; / serves index.html, /demo serves demo.html

docs/
├── ARCHITECTURE.md                  # This file
├── VERIFICATION.md                  # How to verify a bundle, incl. worked hex example
├── ADR/
│   ├── 0001-layered-architecture.md
│   ├── 0002-merkle-over-blockchain.md
│   ├── 0003-hmac-over-hashing.md
│   ├── 0012-module-two-build-gate.md
│   ├── 0013-otel-genai-conventions.md
│   ├── 0014-key-custody-port.md
│   ├── 0015-demo-tamper-endpoint.md
│   └── 0016-client-side-verification.md
├── LIMITATIONS.md                   # Every stub, disclosed twice
├── GLOSSARY.md                      # Fixed vocabulary
├── ONBOARDING.md                    # Day-one path for next engineer
└── SCORING.md                       # Why drift scoring is stubbed
```

**A note on this diagram's history:** earlier versions of this file described several `ports/`, `adapters/`, and `services/` files (`event_repository.py`, `signer.py`, `policy_engine.py`, `ledger_service.py`, and others) that were never actually built — the diagram was written ahead of the code. Earlier versions also listed a `docs/commercial/` folder of market and pricing documents that was planned but never created. The tree above reflects what exists in this repository today, verified against the actual filesystem, not the earlier aspirational version. If you find a mismatch between this tree and `find praman -name "*.py"`, trust the filesystem and file an issue.

---

## Module Architecture

### Module 1: Privacy (BSA §63)

**Responsibility:** Produce court-admissible evidence of control operations.

**Components:**
- `ledger_service`: Append events, generate Merkle roots
- `evidence_service`: Generate BSA §63 certificates
- `signer`: Ed25519 signature generation
- `anchor_backend`: RFC 3161 timestamping

**Data flow:**

```
1. Event arrives (JSON)
   ↓
2. Canonicalised (deterministic serialisation)
   ↓
3. HMAC-chained (client key prevents vendor forgery)
   ↓
4. Appended to ledger (append-only trigger prevents edits)
   ↓
5. Merkle root computed (tamper-evidence: any change detectable)
   ↓
6. Root signed (Ed25519: attribution)
   ↓
7. Root anchored (RFC 3161: independent time proof)
   ↓
8. Certificate generated (modelled on BSA §63 Schedule)
   ↓
9. Certificate signed (non-repudiation)
```

**Non-negotiables:**
- No personal data on the ledger (resolves DPDP §12 paradox)
- Event must never reference the data principal
- HMAC key is client-held; vendor cannot forge
- Canonicalisation is deterministic (verification is reproducible)
- Merkle tree domain-separates leaves and internal nodes (prevents second-preimage attack)

---

### Module 2: AI Risk (RBI FREE-AI Framework)

**Responsibility:** Govern agent autonomy and detect operational drift.

**Components (production-ready; commercial gate met, 16 Aug 2026):**
- `governance_service`: Enforce autonomy tiers and delegation ceilings
- `drift_service`: Three detectors (PSI, semantic entropy, behavioural)
- `circuit_breaker`: HITL intervention point
- `dashboard`: Real-time gauges and workspace switcher

**Constraint hierarchy:**

```
Tier 0: OBSERVE        Agent reads; cannot act
Tier 1: PROPOSE        Agent proposes action; requires approval
Tier 2: ACT_BOUNDED    Agent acts within declared constraints
Tier 3: ACT_FULL       Agent acts freely

Rule: Delegation ceiling
   If Agent A (tier 2) spawns Agent B, then B's effective tier = min(A's tier, B's declared tier)
   Result: B cannot escalate to tier 3 just by declaring it.
```

**Drift detection — three independent signals:**

1. **Data drift (PSI):** Input distribution has changed
2. **Semantic drift (entropy):** Output semantics have changed
3. **Behavioural drift (distribution):** Decision distribution has shifted

Each fails differently. A model safe on PSI may be unsafe on entropy. Having three means a reviewer can see exactly what failed.

**Circuit breaker:**

When any detector triggers, the system halts the agent and falls back to manual review. The halt itself is logged as evidence (in Module 1). The log entry includes: which detector fired, score, threshold, reason.

---

## Event Flow — Module 1 + 2 Combined

```
1. REQUEST arrives
   (tenant_id, event_type, timestamp, data)
   
2. MODULE 1 (Privacy) handles audit trail
   → canonical_event = canonicalise(event)
   → hmac_value = hmac_kdf(client_key, canonical_event)
   → append to events table
   → emit to Module 1 subscribers
   
3. MODULE 2 (AI Risk) handles governance
   → if event_type == "agent_action":
      → tier = get_agent_tier(agent_id)
      → policy_result = policy_engine.evaluate(event, policies)
      → if policy_result.allowed:
            → store_decision(event_id, policy_result)
            → emit to Module 2 subscribers
      → else:
            → store_decision(event_id, policy_result, breaker=true)
            → trigger HITL fallback
            → log breach attempt
            
4. MODULE 1 receives Module 2 decision
   → appends decision itself as an event
   → (proves Module 2 operated; Module 2's decision is now evidence)
   
5. CERTIFICATE generation (on demand or schedule)
   → compute merkle root over all events to date
   → sign root with Ed25519
   → anchor with RFC 3161
   → render BSA §63 certificate
   → return to client
```

**Key insight:** Module 2's decisions become Module 1's evidence. The governance decision is now a tamper-evident, attributed, time-bound record admissible in court. That is the product.

---

## Strategy Interfaces (Swappable Concerns)

**Built and real, in `ports/` today:**

| Port | Ships | Alternative (documented, not implemented) |
|---|---|---|
| `KeyCustody` | `EnvironmentKeyCustody` — stable key from an env var (ADR 0014) | `HsmKmsKeyCustody` — `adapters/key_custody/hsm_kms.py` |

**Planned, not yet built** (no `ports/` file exists for these; do not import them):

| Concern | Would ship | Alternative | Status |
|---|---|---|---|
| Policy evaluation | JSON rules | OPA/Rego, Cedar | Not started |
| Root anchoring | Local-only | RFC 3161, public chain | Not started (see LIMITATIONS.md) |
| Drift scoring | Deterministic stub | PSI, semantic entropy | Stub exists in `domain/drift.py`, not behind a port |
| Certificate rendering | Current: plain text in `certificates.py` | ReportLab/PDF, other jurisdictions | Not behind a port |

**Why the built one matters:** `KeyCustody` is the concrete proof this pattern works — swapping `EnvironmentKeyCustody` for HSM/KMS custody later is one new adapter file plus one `factories.py` branch, not a rewrite of every caller that signs something. That is the same argument the four planned ports above are waiting to make once they exist; until then, treat the table above as a roadmap, not a description of the current codebase.

---

## Deployment Shape

```
Frontend (Vercel)
   └── frontend/demo.html — single static file, no build step
       Calls the Render backend directly via fetch(); progressive
       disclosure (plain English by default, expert toggle reveals
       hash chain + regulatory citations)

Backend (Render, Free tier)
   ├── FastAPI on python:3.11-slim
   ├── Non-root user
   └── Environment-driven config

Database (Neon Postgres)
   ├── Append-only events table
   ├── RLS per tenant (Row Level Security)
   └── Ephemeral filesystem (stream certificates, never write disk)

Secrets
   ├── DATABASE_URL (Neon)
   ├── ED25519_PRIVATE_KEY_PEM (base64-encoded PEM; see ADR 0014 and .env.example)
   ├── HMAC_KEY (client-held; vendor never sees it — separate from the demo's fixed key)
   ├── DEMO_MODE_ENABLED (defaults false; gates POST /demo/tamper-attempt — see ADR 0015)
   └── Environment (development/production)
```

**Cold start:** ~60s (Free tier)  
**Healthy after:** Requests start going to app  
**Request latency:** ~200ms (db + crypto)

---

## Testing Strategy

| Test category | Location | What it proves |
|---|---|---|
| **Architecture** | `tests/test_architecture.py` | Import graph is clean; no violations |
| **Domain** | `tests/domain/` | Crypto functions are deterministic and correct |
| **Integration** | `tests/integration/` | End-to-end flows work (event → root → cert) |
| **Modules** | `tests/modules/` | Modules are independent and composable |

**The tests that carry the project** (never break; verified to exist by name, not assumed):
1. `tests/domain/test_merkle.py::test_tampering_changes_root` — Merkle property: any change → root changes
2. `tests/domain/test_canonical.py::test_canonical_is_deterministic` — Same event → same bytes always
3. `tests/domain/test_signing.py::test_verify_signature_with_wrong_public_key` — Signing actually binds; a different key does not verify

Plus, added by this repository's evidence-verification work (see ADR 0016):

4. `tests/domain/test_verification.py::TestIndependentlyRecomputedRootMatchesServerRoot` — an independently recomputed root matches the server's claimed root
5. `tests/domain/test_verification.py::TestVerifyBundleFullReport::test_tampered_hmac_value_fails_report_and_names_sequence` — tampering is detected and localised to the correct event
6. `tests/scripts/test_verify_bundle.py::test_standalone_verifier_agrees_with_domain_verifier` — the standalone, non-`praman`-importing verifier reaches the same verdict as the in-process domain logic on the same bundle

There is no `test_certificate_root_matches_ledger` in this codebase currently — an earlier version of this document named it, but it was never written. If you are the one who writes it, this is where to record it.

---

## Handover Checklist

**Could a staff engineer clone this tomorrow and be productive by EOD?**

- [ ] Every module opens with a docstring (purpose, responsibility, what it must not do)
- [ ] Every public function has a docstring (why it exists, args, returns, raises)
- [ ] Comments explain why, never what
- [ ] Functions ≤40 lines, files ≤400 lines, nesting ≤3 levels
- [ ] Full type hints; no bare `Any` without justification
- [ ] Names are descriptive and domain-accurate
- [ ] Swappable concerns are behind Strategy interfaces
- [ ] Dependency direction is strictly inward
- [ ] Documentation is updated in the same commit
- [ ] All stubs are disclosed in `LIMITATIONS.md`
- [ ] No dead code, no commented blocks, no debug prints
- [ ] Every new module ships with at least one test

---

## See Also

- `CLAUDE.md` — Engineering contract (binding)
- `LIMITATIONS.md` — Every stub, disclosed
- `ADR/0001-layered-architecture.md` — Why this structure
- `ADR/0002-merkle-over-blockchain.md` — Why Merkle, not chain
- `ADR/0003-hmac-over-hashing.md` — Why HMAC, not hash alone
- `ADR/0012-module-two-build-gate.md` — Module 2 commercial gate
- `ADR/0013-otel-genai-conventions.md` — OpenTelemetry instrumentation
- `ADR/0014-key-custody-port.md` — Why signing keys are stable and behind a port
- `ADR/0015-demo-tamper-endpoint.md` — Safety design for the live tamper-attempt endpoint
- `ADR/0016-client-side-verification.md` — Why verification runs in the browser, not just server-side
- `VERIFICATION.md` — How to independently verify an evidence bundle, with a worked example
