# ADR 0012: Module 2 (AI Risk) Build Gate vs. Commercial Gate

**Status:** Accepted, commercial gate met (16 Aug 2026)  
**Date:** 10 Aug 2026  
**Author:** Sri  
**Related:** PRAMAN_SCOPE_RECONCILIATION.md §5

---

## Context

Praman has two modules: Module 1 (Privacy/Evidence) and Module 2 (AI Risk/Governance). RBI's FREE-AI Framework (published 13 Aug 2025) establishes governance requirements for all RBI-regulated entities. Module 2 directly addresses these requirements, removing the tension between demonstrator and commercial product.

---

## Decision

**Build gate: SUSPENDED.** Module 2 ships with Module 1, live and functional.  
**Commercial gate: MET.** RBI FREE-AI Framework enforcement is final (published 13 Aug 2025, applies to all RBI-regulated entities). Module 2 is positioned as a production-ready commercial product.

### What this means in practice

- Module 2 code is complete and tested (all drift detectors, autonomy tiers, circuit breaker, dashboard)
- Module 2 routes are live and accessible
- Module 2 is now positioned in sales as a production-ready commercial offering
- Sales pitch: Lead with Module 1 for immediate DPDP §12 compliance; position Module 2 as the adjacent AI governance solution for RBI FREE-AI alignment

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

3. **RBI timing.** RBI FREE-AI Framework published 13 Aug 2025; enforcement is final and binding for all regulated entities. This removes the "wait and see" dynamic and makes Module 2 a present-day market requirement, not a future one.

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

### Commercial gate (MET)
RBI FREE-AI Framework enforcement is final (published 13 Aug 2025). Module 2 is now positioned as a production-ready commercial product. The gate is satisfied; Module 2 revenue positioning is active.

---

## Revisit When

- Module 2 traction stalls for 3+ months (reassess market positioning and pricing)
- RBI FREE-AI Framework materially changes (triggering a new gate decision)
- First Module 2 customer closes (begin tracking product/market fit velocity)
