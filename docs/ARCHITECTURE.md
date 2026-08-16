# Praman — System Architecture

**Status:** Active · **Last updated:** 16 Aug 2026

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
├── ports/                           # Abstract interfaces (Protocols)
│   ├── __init__.py
│   ├── event_repository.py          # EventRepository protocol
│   ├── signer.py                    # Signer protocol
│   ├── policy_engine.py             # PolicyEngine protocol
│   ├── drift_scorer.py              # DriftScorer protocol
│   ├── anchor_backend.py            # AnchorBackend protocol
│   └── certificate_renderer.py      # CertificateRenderer protocol
│
├── adapters/                        # Concrete implementations (one file per strategy)
│   ├── __init__.py
│   ├── policy/
│   │   ├── json_rules.py            # JSON policy engine (ships now)
│   │   └── rego.py                  # OPA Rego (documented, not implemented)
│   ├── signing/
│   │   └── ed25519.py               # Ed25519 signing
│   ├── drift/
│   │   ├── deterministic_stub.py    # STUB — disclosed in LIMITATIONS.md
│   │   ├── psi.py                   # Population Stability Index (documented, not impl)
│   │   └── semantic_entropy.py      # Semantic entropy (documented, not impl)
│   ├── anchor/
│   │   ├── local_only.py            # Writes to local ledger only
│   │   └── rfc3161_freetsa.py       # RFC 3161 timestamping
│   ├── certificate/
│   │   └── reportlab_bsa63.py       # BSA §63 certificate rendering
│   └── repository/
│       └── postgres_event_repository.py  # Implements EventRepository
│
├── services/                        # Orchestration — depends on ports, never on adapters
│   ├── __init__.py
│   ├── ledger_service.py            # Append events, generate roots, proofs
│   ├── governance_service.py        # Evaluate policies, apply decisions
│   ├── drift_service.py             # Detect drift, trigger breaker
│   └── evidence_service.py          # Generate certificates
│
├── persistence/                     # SQLAlchemy models + repositories
│   ├── __init__.py
│   ├── models.py                    # ORM: Event, Policy, Tenant, etc.
│   └── migrations/
│       └── 001_initial_schema.sql   # Append-only trigger, RLS
│
├── api/                             # FastAPI routes (thin — parse, call, return)
│   ├── __init__.py
│   ├── routers/
│   │   ├── events.py                # POST /events, GET /events/:id
│   │   ├── certificates.py          # GET /certificates/:id
│   │   ├── governance.py            # GET /governance/tiers, POST /governance/evaluate
│   │   └── health.py                # GET /health
│   └── middleware/
│       └── tenant_scope.py          # RLS: extract tenant from request
│
├── modules/                         # Independent module registrations
│   ├── __init__.py
│   ├── privacy/
│   │   ├── __init__.py              # Module 1 registration
│   │   └── routes.py                # Privacy-specific routes
│   └── ai_risk/
│       ├── __init__.py              # Module 2 registration
│       └── routes.py                # Governance-specific routes
│
├── main.py                          # FastAPI app initialization
├── config.py                        # Typed settings (env-driven)
└── factories.py                     # Build adapters from config (ONLY place to name them)

tests/
├── __init__.py
├── test_architecture.py             # Import graph enforcement
├── domain/
│   ├── test_canonical.py            # Event serialisation is deterministic
│   ├── test_hashing.py              # HMAC properties
│   └── test_merkle.py               # Tamper-evidence, inclusion proofs
├── integration/
│   └── test_ledger_flow.py          # End-to-end: event → root → certificate
└── modules/
    └── test_module_registration.py

docs/
├── ARCHITECTURE.md                  # This file
├── ADR/
│   ├── 0001-layered-architecture.md
│   ├── 0002-merkle-over-blockchain.md
│   ├── 0003-hmac-over-hashing.md
│   ├── 0012-module-two-build-gate.md
│   └── 0013-otel-genai-conventions.md
├── LIMITATIONS.md                   # Every stub, disclosed twice
├── GLOSSARY.md                      # Fixed vocabulary
├── ONBOARDING.md                    # Day-one path for next engineer
├── SCORING.md                       # Why drift scoring is stubbed
└── commercial/
    ├── 00-MARKET-THESIS.md
    ├── 01-MARKET-RESEARCH.md
    ├── ...
    └── 08-VALIDATION-METHOD.md
```

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

Five concerns are behind Strategy interfaces:

| Port | Ships | Alternatives (documented, not implemented) |
|---|---|---|
| `PolicyEngine` | JSON rules | OPA/Rego, Cedar |
| `AnchorBackend` | Local-only | RFC 3161, public chain |
| `Signer` | Ed25519 | ECDSA P-256, HSM/KMS |
| `DriftScorer` | Deterministic stub | PSI, semantic entropy |
| `CertificateRenderer` | ReportLab (BSA §63 format) | HTML/PDF, other jurisdictions |

**Why:** A bank already running OPA should swap one adapter, not rewrite the system. Keeping these behind protocols means adoption is an afternoon, not a rewrite.

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
   ├── ED25519_PRIVATE_KEY (persisted securely)
   ├── CLIENT_HMAC_KEY (client-held; vendor never sees it)
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

**The four tests that carry the project** (never break):
1. `test_tampering_changes_root` — Merkle property: any change → root changes
2. `test_canonicalisation_is_deterministic` — Same event → same hash always
3. `test_certificate_root_matches_ledger` — Certificate's root reflects actual ledger
4. `test_signature_fails_with_wrong_key` — Signing actually binds; tampering is detectable

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
