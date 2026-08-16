"""
Praman — Tamper-evident evidence engine for regulated AI in India.

Two modules, one spine:
    Module 1 (Privacy): HMAC chains, Merkle roots, Ed25519 signatures, BSA §63 certificates
    Module 2 (AI Risk): Agent governance, autonomy tiers, drift detection, HITL breaker

Architecture
    domain ← ports ← adapters ← services ← api
    Dependency direction is strictly inward.
    Swappable concerns behind Strategy interfaces; construction in factories.py.

Deployment
    Backend: Render (Free tier, 750 hrs/month)
    Database: Neon Postgres
    Frontend: Vercel
"""

__version__ = "0.1.0"
