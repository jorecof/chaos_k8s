# Terraform GCP — módulo A.4/B.5 del laboratorio integrador U3

Este directorio es una **copia sincronizada** de `~/otel-e2e-lab/deploy/gcp/terraform`
para que todo el IaC quede en este repo, tal como pide la rúbrica. El `terraform apply`
real se sigue corriendo desde `otel-e2e-lab` — ahí vive el `.tfstate` (deliberadamente
fuera de este repo, ver `.gitignore`: tiene en texto plano el password de
`random_password.data_service_db`).

Si necesitas reaplicar o modificar algo, hazlo en `~/otel-e2e-lab/deploy/gcp/terraform`
y vuelve a copiar los `.tf` (no el estado) hacia acá antes del commit final.

## Qué crea

- `main.tf` — GKE Autopilot + Artifact Registry (de una actividad anterior, no forma
  parte del alcance de U3; se dejó tal cual porque el proyecto ya lo tenía desplegado).
- `cloudsql.tf` — instancia Cloud SQL `db-f1-micro`, base `appdb`, usuario `app`,
  service account `data-service-sql-client` (sin key descargable — la política de
  organización `iam.disableServiceAccountKeyCreation` lo bloquea; el sidecar
  `cloud-sql-proxy` autentica con ADC del usuario en su lugar, ver
  `base/02-deployments.yaml` del repo).
- `cloud-monitoring.tf` — política de alerta por pronóstico sobre
  `workload.googleapis.com/data_requests_total{outcome="error"}` (módulo B, B5-a).
- `budget.tf`, `variables.tf`, `outputs.tf` — heredados de `otel-e2e-lab`.
