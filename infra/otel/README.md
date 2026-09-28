# OpenTelemetry config (Phase 10)

POC uses **RP-native** observability first: `METRIC` + `TRACE_LINK` events in the append-only log, plus `/dev/sessions/{id}/timeline`.

## Optional OTLP profile (local)

```yaml
# collector.yaml — forward to Grafana Tempo / Jaeger post-POC
receivers:
  otlp:
    protocols:
      grpc:
exporters:
  logging:
    loglevel: info
service:
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [logging]
```

Wire gateway/runtime OTLP exporters in a follow-up; do not block POC sign-off on Tempo.

See [OBSERVABILITY_EVAL.md](../../plans/OBSERVABILITY_EVAL.md).
