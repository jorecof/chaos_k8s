# =============================================================================
# Cloud Monitoring — detección por pronóstico sobre data-service (módulo B,
# B5-a del diseño de U3). Motor paralelo a la regla propia
# AIOpsCorrelatedAnomaly (μ+2σ ∧ p99>SLO): la comparación entre ambos —
# qué detecta cada uno sobre el mismo incidente, con qué MTTD y con cuánto
# ruido — es el entregable del módulo, no reemplazar uno con el otro.
#
# Filtro sin resource.type: la métrica llega vía el exporter googlecloud del
# Collector (workload.googleapis.com/*, confirmado en metricDescriptors), y
# no hace falta fijar el tipo de recurso monitoreado para que el filtro
# encuentre la serie.
# =============================================================================

resource "google_monitoring_alert_policy" "data_service_error_forecast" {
  display_name = "U3 — data-service error rate (pronóstico)"
  combiner      = "OR"

  conditions {
    display_name = "Tasa de errores de data-service por encima de lo proyectado"

    condition_threshold {
      filter          = "metric.type=\"workload.googleapis.com/data_requests_total\" AND resource.type=\"generic_task\" AND resource.label.job=\"data-service\" AND metric.label.outcome=\"error\""
      comparison      = "COMPARISON_GT"
      # ~1% de error rate sobre el tráfico de referencia del Game Day (≈2,4 rps,
      # ver U2) — el mismo piso que usa la regla propia, para que la
      # comparación del módulo B.4/B.5 sea contra el mismo umbral de negocio.
      threshold_value = 0.024
      duration        = "0s"

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
      }

      forecast_options {
        forecast_horizon = "3600s"  # mínimo permitido por la API
      }
    }
  }

  alert_strategy {
    auto_close = "1800s"
  }

  documentation {
    content   = "Motor paralelo a la regla propia AIOpsCorrelatedAnomaly (μ+2σ ∧ p99>SLO). Ver módulo B.5 del diseño de U3 — tabla comparativa de motores."
    mime_type = "text/markdown"
  }
}

output "u3_cloud_monitoring_policy_name" {
  value = google_monitoring_alert_policy.data_service_error_forecast.name
}
