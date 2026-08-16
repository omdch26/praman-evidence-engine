"""
Module 1: Privacy — Court-admissible evidence layer.

Responsibility
    Build and manage HMAC-chained, Merkle-rooted, signed evidence.
    Produce BSA §63-compliant certificates.
    Ensure no personal data enters the ledger (resolves §12 paradox).

Must not
    Contain AI governance logic (that is Module 2).
    Import from modules.ai_risk.
    Make decisions about agent autonomy or drift.

Deliverables
    - Append-only event ledger
    - HMAC chaining per client-held key
    - Merkle tree construction and root
    - Ed25519 signatures
    - RFC 3161 timestamping
    - BSA §63 certificate generation
"""

from praman.modules import ModuleRegistration

MODULE = ModuleRegistration(
    name="privacy",
    version="0.1.0",
    enabled=True,
    description="Court-admissible evidence layer with HMAC chains, Merkle roots, §63 certificates",
)
