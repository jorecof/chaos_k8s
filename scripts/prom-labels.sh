#!/bin/bash
# Descubre las etiquetas reales de las metricas de aplicacion en Prometheus,
# para escribir las queries del dashboard sin adivinar.
# Uso: bash scripts/prom-labels.sh
set -u
NS=${NS:-otel-lab}
q(){ kubectl -n "$NS" get --raw \
  "/api/v1/namespaces/$NS/services/prometheus-svc:9090/proxy/api/v1/query?query=$(
     python3 -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1],safe=""))' "$1")" 2>/dev/null; }

for m in otelcol_data_requests_total otelcol_inventory_requests_total \
         otelcol_http_server_duration_milliseconds_count probe_success; do
  echo "══════ $m ══════"
  q "$m" | python3 -c '
import json,sys
try: d=json.load(sys.stdin)
except Exception: print("  (sin respuesta)"); raise SystemExit
r=d.get("data",{}).get("result",[])
if not r: print("  (sin series)"); raise SystemExit
print("  series:",len(r))
print("  etiquetas:",sorted(r[0]["metric"].keys()))
for s in r[:6]:
    m=s["metric"]
    print("   ", {k:v for k,v in m.items() if k not in ("__name__",)})
'
done
echo "══════ pods de data-service ══════"
kubectl -n "$NS" get pods -l app=data-service --no-headers -o custom-columns=NAME:.metadata.name,IP:.status.podIP
