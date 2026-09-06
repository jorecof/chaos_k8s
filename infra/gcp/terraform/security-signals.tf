# =============================================================================
# Módulo C — señal de seguridad para Cloud SQL, en sustitución de Security
# Command Center. SCC (org u3 completo) requiere `securitycenter.sources.list`
# a nivel de la ORGANIZACIÓN 155714767749; jorecof@gmail.com solo tiene rol de
# Owner en el proyecto, sin permisos de organización — confirmado empíricamente
# (403 PERMISSION_DENIED sobre organizations/155714767749), mismo patrón que
# el bloqueo de iam.disableServiceAccountKeyCreation. Ver docs/U3-notas-
# implementacion.md para el detalle completo.
#
# Sustituto: Cloud Audit Logs (Admin Activity, activo por defecto sin permisos
# adicionales) + una métrica basada en logs sobre los intentos de
# autenticación fallidos hacia Cloud SQL (los logs de conexión que activamos
# en cloudsql.tf vía log_connections/log_disconnections). Cubre el panel
# "intentos de autenticación fallidos" del dashboard de Golden Signals de
# Seguridad (módulo C.3) sin depender de ningún permiso de organización.
# =============================================================================

resource "google_logging_metric" "cloudsql_failed_auth" {
  name   = "u3_cloudsql_failed_auth"
  filter = <<-EOT
    resource.type="cloudsql_database"
    resource.labels.database_id="${var.project_id}:${google_sql_database_instance.data_service.name}"
    severity>=ERROR
    textPayload:"authentication failed"
  EOT

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
    display_name = "Cloud SQL — intentos de autenticación fallidos"
  }
}

resource "google_monitoring_alert_policy" "cloudsql_failed_auth_alert" {
  display_name = "U3 — Cloud SQL: intentos de autenticación fallidos"
  combiner      = "OR"

  conditions {
    display_name = "Auth fallida > 0 en 5 min"

    condition_threshold {
      filter          = "resource.type=\"cloudsql_database\" AND metric.type=\"logging.googleapis.com/user/${google_logging_metric.cloudsql_failed_auth.name}\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"

      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_SUM"
      }
    }
  }

  alert_strategy {
    auto_close = "1800s"
  }

  documentation {
    content   = "Sustituye a Security Command Center (bloqueado por política de organización — ver docs/U3-notas-implementacion.md). Cubre el panel 'intentos de autenticación fallidos' del dashboard de Golden Signals de Seguridad, módulo C.3 del diseño de U3."
    mime_type = "text/markdown"
  }
}

output "u3_cloudsql_failed_auth_metric" {
  value = google_logging_metric.cloudsql_failed_auth.id
}
