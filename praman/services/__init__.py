"""
Orchestration layer — the "what happens" layer.

Responsibility
    Use cases and workflows. Receives injected ports (adapters),
    orchestrates them, and returns results. No hard-coded decisions.

Must not
    Import adapters/ directly — only receive them injected.
    Import api/ or contain FastAPI logic.
    Perform database operations directly — use EventRepository.

Pattern
    services.ledger_service.LedgerService(
        event_repository=repository,
        signer=signer,
        policy_engine=policy_engine,
    )
    Services depend on ports, never on adapters.
"""
