# U3 — Notas de implementación (sesión 2026-09-06)

Registro de las decisiones tomadas al construir la parte de GCP del laboratorio
integrador, sobre todo donde la realidad del proyecto (`project-ae3ce4fd-3eea-42ed-b57`,
organización `155714767749`) obligó a desviarse del diseño original
([[U3-Diseno-Laboratorio-Integrador]]).

## 1. Cloud SQL — sin key de service account descargable

El diseño original (A.4) asumía una key de SA montada como Secret para el sidecar
`cloud-sql-proxy`. La política de organización `constraints/iam.disableServiceAccountKeyCreation`
lo bloquea (`FAILED_PRECONDITION: Key creation is not allowed on this service account`),
y `jorecof@gmail.com` no tiene `orgpolicy.policies.create` a nivel de organización para
anularla (confirmado empíricamente, no es una suposición).

**Sustituto:** `gcloud auth application-default login` genera credenciales OAuth del
usuario (`~/.config/gcloud/application_default_credentials.json`), que no son una key
de SA y por lo tanto no las bloquea esa política. Se montan igual, vía el mismo
`GOOGLE_APPLICATION_CREDENTIALS`, en el Secret `data-service-gcp-sql` (clave
`sa-key.json`, nombre heredado del diseño original aunque el contenido ya no es una
key de SA). La service account `data-service-sql-client` se dejó creada en Terraform
como documentación de la identidad "correcta" para una futura migración a Workload
Identity Federation (ver §4, roadmap).

**Limitación de "sin IP pública" del diseño original:** el cluster kubeadm de Bogotá
no tiene VPN ni Interconnect hacia GCP, así que Private IP / Private Service Connect
es inalcanzable desde ahí. La instancia quedó con `ipv4_enabled = true`; el Cloud SQL
Auth Proxy no depende de una allowlist de IP (autentica con IAM + certificados
efímeros), así que esto no reabre el riesgo de exponer el puerto directamente.

## 2. VPC Flow Logs — no aplican al tráfico real de Cloud SQL

VPC Flow Logs capturan tráfico en subredes de VPC (interfaces de VMs/GKE). Cloud SQL
con solo IP pública no tiene una NIC en una subred propia para ese camino — su IP
pública la sirve la infraestructura del propio Cloud SQL, no una subred que se pueda
instrumentar. Activar Flow Logs en la subred del GKE que quedó de la actividad
anterior habría cumplido la letra del enunciado pero sobre tráfico sin relación con
`data-service` ni con U3.

**Sustituto:** `log_connections` y `log_disconnections` activados como
`database_flags` en la instancia — capturan cada conexión/desconexión real del
`cloud-sql-proxy` hacia Cloud Logging (`cloudsql.googleapis.com%2Fpostgres.log`).

## 3. Security Command Center — bloqueado por permisos de organización

Igual patrón que en §1: `securitycenter.sources.list` denegado sobre
`organizations/155714767749` (403 `IAM_PERMISSION_DENIED`). Activar SCC por primera
vez requiere un rol de organización (`securitycenter.admin` u
`organizationAdmin`) que `jorecof@gmail.com` no tiene — es un límite administrativo,
no técnico, y no se puede resolver escribiendo más Terraform.

**Sustituto:** Cloud Audit Logs (Admin Activity, activo por defecto sin permisos
adicionales) + una métrica basada en logs (`google_logging_metric.cloudsql_failed_auth`)
sobre los intentos de autenticación fallidos hacia Cloud SQL, con una política de
alerta encima (`google_monitoring_alert_policy.cloudsql_failed_auth_alert`). Cubre el
panel de "intentos de autenticación fallidos" del dashboard de Golden Signals de
Seguridad (C.3) sin depender de ningún permiso de organización.

**Pendiente real, no técnico:** si alguien con rol de administrador en la organización
`155714767749` habilita SCC (o le concede `securitycenter.admin` a la cuenta), se
puede retomar el plan original sin cambiar nada del resto del laboratorio.

## 4. Para el reporte de madurez (módulo E)

Estos tres puntos son honestos de reportar como brechas con causa administrativa,
no de ingeniería:

- OBSF-6 (AIOps): el motor de Cloud Monitoring por pronóstico sí quedó completo
  (política `data_service_error_forecast`), pero autenticado por ADC de usuario, no
  por Workload Identity Federation — anotar como roadmap a 3 meses la migración a
  WIF una vez haya un endpoint público donde alojar el JWKS del cluster kubeadm.
- OBSF-7 (seguridad y red): VPC Flow Logs clásico no aplica a esta arquitectura
  (IP pública, sin VPN); el sustituto de Cloud SQL logging es real pero más angosto
  que Flow Logs. SCC completo queda fuera de alcance por permisos de organización,
  no por decisión de diseño — documentar la diferencia entre "no lo hicimos" y
  "no pudimos pedirlo".
