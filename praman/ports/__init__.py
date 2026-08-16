"""
Abstract interfaces (Protocols) — the Strategy contracts.

Responsibility
    Define interfaces for swappable concerns: PolicyEngine, AnchorBackend,
    Signer, DriftScorer, CertificateRenderer, EventRepository.
    No concrete implementation here.

Must not
    Import from adapters/, services/, or api/.
    Contain business logic or actual implementations.
    Know how something will be implemented.

Why this layer exists
    A bank running OPA instead of JSON rules should change one adapter file
    and one factory line, not rewrite the entire system.

Example: ports.policy_engine.PolicyEngine is an abstract Protocol;
adapters.policy.json_rules.JsonRulesPolicyEngine is the concrete impl.
"""
