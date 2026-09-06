# U3 — Diseño del Laboratorio Integrador de Observabilidad

**Repo base:** `jorecof/chaos_k8s` · **Cluster:** kubeadm 3 nodos (kube-cp .20, kube-w1 .21, kube-w2 .22)
**Fecha:** 2026-08-31 · **Autor:** Ernesto Ilich Contreras
**Estrategia aprobada:** híbrida — el cluster propio es el sistema de referencia; la nube se enciende
en ventanas medidas y acotadas por presupuesto.

---

## 0. Resumen de decisiones

| # | Decisión | Razón |
|---|---|---|
| D-01 | El cluster kubeadm es el **sistema bajo prueba**; GCP y AWS aportan **piezas reales acotadas** (Cloud SQL, RDS, VPC Flow Logs, SCC, DevOps Guru) | Evidencia auténtica sin costo relevante; el caos y el SLO se miden donde ya hay línea base y herramientas propias |
| D-02 | `data-service` entra en la **cadena de trazas** vía `service-b → data-service` | Hoy cuelga suelto: sin propagación no hay traza distribuida de 4 niveles ni blast radius que suba |
| D-03 | **Tres backends de datos en paralelo**: PostgreSQL local, Cloud SQL (GCP), RDS (AWS), seleccionables por request | Un solo dashboard compara `db.provider`; la latencia WAN real (Bogotá → us-central1) da un flame graph honesto |
| D-04 | Migrar a **OTel DB Semantic Conventions estables** (`db.system.name`, `db.namespace`, `db.operation.name`, `db.collection.name`, `db.query.text`, `server.address`) | Las actuales son la versión experimental previa; la rúbrica pide semconv, no atributos ad hoc |
| D-05 | Service mesh **Istio ambient** (plan B: Linkerd 2) | **AWS App Mesh queda sin soporte el 30-sep-2026** (verificado hoy). Ambient es lo que Cloud Service Mesh usa por debajo y no mete sidecar en cada pod |
| D-06 | La alerta se enriquece con `trace_id` mediante un **webhook receptor** que consulta Loki/Jaeger, no mediante exemplars | Camino más corto y demostrable; los exemplars quedan como refuerzo opcional |
| D-07 | La reducción de ruido se demuestra por **backtesting con `promtool test rules`** sobre las series ya volcadas de la sesión canónica del 30-ago | Datos reales, cero corridas nuevas, comparación estático vs. dinámico sobre la *misma* ventana |
| D-08 | El experimento de error rate se corre en **dos variantes** (500 real en la app vs. `HTTPChaos` abortando la respuesta) | La variante HTTPChaos reproduce el *blind spot* del Hallazgo 1 de U2: sin span de error no hay `trace_id` que adjuntar. El contraste es el hallazgo del módulo B |
| D-09 | Seguridad local = **Falco + Trivy Operator + telemetría L7 del mesh**; en la nube, **SCC Standard (gratis) y Security Hub** | Cubre runtime, CVEs y tráfico E-O con datos reales que exportan a Prometheus |
| D-10 | Todo lo nuevo se instrumenta con **medición de MTTD de tres tiempos** (señal, alerta, notificación) | El objetivo de <2 min es sobre la notificación; hay que presupuestar los retardos, no medirlos a posteriori |

---

## 1. Punto de partida — inventario verificado

Revisado directamente sobre `~/chaos_k8s` y `~/otel-e2e-lab` el 2026-08-31.

### 1.1 Lo que ya existe y sirve

| Componente | Estado | Ubicación |
|---|---|---|
| `service-a` (órdenes, FastAPI, OTel SDK) | 2 réplicas, HPA por CPU | `service-a/main.py`, `base/02-deployments.yaml:196` |
| `service-b` (inventario) | 2 réplicas | `service-b/main.py`, `:274` |
| **`data-service`** (catálogo, OTel SDK, psycopg2 instrumentado) | **ya escrito para esta actividad**, 2 réplicas | `data-service/main.py`, `:346` |
| PostgreSQL 16 + `init.sql` (tablas `orders`, `inventory`, `products`) | 1 réplica | `base/01-configmaps.yaml` |
| OTel Collector 0.103.0 | DaemonSet 3 réplicas, pipelines traces/metrics/logs | `base/02-deployments.yaml:84` |
| Jaeger 1.58 (memoria, `MEMORY_MAX_TRACES=20000`, 1Gi) | corregido tras el OOMKill del 30-ago | `:421` |
| Prometheus 2.52 + reglas | 1 réplica, sin `--web.enable-lifecycle` | `:485`, `monitoring/prometheus-config.yaml` |
| Grafana + dashboard `gameday` | datasource **solo Prometheus** | `monitoring/grafana.yaml` |
| blackbox-exporter, sondas cada 5 s | `/health` y `/data/products` de data-service, `/health` de service-a | `monitoring/blackbox-exporter.yaml` |
| Chaos Mesh: NetworkChaos y HTTPChaos (3 variantes) | validados | `chaos-mesh/*.yaml` |
| Registry propio `192.168.0.20:30500` | imágenes arm64 | `registry/` |
| Scripts instrumentados con preflight, verificación de inyección y limpieza | `run-exp1.sh`, `run-exp2.sh`, `run-gameday.sh`, `prom-labels.sh`, `dump-series.sh` | `scripts/` |
| Terraform GCP (GKE, Artifact Registry, Workload Identity, **budget**) y AWS (ECS, ECR, service discovery, **budget**) | del lab `otel-e2e-lab` | `~/otel-e2e-lab/deploy/{gcp,aws}/terraform` |
| Series de Prometheus a 5 s de la sesión canónica del 30-ago | insumo para el backtesting del módulo B | `results/gameday-final/series-*.json` |

### 1.2 Brechas — lo que el laboratorio integrador exige y hoy no está

| # | Brecha | Impacto | Módulo |
|---|---|---|---|
| G-01 | **`data-service` no está en la cadena de llamadas.** `service-a` solo llama a `service-b` (`service-a/main.py:238`); nadie llama a `data-service` salvo el blackbox y la carga directa | No hay traza distribuida de 3 microservicios; un fallo en data-service no se propaga ni se ve arriba | A, D |
| G-02 | `data-service` apunta a `postgres-svc` local, no a Cloud SQL ni RDS | El módulo A pide explícitamente el acceso a la BD gestionada | A |
| G-03 | Atributos de BD en la convención **experimental antigua** (`db.system`, `db.name`, `db.operation`, `db.sql.table`, `db.statement`, `db.connection_string`) | La rúbrica pide DB Semantic Conventions; además `db.statement` con la query cruda es riesgo de fuga | A |
| G-04 | `/data/analytics/{id}` es `time.sleep` + `random` — **no toca la base** | Un span "de BD" que no consulta nada es evidencia inválida | A |
| G-05 | **Pilar de logs incompleto**: el pipeline `logs` del collector exporta solo a `logging` (stdout). No hay Loki en este repo | Los "3 pilares" no están cerrados; sin Loki no hay pivote log→traza | A, B |
| G-06 | Grafana tiene **un solo datasource** (Prometheus). Sin Jaeger ni Loki, sin `derived fields`, sin trace-to-logs | La correlación existe en el dato pero no en la herramienta | A |
| G-07 | **No hay service mesh** → no hay telemetría L7 de red ni mapa de servicios | A, C |
| G-08 | Las reglas AIOps actuales apuntan a series que **probablemente no existen**: usan `otelcol_http_requests_total{status=...}` y `job="service-b"`, pero el gotcha documentado dice que el servicio se identifica por **`exported_job`** y el contador de la app es `otelcol_data_requests_total` | Alertas que nunca disparan = MTTD infinito | B |
| G-09 | `data_requests_total` **no lleva atributo de resultado** (solo `endpoint` y `cloud`) → no se puede derivar error rate de esa serie | B, D |
| G-10 | El umbral actual es `baseline * 3`, no `baseline + 2σ`; no hay cálculo de σ ni ventana de baseline desplazada | B |
| G-11 | **No hay Alertmanager en el cluster** → no hay entrega, ni enriquecimiento, ni MTTD de notificación medible | B, D |
| G-12 | El SLI de disponibilidad sigue definido como proporción de 5xx; quedó pendiente pasarlo a `probe_success` del blackbox | El Hallazgo 1 de U2 demostró que ese SLI es ciego a `http_code=000` | D |
| G-13 | Sin observabilidad de red ni de seguridad de ningún tipo | C |
| G-14 | Sin autoevaluación de madurez ni roadmap | E |

---

## 2. Arquitectura objetivo

```
                                   ┌──────────────────────────────────────────┐
   generador de carga  ──N-S──►    │  cluster kubeadm (Debian 12 arm64, K8s   │
   (Mac, circuito abierto)         │  v1.35, Calico, malla Istio ambient)     │
                                   │                                          │
                                   │   service-a ──E-O──► service-b           │
                                   │   (órdenes)          (inventario)        │
                                   │       │                  │  │            │
                                   │       │                  │  └──► postgres│
                                   │       │                  │      (local)  │
                                   │       │                  ▼               │
                                   │       │            data-service ◄─ NUEVO │
                                   │       │            (catálogo)   en la    │
                                   │       │                 │       cadena   │
                                   └───────┼─────────────────┼────────────────┘
                                           │                 │
                        ztunnel/waypoint   │                 ├──► PostgreSQL local  (db.provider=local)
                        métricas L7 ───────┘                 ├──► Cloud SQL  (GCP)  (db.provider=cloud-sql)
                                                             └──► RDS        (AWS)  (db.provider=rds)

   TELEMETRÍA                       SEGURIDAD Y RED                 CAOS
   OTel Collector (DaemonSet)       Falco (runtime)                 Chaos Mesh
     ├─ trazas  → Jaeger            Trivy Operator (CVEs)             ├─ NetworkChaos 200 ms → service-b
     ├─ métricas→ Prometheus        VPC Flow Logs GCP + AWS           └─ HTTPChaos / 500 in-app → data-service
     └─ logs    → Loki  ◄─ NUEVO    SCC Standard · Security Hub
                                                  │
   Prometheus ──► Alertmanager ──► webhook enriquecedor ──► alerta con trace_id
                                    (consulta Loki/Jaeger)   + deep-link a Jaeger y Grafana
```

**Cadena de trazas resultante (4 niveles):**
`cliente → service-a /orders → service-b /inventory/{producto} → data-service /data/products → SELECT (local | Cloud SQL | RDS)`

---

## 3. Módulo A — Arquitectura observable completa

### A.1 Integrar `data-service` en la cadena

`service-b`, al resolver `/inventory/{producto}`, llama a `data-service` para enriquecer con catálogo
(precio, categoría). Con `httpx` instrumentado, el contexto se propaga solo.

Se aplica desde el inicio la **remediación #1 verificada en U2** para no reintroducir la debilidad D1:

```python
# service-b/main.py
_client = httpx.AsyncClient(
    timeout=httpx.Timeout(connect=0.25, read=0.8),      # p99 real 36 ms → presupuesto por salto
    limits=httpx.Limits(max_connections=20,             # bulkhead
                        max_keepalive_connections=10),
)
```

Y degradación elegante: si `data-service` falla o excede el presupuesto, `service-b` responde el
inventario con `catalog: {"status": "unavailable"}` y marca el span con
`span.set_attribute("degraded", True)` — nunca 500. Esto es lo que hace que el experimento D2 pueda
responder la pregunta *"¿la alerta fue accionable?"* con algo más que un sí/no.

**Por qué `service-b → data-service` y no `service-a → data-service`:** da profundidad de 4 niveles y
obliga a que el fallo del tercer servicio suba dos saltos, que es donde se ve si el circuit breaker
y el bulkhead funcionan.

### A.2 Instrumentación completa — tres pilares

| Pilar | Hoy | Objetivo |
|---|---|---|
| Trazas | OTLP → Collector → Jaeger; `filter/health` activo | Igual, más el sub-span huérfano de ASGI `/health` filtrado por nombre además de por `http.target` |
| Métricas | OTLP → Collector → Prometheus (`otelcol_*`) | Añadir atributo **`outcome`** (`success`/`error`) y `http.response.status_code` a `data_requests_total` (cierra G-09), y la métrica estable `db.client.operation.duration` |
| **Logs** | solo `logging` a stdout | **Loki 3.x** + pipeline `logs` del collector con exporter `loki`; los logs ya llevan `trace_id` y `span_id` inyectados por `OtelJsonFormatter` |

**Correlación en Grafana** (cierra G-06) — tres datasources y los enlaces:

```yaml
# monitoring/grafana.yaml — datasources
- name: Jaeger
  type: jaeger
  url: http://jaeger-svc:16686
  jsonData:
    tracesToLogsV2:
      datasourceUid: loki
      filterByTraceID: true
      spanStartTimeShift: "-2m"
      spanEndTimeShift: "2m"
    tracesToMetrics:
      datasourceUid: prometheus
- name: Loki
  type: loki
  url: http://loki-svc:3100
  jsonData:
    derivedFields:
      - name: TraceID
        matcherRegex: '"trace_id":"(\w+)"'
        url: '${__value.raw}'
        datasourceUid: jaeger
```

### A.3 Database spans con OTel DB Semantic Conventions (cierra G-03, G-04)

Migración de atributos en `data-service/main.py`:

| Actual (experimental antiguo) | Estable | Valor |
|---|---|---|
| `db.system` | `db.system.name` | `postgresql` |
| `db.name` | `db.namespace` | `appdb` |
| `db.operation` | `db.operation.name` | `SELECT` |
| `db.sql.table` | `db.collection.name` | `products` |
| `db.statement` (query cruda) | `db.query.text` | **query parametrizada**, sin valores: `SELECT id, name, category, price, stock FROM products WHERE category = $1 LIMIT 50` |
| `db.connection_string` (`"gcp-db"`) | `server.address` + `server.port` | endpoint real de Cloud SQL / RDS |
| — | `db.response.returned_rows` | `len(rows)` |
| — | `network.peer.address`, `db.client.connection.pool.name` | del pool |
| — | `cloud.provider`, `cloud.region`, `db.provider` | ya presentes en el Resource |

Nombre del span según la convención: **`{db.operation.name} {db.collection.name}`** → `SELECT products`
(hoy es `db.query.products`, que no sigue la convención).

Métrica estable: `db.client.operation.duration` (histograma, segundos) con atributos
`db.system.name`, `db.operation.name`, `db.collection.name`, `server.address`, `db.provider`.
Se conserva `db_query_duration_seconds` un ciclo para no romper los paneles existentes.

`/data/analytics/{id}` deja de ser `sleep` y ejecuta un JOIN real contra una tabla `sales` nueva
(sembrada en `init.sql` con ~50 k filas) — así el span analítico refleja trabajo de base de datos y el
flame graph tiene algo que mostrar.

### A.4 Multi-cloud: Cloud SQL y RDS (cierra G-02)

`data-service` expone tres DSN y elige por query param o header:

```python
DSN = {
  "local":     os.getenv("DATABASE_URL"),
  "cloud-sql": os.getenv("DATABASE_URL_GCP"),   # vía Cloud SQL Auth Proxy sidecar → 127.0.0.1:5432
  "rds":       os.getenv("DATABASE_URL_AWS"),   # endpoint público, SG restringido a la IP de casa
}
# GET /data/products?backend=cloud-sql
```

**Conectividad**

- **GCP**: sidecar `cloud-sql-connectors/cloud-sql-proxy:2.x` (hay arm64) en el pod de `data-service`,
  con la SA key montada como Secret. Instancia `db-f1-micro`, sin IP pública, sin HA.
- **AWS**: `db.t4g.micro` en la VPC default con security group `/32` a la IP pública de casa
  (dinámica → script de refresco en `scripts/cloud-up.sh`).

**Efecto buscado:** el RTT Bogotá → `us-central1` (~40-80 ms) hace que el span de BD deje de valer
0,4 ms y pase a dominar la traza. Es la comparación que el dashboard muestra: mismo query, tres
`db.provider`, tres distribuciones de latencia. Y vuelve a poner a prueba la remediación #1: con
`statement_timeout=2000` y `connect_timeout=2`, un enlace WAN degradado se corta rápido en vez de
colgar el threadpool.

### A.5 Service mesh (cierra G-07)

**No usar AWS App Mesh: AWS lo deja sin soporte el 30 de septiembre de 2026** — 30 días desde hoy.
La ruta de migración que AWS señala es Amazon ECS Service Connect.

| Entorno | Elección | Telemetría que aporta |
|---|---|---|
| Cluster propio | **Istio ambient** (ztunnel DaemonSet + waypoint solo en `otel-lab`) | `istio_requests_total`, `istio_request_duration_milliseconds`, `connection_security_policy`, mapa origen→destino |
| Plan B si no cabe en RAM | **Linkerd 2** (micro-proxy ~30 Mi) | `request_total`, `response_latency_ms`, `tls` |
| GCP | Cloud Service Mesh gestionado sobre GKE | mismas métricas, gestionadas |
| AWS | ECS Service Connect (o Istio sobre EKS) | métricas de Service Connect en CloudWatch |

**El mesh no es decorativo: cierra el blind spot del Hallazgo 1 de U2.** Con `HTTPChaos` y
`target: Response`, la app responde 200, cierra su span y *después* se corta la conexión: Jaeger
mostró 1 413 trazas todas en 200 contra 73 errores del cliente. El proxy del mesh mide la conexión,
no el handler, así que **debe ver lo que la instrumentación de la app no ve**. Verificarlo es un
resultado del módulo D, no una suposición del módulo A.

**Criterio de aceptación A:** una traza de `/orders` muestra 4 niveles y contiene un span
`SELECT products` con `db.system.name`, `db.namespace`, `db.query.text` y `server.address` del
endpoint de nube; el mismo `trace_id` aparece en Loki y el enlace Jaeger→Loki funciona; el mapa de
servicios del mesh muestra las tres aristas.

---

## 4. Módulo B — AIOps: detección automática de anomalías

### B.1 Contrato de series (paso previo obligatorio, cierra G-08)

Antes de escribir una sola regla se corre `scripts/prom-labels.sh` y se fija en
`docs/METRICS-CONTRACT.md` el nombre exacto de cada serie y su etiqueta de servicio
(`exported_job`, no `job`). Las reglas actuales están escritas contra series que muy probablemente no
existen; una alerta que no dispara es peor que no tener alerta, porque parece cobertura.

### B.2 Baseline + 2σ (cierra G-10)

```yaml
groups:
  - name: aiops.baseline
    interval: 30s
    rules:
      # SLI de error, medido en el borde (blackbox) y en la app
      - record: sli:error_rate:ratio5m
        expr: |
          1 - (
            sum by (exported_job) (rate(otelcol_data_requests_total{outcome="success"}[5m]))
            /
            sum by (exported_job) (rate(otelcol_data_requests_total[5m]))
          )

      # μ y σ sobre 6 h, DESPLAZADAS 10 min para que la ventana anómala
      # no contamine su propio baseline
      - record: sli:error_rate:mu6h
        expr: avg_over_time(sli:error_rate:ratio5m[6h] offset 10m)
      - record: sli:error_rate:sigma6h
        expr: stddev_over_time(sli:error_rate:ratio5m[6h] offset 10m)

      - record: sli:latency_p99:5m
        expr: |
          histogram_quantile(0.99,
            sum by (exported_job, le) (rate(otelcol_http_server_duration_milliseconds_bucket[5m])))
          / 1000
```

**Regla de correlación** — la que pide el enunciado, con dos guardarraíles:

```yaml
      - alert: AIOpsCorrelatedAnomaly
        expr: |
              sli:error_rate:ratio5m
            > (sli:error_rate:mu6h + 2 * sli:error_rate:sigma6h)
          and sli:latency_p99:5m > 0.25          # SLO_threshold
          and sli:error_rate:ratio5m > 0.01      # piso absoluto: evita disparar
                                                 # cuando μ=0 y σ≈0 (ruido de un solo error)
        for: 30s
        labels: {severity: critical, playbook: "runbook-trace-pivot"}
        annotations:
          summary: "Anomalía correlacionada en {{ $labels.exported_job }}"
          error_rate: "{{ $value | humanizePercentage }}"
          baseline:   "{{ with query \"sli:error_rate:mu6h\" }}{{ . | first | value }}{{ end }}"
```

Dos detalles que dan la nota: el `offset 10m` en la ventana de baseline (sin él, un incidente largo
sube μ y σ y la regla se auto-silencia) y el piso absoluto (sin él, con μ=0 y σ=0 cualquier error
aislado cruza el umbral — que es exactamente el ruido que la actividad pide reducir).

### B.3 Enriquecimiento con `trace_id` (cierra G-11)

Se despliega **Alertmanager** y un receptor propio, `alert-enricher` (~80 líneas de FastAPI,
misma imagen base que los demás servicios, al registry local):

```
Prometheus ──firing──► Alertmanager ──webhook──► alert-enricher
                                                    │
                                    1. lee startsAt y exported_job de la alerta
                                    2. consulta Loki:
                                       {service="data-service"} |= "ERROR"
                                         | json | trace_id != ""      (ventana ±2 min)
                                    3. fallback a la API de Jaeger:
                                       /api/traces?service=data-service&tags={"error":"true"}
                                    4. arma la alerta enriquecida:
                                       - trace_id + deep-link a Jaeger
                                       - deep-link a Grafana Explore (logs de esa traza)
                                       - span más lento de la traza y su servicio
                                       - runbook: "arranque por el pivote trace_id"
                                    5. la publica (log estructurado + métrica
                                       alert_enriched_total) y sella t_notify
```

`alert_enriched_total{alertname, enriched="true|false"}` sirve para dos cosas: medir el MTTD de
notificación y **cuantificar cuántas alertas quedan sin `trace_id`** — que es justo lo que ocurre en
la variante `HTTPChaos` del D-08 y el hallazgo central de este módulo.

### B.4 Demostrar la reducción de ruido (cierra el tercer punto del módulo)

Método: **backtesting sobre las series reales ya volcadas**, sin correr nada nuevo.

1. Convertir `results/gameday-final/series-*.json` (resolución 5 s, sesión canónica del 30-ago:
   E1 10:33, E2-A 11:12, E2-B 11:35) al formato de `promtool test rules`.
2. Evaluar **dos conjuntos de reglas sobre la misma ventana**:
   - **Estático** — lo que haría un equipo sin AIOps: `error_rate > 1%` `for: 1m`;
     `p99 > 250ms` `for: 1m`; `restarts > 0`; `probe_success == 0`. Cuatro reglas independientes.
   - **Dinámico** — `AIOpsCorrelatedAnomaly` (μ+2σ ∧ p99 > SLO ∧ piso 1 %).
3. Contar sobre la misma línea de tiempo:

| Métrica | Estático | Dinámico |
|---|---|---|
| Alertas totales disparadas | | |
| Alertas **fuera** de la ventana de inyección (falsos positivos) | | |
| Alertas distintas por el **mismo** incidente (tormenta) | | |
| MTTD de la primera alerta verdadera | | |
| Incidentes detectados / incidentes reales | | |

La hipótesis a poner a prueba es doble, y hay que ser honesto con el resultado: el conjunto dinámico
debería **reducir tormenta y falsos positivos**, pero probablemente **detecte algo más tarde** que el
umbral estático (el `for: 30s` y la ventana de 5 m del rate cuestan segundos). Si sale así, ese
trade-off *es* el hallazgo: menos ruido no es gratis, se paga en MTTD, y el margen de 2 min lo
absorbe.

Ventaja adicional: la ventana ya contiene un caso donde el error rate **baja** por una razón mala
(Hallazgo 3b — la corrida A completó 27 % menos peticiones porque cada abort bloqueaba un worker
9 s). Una regla basada solo en proporción de errores premia la corrida rota. Se añade por eso una
tercera regla al conjunto dinámico:

```yaml
      - alert: ThroughputCollapse
        expr: |
          sum by (exported_job) (rate(otelcol_data_requests_total[5m]))
            < 0.7 * avg_over_time(
                sum by (exported_job) (rate(otelcol_data_requests_total[5m]))[6h:5m] offset 10m)
        for: 1m
```

### B.5 La pieza de nube — y un problema de fidelidad que hay que resolver

El enunciado pide detección de anomalías gestionada **sobre `data-service`**. Pero `data-service`
corre en el cluster de casa, y DevOps Guru solo analiza recursos de AWS: no puede verlo. Hay tres
salidas, y la elegida importa para no entregar algo que solo *parece* cumplir.

| Opción | Qué observa realmente | Costo / esfuerzo | Veredicto |
|---|---|---|---|
| **B5-a — Cloud Monitoring sobre métricas propias de `data-service`** (elegida como principal) | El servicio mismo. El Collector **ya tiene el exporter `googlecloud` configurado**, comentado en `base/01-configmaps.yaml` con la nota *"quitado: sin credenciales GCP en el cluster local"*. Basta montar una SA key como Secret y reactivarlo para que `data_requests_total`, `db_query_duration` y `http.server.duration` lleguen a Cloud Monitoring como métricas personalizadas | Métricas personalizadas: asignación gratuita mensual; el volumen del lab es trivial | **Sí.** Cumple literalmente "en el servicio data-service" y reutiliza una pieza ya diseñada |
| **B5-b — DevOps Guru sobre la RDS que consume `data-service`** | La dependencia, no el servicio | Free tier 7 200 horas-recurso/mes (grupo A y B) + 10 000 llamadas API/mes por 3 meses; RDS es grupo B a US$0,0042/h fuera de él | **Sí, como segundo motor.** Un experimento de latencia contra la RDS produce insights reales con reasoning propio |
| B5-c — desplegar una copia de `data-service` en ECS para que DevOps Guru la vea | El servicio, pero una copia sin el caos ni la cadena | El Terraform de ECS ya existe en `otel-e2e-lab`, pero duplica el sistema bajo prueba | No, salvo que sobre tiempo en F4 |

Sobre B5-a, la condición de alerta en Cloud Monitoring se configura como **detección de anomalía por
pronóstico** (la política dispara cuando el valor observado sale de la banda proyectada), que es el
mecanismo equivalente al μ+2σ de la regla propia — y esa equivalencia es precisamente lo que hace
comparables los tres motores.

Entregable: captura de la política de Cloud Monitoring disparando sobre la métrica de `data-service`,
captura del insight de DevOps Guru sobre la RDS, y la tabla comparando **qué detectó cada motor sobre
el mismo incidente**:

| Motor | Qué señal usa | ¿Detectó D2-app? | ¿Detectó D2-mesh? | MTTD | Ruido en 24 h |
|---|---|---|---|---|---|
| Regla propia μ+2σ correlacionada | métricas OTel del cluster | | | | |
| Cloud Monitoring (pronóstico) | métricas de `data-service` exportadas | | | | |
| DevOps Guru | telemetría de la RDS | | | | |

La columna de D2-mesh es la interesante: los tres motores comparten la misma ceguera si todos leen
métricas que la app genera después de haber respondido 200.

**Criterio de aceptación B:** el backtesting produce la tabla con números reales; una alerta llega al
webhook con `trace_id` resoluble y su deep-link abre la traza correcta en Jaeger.

---

## 5. Módulo C — Observabilidad de red y seguridad

### C.1 Flow logs

| Plano | Implementación | Qué se obtiene |
|---|---|---|
| **Nube (real)** | GCP: VPC Flow Logs en la subred de la instancia, `sampling 0.5`, agregación 30 s → Cloud Logging. AWS: VPC Flow Logs de la VPC default → S3 (más barato que CloudWatch) | Flujos L3/L4 auténticos hacia Cloud SQL y RDS: los que produce el propio `data-service` desde casa. Coste acotado por el volumen ínfimo del lab |
| **Cluster propio (equivalente)** | Los flow logs de Calico son de la edición Enterprise, no de la OSS. El equivalente honesto es la **telemetría L7 del mesh** (`istio_requests_total` con `source_workload`/`destination_workload`), que es *mejor* que un flow log L4 porque distingue endpoint y código de respuesta, más las conexiones denegadas que reporta Falco | Matriz origen→destino E-O completa, con `connection_security_policy` |

Se documenta explícitamente el mapeo y su límite: el mesh no ve tráfico que no pasa por el proxy
(DNS, tráfico de nodo), un flow log de VPC sí. Reconocerlo suma; disfrazarlo resta.

**Alerta de tráfico anómalo** (dos reglas, una por plano):

```yaml
      # E-O: un par origen→destino que nunca antes se habló
      - alert: UnexpectedEastWestFlow
        expr: |
          sum by (source_workload, destination_workload) (rate(istio_requests_total[5m])) > 0
          unless
          sum by (source_workload, destination_workload) (rate(istio_requests_total[5m] offset 24h)) > 0
        for: 2m

      # N-S: salto de volumen de entrada respecto del baseline propio
      - alert: NorthSouthTrafficSpike
        expr: |
          sum(rate(istio_requests_total{source_workload="unknown"}[5m]))
            > 3 * avg_over_time(sum(rate(istio_requests_total{source_workload="unknown"}[5m]))[6h:5m] offset 10m)
        for: 2m
```

En la nube, la alerta equivalente se arma con una métrica basada en logs sobre los VPC Flow Logs
(conexiones a puertos o destinos fuera de la lista esperada).

### C.2 Postura de seguridad

| Pieza | Local | Nube |
|---|---|---|
| Detección en runtime | **Falco** (modern eBPF; Debian 12 con kernel reciente lo soporta) + `falco-exporter` → Prometheus | — |
| Vulnerabilidades | **Trivy Operator** — escanea las imágenes del cluster y expone `trivy_image_vulnerabilities{severity}` | — |
| Postura de la plataforma | Trivy config-audit (pods privilegiados, `hostNetwork`, sin `runAsNonRoot`) | **SCC Standard — gratuito** (verificado): detecciones de configuración sobre el proyecto GCP. **AWS Security Hub** con free trial de 30 días sobre la cuenta |

Riesgo conocido: Falco en arm64 sobre VirtualBox puede requerir el driver `modern_ebpf` y un kernel
≥ 5.8. Se verifica en F0; si no arranca, se sustituye por reglas de auditoría del apiserver
(`audit-policy` + `filelog` receiver del collector), que cubre el mismo golden signal de
autenticación.

### C.3 Dashboard «Golden Signals de Seguridad»

Traducción explícita de los cuatro golden signals al dominio de seguridad — este encuadre es lo que
convierte una colección de paneles en un argumento:

| Golden signal | Traducción a seguridad | Panel / consulta |
|---|---|---|
| **Traffic** | Volumen y forma de los flujos | (1) N-S vs E-O: `sum(rate(istio_requests_total{source_workload="unknown"}[5m]))` vs el resto. (2) Matriz origen→destino |
| **Errors** | Intentos rechazados | (3) Autenticación fallida: `rate(auth_attempts_total{result="failure"}[5m])` por `reason` (endpoint `/auth/login` nuevo en service-a con contador propio) + 401/403 del mesh + eventos de Falco de tipo `K8s Audit` |
| **Saturation** | Deuda de seguridad acumulada | (4) CVEs activos: `sum by (severity, workload) (trivy_image_vulnerabilities)`, con tendencia a 7 días. (5) % de tráfico E-O con mTLS: `istio_requests_total{connection_security_policy="mutual_tls"}` sobre el total |
| **Latency** | Tiempo hasta detectar y remediar | (6) MTTD de hallazgos de seguridad y edad del hallazgo más viejo sin cerrar |

Se añade un panel (7) con los hallazgos de SCC/Security Hub del lado nube, para que el tablero cubra
los dos planos.

**Criterio de aceptación C:** el dashboard muestra los 7 paneles con datos reales; una conexión
provocada a propósito desde un pod hacia un destino no esperado dispara `UnexpectedEastWestFlow` y
aparece en Falco; los VPC Flow Logs de GCP y AWS muestran el tráfico de `data-service` hacia la BD.

---

## 6. Módulo D — Chaos engineering controlado

### D.1 Experimento 1 — latencia 200 ms en `service-b`

Ya ejecutado y medido el 30-ago (`NetworkChaos` delay 200 ms ±10 ms, `direction: to`,
amplificación **1,97×**: p95 76,2 ms → 484,1 ms; 0 errores; rollback por TTL en t+301,0 s).

Se **repite con la malla instalada y con `data-service` ya en la cadena**, para responder dos
preguntas nuevas:

1. ¿La latencia inyectada entre a→b se propaga al span de BD del tercer servicio o queda contenida?
2. ¿Coinciden `istio_request_duration_milliseconds` (proxy) y `otelcol_http_server_duration` (app)?
   La diferencia entre ambas *es* el tiempo de red y de cola — que en U2 hubo que deducir restando
   spans.

### D.2 Experimento 2 — error rate 10 % en `data-service`, dos variantes

| | **D2-app** (primaria) | **D2-mesh** (control) |
|---|---|---|
| Mecanismo | `CHAOS_ERROR_RATE=0.1` → `HTTPException(500)` real dentro del handler | `HTTPChaos` `abort`, `path: "/data/*"`, `target: Response`, `mode: fixed value: 1` sobre 10 réplicas ≈ 10 % |
| Qué produce | Span con `StatusCode.ERROR`, log con `trace_id`, 500 visible en métricas y en el mesh | Cliente ve `http_code=000`; la app registra 200 y cierra el span |
| Alerta enriquecida | **Sí** — hay `trace_id` que adjuntar | **No** — no existe traza de error que buscar |
| Precedente | — | Validado tres veces (00:40, 08:57, 11:35): 0 reinicios, rollback dentro del TTL, error rate 11,8 % |

El 10 % por reparto de réplicas ya está validado empíricamente: la corrida B con `path: "/data/*"`
dio 11,8 % de error con una réplica afectada de diez.

**El contraste es el entregable.** D2-app demuestra que la cadena
detección → correlación → alerta accionable funciona. D2-mesh demuestra que hay una clase de fallo
donde el APM afirma éxito, y responde *"¿la alerta fue accionable?"* con un **no** documentado y su
causa. Con el mesh instalado hay además una tercera respuesta posible: **si el proxy sí cuenta esos
cortes**, el mesh cierra el blind spot y eso pasa a ser una remediación arquitectónica, no solo un
hallazgo.

### D.3 Medición del MTTD (objetivo < 2 min)

Cuatro sellos de tiempo, todos instrumentados en `run-exp1.sh` / `run-exp2.sh`:

| Sello | Fuente |
|---|---|
| `t_inject` | `creationTimestamp` del CRD de Chaos Mesh, **validado contra el reloj del apiserver** con `kubectl create configmap probe --dry-run=server -o jsonpath='{.metadata.creationTimestamp}'` |
| `t_signal` | primera muestra de la serie SLI fuera de umbral (blackbox a 5 s, apps a 15 s) |
| `t_alert` | primer punto con `ALERTS{alertname="...", alertstate="firing"} == 1` |
| `t_notify` | sello que pone `alert-enricher` al recibir el webhook |

**MTTD = `t_notify − t_inject`.** Presupuesto de retardo, sumando el peor caso:

| Etapa | Peor caso | Ajuste |
|---|---|---|
| scrape | 15 s (5 s blackbox) | — |
| `evaluation_interval` | 15 s | — |
| `for:` de la regla | 30 s | ← palanca principal |
| `group_wait` de Alertmanager | 30 s por defecto | **bajar a 10 s** |
| entrega del webhook | < 1 s | — |
| **Total** | **≈ 71 s** | margen de 49 s sobre el objetivo de 120 s |

El objetivo de 2 min se **diseña**, no se descubre. El experimento verifica el diseño.

### D.4 SLO y error budget

Se formaliza primero el SLI de disponibilidad sobre `probe_success` (cierra G-12, pendiente desde
U2), porque el SLI de 5xx demostradamente no ve `http_code=000`.

| SLI | Definición | SLO | Budget mensual |
|---|---|---|---|
| Disponibilidad | `avg_over_time(probe_success[30d])` (blackbox, borde) | 99,5 % | 216 min |
| Latencia | proporción de peticiones bajo 250 ms | 95 % | 5 % de las peticiones |
| Frescura de datos | proporción de respuestas de `data-service` no degradadas | 99 % | 1 % |

Las tres preguntas obligatorias del módulo, con el método de respuesta:

- **¿Se degradó el SLO?** Sí en latencia, previsiblemente: 200 ms inyectados sobre un p95 de 76 ms
  ponen el ~100 % de las peticiones sobre el umbral de 250 ms durante los 300 s. Disponibilidad,
  intacta (0 errores en E1). Se reporta por SLI, no en bloque.
- **¿Se consumió error budget?** El total consumido es despreciable — con ~2,4 rps, 300 s al 10 % de
  error son ~72 peticiones malas contra un presupuesto mensual de ~31 100. **Lo relevante es el burn
  rate**: 10 % / 0,5 % = **20×**, muy por encima del 14,4× que dispara página en la ventana de 1 h.
  Ese es el argumento: un experimento corto no agota el budget, pero su *tasa* es la señal.
- **¿La alerta fue accionable?** Se responde con el contraste D2-app vs D2-mesh y con una prueba
  concreta: desde la alerta recibida, ¿cuántos clics hasta el span culpable? En D2-app: alerta →
  `trace_id` → traza en Jaeger → span del handler → logs de esa traza en Loki. En D2-mesh: la alerta
  llega sin `trace_id` y el runbook se rompe en el primer paso.

**Criterio de aceptación D:** los cuatro sellos de tiempo quedan registrados en el reporte de cada
corrida; MTTD < 120 s en al menos 2 de 3 réplicas de cada experimento; tabla de consumo de budget y
burn rate por experimento.

---

## 7. Módulo E — Reporte de madurez

### E.1 Autoevaluación contra los 8 dominios de Observability Foundation

Escala: **1** inexistente · **2** ad hoc · **3** definido y repetible · **4** medido y automatizado ·
**5** optimizado con retroalimentación.

| # | Dominio | Hoy | Meta (3 m) | Evidencia del nivel actual | Qué falta para subir |
|---|---|---|---|---|---|
| OBSF-1 | Exploring Observability | 3 | 4 | Documentos U1/U2, distinción monitoreo vs. observabilidad aplicada; los hallazgos de U2 salen de preguntas no anticipadas | Convertir la práctica en política: definición de "listo para producción" observable |
| OBSF-2 | Pillars of Observability | 3 → **4 con este lab** | 4 | Trazas y métricas correlacionadas por `trace_id`; **logs aún sin backend** (G-05) | Loki + los tres datasources en Grafana + los enlaces derivados |
| OBSF-3 | Open Source Landscape / OTel | 4 | 4 | OTel SDK en los 3 servicios, Collector con 3 pipelines, semconv aplicadas | Migrar a semconv estables (A.3) y fijar el contrato de métricas |
| OBSF-4 | Service Maps and Topology | **1** | 4 | No hay mapa de servicios ni topología; la cadena se deduce leyendo el código | Service mesh (A.5) → mapa automático y matriz E-O |
| OBSF-5 | DataOps | **2** | 3 | Sin política de retención, muestreo ni control de cardinalidad. Jaeger en memoria **ya murió por OOM** el 30-ago y se llevó la evidencia (Hallazgo 5) | Retención explícita, tail sampling en el Collector, presupuesto de cardinalidad, Jaeger con backend persistente |
| OBSF-6 | Building Observability with AIOps | **2** | 4 | Reglas escritas pero apuntando a series inexistentes (G-08); umbral `×3` en vez de μ+2σ | Todo el módulo B |
| OBSF-7 | Security and Networking | **1** | 3 | Cero cobertura | Todo el módulo C |
| OBSF-8 | Practices for DevOps and SRE | 3 | 4 | SLIs/SLOs derivados de una línea base medida, error budget calculado, Game Day ejecutado con verificación de inyección, runbook escrito | Alertas multiventana por burn rate en producción, postmortem sin culpa formalizado, MTTD como métrica de seguimiento |

Promedio actual **2,4** → meta **3,75**. Los dos ceros de facto (OBSF-4 y OBSF-7) son los que más
mueven la aguja y son justamente los módulos A.5 y C.

### E.2 Roadmap a 3 meses

| Mes | Foco | Entregables | Sube |
|---|---|---|---|
| **1** | Cerrar los pilares y la topología | Loki + 3 datasources con enlaces derivados; semconv estables; `data-service` en la cadena; Istio ambient con mapa de servicios | OBSF-2 →4, OBSF-3 →4, OBSF-4 →3 |
| **2** | AIOps y seguridad | Contrato de métricas; reglas μ+2σ con backtesting; Alertmanager + `alert-enricher`; Falco + Trivy; dashboard de golden signals de seguridad; VPC Flow Logs en ambas nubes | OBSF-6 →4, OBSF-7 →3, OBSF-4 →4 |
| **3** | DataOps y disciplina operativa | Tail sampling y retención por clase de traza; Jaeger con almacenamiento persistente (la lección del OOM); presupuesto de cardinalidad; alertas multiventana de burn rate; Game Day mensual con verificación de inyección obligatoria; postmortem sin culpa | OBSF-5 →3, OBSF-8 →4, OBSF-1 →4 |

Principio que ordena el roadmap: **el sistema que guarda la evidencia debe ser al menos tan robusto
como el sistema bajo prueba.** Es la lección del Hallazgo 5 (Jaeger OOMKilled se llevó las trazas del
experimento mientras el tablero seguía mostrando el pipeline sano) y es la que justifica poner
DataOps antes que cualquier funcionalidad nueva en el mes 3.

---

## 8. Plan de ejecución

| Fase | Trabajo | Esfuerzo | Criterio de salida |
|---|---|---|---|
| **F0** Verificación | RAM libre por nodo (¿cabe Istio?); `prom-labels.sh` → contrato de métricas; kernel de los nodos (¿Falco eBPF?); `gcloud`/`aws` CLI y credenciales; limpiar los locks huérfanos de git desde la Mac | 1 h | `docs/METRICS-CONTRACT.md` escrito; go/no-go de Istio y Falco |
| **F1** Cadena + semconv | `service-b → data-service` con timeouts/bulkhead/degradación; migración de atributos y métricas de BD; tabla `sales`; rebuild y push al registry | 3 h | Traza de 4 niveles en Jaeger con `SELECT products` conforme |
| **F2** Tercer pilar | Loki; pipeline `logs` del Collector; 3 datasources en Grafana con enlaces derivados | 2 h | Clic de traza → logs de esa traza y viceversa |
| **F3** Mesh | Istio ambient en `otel-lab`, waypoint, dashboard de métricas L7 | 3 h | Mapa de servicios con 3 aristas; métricas de proxy y de app lado a lado |
| **F4** Nube | Terraform mínimo: Cloud SQL `db-f1-micro` + proxy sidecar; RDS `db.t4g.micro` + SG; VPC Flow Logs en ambas; SCC Standard; Security Hub; DevOps Guru sobre RDS. Budgets a US$5 | 4 h | `/data/products?backend=cloud-sql` y `?backend=rds` responden con span de BD hacia el endpoint real |
| **F5** AIOps | Reglas μ+2σ; Alertmanager (`group_wait: 10s`); `alert-enricher`; backtesting con `promtool` sobre `series-*.json` | 4 h | Tabla de reducción de ruido con números; alerta con `trace_id` resoluble |
| **F6** Seguridad | Falco + Trivy Operator; endpoint `/auth/login` con contador; dashboard de golden signals de seguridad; alertas de tráfico anómalo | 3 h | 7 paneles con datos reales |
| **F7** Game Day | E1 y E2 (dos variantes) con los 4 sellos de tiempo; 3 réplicas de cada uno; volcado de series y capturas | 3 h | MTTD < 120 s en ≥2/3 réplicas; tabla de budget y burn rate |
| **F8** Documentación | Reporte de madurez, roadmap, figuras, PDF | 4 h | Entregable final |

**Total ≈ 27 h.** Las fases F1–F3 son secuenciales; F4 puede adelantarse en paralelo (Terraform no
depende del cluster); F5 y F6 son independientes entre sí.

---

## 9. Costos y guardarraíles de la nube

Verificado el 2026-08-31:

| Recurso | Costo | Guardarraíl |
|---|---|---|
| GCP: crédito de bienvenida US$300 para cuentas nuevas; **Cloud SQL no está en el Always Free** (sí hay una prueba de 30 días para Cloud SQL) | `db-f1-micro` ≈ US$0,01–0,04/h | `google_billing_budget` ya existe en `otel-e2e-lab/deploy/gcp/terraform/budget.tf` → bajar a US$5 con alerta al 50 % |
| AWS: el free tier de cuentas nuevas pasó a un modelo de **créditos** (US$100 + hasta US$100, 6 meses); las cuentas antiguas no lo tienen | RDS `db.t4g.micro` ≈ US$0,016/h | `aws_budgets_budget` ya existe en `deploy/aws/terraform/budget.tf` |
| DevOps Guru | free tier de **7 200 horas-recurso/mes**; RDS es grupo B a US$0,0042/h fuera de él | Activar solo sobre la RDS del lab, no sobre la cuenta entera |
| SCC Standard | **gratuito** | Cuidado con costos indirectos de ingesta de logs |
| VPC Flow Logs | se pagan por ingesta de logs | GCP: `sampling 0.5`, agregación 30 s. AWS: destino S3, no CloudWatch |

**Regla operativa:** ninguna sesión de laboratorio deja recursos de nube encendidos.
`scripts/cloud-up.sh` y `scripts/cloud-down.sh`, y `cloud-down` obligatorio en el `trap EXIT` del
runbook, igual que ya se hace con la limpieza del chaos.

**Nota de riesgo:** si la cuenta AWS de Ilich tiene más de 12 meses, no aplica ningún free tier de
RDS y el costo es real (aunque mínimo: 3 h ≈ US$0,05). Confirmar en F0.

---

## 10. Riesgos heredados y mitigaciones

Todos documentados en corridas anteriores; el diseño los da por conocidos.

| Riesgo | Mitigación ya implementada o prevista |
|---|---|
| **El Mac se duerme** y suspende las VMs → el reloj del apiserver queda atrasado → Chaos Mesh dispara `TimeUp` y el experimento **no se inyecta pero reporta éxito** (Hallazgo 4) | `caffeinate -dimsu` obligatorio; chequeo del reloj del apiserver en el preflight; verificación de que el record llega a `Injected` a los 30 s; el reporte invalida la comparación si A da <1 % de error |
| **Jaeger en memoria muere por OOM** y se lleva la evidencia (Hallazgo 5) | `MEMORY_MAX_TRACES` 20 000 y límite 1 Gi ya aplicados; en F3 del roadmap, backend persistente. Añadir alerta sobre `kube_pod_container_status_restarts_total{pod=~"jaeger.*"}` |
| Prometheus **sin `--web.enable-lifecycle`**: no hay `/-/reload`, y un ConfigMap recién aplicado tarda ~60 s en llegar al volumen | Esperar 60 s antes de reiniciar el Deployment; documentado en el runbook. Con muchas reglas nuevas en F5, conviene añadir el flag |
| Las métricas de la app llegan con prefijo `otelcol_` y el servicio se identifica por **`exported_job`**, no `job`; `exported_instance` cambia en cada reinicio | Contrato de métricas en F0 antes de escribir reglas |
| `device_bash` del puente **no puede borrar archivos ni tiene `kubectl`** | Git y todo lo que hable con el cluster, desde la Mac. El puente solo lee y edita archivos |
| Istio ambient puede no caber en la RAM de las VMs | Go/no-go en F0; plan B Linkerd 2; plan C solo métricas de app y se documenta la limitación |
| Falco en arm64/VirtualBox puede requerir kernel ≥ 5.8 con `modern_ebpf` | Go/no-go en F0; alternativa: auditoría del apiserver vía `filelog` receiver |
| El pod objetivo de `HTTPChaos` con `path: "*"` aborta también el health check → crash-loop → rollback fallido (Hallazgo 2) | Usar siempre `path: "/data/*"`; secuencia de limpieza `patch finalizers:[] → delete pod → scale` ya implementada en `run-exp2.sh` |
| IP pública de casa dinámica → el SG de RDS deja de servir | `scripts/cloud-up.sh` refresca el `/32` en cada arranque |
| **Cadena de suministro de imágenes arm64.** Este diseño mete al menos 7 imágenes nuevas al cluster (Loki, Alertmanager, `alert-enricher`, istiod, ztunnel, Falco, Trivy Operator, Cloud SQL Auth Proxy). Todas deben existir en arm64 y llegar al registry `192.168.0.20:30500` | Verificar arm64 de cada una en F0 antes de comprometer la fase. Las que no tengan arm64 oficial se sustituyen o se compilan. Presupuestar el tiempo de push: es la parte lenta de F2/F3/F6, no la configuración |

---

## 11. Trazabilidad: enunciado → entregable → evidencia

| Enunciado | Entregable | Evidencia |
|---|---|---|
| A · tercer microservicio con acceso a Cloud SQL y RDS | `data-service` en la cadena, 3 backends | Traza de 4 niveles; latencia comparada por `db.provider` |
| A · OTel SDK, 3 pilares, DB semconv | Loki + semconv estables + contrato de métricas | Span `SELECT products` conforme; pivote traza↔log en Grafana |
| A · service mesh para observabilidad L7 | Istio ambient | Mapa de servicios; métricas de proxy vs. de app |
| B · detección de anomalías gestionada | DevOps Guru sobre RDS (+ Cloud Monitoring como contraste) | Captura del insight; tabla comparativa de motores |
| B · regla `error_rate > μ+2σ ∧ p99 > SLO` → alerta con `trace_id` | Recording rules + `AIOpsCorrelatedAnomaly` + `alert-enricher` | Alerta recibida con `trace_id` y deep-links |
| B · reducción de alertas ruidosas | Backtesting `promtool` sobre las series del 30-ago | Tabla estático vs. dinámico con conteos y MTTD |
| C · VPC Flow Logs GCP y AWS + alertas de tráfico anómalo | Flow logs en ambas nubes; `UnexpectedEastWestFlow`, `NorthSouthTrafficSpike` | Registros de flujo hacia Cloud SQL/RDS; alerta disparada a propósito |
| C · SCC o Security Hub | SCC Standard + Security Hub (trial) | Capturas de hallazgos |
| C · dashboard de golden signals de seguridad | 7 paneles | Dashboard con datos reales |
| D · latencia 200 ms en service-b | E1 repetido con mesh y cadena completa | Series a 5 s, capturas, desglose por span |
| D · error rate 10 % en data-service | E2 en dos variantes (D2-app, D2-mesh) | Comparativa; conteo de alertas con y sin `trace_id` |
| D · MTTD < 2 min | 4 sellos de tiempo instrumentados + presupuesto de retardo | Tabla de MTTD por réplica |
| D · SLO, error budget, accionabilidad | SLIs formalizados sobre `probe_success` | Tabla de burn rate; ruta de clics desde la alerta al span |
| E · autoevaluación 8 dominios, escala 1–5 | Matriz de madurez con evidencia por dominio | §7.1 |
| E · roadmap a 3 meses | Plan mensual con dominios objetivo | §7.2 |

---

## 12. Decisiones pendientes

1. **Formato y límite de páginas del entregable de U3.** En U2 el criterio pedía 4–5 páginas y hubo
   que separar el documento evaluable del anexo de evidencia. Conviene confirmarlo antes de F8 para
   no repetir el desdoble a última hora.
2. **¿Grupal o individual?** U1 fue grupal (3 integrantes), U2 individual.
3. **¿Se entrega sobre `chaos_k8s` o se abre repo nuevo?** Recomendación: seguir en `chaos_k8s`, en
   una rama `u3-integrador`, para conservar la línea base y los resultados del Game Day como insumo
   del módulo B.
4. **Alcance real de la nube**: confirmar en F0 la antigüedad de las cuentas GCP y AWS, porque de eso
   depende si el free tier aplica.
