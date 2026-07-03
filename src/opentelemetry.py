"""OpenTelemetry instrumentation for AegisNex.

Optional: activated only when AEGISNEX_OTEL_ENABLED=true or
OTEL_ENABLED=true environment variable is set.
"""

from __future__ import annotations

import os
from typing import Any


def is_otel_enabled() -> bool:
    return (
        os.getenv("AEGISNEX_OTEL_ENABLED", "").strip().lower() in ("true", "1", "yes")
        or os.getenv("OTEL_ENABLED", "").strip().lower() in ("true", "1", "yes")
    )


def instrument_app(app: Any) -> None:
    """Instrument a FastAPI application with OpenTelemetry.

    This is a no-op if OpenTelemetry is not enabled or dependencies
    are not installed.
    """
    if not is_otel_enabled():
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.requests import RequestsInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ModuleNotFoundError:
        import logging
        logging.getLogger(__name__).warning(
            "OpenTelemetry packages not installed. "
            "Install: opentelemetry-api opentelemetry-sdk "
            "opentelemetry-exporter-otlp-proto-grpc "
            "opentelemetry-instrumentation-fastapi "
            "opentelemetry-instrumentation-requests"
        )
        return

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    service_name = os.getenv("OTEL_SERVICE_NAME", "aegisnex")

    resource = Resource.create({
        "service.name": service_name,
        "service.version": "1.0.0",
        "deployment.environment": os.getenv("AEGISNEX_ENV", "development"),
    })

    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=endpoint)
    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app)
    RequestsInstrumentor().instrument()

    import logging
    logging.getLogger(__name__).info(
        "OpenTelemetry instrumentation enabled, exporting to %s", endpoint
    )
