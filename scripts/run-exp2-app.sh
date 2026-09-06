#!/bin/bash
# ══════════════════════════════════════════════════════════════════════
# run-exp2-app.sh — Experimento 2, variante D2-app (error real en la app)
#
# A diferencia de run-exp2.sh (HTTPChaos abort — corta la conexion de
# VUELTA, la app nunca se entera, blind spot de trazas), esta variante
# inyecta el error DENTRO del handler via CHAOS_ERROR_RATE (ya soportado
# en data-service/main.py): con probabilidad ERROR_RATE, el propio
# codigo levanta HTTPException(500) real, con status ERROR en el span
# y log con trace_id. Es el contraste D2-app vs D2-mesh del diseño
# (D-08): misma tasa de error nominal, blind spot de trazas opuesto.
#
# Mecanismo de inyeccion/rollback: NO es un CRD de Chaos Mesh con TTL
# propio -- es un patch de env var + rollout, y el rollback lo dispara
# este script explicitamente a los CHAOS_SECS (temporizador en
# background), no Kubernetes.
#
# Uso:   bash scripts/run-exp2-app.sh
# Vars:  NODE_IP=192.168.0.20 WORKERS=4 INTERVAL=1.5 ERROR_RATE=0.1 ...
# Dura:  ~12 min.
# ══════════════════════════════════════════════════════════════════════
set -u

NS=${NS:-otel-lab}
DEP=${DEP:-data-service}
SVC=${SVC:-data-service-svc}
NODE_IP=${NODE_IP:-192.168.0.20}
ERROR_RATE=${ERROR_RATE:-0.1}
WORKERS=${WORKERS:-4}
INTERVAL=${INTERVAL:-1.5}
BASELINE_SECS=${BASELINE_SECS:-90}
CHAOS_SECS=${CHAOS_SECS:-300}
POST_SECS=${POST_SECS:-240}
MAX_TIME=${MAX_TIME:-15}
SAMPLE_INT=${SAMPLE_INT:-15}
TEST_PATH=${TEST_PATH:-/data/products}
OUT_ROOT=${OUT_ROOT:-results}
RUN_LABEL=${RUN_LABEL:-}
FORCE=${FORCE:-0}

cd "$(dirname "$0")/.." || exit 1
STAMP=$(date +%Y%m%d-%H%M%S)
OUT="$OUT_ROOT/exp2-app${RUN_LABEL:+-$RUN_LABEL}-$STAMP"
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
    "/api/v1/namespaces/$NS/services/jaeger-svc:16686/proxy/api/traces?service=data-service&start=$1&end=$2&limit=3000" 2>/dev/null
}

# ══ 0. PREFLIGHT ══════════════════════════════════════════════════════
hr; log "FASE 0 — preflight"
for b in kubectl curl python3; do
  command -v "$b" >/dev/null 2>&1 || { log "FALTA $b — abortando"; exit 1; }
done
kubectl get --raw /readyz >/dev/null 2>&1 || { log "El apiserver no responde. Abortando."; exit 1; }

CURRENT_RATE=$(kubectl -n "$NS" get deploy "$DEP" \
  -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="CHAOS_ERROR_RATE")].value}' 2>/dev/null)
if [ -n "$CURRENT_RATE" ] && [ "$CURRENT_RATE" != "0" ] && [ "$FORCE" != "1" ]; then
  log "CHAOS_ERROR_RATE ya está en $CURRENT_RATE de una corrida anterior sin limpiar."
  log "Corre: kubectl -n $NS set env deploy/$DEP CHAOS_ERROR_RATE=0   o usa FORCE=1."
  exit 1
fi

kubectl -n "$NS" get pods -o wide > "$OUT/preflight-pods.txt" 2>&1

check_reloj(){
  local ts skew
  ts=$(kubectl create configmap "clock-probe-$$" -n "$NS" --dry-run=server \
       -o jsonpath='{.metadata.creationTimestamp}' 2>/dev/null)
  [ -z "$ts" ] && { log "no pude leer el reloj del apiserver — sigo sin verificar"; return 0; }
  skew=$(python3 -c "
import datetime,sys
t=sys.argv[1].replace('Z','+00:00').split('.')[0]
if '+' not in t: t=t+'+00:00'
d=datetime.datetime.fromisoformat(t)
print(int(abs((datetime.datetime.now(datetime.timezone.utc)-d).total_seconds())))
" "$ts" 2>/dev/null)
  if [ "${skew:-0}" -gt 60 ] 2>/dev/null; then
    log "DESFASE DE RELOJ de ${skew}s — corrige antes de seguir."
    exit 1
  fi
  log "reloj del apiserver verificado (desfase ${skew}s)"
}
check_reloj

NODEPORT=$(kubectl -n "$NS" get svc "$SVC" -o jsonpath='{.spec.ports[0].nodePort}' 2>/dev/null)
[ -z "$NODEPORT" ] && { log "$SVC no tiene nodePort. Abortando."; exit 1; }
URL="http://$NODE_IP:$NODEPORT$TEST_PATH"
SMOKE=$(curl -s -o /dev/null -m 10 -w '%{http_code}' "$URL")
[ "$SMOKE" = "200" ] || { log "smoke test devolvió $SMOKE — abortando"; exit 1; }
log "target: $URL  (smoke test OK)"

# ══ limpieza garantizada ══════════════════════════════════════════════
CLEANED=0
cleanup(){
  [ "$CLEANED" = "1" ] && return
  CLEANED=1
  hr; log "LIMPIEZA — CHAOS_ERROR_RATE=0"
  kubectl -n "$NS" set env deploy/"$DEP" CHAOS_ERROR_RATE=0 2>&1 | tee -a "$LOG"
  kubectl -n "$NS" rollout status deploy/"$DEP" --timeout=120s 2>&1 | tee -a "$LOG"
  kubectl -n "$NS" get pods -l app="$DEP" -o wide > "$OUT/pods-after-cleanup.txt" 2>&1
  log "limpieza terminada"
}
trap 'echo; log "INTERRUMPIDO"; cleanup; exit 130' INT TERM

# ══ carga y muestreo (identico a run-exp2.sh) ═════════════════════════
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
        -o custom-columns='NAME:.metadata.name,READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount'
    } >> "$OUT/samples/pods.txt" 2>&1
    { echo "=== t=$t ==="
      promq 'sum(rate(otelcol_data_requests_total{outcome="error"}[1m]))'
    } >> "$OUT/samples/prom.txt" 2>&1
    sleep "$SAMPLE_INT"
  done
}

# ══ 1. LÍNEA BASE ═════════════════════════════════════════════════════
hr; log "FASE 1 — línea base ($BASELINE_SECS s)"
T_BASE_START=$(now)
load_for "$BASELINE_SECS"; wait
T_BASE_END=$(now)

# ══ 2. INYECCIÓN (env var, no CRD) + rollback programado ═════════════
hr; log "FASE 2 — CHAOS_ERROR_RATE=$ERROR_RATE en $DEP"
kubectl -n "$NS" set env deploy/"$DEP" CHAOS_ERROR_RATE="$ERROR_RATE" 2>&1 | tee -a "$LOG"
T_CHAOS=$(now)
kubectl -n "$NS" rollout status deploy/"$DEP" --timeout=120s 2>&1 | tee -a "$LOG" \
  || { log "el rollout no completó — abortando"; cleanup; exit 1; }
T_ROLLOUT_DONE=$(now)
log "rollout completo a t_inject+$(python3 -c "print(round($T_ROLLOUT_DONE-$T_CHAOS,1))")s (el error real no empieza hasta aca)"
kubectl -n "$NS" get pods -l app="$DEP" -o wide > "$OUT/pods-after-chaos.txt" 2>&1

# Rollback disparado por ESTE script (no hay TTL de Chaos Mesh aca)
( sleep "$CHAOS_SECS"
  kubectl -n "$NS" set env deploy/"$DEP" CHAOS_ERROR_RATE=0 >> "$LOG" 2>&1
  kubectl -n "$NS" rollout status deploy/"$DEP" --timeout=120s >> "$LOG" 2>&1
  echo "$(now)" > "$OUT/t_rollback_issued.txt"
) &
ROLLBACK_PID=$!

TOTAL=$((CHAOS_SECS + POST_SECS))
log "carga durante ${TOTAL}s (${CHAOS_SECS}s de error real + ${POST_SECS}s post-rollback)"
sampler $(( $(date +%s) + TOTAL + 10 )) &
SPID=$!
load_for "$TOTAL"
wait "$SPID" 2>/dev/null
wait
T_END=$(now)
kill "$SPID" "$ROLLBACK_PID" 2>/dev/null

# ══ 3. RECOLECCIÓN ════════════════════════════════════════════════════
hr; log "FASE 3 — recolectando evidencia"
kubectl -n "$NS" get events --sort-by=.lastTimestamp > "$OUT/events.txt" 2>&1
kubectl -n "$NS" get pods -l app="$DEP" -o wide > "$OUT/pods-final.txt" 2>&1

US_START=$(python3 -c "print(int(float('$T_CHAOS')*1000000))")
US_END=$(python3 -c "print(int(float('$T_END')*1000000))")
jaegerq "$US_START" "$US_END" > "$OUT/jaeger-traces.json" 2>&1
log "trazas de data-service de la ventana guardadas"

cat > "$OUT/meta.json" <<META
{"experimento": "E2-app-real-error",
 "t_base_start": $T_BASE_START, "t_base_end": $T_BASE_END,
 "t_chaos": $T_CHAOS, "t_rollout_done": $T_ROLLOUT_DONE, "t_end": $T_END,
 "chaos_secs": $CHAOS_SECS, "post_secs": $POST_SECS, "error_rate": $ERROR_RATE,
 "workers": $WORKERS, "interval": $INTERVAL,
 "url": "$URL", "target": "$DEP"}
META

cat "$OUT"/raw-w*.csv 2>/dev/null | sort -t, -k1 -n > "$OUT/exp2app_repeat.csv"
log "$(wc -l < "$OUT/exp2app_repeat.csv" | tr -d ' ') requests registradas"

cleanup

# ══ 4. ANÁLISIS ═══════════════════════════════════════════════════════
hr; log "FASE 4 — análisis"
OUT="$OUT" python3 - <<'PY' > /dev/null
import csv, json, os, statistics as st
out = os.environ["OUT"]
meta = json.load(open(f"{out}/meta.json"))
tc, tend = meta["t_chaos"], meta["t_end"]
tbe = meta["t_base_end"]
nominal_end = tc + meta["chaos_secs"]

rows = []
with open(f"{out}/exp2app_repeat.csv") as f:
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

L = ["═══ RESUMEN EXPERIMENTO 2-APP — error real via CHAOS_ERROR_RATE ═══\n"]
for p, label in (("base","LÍNEA BASE"),("chaos","CHAOS (error real, 0-300s)"),("post","POST-ROLLBACK")):
    b = [x for x in rows if phase(x[0]) == p]
    if not b: continue
    err = [x for x in b if x[1] != "200"]
    ok  = [x[2] for x in b if x[1] == "200"]
    L.append(f"{label}: n={len(b)}  errores={len(err)} ({100*len(err)/len(b):.1f}%)")
    if ok:
        L.append(f"   OK  p50={1000*pct(ok,.5):.0f}ms  p95={1000*pct(ok,.95):.0f}ms  max={1000*max(ok):.0f}ms")
    if err:
        codes = {}
        for x in err: codes[x[1]] = codes.get(x[1],0)+1
        L.append(f"   ERR códigos={codes}")
    L.append("")

try:
    tr = json.load(open(f"{out}/jaeger-traces.json")).get("data") or []
    err_spans = 0
    for t_ in tr:
        for s in t_.get("spans", []):
            tags = {tag.get("key"): tag.get("value") for tag in s.get("tags", [])}
            if tags.get("otel.status_code") == "ERROR" or str(tags.get("http.status_code")) == "500":
                err_spans += 1
    total_err_client = sum(1 for t,c,_ in rows if c != "200" and tc <= t <= tend)
    L.append("CONTRASTE CON EL BLIND SPOT DE D2-MESH")
    L.append(f"   trazas de data-service en la ventana: {len(tr)}")
    L.append(f"   spans con error real detectados: {err_spans}")
    L.append(f"   errores del lado cliente en la misma ventana: {total_err_client}")
    if err_spans > 0:
        L.append("   -> CONFIRMADO (esperado): a diferencia de D2-mesh, aca SI hay")
        L.append("      span de error con trace_id -- la alerta enriquecida deberia")
        L.append("      resolver un trace_id real. Este es el contraste D-08 del diseno.")
    else:
        L.append("   -> INESPERADO: no se ven spans de error pese a errores del cliente.")
        L.append("      Revisar si otel.status_code se está seteando en el handler.")
except Exception as e:
    L.append(f"(no se pudo analizar Jaeger: {e})")

txt = "\n".join(L)
open(f"{out}/summary.txt", "w").write(txt + "\n")
PY
hr
cat "$OUT/summary.txt" 2>/dev/null | tee -a "$LOG"
hr
log "TODO EN: $OUT"
log "Ahora corre: python3 scripts/mttd-analysis.py $OUT AIOpsCorrelatedAnomaly data-service"
