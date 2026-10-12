"""OpenTelemetry traces derived from Relay Protocol events."""

from relay_adapter_observability_otel.bridge import OtelTraceBridge, tracer_provider_from_env

__all__ = ["OtelTraceBridge", "tracer_provider_from_env"]
