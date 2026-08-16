"""
FastAPI routers — the thin HTTP layer.

Responsibility
    Parse HTTP requests, call services, serialize responses.
    No business logic. Route handlers are 5–10 lines maximum.

Must not
    Contain business logic, cryptographic decisions, or orchestration.
    Import domain/ directly.
    Make decisions about policy evaluation or evidence creation.

Pattern
    @router.get("/events/{event_id}")
    async def get_event(event_id: str, service: LedgerService = Depends(...)):
        return await service.get_event(event_id)

If the handler is >10 lines, the logic belongs in services/.
"""
