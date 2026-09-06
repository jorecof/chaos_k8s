# Contrato de metricas -- U3 modulo B (cierra G-08)

Paso previo obligatorio antes de escribir cualquier regla de alerta (Sec.B.1 del
diseno): fijar el nombre exacto de cada serie y su etiqueta de servicio. Las
reglas heredadas de U2 apuntaban a series que no existen (`otelcol_http_requests_total`,
`job="service-b"`) -- una alerta que nunca dispara es peor que no tener alerta,
porque parece cobertura. Verificado el 2026-09-06 contra el Prometheus real del
cluster (`scripts/prom-labels.sh` + queries directas a la API).

## Regla de oro: `exported_job`, no `job`

Todas las metricas de aplicacion llegan a Prometheus via scrape del **Collector**
(`otel-collector-svc:8889`), no de las apps directamente. Por eso `job` siempre
vale `"otel-collector"` (el propio scrape target) y el servicio real que genero
el dato queda en **`exported_job`** (`data-service`, `service-a`, `service-b`).
Cualquier regla que filtre por `job="service-b"` no selecciona nada.

La excepcion es `probe_success`, que blackbox-exporter expone directamente y
Prometheus scrapea sin pasar por el Collector -- ahi el servicio se identifica
por `instance` (la URL sondeada) bajo `job="blackbox-http"`.

## Series verificadas

| Metrica | Tipo | Servicio (`exported_job`) | Etiquetas clave | Uso |
|---|---|---|---|---|
| `otelcol_data_requests_total` | counter | `data-service` | `outcome` (`success`/`error`), `http_response_status_code`, `db_provider`, `endpoint` | SLI de error rate (cierra G-09: ya trae `outcome`, no solo `endpoint`/`cloud` como antes) |
| `otelcol_http_server_duration_milliseconds_count` / `_sum` / `_bucket` | histograma | `service-a`, `service-b`, `data-service` (FastAPI auto-instrumentado) | `http_status_code`, `http_target`, `http_method`, `le` (solo `_bucket`) | SLI de latencia (p99 via `histogram_quantile`) |
| `otelcol_inventory_requests_total` | counter | `service-b` | `product` | **Sin atributo de resultado** -- no sirve para error rate; solo volumen por producto |
| `probe_success` | gauge (0/1) | -- (usar `instance`) | `instance` (URL completa sondeada) | SLI de disponibilidad de borde (blackbox, cierra G-12 -- ve `http_code=000`, que el 5xx de la app no ve) |

Series confirmadas vacias/inexistentes (no usar en reglas nuevas):
`otelcol_http_requests_total`, `otelcol_http_request_duration_seconds_bucket` --
eran los nombres de la convencion experimental antigua o simplemente nunca
existieron con ese nombre exacto.

## Ejemplos reales (2026-09-06)

```
otelcol_data_requests_total{db_provider="cloud-sql", endpoint="/data/products",
  exported_job="data-service", http_response_status_code="200", outcome="success"}

otelcol_http_server_duration_milliseconds_bucket{exported_job="service-a",
  http_status_code="200", http_target="/order/{order_id}", le="..."}

probe_success{instance="http://data-service-svc:8002/data/products", job="blackbox-http"}
```
