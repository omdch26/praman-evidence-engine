"""
Observability layer — OpenTelemetry integration.

Responsibility
    Initialize OTel tracer and meter.
    Provide utilities for emitting traces and metrics.
    Isolate gen_ai.* attribute mapping (abstracted in adapter).

Must not
    Contain business logic (that is services/).
    Emit telemetry outside the client VPC.
    Depend on services/ or api/ (observability is cross-cutting).

Design notes
    OTel runs in-VPC only. Exporter endpoint is configured at deployment time
    (OTEL_EXPORTER_OTLP_ENDPOINT env var). No telemetry leaves on-premise
    without explicit operator configuration.

    gen_ai.* attributes are in Development status (as of June 2026). Wrapped
    in an adapter layer (adapters/instrumentation/otel_adapter.py) so that
    if the spec changes, only the adapter changes.

See also
    docs/ADR/0013-otel-genai-conventions.md
    adapters/instrumentation/otel_adapter.py
"""
