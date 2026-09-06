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

## 5. Logs (G-05) — OTel SDK real en vez de scraping de stdout

El diseño original (`U3-Diseno-Laboratorio-Integrador.md`, §A.2) asumía que el
pilar de logs se cerraría alimentando el exporter `loki` del Collector con los
logs que las apps ya escriben a stdout (`OtelJsonFormatter`, con la clave
`trace_id`), probablemente vía un receiver `filelog`. En la implementación real
se tomó un camino distinto y más nativo de OTel: cada servicio ahora corre un
`LoggerProvider` + `OTLPLogExporter` real (SDK de logs de OTel) en paralelo al
`StreamHandler` de stdout existente (que se dejó intacto). Los logs llegan al
Collector por OTLP igual que trazas y métricas, y el Collector los reserializa
al empujarlos a Loki — en ese formato la clave del trace id es **`traceid`**
(sin guion bajo), no `trace_id` como en el JSON de stdout. El `derivedField` de
Grafana y la query `tracesToLogsV2` usan `traceid` por esto — quien lea el
diseño original y busque `trace_id` en Loki no lo va a encontrar.

No es una regresión: es una implementación más fiel al principio "3 pilares con
el SDK de OTel" que dejar el pilar de logs dependiendo de scraping de contenedor.
Se documenta porque el diseño original especificaba el otro mecanismo.

## 6. Service mesh (G-07) — Calico requiere un ajuste de compatibilidad

`istioctl x precheck`/`install` detectó `bpfConnectTimeLoadBalancing=TCP` en la
`FelixConfiguration` de Calico como incompatible con la redirección in-pod de
ztunnel (ambos reescriben la misma conexión). Se corrigió con
`kubectl patch felixconfiguration default --type=merge -p '{"spec":{"bpfConnectTimeLoadBalancing":"Disabled"}}'`
antes de habilitar el namespace en la malla — ver `scripts/setup-istio-ambient.sh`.
No estaba anticipado en el diseño original; es el tipo de detalle de plataforma
que solo aparece al ejecutar contra el cluster real (issue conocido:
https://github.com/istio/istio/issues/53750).

## 7. Alertmanager + alert-enricher (G-11) — desplegados y verificados end-to-end

El diseño (§B.3) pedía Alertmanager con un receptor `alert-enricher` propio.
Se implementó tal cual: `monitoring/alertmanager-config.yaml` (`group_wait:
10s`, ruteo único por webhook) y `alert-enricher/` (FastAPI, ~150 líneas)
que busca `trace_id` en Loki con fallback a la API de Jaeger, arma
deep-links y publica `alert_enriched_total{alertname,enriched}`. Verificado
con una alerta sintética vía `curl -X POST .../webhook`: el pipeline
completo (Prometheus ve a Alertmanager activo, Alertmanager rutea al
enricher, el enricher responde y expone la métrica) funciona; con esa
alerta sintética el resultado fue `enriched=false` porque no había ningún
error real de `data-service` en ese instante — comportamiento correcto,
no una falla.

## 8. Backtesting B.4 — promtool sustituido por replay directo sobre CSV crudos

Ver `docs/backtesting-B4-reduccion-ruido.md` para el detalle completo y el
hallazgo. Resumen: `promtool` no estaba instalado y los `series-*.json` ya
volcados no traen el desglose por `outcome` que las reglas nuevas
necesitan (se capturaron antes del fix de G-08/G-09) — se reimplementó la
lógica de las reglas en Python sobre los CSV crudos por petición
(`raw-w*.csv`), que sí tienen el detalle necesario. El resultado no es un
simple "la regla dinámica gana": la regla correlacionada
(`AIOpsCorrelatedAnomaly`) solo dispara cuando el fallo *también* eleva la
latencia, y dos de las tres corridas reales (E1, latencia pura; E2-B,
error rápido sin colgar la conexión) no cumplen esa condición aunque hay
un incidente real. Se documenta como hallazgo, no se oculta.
