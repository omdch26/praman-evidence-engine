# ADR 0001: Layered Architecture with Strict Dependency Inflow

**Status:** Accepted  
**Date:** 10 Aug 2026  
**Author:** Sri

---

## Context

The ledger must be independently verifiable. If cryptographic logic is entangled with FastAPI routes and SQLAlchemy queries, no reviewer can audit the claim without understanding the entire application. We need a structure that isolates pure logic from I/O.

---

## Options Considered

| Option | Pros | Cons |
|---|---|---|
| **Layered (chosen)** | Pure logic in `domain/`, ports as contracts, adapters as implementations, services as orchestration. Dependency flows strictly inward. | Requires discipline; more files. |
| **Hexagonal (ports & adapters only)** | Simpler than layered; still isolates domain. | Mixes orchestration logic with domain logic; harder to test. |
| **Monolith** | Fast to write; single import tree. | Unmaintainable at scale; cryptographic logic tangled with web framework. |
| **Microservices** | Clean separation by concern. | Over-engineered for a two-module system; adds latency and operational complexity. |

---

## Decision

Implement layered architecture with five layers, each with strict import rules:

```
domain ← ports ← adapters ← services ← api
```

**Rules:**
- `domain/` imports nothing from `praman/` (only stdlib and third-party crypto)
- `ports/` imports only `domain/` and `typing`
- `adapters/` import only `ports/`, `domain/`, and third-party libraries
- `services/` import only `ports/`, `domain/` — adapters are injected
- `api/` imports only `services/`, `factories.py`, and FastAPI

---

## Rationale

1. **Auditability:** A lawyer can read `domain/` and `ports/` without understanding FastAPI. The cryptographic claim is verifiable in isolation.

2. **Testability:** Unit tests for `domain/` require no database, no network, no framework. A proof like "tampering changes the Merkle root" is testable in 10 lines without mocks.

3. **Swappability:** A bank using OPA instead of JSON rules changes one adapter file and one factory line. No rewrite.

4. **Evolvability:** Adding a new drift detector is a new adapter. Removing JSON rules (once OPA ships) is a delete. No refactoring.

5. **Handover:** A staff engineer can clone this, read `domain/` + `ports/`, and understand the core claims in an hour.

---

## Consequences

**Easy:**
- Swapping adapters (policy engine, signer, etc.)
- Unit-testing domain logic
- Delegating feature work to junior engineers (they work in services/; architecture is already decided)
- Onboarding new reviewers (documentation is structured by layer)

**Hard:**
- Requires discipline; mistakes (a service importing an adapter) will compile but violate the contract
- More files than a monolith (40 vs. 10)
- Synchronisation between layers (adding a new port means adding adapters, factories, and services)

**Mitigations:**
- `test_architecture.py` catches upward imports at test time
- CLAUDE.md documents the rule
- Code review checklist checks the import graph
- Commit messages record layer choices (ADRs for each new port)

---

## Revisit When

- Code review finds a repeated violation pattern (suggests the rule is too strict)
- More than two modules are added (layering might need a third dimension)
- A port is added but none of the adapters are swapped (suggests the port was unnecessary)
