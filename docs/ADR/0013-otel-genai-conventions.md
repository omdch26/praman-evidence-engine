# ADR 0013: OpenTelemetry with gen_ai.* Attributes (Development Status)

**Status:** Accepted  
**Date:** 10 Aug 2026  
**Author:** Sri  
**Reference:** PRAMAN_GRAPH_VALIDATION_v4.md (10 Aug validation pass)

---

## Context

Module 2 (AI Risk) needs to trace agent actions, model calls, and policy evaluations. OpenTelemetry (OTel) is the standard observability format. The OTEL community publishes gen_ai.* semantic conventions for tracing LLM calls.

However, as of June 2026, the `gen_ai.*` attributes are in **Development** status, not Stable. This means they can change without deprecation warnings.

---

## Decision

Use OpenTelemetry with `gen_ai.*` attributes for:
- `gen_ai.system` (e.g., "openai", "azure", "ollama")
- `gen_ai.request.model` (model identifier)
- `gen_ai.request.temperature` (sampling parameter)
- `gen_ai.response.finish_reason` (why the generation stopped)

**Isolation strategy:**
- Wrap OTel calls in a thin adapter layer (`adapters/instrumentation/otel_adapter.py`)
- Attribute mapping is centralised in one file
- If OTel changes the conventions (post-Stable), one file changes
- If you need to swap OTel for Langfuse or Arize later, one adapter swaps

---

## Rationale

1. **Vendor independence.** OTel is backend-agnostic; one exporter sends traces to Grafana, Datadog, or your own collector.

2. **Client VPC isolation.** OTel runs inside the client's VPC; no telemetry leaves on-premise without explicit consent. This is non-negotiable for BFSI.

3. **Standards are converging.** `gen_ai.*` development status is temporary; stable release is expected by end of 2026. Being early is safer than being late.

4. **Competitive transparency.** Praman instruments *all* decisions (policy evaluation, drift detection, circuit breaker). Langfuse/Arize instrument some decisions and hide others. Full instrumentation is the product claim.

---

## Consequences

**Easy:**
- One vendor for all telemetry (not a patchwork of Langfuse + Arize + custom logging)
- Backend flexibility (choose exporter at deployment time, not code-change time)
- Evidence compliance (drift detection decision is logged as OTel span, captured in Module 1 ledger)

**Hard:**
- `gen_ai.*` spec may change (medium risk; Stable release likely by end of 2026)
- Custom exporters are not built-in (you may need to write your own if exporting to an old system)

**Mitigations:**
- Isolated adapter layer means one file changes if spec evolves
- Monitor OTEL repo for spec changes; subscribe to release notes
- Write tests for attribute mapping (if spec changes, tests will fail with clear error)

---

## Configuration

In `praman/config.py`:

```python
OTEL_ENABLED: bool = False  # Development: disabled by default
OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:4317"  # For local testing
OTEL_SERVICE_NAME: str = "praman-api"
OTEL_ENVIRONMENT: str = "development"
```

At deployment time (Render):
```bash
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=https://your-collector.example.com:4317
OTEL_ENVIRONMENT=production
```

---

## Revisit When

- OTEL `gen_ai.*` moves to Stable (update this ADR to note the version)
- You need to export to a system that does not support OTEL OTLP (May need a second exporter)
- Performance analysis shows OTel overhead is unacceptable (unlikely; OTel is designed for production)
