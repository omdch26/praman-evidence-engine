# ADR 0012: Module 2 (AI Risk) Build Gate vs. Commercial Gate

**Status:** Accepted, gate condition needs reassessment (see addendum)  
**Date:** 10 Aug 2026  
**Author:** Sri  
**Related:** PRAMAN_SCOPE_RECONCILIATION.md §5

---

## Addendum — 16 Aug 2026

This ADR's commercial gate condition #2 refers to "RBI MRM circular enforcement final" and describes the guidance as "in draft, final circular pending" as of 10 Aug 2026. That description is out of date: RBI's actual instrument in this space is the **FREE-AI Framework** ("Framework for Responsible and Ethical Enablement of AI"), released **13 Aug 2025** — a full year before this ADR was written, not a pending draft. It sets 7 Sutras, 6 Pillars, and 26 Recommendations, and applies to all RBI-regulated entities.

Whether this counts as "circular enforcement final" in the sense gate condition #2 intended is a judgment call — FREE-AI is a committee framework with recommendations, not necessarily a binding circular with penalties in the way "MRM circular" implied. **This needs Sri's decision, not an automated one.** The terminology below is corrected to the accurate regulation name; the gate status itself is left for reassessment rather than silently marked met.

---

## Context

Praman has two modules: Module 1 (Privacy/Evidence) and Module 2 (AI Risk/Governance). At the time of writing, RBI's AI governance guidance was believed to be in draft. There is tension between shipping Module 2 as a demonstrator and making a commercial claim on it. *(See addendum above — RBI's FREE-AI Framework was in fact already published by this date.)*

---

## Decision

**Build gate: SUSPENDED.** Module 2 ships with Module 1, live and functional.  
**Commercial gate: STANDS.** Revenue claims on Module 2 require either (1) four paying Module-1 customers, OR (2) RBI FREE-AI Framework enforcement final (see addendum — this may already apply; needs review).

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

3. **RBI timing.** *(As believed at time of writing — see addendum: FREE-AI was already published by this date.)* The guidance is written; the circular is pending. Saying "pending" today is defensible. Saying it three months from now is weak positioning.

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
2. RBI FREE-AI Framework enforcement is final (addendum: the framework itself has been published since 13 Aug 2025 — confirm whether this satisfies "enforcement final" before treating the gate as met), AND the kill criteria have not been triggered

---

## Revisit When

- First Module-1 customer closes (record the date; start counting to four)
- RBI FREE-AI Framework enforcement status is confirmed final (addendum: framework already published — this line item may already be triggered; move to commercial positioning once confirmed)
- Q2 2027 arrives and neither gate has been met (this becomes a product/market fit question, not a build question)
