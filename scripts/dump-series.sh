#!/bin/bash
# Extrae de Prometheus las series de la ventana del Game Day a resolucion
# completa (el muestreo del script solo guarda un punto cada 15 s).
# Uso: bash scripts/dump-series.sh [directorio-del-gameday]
set -u
NS=${NS:-otel-lab}
cd "$(dirname "$0")/.." || exit 1
GD=${1:-$(ls -1dt results/gameday-* 2>/dev/null | head -1)}
[ -d "$GD" ] || { echo "no encuentro el directorio del gameday"; exit 1; }
echo "gameday: $GD"

read -r START END <<<"$(python3 - "$GD" <<'PY'
import glob,json,sys
gd=sys.argv[1]; s=[];e=[]
for f in glob.glob(f"{gd}/*/meta.json"):
    m=json.load(open(f)); s.append(m["t_base_start"]); e.append(m["t_end"])
print(int(min(s)-60), int(max(e)+120))
PY
)"
echo "ventana: $START → $END  ($(( (END-START)/60 )) min)"

rng(){ # $1=query  $2=step  $3=archivo
  local enc; enc=$(python3 -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1],safe=""))' "$1")
  kubectl -n "$NS" get --raw \
    "/api/v1/namespaces/$NS/services/prometheus-svc:9090/proxy/api/v1/query_range?query=$enc&start=$START&end=$END&step=$2" \
    > "$GD/$3" 2>/dev/null
  echo "  $3  $(wc -c < "$GD/$3" | tr -d ' ') bytes"
}

rng 'probe_success'                                                        5  series-probe-success.json
rng 'probe_duration_seconds'                                               5  series-probe-duration.json
rng 'sum by (exported_instance) (rate(otelcol_data_requests_total[1m]))'   15 series-data-por-replica.json
rng 'histogram_quantile(0.95, sum by (le, exported_job) (rate(otelcol_http_server_duration_milliseconds_bucket[1m])))' 15 series-p95-por-servicio.json
rng 'sum by (exported_job) (rate(otelcol_http_server_duration_milliseconds_count[1m]))' 15 series-throughput.json
echo "listo"
