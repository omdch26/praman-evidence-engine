# ADR 0002: Merkle Tree Over Blockchain

**Status:** Accepted  
**Date:** 10 Aug 2026  
**Author:** Sri

---

## Context

We need tamper-evidence: any change to an event must be detectable. Three approaches exist: Merkle tree, blockchain (consensus-based ledger), or centralised notary. Each has different trust properties and operational costs.

---

## Options Considered

| Option | Tamper-evidence? | Consensus needed? | Cost | Operational surface |
|---|---|---|---|---|
| **Merkle tree (chosen)** | Yes (any change → root changes) | No (one writer, one ledger) | Free | Low (just storage) |
| **Blockchain** | Yes (all replicas must agree) | Yes (Byzantine consensus) | High (fees, latency) | High (nodes, coordination) |
| **Centralised notary (RFC 3161)** | No at write time; anchored retroactively | No | Medium (timestamping service) | Low (external service) |

---

## Decision

Use a Merkle tree to prove tamper-evidence locally. Anchor the root externally via RFC 3161 for time proof. Never use blockchain.

**Merkle tree properties:**
- Binary tree over event HMACs
- Root is a single hash; any event change flips it
- Odd nodes duplicate the final hash (CT convention)
- Leaves and internal nodes are domain-separated (0x00 prefix for leaves, 0x01 for nodes) to prevent second-preimage attack
- Inclusion proofs allow proving one event is in the tree without revealing others

**RFC 3161 anchoring:**
- Root is sent to a Timestamping Authority (TSA)
- TSA returns a signed timestamp proving "the root existed on this date"
- Timestamp is then part of the certificate
- Verification needs only the TSA's public key; no ongoing trust in the TSA

---

## Rationale

1. **No consensus problem.** A blockchain requires Byzantine consensus. We have one writer (the bank) and one ledger per tenant. Zero Byzantine problem exists.

2. **Cost.** Blockchain fees (Ethereum, Solana) cost ₹1000–10000+ per transaction. Merkle is free.

3. **Latency.** Blockchain blocks are confirmed over minutes or seconds. Merkle roots are computed in milliseconds.

4. **Regulatory clarity.** Merkle roots are well-understood in Indian evidence law (BSA §63 contemplates hash values). Blockchain has no clear standing in Indian courts yet.

5. **Operational simplicity.** Running blockchain nodes is a DevOps burden. Storing a Merkle tree is just a table.

6. **Vendor independence.** RFC 3161 Timestamping Authorities are commodity services (FreeTSA, Digicert, etc.). No lock-in.

---

## Consequences

**Easy:**
- Proving tamper-evidence locally without external dependencies
- Off-chain storage; no blockchain operational complexity
- Efficient inclusion proofs (O(log n) proof size)
- Portable to any ledger structure (not locked to one blockchain)

**Hard:**
- Must have one writer per tenant (scalability constraint; but this is a feature for evidence isolation)
- Cannot redistribute trust across multiple parties (one bank owns one ledger)
- Anchoring is separate from storage (adds a step in the workflow)

**Mitigations:**
- If multi-party auditability is needed later, the root can be published on-chain without rewriting the system
- RFC 3161 anchoring is instantaneous; can be added post-commit
- Merkle tree only proves tampering was detected; it does not prove non-tampering

---

## Revisit When

- Regulation requires blockchain (unlikely in India; BSA §63 does not mandate it)
- Multi-tenant shared ledger is needed (current design is tenant-isolated)
- Consensus among multiple validators is a requirement (currently: single writer per tenant)
