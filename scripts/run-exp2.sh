#!/bin/bash
# ══════════════════════════════════════════════════════════════════════
# run-exp2.sh — Experimento 2 (repetición instrumentada)
#
# HTTPChaos abort:true sobre data-service escalado a 10 réplicas
# (mode: fixed-percent, value: "10" → 1 pod aborta el 100% de SUS
# requests → ~10% de error agregado).
#
# Además del error rate, esta corrida mide lo que faltó la vez pasada:
#   · RESTARTS del pod objetivo antes/durante/después  (hipótesis del
#     hallazgo 2: el rollback "falló" porque el contenedor reinició)
#   · timeline del rollback: último error observado vs. t=300s nominal
#   · contadores de Prometheus por pod, en paralelo al cliente
#   · conteo de trazas en Jaeger en la ventana (hallazgo 1: blind spot)
#   · latencia de los aborts (~8.5 s la vez pasada) vs. las OK (12-50 ms)
#
# Uso:   bash scripts/run-exp2.sh
# Vars:  NODE_IP=192.168.0.20 WORKERS=4 INTERVAL=1.5 POST_SECS=240 ...
# Dura:  ~12 min. Limpia solo al terminar (y también si lo cortas con ^C).
# ══════════════════════════════════════════════════════════════════════
set -u

NS=${NS:-otel-lab}
DEP=${DEP:-data-service}
SVC=${SVC:-data-service-svc}
CHAOS_FILE=${CHAOS_FILE:-chaos-mesh/experiment-2-http-error.yaml}
CHAOS_NAME=${CHAOS_NAME:-error-rate-data-service-10pct}
NODE_IP=${NODE_IP:-192.168.0.20}
REPLICAS=${REPLICAS:-10}
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
OUT="$OUT_ROOT/exp2${RUN_LABEL:+-$RUN_LABEL}-$STAMP"
mkdir -p "$OUT/samples"
LOG="$OUT/run.log"

log(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }
hr(){ echo "──────────────────────────────────────────────────────────" | tee -a "$LOG"; }

# ── reloj de alta resolución ──────────────────────────────────────────
if command -v gdate >/dev/null 2>&1; then now(){ gdate +%s.%3N; }
elif command -v perl >/dev/null 2>&1; then now(){ perl -MTime::HiRes=time -e 'printf "%.3f\n", time'; }
else now(){ date +%s; }; fi

# ── helpers de consulta vía apiserver proxy (sin port-forward) ────────
promq(){
  local enc
  enc=$(python3 -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1],safe=""))' "$1")
  kubectl -n "$NS" get --raw \
    "/api/v1/namespaces/$NS/services/prometheus-svc:9090/proxy/api/v1/query?query=$enc" 2>/dev/null
}
jaegerq(){  # $1=start_us  $2=end_us
  kubectl -n "$NS" get --raw \
    "/api/v1/namespaces/$NS/services/jaeger-svc:16686/proxy/api/traces?service=data-service&start=$1&end=$2&limit=3000" 2>/dev/null
}

# ══ 0. PREFLIGHT ══════════════════════════════════════════════════════
hr; log "FASE 0 — preflight"
for b in kubectl curl python3; do
  command -v "$b" >/dev/null 2>&1 || { log "FALTA $b — abortando"; exit 1; }
done
if ! kubectl get --raw /readyz >/dev/null 2>&1; then
  log "El apiserver no responde. ¿VMs encendidas? Abortando."; exit 1
fi
kubectl get nodes -o wide            > "$OUT/preflight-nodes.txt" 2>&1
kubectl top nodes                   >> "$OUT/preflight-nodes.txt" 2>&1
kubectl -n "$NS" get pods -o wide    > "$OUT/preflight-pods.txt"  2>&1
kubectl -n "$NS" get svc             > "$OUT/preflight-svc.txt"   2>&1

LEFTOVER=$(kubectl -n "$NS" get httpchaos,networkchaos,podchaos,stresschaos,schedule \
             --no-headers 2>/dev/null | wc -l | tr -d ' ')
if [ "$LEFTOVER" != "0" ] && [ "$FORCE" != "1" ]; then
  log "Hay $LEFTOVER objeto(s) de chaos vivos de una corrida anterior:"
  kubectl -n "$NS" get httpchaos,networkchaos,podchaos,stresschaos,schedule 2>&1 | tee -a "$LOG"
  log "Bórralos (kubectl -n $NS delete httpchaos --all) o corre con FORCE=1. Abortando."
  exit 1
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
if [ -z "$NODEPORT" ]; then
  log "$SVC no tiene nodePort (¿sigue en ClusterIP?). Abortando."; exit 1
fi
URL="http://$NODE_IP:$NODEPORT$TEST_PATH"
log "target: $URL"
SMOKE=$(curl -s -o /dev/null -m 10 -w '%{http_code}' "$URL")
[ "$SMOKE" = "200" ] || { log "smoke test devolvió $SMOKE — abortando"; exit 1; }
log "smoke test OK"

kubectl -n "$NS" get --raw \
  "/api/v1/namespaces/$NS/services/prometheus-svc:9090/proxy/api/v1/label/__name__/values" \
  > "$OUT/prom-metric-names.json" 2>/dev/null && log "catálogo de métricas de Prometheus guardado"

# ══ limpieza garantizada ══════════════════════════════════════════════
CLEANED=0
cleanup(){
  [ "$CLEANED" = "1" ] && return
  CLEANED=1
  hr; log "LIMPIEZA — borrando chaos y volviendo a 2 réplicas"
  # El finalizer de Chaos Mesh espera un recovery que puede no completar
  # nunca (ver hallazgo 2): por eso el delete lleva timeout y, si queda
  # colgado, se fuerza quitando el finalizer.
  kubectl -n "$NS" delete -f "$CHAOS_FILE" --ignore-not-found=true --timeout=45s 2>&1 | tee -a "$LOG"
  if kubectl -n "$NS" get httpchaos "$CHAOS_NAME" >/dev/null 2>&1; then
    log "el borrado quedó bloqueado por el finalizer — forzando"
    kubectl -n "$NS" patch httpchaos "$CHAOS_NAME" --type=merge \
      -p '{"metadata":{"finalizers":[]}}' 2>&1 | tee -a "$LOG"
    echo "FINALIZER_FORZADO=1" >> "$OUT/meta-extra.txt"
  fi
  # Quitar el finalizer NO revierte las reglas iptables: eso lo hace
  # destruir el netns, o sea borrar el pod objetivo.
  if [ -n "${TARGET:-}" ]; then
    TPOD=$(echo "$TARGET" | tr ' ' '\n' | head -1 | awk -F/ '{print $2}')
    [ -n "$TPOD" ] && kubectl -n "$NS" delete pod "$TPOD" --ignore-not-found=true --wait=false 2>&1 | tee -a "$LOG"
  fi
  kubectl -n "$NS" scale deploy "$DEP" --replicas=2 2>&1 | tee -a "$LOG"
  sleep 8
  kubectl -n "$NS" get pods -l app="$DEP" -o wide > "$OUT/pods-after-cleanup.txt" 2>&1
  kubectl -n "$NS" get httpchaos                 >> "$OUT/pods-after-cleanup.txt" 2>&1
  log "limpieza terminada"
}
trap 'echo; log "INTERRUMPIDO por el usuario"; cleanup; exit 130' INT TERM

# ══ generador de carga ════════════════════════════════════════════════
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
load_for(){  # $1 = segundos
  local endts=$(( $(date +%s) + $1 )) i=1
  while [ "$i" -le "$WORKERS" ]; do worker "$i" "$endts" & i=$((i+1)); done
}

# ══ muestreador ═══════════════════════════════════════════════════════
sampler(){
  local endts=$1 t
  while [ "$(date +%s)" -lt "$endts" ]; do
    t=$(date +%s)
    { echo "=== t=$t ==="
      kubectl -n "$NS" get pods -l app="$DEP" --no-headers \
        -o custom-columns='NAME:.metadata.name,NODE:.spec.nodeName,PHASE:.status.phase,READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount,STARTED:.status.containerStatuses[0].state.running.startedAt'
    } >> "$OUT/samples/pods.txt" 2>&1
    { echo "=== t=$t ==="
      kubectl -n "$NS" get httpchaos "$CHAOS_NAME" -o json 2>/dev/null \
      | python3 -c '
import json,sys
try: d=json.load(sys.stdin)
except Exception: print("(sin objeto)"); raise SystemExit
st=d.get("status",{})
print("conditions:", [(c.get("type"),c.get("status")) for c in st.get("conditions",[])])
for r in st.get("experiment",{}).get("containerRecords",[]):
    print("  record:", r.get("id"), "phase:", r.get("phase"), "sel:", r.get("selectorKey"))
'
    } >> "$OUT/samples/chaos-status.txt" 2>&1
    { echo "=== t=$t ==="
      echo "-- app: requests registradas por data-service --"
      promq 'sum(rate(otelcol_data_requests_total[1m]))'
      echo; echo "-- borde: probe_success por endpoint --"
      promq 'probe_success'
      echo; echo "-- borde: probe_duration_seconds --"
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
log "línea base terminada"

# ══ 2. ESCALADO A 10 RÉPLICAS ═════════════════════════════════════════
hr; log "FASE 2 — escalando $DEP a $REPLICAS réplicas"
kubectl -n "$NS" scale deploy "$DEP" --replicas="$REPLICAS" 2>&1 | tee -a "$LOG"
kubectl -n "$NS" rollout status deploy "$DEP" --timeout=180s 2>&1 | tee -a "$LOG" \
  || { log "el rollout no completó — abortando"; cleanup; exit 1; }
kubectl -n "$NS" get pods -l app="$DEP" -o wide > "$OUT/pods-before-chaos.txt" 2>&1
kubectl -n "$NS" get pods -l app="$DEP" --no-headers \
  -o custom-columns='NAME:.metadata.name,NODE:.spec.nodeName,RESTARTS:.status.containerStatuses[0].restartCount' \
  >> "$OUT/pods-before-chaos.txt" 2>&1
log "réplicas listas — distribución por nodo:"
awk 'NF>3 {print $7}' "$OUT/pods-before-chaos.txt" | sort | uniq -c | tee -a "$LOG"
kubectl top pods -n "$NS" > "$OUT/top-before-chaos.txt" 2>&1
sleep 10   # que Prometheus alcance a raspar los pods nuevos

# ══ 3. INYECCIÓN + CARGA ══════════════════════════════════════════════
hr; log "FASE 3 — aplicando HTTPChaos (duration del manifiesto: ${CHAOS_SECS}s)"
kubectl apply -f "$CHAOS_FILE" 2>&1 | tee -a "$LOG"
T_CHAOS=$(now)
sleep 5
kubectl -n "$NS" get httpchaos "$CHAOS_NAME" -o yaml > "$OUT/chaos-applied.yaml" 2>&1
TARGET=$(kubectl -n "$NS" get httpchaos "$CHAOS_NAME" \
         -o jsonpath='{.status.experiment.containerRecords[*].id}' 2>/dev/null)
log "pod(s) objetivo seleccionado(s): ${TARGET:-(aún no reportado)}"
echo "$TARGET" > "$OUT/target-pod.txt"

# Confirmar que la inyeccion ocurrio de verdad. Un experimento que no
# inyecta produce cero errores, que es indistinguible de "el sistema
# aguanto" si nadie mira el estado del CRD.
INJ=""
for _ in 1 2 3 4 5 6 7 8 9 10; do
  INJ=$(kubectl -n "$NS" get httpchaos "$CHAOS_NAME" \
        -o jsonpath='{.status.experiment.containerRecords[0].phase}' 2>/dev/null)
  case "$INJ" in Injected*) break;; esac
  sleep 3
done
if ! case "$INJ" in Injected*) true;; *) false;; esac; then
  log "EL CHAOS NO SE INYECTO — phase: ${INJ:-desconocida}"
  kubectl -n "$NS" describe httpchaos "$CHAOS_NAME" 2>&1 | grep -A6 "Events:" | tee -a "$LOG"
  log "Si aparece 'TimeUp ... according to the duration' recien creado, es desfase de reloj."
  cleanup
  exit 1
fi
log "inyeccion confirmada (phase: $INJ)"

TOTAL=$((CHAOS_SECS + POST_SECS))
log "carga durante ${TOTAL}s (${CHAOS_SECS}s de chaos + ${POST_SECS}s de observación post-rollback)"
SAMPLER_END=$(( $(date +%s) + TOTAL + 10 ))
sampler "$SAMPLER_END" &
SPID=$!
load_for "$TOTAL"
wait
T_END=$(now)
kill "$SPID" 2>/dev/null

# ══ 4. RECOLECCIÓN ════════════════════════════════════════════════════
hr; log "FASE 4 — recolectando evidencia"
kubectl -n "$NS" describe httpchaos "$CHAOS_NAME" > "$OUT/chaos-describe.txt" 2>&1
kubectl -n "$NS" get events --sort-by=.lastTimestamp > "$OUT/events.txt" 2>&1
kubectl -n "$NS" get pods -l app="$DEP" -o wide > "$OUT/pods-after-chaos.txt" 2>&1
kubectl -n "$NS" get pods -l app="$DEP" --no-headers \
  -o custom-columns='NAME:.metadata.name,RESTARTS:.status.containerStatuses[0].restartCount,LASTSTATE:.status.containerStatuses[0].lastState.terminated.reason' \
  >> "$OUT/pods-after-chaos.txt" 2>&1
if [ -n "$TARGET" ]; then
  TPOD=$(echo "$TARGET" | tr ' ' '\n' | head -1 | awk -F/ '{print $2}')
  [ -n "$TPOD" ] && kubectl -n "$NS" logs "$TPOD" --tail=200 > "$OUT/target-pod-logs.txt" 2>&1
  [ -n "$TPOD" ] && kubectl -n "$NS" describe pod "$TPOD" > "$OUT/target-pod-describe.txt" 2>&1
fi
kubectl -n "$NS" logs -l app.kubernetes.io/component=chaos-daemon -n chaos-mesh --tail=300 \
  > "$OUT/chaos-daemon-logs.txt" 2>&1

US_START=$(python3 -c "print(int(float('$T_CHAOS')*1000000))")
US_END=$(python3 -c "print(int(float('$T_END')*1000000))")
jaegerq "$US_START" "$US_END" > "$OUT/jaeger-traces.json" 2>&1
log "trazas de Jaeger de la ventana guardadas"

promq 'sum by (pod) (data_requests_total)'                 > "$OUT/prom-final-requests.json" 2>&1
promq 'sum(rate(data_requests_total[5m])) by (status)'     > "$OUT/prom-final-by-status.json" 2>&1

cat > "$OUT/meta.json" <<META
{"t_base_start": $T_BASE_START, "t_base_end": $T_BASE_END,
 "t_chaos": $T_CHAOS, "t_end": $T_END,
 "chaos_secs": $CHAOS_SECS, "post_secs": $POST_SECS,
 "workers": $WORKERS, "interval": $INTERVAL, "replicas": $REPLICAS,
 "url": "$URL", "target": "$TARGET"}
META

cat "$OUT"/raw-w*.csv 2>/dev/null | sort -t, -k1 -n > "$OUT/exp2_repeat.csv"
log "$(wc -l < "$OUT/exp2_repeat.csv" | tr -d ' ') requests registradas"

cleanup

# ══ 5. ANÁLISIS ═══════════════════════════════════════════════════════
hr; log "FASE 5 — análisis"
OUT="$OUT" python3 - <<'PY' | tee -a "$LOG" > /dev/null
import csv, json, os, statistics as st
out = os.environ["OUT"]
meta = json.load(open(f"{out}/meta.json"))
tc, tend = meta["t_chaos"], meta["t_end"]
tbs, tbe = meta["t_base_start"], meta["t_base_end"]
nominal_end = tc + meta["chaos_secs"]

rows = []
with open(f"{out}/exp2_repeat.csv") as f:
    for r in csv.reader(f):
        if len(r) < 5: continue
        try: rows.append((float(r[0]), r[2], float(r[3])))
        except ValueError: pass

def phase(t):
    if t <= tbe: return "base"
    if t < tc: return "scale"
    if t <= nominal_end: return "chaos"
    return "post"

L = []
buckets = {"base": [], "chaos": [], "post": []}
for t, code, dur in rows:
    p = phase(t)
    if p in buckets: buckets[p].append((t, code, dur))

def pct(v, q):
    v = sorted(v)
    return v[min(len(v)-1, int(q*len(v)))] if v else float("nan")

L.append("═══ RESUMEN EXPERIMENTO 2 (repetición instrumentada) ═══\n")
for p, label in (("base","LÍNEA BASE"),("chaos","CHAOS (0-300s)"),("post","POST-ROLLBACK (300s+)")):
    b = buckets[p]
    if not b: continue
    err = [x for x in b if x[1] != "200"]
    ok  = [x[2] for x in b if x[1] == "200"]
    L.append(f"{label}: n={len(b)}  errores={len(err)} ({100*len(err)/len(b):.1f}%)")
    if ok:
        L.append(f"   OK    p50={1000*pct(ok,.5):.0f}ms  p95={1000*pct(ok,.95):.0f}ms  max={1000*max(ok):.0f}ms")
    if err:
        d = [x[2] for x in err]
        codes = {}
        for x in err: codes[x[1]] = codes.get(x[1],0)+1
        L.append(f"   ERR   códigos={codes}  duración media={st.mean(d):.2f}s  min={min(d):.2f}s  max={max(d):.2f}s")
    L.append("")

errs = [t for t,c,_ in rows if c != "200" and t >= tc]
if errs:
    L.append(f"TIMELINE DEL ROLLBACK")
    L.append(f"   primer error:  t+{errs[0]-tc:6.1f}s   (MTTD del cliente)")
    L.append(f"   último error:  t+{errs[-1]-tc:6.1f}s")
    L.append(f"   fin nominal:   t+{meta['chaos_secs']:6.1f}s")
    lag = errs[-1] - nominal_end
    L.append(f"   → {'ROLLBACK TARDÍO: ' + format(lag,'.1f') + 's de errores después del duration' if lag > 15 else 'rollback dentro de lo esperado (' + format(lag,'.1f') + 's)'}")
    L.append("")

try:
    tr = json.load(open(f"{out}/jaeger-traces.json")).get("data") or []
    codes = {}
    for t_ in tr:
        for s in t_.get("spans", []):
            for tag in s.get("tags", []):
                if tag.get("key") in ("http.status_code","http.response.status_code"):
                    codes[str(tag["value"])] = codes.get(str(tag["value"]),0)+1
    total_err = sum(1 for t_,c,_ in rows if c != "200" and tc <= t_ <= tend)
    L.append("BLIND SPOT DE TRAZAS")
    L.append(f"   trazas de data-service en la ventana: {len(tr)}")
    L.append(f"   status codes vistos en spans: {codes or '(ninguno etiquetado)'}")
    L.append(f"   errores del lado cliente en la misma ventana: {total_err}")
    ciego = not any(k.startswith(("4", "5")) for k in codes) and total_err
    L.append("   → CONFIRMADO: el APM no registra ni un error." if ciego
             else "   → revisar: aparecen spans con status de error")
    L.append("     target: Response aborta en el camino de VUELTA: la app ya proceso")
    L.append("     la request y emitio su span 200 cuando Chaos Mesh corta la conexion.")
    L.append("     La telemetria no tiene un hueco: afirma exito para requests fallidas.")
except Exception as e:
    L.append(f"(no se pudo analizar Jaeger: {e})")

txt = "\n".join(L)
open(f"{out}/summary.txt","w").write(txt+"\n")
print(txt)
PY
hr
cat "$OUT/summary.txt"
hr
log "TODO EN: $OUT"
log "Pásame  $OUT/summary.txt  y, si querés, $OUT/chaos-describe.txt"
