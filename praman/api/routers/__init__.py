"""
API route modules.

Responsibility
    Each router module handles one set of related endpoints.
    Routers are thin (parse, call service, return).
    No business logic in the router.

Pattern
    from praman.api.routers.events import router as events_router
    app.include_router(events_router, prefix="/api", tags=["events"])
"""
