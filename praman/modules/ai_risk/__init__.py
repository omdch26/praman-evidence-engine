"""
Module 2: AI Risk — Agent governance and drift detection.

Responsibility
    Implement autonomy tiers and delegation ceilings.
    Three drift detectors: data (PSI), semantic (entropy), behavioural (distribution).
    Human-in-the-loop circuit breaker.
    Dashboard with three gauges and two workspaces.

Must not
    Contain privacy/evidence logic (that is Module 1).
    Import from modules.privacy.
    Make decisions about record admissibility.

Deliverables (production-ready — see docs/ADR/0012-module-two-build-gate.md)
    - Autonomy tier enforcement
    - Delegation ceiling logic
    - Three drift detectors
    - Circuit breaker with fallback
    - Dashboard gauges and workspace switcher
    - LLM-as-judge policy evaluation

Commercial gate: met (RBI FREE-AI Framework published 13 Aug 2025). Module 2
ships as a production-ready commercial offering alongside Module 1.
"""

from praman.modules import ModuleRegistration

MODULE = ModuleRegistration(
    name="ai_risk",
    version="0.1.0",
    enabled=True,
    description="Agent governance, autonomy tiers, drift detection, HITL breaker",
)
