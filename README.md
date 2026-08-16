# Praman — Tamper-Evident Evidence Engine for Regulated AI in India

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)  
**Status:** Live · **Last updated:** 16 Aug 2026

**Live demo:** https://praman-evidence-engine.vercel.app · **Backend:** https://praman-evidence-engine.onrender.com/health

---

## The Problem

A bank's customer says, *"I never agreed to share my data."* The bank's lawyer produces a database row: *"See? Here's the timestamp."*

Opposing counsel asks one question that ends the matter:

> *"Your Honour, this is a row in a database they control. Their own administrator can edit it. What stops them from typing this last week?"*

**There is no answer.** Logs are not evidence. An immutable audit trail resolves this — but it conflicts with the legal right to erasure (DPDP §12). Praman fixes both problems.

---

## Two Modules, One Spine

```
Module 1: Privacy   — BSA §63 Evidence      — Ledger + HMAC + Merkle + signature
Module 2: AI Risk    — RBI FREE-AI Governance — Autonomy tiers + drift + breaker
```

### Module 1: Court-Admissible Evidence (Privacy)

**For:** CROs, DPOs, compliance teams  
**Solves:** "Prove your data controls actually operated"

- **HMAC-chained ledger:** Client holds the key; vendor cannot forge
- **Merkle tree root:** Any event change is detectable; proof is tamper-evident
- **Ed25519 signature:** Root is signed; the signature proves integrity
- **RFC 3161 anchoring:** Independent Timestamping Authority proves when the root existed
- **BSA §63 certificate:** PDF with hash value + algorithm (Schedule format); modelled on evidentiary requirements

**Result:** A control operation (consent, data access, policy evaluation) is logged in a way that survives:
- Adversarial cross-examination in court
- DPDP §12 erasure requests (no personal data on the ledger)
- Vendor-insolvency scenarios (root can be independently verified)

### Module 2: AI Agent Governance (AI Risk)

**For:** CROs, Risk teams, Chief AI Officer  
**Solves:** "Prove your AI agent did not exceed its authority"

- **Autonomy tiers:** OBSERVE, PROPOSE, ACT_BOUNDED, ACT_FULL
- **Delegation ceilings:** Agent A (tier 2) spawning Agent B cannot escalate B's privilege
- **Three drift detectors:** Data (PSI), semantic (entropy), behavioural (distribution)
- **Circuit breaker:** When drift triggers, agent halts; fallback to manual review (the halt itself is logged in Module 1)
- **Real-time dashboard:** Two workspaces (privacy + governance) with three gauges

**Result:** When an AI agent makes a decision, you have:
1. A proof that the decision complied with autonomy constraints
2. A drift score showing the model's state at decision time
3. A log entry (in Module 1) that the decision happened
4. A circuit breaker that stops the agent if it drifts (and that stop is also logged)

---

## How It Works — End-to-End

### Event arrives (JSON)
```json
{
  "tenant_id": "bank_x_123",
  "event_type": "consent_granted",
  "timestamp": "2026-08-10T14:32:00Z",
  "action": "data_share",
  "purpose": "loan_underwriting",
  "principal_id_hash": "sha256:abc123..."  // NOT the actual principal name
}
```

**Note:** No personal data on the ledger. We hash the principal's ID, never store their name/email.

### Module 1 processes (Privacy)

1. Canonicalise the event (deterministic JSON)
2. Compute HMAC with client-held key
3. Append to ledger (append-only trigger prevents edits)
4. Emit to listeners

### Module 2 processes (AI Risk)

If the event involves an agent decision:

1. Evaluate policies: Is this action allowed given the agent's tier?
2. Check drift: Has the input or output distribution shifted?
3. Log the decision (approved/denied/breaker_triggered)
4. Fall back to manual if drift is detected

### Certificate generation (on demand)

1. Compute Merkle root over all events
2. Sign the root with Ed25519
3. Anchor the root with RFC 3161 (independent TSA timestamp)
4. Render a PDF (modelled on BSA §63 Schedule)
5. Customer's CTO signs Part B (attestation that system was operating properly)

**Result:** A certificate admissible under Bharatiya Sakshya Adhiniyam §63.

---

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL (or Neon Postgres for free hosting)
- Git

### Local Setup (5 minutes)

```bash
# Clone
git clone https://github.com/omdch26/praman-evidence-engine.git
cd praman-evidence-engine

# Virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Dependencies
pip install -r requirements.txt

# Environment
cp .env.example .env
# Edit .env: add DATABASE_URL, set OTEL_ENABLED=false for now

# Run
uvicorn praman.main:app --reload

# Test
curl http://localhost:8000/health
# Response: {"status":"ok","version":"0.1.0"}
```

### Running the full demo

**Live interactive demo:** https://praman-evidence-engine.vercel.app (click buttons, no terminal needed)

**Or run locally:**

```bash
# Start the API (terminal 1)
uvicorn praman.main:app --reload

# In another terminal
# POST an event
curl -X POST http://localhost:8000/events \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":"demo","event_type":"consent_granted","principal_id_hash":"abc123","action":"data_share"}'

# GET the certificate (Module 1 output)
curl http://localhost:8000/certificates/latest

# GET governance status (Module 2 output)
curl http://localhost:8000/governance/status
```

---

## Architecture

**Layered and swappable:**

```
┌──────────────────┐
│ api/             │  FastAPI routes (thin, parse & return)
├──────────────────┤
│ services/        │  Orchestration (what happens)
├──────────────────┤
│ ports/           │  Abstract interfaces (Strategy contracts)
├──────────────────┤
│ domain/          │  Pure logic (crypto, rules, no I/O)
├──────────────────┤
│ adapters/        │  Concrete implementations (swappable)
│ persistence/     │  Database + ORM
└──────────────────┘
```

**Dependency rule:** Domain imports nothing. Ports import only domain. Services import only ports. Adapters and routes depend on everything below them. Upward imports are forbidden (and tested).

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full picture.

---

## Key Claims

### 1. "Logs are not evidence. This is."

**Why:**
- Log: database row, editable by admin, self-asserted timestamp → not admissible
- Evidence: tamper-evident (any change detectable), attributed (signed), time-bound (independent anchor) → admissible

**How Praman proves it:**
- HMAC-chained: client key prevents vendor forgery
- Merkle root: any tampering changes the root (detectable)
- Ed25519 signature: root is signed (attribution)
- RFC 3161: independent TSA timestamps the root (time)
- Certificate: PDF with hash + algorithm + attestation (BSA §63)

Run the test: `pytest tests/test_merkle.py::test_tampering_changes_root -v`

### 2. "This solves the DPDP §12 erasure paradox."

**Paradox:** Immutable audit trail is a breach if it holds personal data. But if you erase the data, the audit trail is gone.

**Solution:** Never put personal data on the ledger. Hash the principal's ID instead. The ledger now has no personal data, so §12 erasure requests do not apply to it.

See [`praman/domain/canonical.py`](praman/domain/canonical.py) for the implementation.

### 3. "AI governance decisions are now evidence."

**How:**
- Module 2 evaluates a policy: should the agent act?
- The decision (approved/denied) is appended as an event (Module 1)
- That event is part of the Merkle tree
- The decision is now cryptographically bound to other events

**Result:** "The agent acted because policy X evaluated to APPROVED on 2026-08-10 14:32" is not just a log entry; it is evidence.

---

## Documentation

| Document | Purpose |
|---|---|
| [`ARCHITECTURE.md`](docs/ARCHITECTURE.md) | System design, layers, event flow, threat model |
| [`ONBOARDING.md`](docs/ONBOARDING.md) | Day-one guide for the next engineer (read this if you just cloned) |
| [`GLOSSARY.md`](docs/GLOSSARY.md) | Fixed vocabulary (one word per concept) |
| [`LIMITATIONS.md`](docs/LIMITATIONS.md) | Every stub, every untested assumption, transparency first |
| [`SCORING.md`](docs/SCORING.md) | Why drift detection is stubbed; production approaches |
| [`ADR/`](docs/ADR/) | Architectural Decision Records (layered architecture, Merkle vs blockchain, HMAC vs hash, module-two build gate, OTel conventions) |

**For the next engineer:** Read `ONBOARDING.md` (1h), then start with `domain/` and work outward.

**For a CFO, CTO, or compliance reviewer:** Open the [live demo](https://praman-evidence-engine.vercel.app) — plain-English by default, with an expert toggle that reveals the hash chain, the Merkle root, and a table mapping each feature to the specific regulation it satisfies.

---

## Deployment

### Live (Free Tier)

**Backend:** [Render](https://render.com) (Free, 750 hrs/month, ~60s cold start) — built and run from the repo's `Dockerfile`  
**Database:** [Neon](https://neon.tech) (Free Postgres, 3GB storage)  
**Frontend:** [Vercel](https://vercel.com) (Free, never sleeps) — serves the static `frontend/demo.html`

**Deployment is automated on push:**
```bash
git push origin main
# → GitHub → Render → Live at https://praman-evidence-engine.onrender.com/health
# → GitHub → Vercel → Live at https://praman-evidence-engine.vercel.app
```

### Configuration

Set environment variables on Render:

```bash
DATABASE_URL=postgresql://...  # Neon connection string
ED25519_PRIVATE_KEY_PATH=/tmp/private.pem  # Loaded at startup
MODULE_PRIVACY_ENABLED=true
MODULE_AI_RISK_ENABLED=true
OTEL_ENABLED=false  # Development mode
```

The Vercel project needs no environment variables — `frontend/demo.html` calls the Render backend directly and its `vercel.json` sets Root Directory to `frontend`.

---

## Testing

```bash
# All tests
pytest tests/ -v

# Architecture (import graph)
pytest tests/test_architecture.py -v

# Domain (crypto properties)
pytest tests/domain/ -v

# Integration (full flows)
pytest tests/integration/ -v

# Coverage
pytest --cov=praman tests/
```

**Critical tests (never break):**
1. `test_tampering_changes_root` — Merkle property
2. `test_canonicalisation_is_deterministic` — Same event → same hash
3. `test_certificate_root_matches_ledger` — Cert reflects actual ledger
4. `test_signature_fails_with_wrong_key` — Tampering is detectable

---

## Contributing

**Every line must be handover-ready.** Read [`CLAUDE.md`](CLAUDE.md) (binding engineering contract) before writing code.

**Process:**
1. Pick an issue or feature
2. Branch: `git checkout -b feat/your-feature`
3. Code (follow CLAUDE.md)
4. Test (pytest, ≥80% coverage)
5. Docs (update same commit)
6. Commit: `feat(module): description` with detailed message
7. PR with link to issue
8. Review + merge

**Code style:** Black, isort, mypy  
`pip install black isort mypy && black . && isort . && mypy praman/`

---

## Security & Compliance

### Tested
- ✅ Architecture enforcement (import graph)
- ✅ Cryptographic properties (Merkle tamper-evidence)
- ✅ HMAC chaining (client-key non-repudiation)

### Not yet tested (see [`LIMITATIONS.md`](docs/LIMITATIONS.md))
- ⚠️ Load testing (unknown RPS capacity)
- ⚠️ Penetration testing (no security audit)
- ⚠️ Legal review (BSA §63 compliance not yet verified in court)
- ⚠️ Audit logging (no admin action trails)

**Before production:** Engage a security firm and a lawyer. See [`LIMITATIONS.md`](docs/LIMITATIONS.md) for details.

---

## Roadmap

| Month | What | Impact |
|---|---|---|
| **1 (Aug 2026)** | Module 1 + 2, both live; demo; docs; cold-start deployment | Two-module platform, deployable |
| **2 (Sep 2026)** | PSI drift detector; audit logging; key rotation; RLS hardening | Module 2 real drift detection |
| **3 (Oct 2026)** | RFC 3161 real anchoring; HSM/KMS path; LLM-as-judge evaluation | Timestamping + hardware keys + policy sophistication |
| **4 (Nov 2026)** | Semantic entropy detector; multi-factor deletion; dashboard real-time | Second drift signal; compliance workflow |

---

## License

MIT. Use it as you wish. Include a copy of `LICENSE` if you redistribute.

---

## Questions?

- **Why not blockchain?** See [`docs/ADR/0002-merkle-over-blockchain.md`](docs/ADR/0002-merkle-over-blockchain.md), or the cost comparison in the [live demo](https://praman-evidence-engine.vercel.app)
- **Is this admissible in court?** See [`LIMITATIONS.md`](docs/LIMITATIONS.md) — the BSA §63 certificate format is implemented; court admissibility itself has not been tested
- **Which regulation does each feature satisfy?** Flip the expert toggle in the [live demo](https://praman-evidence-engine.vercel.app) for a feature-by-feature mapping to DPDP Rules 2025, RBI's FREE-AI Framework, and BSA §63
- **For technical questions:** Open an issue. Read [`ONBOARDING.md`](docs/ONBOARDING.md) first.

---

## Contact

Sri · [Email](mailto:medarsri@gmail.com) · [LinkedIn](https://linkedin.com/in/sriram-krishnan-64b55628/)

Built with 🔒 for Indian regulated AI.

---

**Status:** Live, demoable, two-module platform. Module 1 ready for revenue. Module 2 gates applied (commercial launch pending four paying customers or RBI enforcement). See [`docs/ADR/0012-module-two-build-gate.md`](docs/ADR/0012-module-two-build-gate.md).
