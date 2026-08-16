# Praman — Fixed Vocabulary

**One concept, one word, everywhere.** Code, docs, UI, video, demo.

Introducing a synonym costs more than the 5 seconds it saves the writer.

---

## Core Terms

| Term | Meaning | Example |
|---|---|---|
| **Event** | One atomic action logged to the ledger. | "User consented on 2026-08-10 at 14:32 UTC" |
| **Ledger** | Append-only table of events. | `events` table in PostgreSQL |
| **Ledger entry** | One row in the ledger; immutable once committed. | Event ID 12345: {canonical_event, hmac_value, timestamp} |
| **Canonical event** | Deterministic JSON serialisation of an event. | `{"type":"consent","timestamp":"2026-08-10T14:32:00Z","principal_id":"hash:abc...",...}` |
| **HMAC** | Hash-based message authentication code; proves authenticity. | `HMAC-SHA256(client_key, canonical_event)` |
| **HMAC chain** | Sequential HMAC values linking event to event. | Event N's HMAC depends on Event N-1's HMAC |
| **Merkle tree** | Binary tree over event HMACs; root proves any tampering. | Tree with 1024 leaves; one root hash |
| **Merkle root** | Single hash representing all events. | `0xabcd...` (32 bytes) |
| **Inclusion proof** | Cryptographic proof one event is in the tree, without revealing others. | Proof path: [0xabc..., 0xdef..., 0x123...] |
| **Signature** | Cryptographic proof of authorship; proves the root was not changed after signing. | Ed25519 signature: 64 bytes |
| **Anchor** | Independent time proof that the root existed on a specific date. | RFC 3161 timestamp from FreeTSA |
| **Certificate** | Modelled on BSA §63 Schedule; proves the event system was operating. | PDF with Part A (description) + Part B (attestation) |
| **Evidence** | Tamper-evident, attributed, time-bound record admissible in court. | Certificate + root + inclusion proof + signature |
| **Policy** | Rule governing what an agent may do. | "Agent may spend ≤₹10K without approval" |
| **Decision** | Result of evaluating an event against policies. | "Approved" or "Denied" |
| **Autonomy tier** | Ceiling on what an agent can do without human intervention. | OBSERVE, PROPOSE, ACT_BOUNDED, ACT_FULL |
| **Delegation ceiling** | Effective tier when an agent spawns another. | Agent A (tier 2) spawns B (declared tier 3) → B's effective tier = min(2,3) = 2 |
| **Drift** | Statistically significant change in the distribution. | Input distribution shifted; model accuracy dropped 15% |
| **Drift detector** | Component that flags when drift occurs. | PSI (data), semantic entropy (semantics), or behavioural (decisions) |
| **Circuit breaker** | Stops the agent when drift is detected; fallback to manual review. | When drift > threshold, agent stops; incident logged |
| **Tenant** | One customer's isolated ledger and policy space. | Bank X has tenant ID 12345; Bank Y has 12346 |
| **Module** | One capability (privacy or governance). | Module 1: evidence; Module 2: AI risk |
| **Adapter** | Concrete implementation of a swappable concern. | JsonRulesPolicyEngine, Ed25519Signer, local-only anchor |
| **Port** | Abstract interface for a swappable concern. | PolicyEngine protocol, Signer protocol |
| **Domain** | Pure logic layer; no I/O, no framework. | Merkle tree construction, HMAC verification |
| **Service** | Orchestration layer; uses injected ports and adapters. | LedgerService, GovernanceService |

---

## Regulatory Terms

| Term | Meaning | Context |
|---|---|---|
| **DPDP Act 2023** | Data Protection Act; effective 13 May 2027; penalties up to ₹250 crore. | Privacy module built to this regulation |
| **§6 (Purpose limitation)** | Data collected for purpose A cannot be used for purpose B without fresh consent. | We solve this with zero PII on the ledger |
| **§12 (Right to erasure)** | Data principals can demand deletion; immutable audit trail conflicts with this. | Module 1 resolves by never storing PII |
| **Data Fiduciary** | Organisation that collects and processes data (usually the customer). | Bank is the Fiduciary; Praman is the vendor |
| **Data Principal** | Person whose data is being processed (customer of the bank). | Individual whose consent is logged |
| **BSA 2023** | Bharatiya Sakshya Adhiniyam; evidence law; in force 1 July 2024. | Module 1 builds to this |
| **§63 (Admissibility of electronic records)** | Electronic record is admissible if accompanied by a certificate attesting how it was produced. | We generate the certificate; customer signs Part B |
| **Schedule (to §63)** | Prescribed format for the certificate; two parts (Part A: description, Part B: attestation). | Our PDF is modelled on this |
| **RBI MRM** | Reserve Bank's Model Risk Management guidance; draft June 2026, final pending. | Module 2 (AI Risk) is built for this |
| **Kill-switch** | Ability to halt an AI/ML model in production; mandated in RBI MRM for models. | Module 2's circuit breaker implements this |
| **Significant Data Fiduciary** | Organisations the government designates as handling sensitive data; extra obligations. | SDF list not yet published |

---

## Non-negotiables (Never use synonyms)

❌ Don't use: ledger, logfile, audit trail, record, entry, log, journal  
✅ Use: **event**, **ledger**, **ledger entry**

❌ Don't use: controller, orchestrator, coordinator, manager, handler  
✅ Use: **service** (for orchestration), **adapter** (for concrete implementation)

❌ Don't use: interface, contract, abstraction, trait  
✅ Use: **port** (always, for Protocol/ABC)

❌ Don't use: decision point, trigger, activation, condition  
✅ Use: **policy** (the rule), **decision** (the result)

❌ Don't use: pause, halt, stop, shutdown  
✅ Use: **circuit breaker** (the mechanism), **fallback** (the alternative path)

❌ Don't use: principal, actor, subject  
✅ Use: **agent** (for AI/automation), **tenant** (for customer isolation)

---

## Related

See `ARCHITECTURE.md` for system concepts. See `docs/commercial/` for business vocabulary.
