"""
Instrumentation adapters — telemetry emission.

Responsibility
    Abstract telemetry concerns behind clean interfaces.
    Map business concepts to vendor formats (OTel, Langfuse, Datadog).
    Centralise spec version handling (gen_ai.* is Development status).

Must not
    Import from services/ or api/.
    Contain business logic.
    Make assumptions about who consumes the telemetry.
"""
