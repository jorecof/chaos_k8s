#!/bin/bash
# ══════════════════════════════════════════════════════════════════════
# run-exp1.sh — Experimento 1 instrumentado
#
# NetworkChaos delay 200ms ±10ms sobre los pods de service-b.
# Carga: GET /order/{id} contra el NodePort de service-a
#        (cliente → service-a → service-b → PostgreSQL).
#
# Mide, además de la latencia del cliente:
#   · p95 propio de service-b desde Prometheus — la señal que se queda
#     en verde mientras el usuario sufre (debilidad D2 del Plan)
#   · SLI de borde del blackbox exporter, si está desplegado
#   · RESTARTS de los pods (control: aquí deben quedarse en 0, a
#     diferencia del Experimento 2)
#   · timeline del rollback por TTL, para contrastarlo con el del
#     Experimento 2, que falla
#
# Uso:   bash scripts/run-exp1.sh
# Dura:  ~11 min.
# ══════════════════════════════════════════════════════════════════════
set -u

NS=${NS:-otel-lab}
DEP=${DEP:-service-b}
SVC=${SVC:-service-a-svc}
CHAOS_FILE=${CHAOS_FILE:-chaos-mesh/experiment-1-network-latency.yaml}
CHAOS_NAME=${CHAOS_NAME:-latency-service-b-200ms}
NODE_IP=${NODE_IP:-192.168.0.20}
WORKERS=${WORKERS:-4}
INTERVAL=${INTERVAL:-1.5}
BASELINE_SECS=${BASELINE_SECS:-90}
CHAOS_SECS=${CHAOS_SECS:-300}
POST_SECS=${POST_SECS:-240}
MAX_TIME=${MAX_TIME:-15}
SAMPLE_INT=${SAMPLE_INT:-15}
ORDER_ID=${ORDER_ID:-ord-001}
OUT_ROOT=${OUT_ROOT:-results}
FORCE=${FORCE:-0}

cd "$(dirname "$0")/.." || exit 1
STAMP=$(date +%Y%m%d-%H%M%S)
OUT="$OUT_ROOT/exp1-$STAMP"
mkdir -p "$OUT/samples"
LOG="$OUT/run.log"

log(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }
hr(){ echo "──────────────────────────────────────────────────────────" | tee -a "$LOG"; }

if command -v gdate >/dev/null 2>&1; then now(){ gdate +%s.%3N; }
elif command -v perl >/dev/null 2>&1; then now(){ perl -MTime::HiRes=time -e 'printf "%.3f\n", time'; }
else now(){ date +%s; }; fi

promq(){
  local enc
  enc=$(python3 -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1],safe=""))' "$1")
  kubectl -n "$NS" get --raw \
    "/api/v1/namespaces/$NS/services/prometheus-svc:9090/proxy/api/v1/query?query=$enc" 2>/dev/null
}
jaegerq(){
  kubectl -n "$NS" get --raw \
    "/api/v1/namespaces/$NS/services/jaeger-svc:16686/proxy/api/traces?service=service-a&start=$1&end=$2&limit=3000" 2>/dev/null
}

# ══ 0. PREFLIGHT ══════════════════════════════════════════════════════
hr; log "FASE 0 — preflight"
for b in kubectl curl python3; do
  command -v "$b" >/dev/null 2>&1 || { log "FALTA $b — abortando"; exit 1; }
done
kubectl get --raw /readyz >/dev/null 2>&1 || { log "El apiserver no responde. Abortando."; exit 1; }

kubectl get nodes -o wide          > "$OUT/preflight-nodes.txt" 2>&1
kubectl top nodes                 >> "$OUT/preflight-nodes.txt" 2>&1
kubectl -n "$NS" get pods -o wide  > "$OUT/preflight-pods.txt"  2>&1

LEFTOVER=$(kubectl -n "$NS" get httpchaos,networkchaos,podchaos,stresschaos,schedule \
             --no-headers 2>/dev/null | wc -l | tr -d ' ')
if [ "$LEFTOVER" != "0" ] && [ "$FORCE" != "1" ]; then
  log "Hay $LEFTOVER objeto(s) de chaos vivos de una corrida anterior:"
  kubectl -n "$NS" get httpchaos,networkchaos,podchaos,stresschaos,schedule 2>&1 | tee -a "$LOG"
  log "Bórralos o corre con FORCE=1. Abortando."; exit 1
fi

# ── Sincronizacion de relojes ─────────────────────────────────────────
# Un desfase entre el reloj de los nodos y el del host convierte el
# experimento en un no-op silencioso: Chaos Mesh calcula
# creationTimestamp + duration y, si el sello viene del pasado, dispara
# TimeUp al instante y el chaos nunca se inyecta. Paso real: tras
# suspender las VMs, el apiserver sello un objeto con 1h51m de atraso.
check_reloj(){
  # Medir el reloj del APISERVER, que es el que sella creationTimestamp.
  # Un dry-run del lado servidor devuelve el objeto sellado sin crear nada.
  # (No sirve el lastHeartbeatTime de los nodos: con NodeLease ese campo
  #  se refresca cada 5 min, asi que siempre parece 300 s de atraso.)
  local ts skew
  ts=$(kubectl create configmap "clock-probe-$$" -n "$NS" --dry-run=server \
       -o jsonpath='{.metadata.creationTimestamp}' 2>/dev/null)
  if [ -z "$ts" ]; then
    ts=$(kubectl get lease -n kube-node-lease -o jsonpath='{.items[0].spec.renewTime}' 2>/dev/null)
  fi
  if [ -z "$ts" ]; then
    log "no pude leer el reloj del apiserver — sigo sin verificar"
    return 0
  fi
  skew=$(python3 -c "
import datetime,sys
t=sys.argv[1].replace('Z','+00:00').split('.')[0]
if '+' not in t: t=t+'+00:00'
d=datetime.datetime.fromisoformat(t)
print(int(abs((datetime.datetime.now(datetime.timezone.utc)-d).total_seconds())))
" "$ts" 2>/dev/null)
  if [ "${skew:-0}" -gt 60 ] 2>/dev/null; then
    log "DESFASE DE RELOJ: el apiserver sella ${skew}s fuera del reloj local."
    log "Chaos Mesh calcula la duracion contra creationTimestamp: con este desfase"
    log "el experimento se marcaria TimeUp al instante y NO inyectaria nada."
    log "Arreglar:  ssh -t <nodo> 'sudo timedatectl set-ntp true && sudo systemctl restart systemd-timesyncd'"
    exit 1
  fi
  log "reloj del apiserver verificado (desfase ${skew}s)"
}
check_reloj

NODEPORT=$(kubectl -n "$NS" get svc "$SVC" -o jsonpath='{.spec.ports[0].nodePort}' 2>/dev/null)
[ -z "$NODEPORT" ] && { log "$SVC no tiene nodePort. Abortando."; exit 1; }

URL="http://$NODE_IP:$NODEPORT/order/$ORDER_ID"
SMOKE=$(curl -s -o /dev/null -m 10 -w '%{http_code}' "$URL")
if [ "$SMOKE" != "200" ]; then
  log "order/$ORDER_ID devolvió $SMOKE — buscando un pedido válido…"
  for i in ord-001 ord-002 ord-003 1 2 3; do
    if [ "$(curl -s -o /dev/null -m 10 -w '%{http_code}' "http://$NODE_IP:$NODEPORT/order/$i")" = "200" ]; then
      ORDER_ID=$i; URL="http://$NODE_IP:$NODEPORT/order/$i"; SMOKE=200; break
    fi
  done
fi
if [ "$SMOKE" != "200" ]; then
  log "ningún pedido conocido responde 200. Pedidos sembrados por init.sql:"
  log "  ord-001 / ord-002 / ord-003  (id es VARCHAR, no entero)"
  log "Verifica que la tabla orders tenga datos:"
  log "  kubectl -n $NS exec deploy/postgres -- psql -U app -d appdb -c 'select id from orders;'"
  exit 1
fi
log "target: $URL  (smoke test OK)"

BB=$(promq 'probe_success' | python3 -c 'import json,sys;print(len(json.load(sys.stdin)["data"]["result"]))' 2>/dev/null || echo 0)
log "blackbox exporter: ${BB:-0} series de probe_success"

# ══ limpieza garantizada ══════════════════════════════════════════════
CLEANED=0
cleanup(){
  [ "$CLEANED" = "1" ] && return
  CLEANED=1
  hr; log "LIMPIEZA"
  kubectl -n "$NS" delete -f "$CHAOS_FILE" --ignore-not-found=true --timeout=45s 2>&1 | tee -a "$LOG"
  if kubectl -n "$NS" get networkchaos "$CHAOS_NAME" >/dev/null 2>&1; then
    log "el borrado no completó (finalizer) — forzando"
    kubectl -n "$NS" patch networkchaos "$CHAOS_NAME" --type=merge \
      -p '{"metadata":{"finalizers":[]}}' 2>&1 | tee -a "$LOG"
  fi
  sleep 3
  kubectl -n "$NS" get networkchaos > "$OUT/chaos-after-cleanup.txt" 2>&1
  kubectl -n "$NS" get pods -l app="$DEP" -o wide >> "$OUT/chaos-after-cleanup.txt" 2>&1
  log "limpieza terminada"
}
trap 'echo; log "INTERRUMPIDO"; cleanup; exit 130' INT TERM

# ══ carga y muestreo ══════════════════════════════════════════════════
worker(){
  local id=$1 endts=$2 f="$OUT/raw-w$1.csv" res t0
  while [ "$(date +%s)" -lt "$endts" ]; do
    t0=$(now)
    res=$(curl -s -o /dev/null --max-time "$MAX_TIME" \
          -w '%{http_code},%{time_total},%{time_connect}' "$URL" 2>/dev/null)
    [ -z "$res" ] && res="000,$MAX_TIME,0"
    echo "$t0,$id,$res" >> "$f"
    sleep "$INTERVAL"
  done
}
load_for(){
  local endts=$(( $(date +%s) + $1 )) i=1
  while [ "$i" -le "$WORKERS" ]; do worker "$i" "$endts" & i=$((i+1)); done
}

sampler(){
  local endts=$1 t
  while [ "$(date +%s)" -lt "$endts" ]; do
    t=$(date +%s)
    { echo "=== t=$t ==="
      kubectl -n "$NS" get pods -l app="$DEP" --no-headers \
        -o custom-columns='NAME:.metadata.name,NODE:.spec.nodeName,READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount'
    } >> "$OUT/samples/pods.txt" 2>&1
    { echo "=== t=$t ==="
      kubectl -n "$NS" get networkchaos "$CHAOS_NAME" -o json 2>/dev/null \
      | python3 -c '
import json,sys
try: d=json.load(sys.stdin)
except Exception: print("(sin objeto)"); raise SystemExit
st=d.get("status",{})
print("conditions:", [(c.get("type"),c.get("status")) for c in st.get("conditions",[])])
for r in st.get("experiment",{}).get("containerRecords",[]):
    print("  record:", r.get("id"), "phase:", r.get("phase"))
'
    } >> "$OUT/samples/chaos-status.txt" 2>&1
    { echo "=== t=$t ==="
      echo "-- p95 service-b (propio) --"
      promq 'histogram_quantile(0.95, sum by (le) (rate(otelcol_http_server_duration_milliseconds_bucket[1m])))'
      echo; echo "-- probe_success (borde) --"
      promq 'probe_success'
      echo; echo "-- probe_duration_seconds --"
      promq 'probe_duration_seconds'
    } >> "$OUT/samples/prom.txt" 2>&1
    sleep "$SAMPLE_INT"
  done
}

# ══ 1. LÍNEA BASE ═════════════════════════════════════════════════════
hr; log "FASE 1 — línea base ($BASELINE_SECS s, $WORKERS workers cada ${INTERVAL}s)"
T_BASE_START=$(now)
load_for "$BASELINE_SECS"; wait
T_BASE_END=$(now)

# ══ 2. INYECCIÓN ══════════════════════════════════════════════════════
hr; log "FASE 2 — aplicando NetworkChaos (delay 200ms ±10ms sobre $DEP)"
kubectl -n "$NS" get pods -l app="$DEP" -o wide > "$OUT/pods-before-chaos.txt" 2>&1
kubectl apply -f "$CHAOS_FILE" 2>&1 | tee -a "$LOG"
T_CHAOS=$(now)
sleep 5
kubectl -n "$NS" get networkchaos "$CHAOS_NAME" -o yaml > "$OUT/chaos-applied.yaml" 2>&1
TARGET=$(kubectl -n "$NS" get networkchaos "$CHAOS_NAME" \
         -o jsonpath='{.status.experiment.containerRecords[*].id}' 2>/dev/null)
log "pods afectados: ${TARGET:-(aún no reportado)}"
echo "$TARGET" > "$OUT/target-pods.txt"

TOTAL=$((CHAOS_SECS + POST_SECS))
log "carga durante ${TOTAL}s (${CHAOS_SECS}s de chaos + ${POST_SECS}s post-rollback)"
sampler $(( $(date +%s) + TOTAL + 10 )) &
SPID=$!
load_for "$TOTAL"
wait
T_END=$(now)
kill "$SPID" 2>/dev/null

# ══ 3. RECOLECCIÓN ════════════════════════════════════════════════════
hr; log "FASE 3 — recolectando evidencia"
kubectl -n "$NS" describe networkchaos "$CHAOS_NAME" > "$OUT/chaos-describe.txt" 2>&1
kubectl -n "$NS" get events --sort-by=.lastTimestamp    > "$OUT/events.txt" 2>&1
kubectl -n "$NS" get pods -l app="$DEP" -o wide          > "$OUT/pods-after-chaos.txt" 2>&1

US_START=$(python3 -c "print(int(float('$T_CHAOS')*1000000))")
US_END=$(python3 -c "print(int(float('$T_END')*1000000))")
jaegerq "$US_START" "$US_END" > "$OUT/jaeger-traces.json" 2>&1
log "trazas de service-a de la ventana guardadas"

cat > "$OUT/meta.json" <<META
{"experimento": "E1-network-latency",
 "t_base_start": $T_BASE_START, "t_base_end": $T_BASE_END,
 "t_chaos": $T_CHAOS, "t_end": $T_END,
 "chaos_secs": $CHAOS_SECS, "post_secs": $POST_SECS,
 "workers": $WORKERS, "interval": $INTERVAL,
 "url": "$URL", "target": "$TARGET"}
META

cat "$OUT"/raw-w*.csv 2>/dev/null | sort -t, -k1 -n > "$OUT/exp1_repeat.csv"
log "$(wc -l < "$OUT/exp1_repeat.csv" | tr -d ' ') requests registradas"

cleanup

# ══ 4. ANÁLISIS ═══════════════════════════════════════════════════════
hr; log "FASE 4 — análisis"
OUT="$OUT" python3 - <<'PY' > /dev/null
import csv, json, os, statistics as st
out = os.environ["OUT"]
meta = json.load(open(f"{out}/meta.json"))
tc, tbe = meta["t_chaos"], meta["t_base_end"]
nominal_end = tc + meta["chaos_secs"]

rows = []
with open(f"{out}/exp1_repeat.csv") as f:
    for r in csv.reader(f):
        if len(r) < 5: continue
        try: rows.append((float(r[0]), r[2], float(r[3])))
        except ValueError: pass

def phase(t):
    if t <= tbe: return "base"
    if t < tc: return "gap"
    if t <= nominal_end: return "chaos"
    return "post"

def pct(v, q):
    v = sorted(v)
    return v[min(len(v)-1, int(q*len(v)))] if v else float("nan")

L = ["═══ RESUMEN EXPERIMENTO 1 — NetworkChaos 200 ms ±10 ms ═══\n"]
base_p50 = None
for p, label in (("base","LÍNEA BASE"),("chaos","CHAOS (0-300s)"),("post","POST-ROLLBACK")):
    b = [x for x in rows if phase(x[0]) == p]
    if not b: continue
    ok = [x[2] for x in b if x[1] == "200"]
    err = [x for x in b if x[1] != "200"]
    if p == "base" and ok: base_p50 = pct(ok, .5)
    L.append(f"{label}: n={len(b)}  errores={len(err)} ({100*len(err)/len(b):.1f}%)")
    if ok:
        L.append(f"   p50={1000*pct(ok,.5):7.1f} ms   p95={1000*pct(ok,.95):7.1f} ms   "
                 f"p99={1000*pct(ok,.99):7.1f} ms   máx={1000*max(ok):7.1f} ms")
    L.append("")

ch = [x[2] for x in rows if phase(x[0]) == "chaos" and x[1] == "200"]
if base_p50 and ch:
    delta = 1000 * (pct(ch, .5) - base_p50)
    L.append(f"LATENCIA AÑADIDA (p50 chaos − p50 base): {delta:.1f} ms")
    L.append(f"   inyectado 200 ms en direction:to → esperado ~200-400 ms según ida/vuelta")
    L.append(f"   amplificación observada: {delta/200:.2f}× el delay inyectado\n")

# ¿cuándo volvió a la línea base tras el rollback?
post = [(t, d) for t, c, d in rows if t > nominal_end and c == "200"]
if post and base_p50:
    thr = base_p50 * 2
    back = next((t for t, d in post if d <= thr), None)
    if back:
        L.append(f"ROLLBACK: latencia de vuelta bajo 2× la línea base a t+{back-tc:.1f} s "
                 f"(fin nominal {meta['chaos_secs']} s) → desfase {back-nominal_end:+.1f} s")
    else:
        L.append("ROLLBACK: la latencia NO volvió a 2× la línea base dentro de la ventana observada")
    L.append("")

# El contador de RESTARTS es acumulado desde que nacio el pod: lo que
# importa es si CAMBIO durante el experimento, no su valor absoluto.
vals = {}
try:
    for line in open(f"{out}/samples/pods.txt"):
        p = line.split()
        if len(p) >= 4 and p[0].startswith("service-b") and p[3].isdigit():
            vals.setdefault(p[0], []).append(int(p[3]))
    deltas = {k: max(v) - min(v) for k, v in vals.items()}
    tot = sum(deltas.values())
    L.append(f"REINICIOS DURANTE EL EXPERIMENTO: {tot}   (control: debe ser 0)")
    for k, v in sorted(vals.items()):
        L.append(f"   {k}: contador {min(v)} → {max(v)}   (delta {deltas[k]})")
except Exception:
    pass

txt = "\n".join(L)
open(f"{out}/summary.txt", "w").write(txt + "\n")
PY
hr
cat "$OUT/summary.txt" 2>/dev/null | tee -a "$LOG"
hr
log "TODO EN: $OUT"
