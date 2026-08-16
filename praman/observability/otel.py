"""
OpenTelemetry tracer and meter initialization.

Responsibility
    Create and configure OTel tracer and meter for the application.
    Initialize OTLP exporter if OTEL_ENABLED (else use no-op).
    Provide utilities for creating spans and recording metrics.

Must not
    Import from services/, api/, or adapters/.
    Emit telemetry outside the VPC (exporter endpoint is VPC-internal).
    Contain business logic or domain knowledge.

Design
    OTel is optional (controlled by OTEL_ENABLED env var).
    If disabled, tracer/meter are no-ops (zero overhead).
    If enabled, OTLP exporter sends to OTEL_EXPORTER_OTLP_ENDPOINT.
    All gen_ai.* attributes are mapped in adapters/ (not here).
"""

from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import SimpleMetricReader
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.resources import Resource
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def init_otel(
    enabled: bool,
    exporter_endpoint: str,
    service_name: str,
    environment: str,
) -> tuple[trace.Tracer, metrics.Meter]:
    """
    Initialize OpenTelemetry tracer and meter.

    If enabled=False, returns no-op tracer and meter (zero overhead).
    If enabled=True, initializes OTLP exporter to send telemetry to
    exporter_endpoint.

    Args:
        enabled: Whether OTel is enabled (OTEL_ENABLED env var).
        exporter_endpoint: OTLP collector endpoint (e.g., http://localhost:4317).
        service_name: Service name for resource (praman-api).
        environment: Environment tag (development, production, etc.).

    Returns:
        tuple of (tracer, meter) ready to use.
    """
    if not enabled:
        # No-op tracer and meter
        logger.info("OTel disabled. Using no-op tracer and meter.")
        return trace.get_tracer(__name__), metrics.get_meter(__name__)

    # Create resource
    resource = Resource.create({
        "service.name": service_name,
        "deployment.environment": environment,
    })

    # Initialize tracer provider with OTLP exporter
    try:
        otlp_span_exporter = OTLPSpanExporter(endpoint=exporter_endpoint)
        trace_provider = TracerProvider(resource=resource)
        trace_provider.add_span_processor(SimpleSpanProcessor(otlp_span_exporter))
        trace.set_tracer_provider(trace_provider)
        tracer = trace.get_tracer(__name__)
        logger.info(f"OTel tracer initialized (endpoint={exporter_endpoint})")
    except Exception as e:
        logger.warning(f"Failed to initialize OTel tracer: {e}. Using no-op.")
        tracer = trace.get_tracer(__name__)

    # Initialize meter provider with OTLP exporter
    try:
        otlp_metric_exporter = OTLPMetricExporter(endpoint=exporter_endpoint)
        metric_reader = SimpleMetricReader(otlp_metric_exporter)
        meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
        metrics.set_meter_provider(meter_provider)
        meter = metrics.get_meter(__name__)
        logger.info(f"OTel meter initialized (endpoint={exporter_endpoint})")
    except Exception as e:
        logger.warning(f"Failed to initialize OTel meter: {e}. Using no-op.")
        meter = metrics.get_meter(__name__)

    return tracer, meter


def create_span_attributes(
    span_type: str,
    **kwargs,
) -> dict:
    """
    Create span attributes with a standard format.

    Args:
        span_type: Type of span (e.g., "policy.evaluate", "drift.detect")
        **kwargs: Additional attributes to add

    Returns:
        dict of span attributes
    """
    attrs = {
        "span.type": span_type,
    }
    attrs.update(kwargs)
    return attrs
