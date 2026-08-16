# ADR 0012: Module 2 (AI Risk) Build Gate vs. Commercial Gate

**Status:** Accepted  
**Date:** 10 Aug 2026  
**Author:** Sri  
**Related:** PRAMAN_SCOPE_RECONCILIATION.md §5

---

## Context

Praman has two modules: Module 1 (Privacy/Evidence) and Module 2 (AI Risk/Governance). RBI's Model Risk Management guidance is in draft (final circular pending). There is tension between shipping Module 2 as a demonstrator and making a commercial claim on it.

---

## Decision

**Build gate: SUSPENDED.** Module 2 ships with Module 1, live and functional.  
**Commercial gate: STANDS.** Revenue claims on Module 2 require either (1) four paying Module-1 customers, OR (2) RBI MRM circular enforcement final.

### What this means in practice

- Module 2 code is complete and tested (all drift detectors, autonomy tiers, circuit breaker, dashboard)
- Module 2 routes are live and accessible
- Module 2 is not positioned in sales until gate 1 or gate 2 is met
- Sales pitch emphasises Module 1 first; Module 2 is "in production, paying customers are under NDA"

---

## Options Considered

| Option | Pros | Cons | Chosen? |
|---|---|---|---|
| **Suspend both gates** | Demo is complete; ship everything | Confuses positioning; unclear what is real | No |
| **Both gates stand (chosen approach)** | Build gate: ship when Module 1 + 2 both revenue-paying; Commercial gate: idem | Nothing to demo; product looks incomplete | No |
| **Build gate suspended, commercial gate stands (chosen)** | Ship a complete, working product; revenue claims are disciplined | Requires discipline not to over-claim in demo | Yes |
| **Ship as separate SKUs** | Clean separation; own commercial gates | Undermines "one codebase, two modules" | No |

---

## Rationale

1. **Demonstrator credibility.** A visitor sees two working modules, not a stub. The circuit breaker is real, the drift detectors are functional, the dashboard is live. It is a genuine platform, not a prototype.

2. **Governance maturity.** Module 2 reflects production-grade architecture: three independent drift detectors, each with failure modes stated, circuit breaker that logs its actions (to Module 1), dashboard with real-time state. This is not a toy.

3. **RBI timing.** The Model Risk Management guidance is written; the circular is pending (comments closed July 2026). Saying "pending" today (August 2026) is defensible. Saying it three months from now is weak positioning.

4. **Reference-ability.** A CTO visiting the demo sees a working AI governance platform. Under NDA, you can reference one of them as a customer. That is worth more than "we have Module 2 and we are thinking about selling it."

5. **Honest risk disclosure.** The build gate being suspended does not mean the product is incomplete. It means your commercial read on market timing is conservative. Stating this unprompted is credible.

---

## Consequences

**Easy:**
- Complete, testable system from Day 1
- Impressive demo (two modules, working together)
- Reference narrative: "Module 1 has four paying customers. Module 2 is in production with them; the circle closes when RBI enforcement is final."

**Hard:**
- Must discipline the sales conversation (lead with Module 1)
- Must resist the urge to claim Module 2 early (the gate exists to prevent this)
- If commercial gate is not met by Q2 2027, Module 2 becomes a sunk cost

**Mitigations:**
- Commercial gate is not speculative (RBI circular will come; customers who deploy for DPDP §12 compliance have AI governance as an adjacent problem)
- Build gate being suspended does not mean you built too much; it means you positioned conservatively
- If RBI circular lands and Module 2 is still not selling, the design was right but the market was not ready — a product problem, not an architecture problem

---

## The gate conditions (exactly)

### Build gate (SUSPENDED)
Not required to ship Module 2 code. Module 2 is buildable, testable, demonstrable on Day 1.

### Commercial gate (ACTIVE)
Module 2 cannot be positioned to customers as a revenue product until **one of:**
1. Four paying Module-1 customers exist, AND you have secured at least one of them for Module 2 as a reference
2. RBI Model Risk Management final regulatory circular is published, AND the kill criteria in `docs/commercial/07-KILL-CRITERIA.md` have not been triggered

---

## Revisit When

- First Module-1 customer closes (record the date; start counting to four)
- RBI MRM circular is published (move to commercial positioning)
- Q2 2027 arrives and neither gate has been met (this becomes a product/market fit question, not a build question)
