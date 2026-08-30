#!/bin/bash
# ══════════════════════════════════════════════════════════════════════
# run-gameday.sh — Game Day completo, desatendido
#
#   E1   NetworkChaos 200ms ±10ms sobre service-b        (~11 min)
#   ──   pausa de recuperación
#   E2A  HTTPChaos abort, path: "*"          → health check DENTRO
#        del blast radius: crash-loop y rollback fallido  (~12 min)
#   ──   pausa de recuperación
#   E2B  HTTPChaos abort, path: "/data/*"    → health check FUERA
#        del blast radius: debería hacer rollback limpio  (~12 min)
#
# La comparación A vs B es la prueba experimental de la remediación #1
# del addendum. Al final escribe un reporte unificado.
#
# Uso:  bash scripts/run-gameday.sh
# Dura: ~40 min. Limpia después de cada experimento y también si lo
#       cortas con Ctrl-C.
# ══════════════════════════════════════════════════════════════════════
set -u

NS=${NS:-otel-lab}
RECOVER=${RECOVER:-150}          # pausa entre experimentos
SKIP_E1=${SKIP_E1:-0}
SKIP_E2A=${SKIP_E2A:-0}
SKIP_E2B=${SKIP_E2B:-0}

# ── Evitar que el equipo se duerma a mitad del Game Day ───────────────
# Un MacBook dormido suspende las VMs de VirtualBox: el apiserver
# desaparece, el chaos queda inyectado sin poder revertirse y la corrida
# se pierde. caffeinate -dimsu mantiene el equipo despierto mientras dura.
if [ "$(uname -s)" = "Darwin" ] && [ "${GAMEDAY_CAFFEINATED:-0}" != "1" ] \
   && command -v caffeinate >/dev/null 2>&1; then
  echo "[$(date +%H:%M:%S)] relanzando bajo caffeinate para que el Mac no se duerma"
  GAMEDAY_CAFFEINATED=1 exec caffeinate -dimsu "$0" "$@"
fi

cd "$(dirname "$0")/.." || exit 1
STAMP=$(date +%Y%m%d-%H%M%S)
GD="results/gameday-$STAMP"
mkdir -p "$GD"
LOG="$GD/gameday.log"

log(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }
banner(){
  echo "" | tee -a "$LOG"
  echo "══════════════════════════════════════════════════════════" | tee -a "$LOG"
  echo "  $*" | tee -a "$LOG"
  echo "══════════════════════════════════════════════════════════" | tee -a "$LOG"
}

trap 'echo; log "GAME DAY INTERRUMPIDO — los scripts hijos ya limpiaron lo suyo"; exit 130' INT TERM

banner "GAME DAY — $(date '+%Y-%m-%d %H:%M')"
log "salida: $GD"

# ── preflight común ───────────────────────────────────────────────────
kubectl get --raw /readyz >/dev/null 2>&1 || { log "apiserver no responde — abortando"; exit 1; }
LEFT=$(kubectl -n "$NS" get httpchaos,networkchaos,podchaos,stresschaos,schedule --no-headers 2>/dev/null | wc -l | tr -d ' ')
if [ "$LEFT" != "0" ]; then
  log "Hay $LEFT objeto(s) de chaos vivos. Bórralos antes de empezar:"
  kubectl -n "$NS" get httpchaos,networkchaos,podchaos,stresschaos,schedule 2>&1 | tee -a "$LOG"
  exit 1
fi
BB=$(kubectl -n "$NS" get deploy blackbox-exporter -o jsonpath='{.status.readyReplicas}' 2>/dev/null)
if [ "${BB:-0}" -ge 1 ] 2>/dev/null; then
  log "blackbox-exporter listo — el SLI de borde quedará registrado"
else
  log "AVISO: blackbox-exporter no está desplegado; el tablero no verá los aborts"
fi
kubectl -n "$NS" get pods -o wide > "$GD/estado-inicial.txt" 2>&1

pausa(){
  log "pausa de recuperación: ${RECOVER}s"
  sleep "$RECOVER"
  kubectl -n "$NS" get pods -o wide >> "$GD/estado-entre-experimentos.txt" 2>&1
}

# Si el cluster desaparece no tiene sentido seguir: cada experimento
# gastaria su preflight y dejaria chaos sin revertir.
exigir_cluster(){
  if ! kubectl get --raw /readyz >/dev/null 2>&1; then
    log "EL APISERVER NO RESPONDE — abortando el Game Day."
    log "Causa tipica: el equipo se durmio y suspendio las VMs."
    log "Revisa que quede chaos vivo cuando el cluster vuelva:"
    log "  kubectl -n $NS get networkchaos,httpchaos"
    exit 1
  fi
}

# ── E1 ────────────────────────────────────────────────────────────────
if [ "$SKIP_E1" != "1" ]; then
  exigir_cluster
  banner "EXPERIMENTO 1 — NetworkChaos 200 ms ±10 ms sobre service-b"
  OUT_ROOT="$GD" bash scripts/run-exp1.sh 2>&1 | tee -a "$LOG"
  [ "${PIPESTATUS[0]}" = "0" ] || log "AVISO: el Experimento 1 terminó con error — sigo con los siguientes"
  pausa
fi

# ── E2A ───────────────────────────────────────────────────────────────
if [ "$SKIP_E2A" != "1" ]; then
  exigir_cluster
  banner "EXPERIMENTO 2A — HTTPChaos abort, path: \"*\"  (health check DENTRO del blast radius)"
  OUT_ROOT="$GD" RUN_LABEL=A bash scripts/run-exp2.sh 2>&1 | tee -a "$LOG"
  [ "${PIPESTATUS[0]}" = "0" ] || log "AVISO: el Experimento 2A terminó con error"
  pausa
fi

# ── E2B ───────────────────────────────────────────────────────────────
if [ "$SKIP_E2B" != "1" ]; then
  exigir_cluster
  banner "EXPERIMENTO 2B — HTTPChaos abort, path: \"/data/*\"  (health check FUERA del blast radius)"
  OUT_ROOT="$GD" RUN_LABEL=B \
    CHAOS_FILE=chaos-mesh/experiment-2-http-error-remediado.yaml \
    CHAOS_NAME=error-rate-data-service-10pct-remediado \
    bash scripts/run-exp2.sh 2>&1 | tee -a "$LOG"
  [ "${PIPESTATUS[0]}" = "0" ] || log "AVISO: el Experimento 2B terminó con error"
fi

# ── reporte unificado ─────────────────────────────────────────────────
banner "REPORTE UNIFICADO"
kubectl -n "$NS" get pods -o wide > "$GD/estado-final.txt" 2>&1
kubectl -n "$NS" get httpchaos,networkchaos >> "$GD/estado-final.txt" 2>&1

GD="$GD" python3 - <<'PY'
import csv, glob, json, os, re

gd = os.environ["GD"]
L = ["═══════════════════════════════════════════════════════════════",
     "  GAME DAY — REPORTE UNIFICADO",
     "═══════════════════════════════════════════════════════════════", ""]

def load(d, csvname):
    meta = json.load(open(f"{d}/meta.json"))
    rows = []
    for r in csv.reader(open(f"{d}/{csvname}")):
        if len(r) >= 5:
            try: rows.append((float(r[0]), r[2], float(r[3])))
            except ValueError: pass
    return meta, rows

def pct(v, q):
    v = sorted(v)
    return v[min(len(v)-1, int(q*len(v)))] if v else float("nan")

def restarts_delta(d, prefix):
    """Reinicios OCURRIDOS durante el experimento = max-min del contador
    acumulado. exp1 muestrea 4 columnas y exp2 seis, de ahi el barrido."""
    vals = {}
    try:
        for line in open(f"{d}/samples/pods.txt"):
            p = line.split()
            if not p or not p[0].startswith(prefix): continue
            n = next((int(t) for t in p[3:6] if t.isdigit()), None)
            if n is not None: vals.setdefault(p[0], []).append(n)
    except Exception:
        pass
    return sum(max(v) - min(v) for v in vals.values()) if vals else 0

rows_tbl = []

for d in sorted(glob.glob(f"{gd}/exp1-*")):
    try:
        meta, rows = load(d, "exp1_repeat.csv")
    except (FileNotFoundError, ValueError):
        L += [f"── EXPERIMENTO 1 ({os.path.basename(d)}): sin datos, la corrida no completo", ""]
        continue
    tc, tbe = meta["t_chaos"], meta["t_base_end"]
    nom = tc + meta["chaos_secs"]
    base = [x[2] for x in rows if x[0] <= tbe and x[1] == "200"]
    ch   = [x[2] for x in rows if tc <= x[0] <= nom and x[1] == "200"]
    post = [(x[0], x[2]) for x in rows if x[0] > nom and x[1] == "200"]
    thr = pct(base, .5) * 2 if base else 0
    back = next((t for t, v in post if v <= thr), None)
    L += [f"── EXPERIMENTO 1 — NetworkChaos delay 200 ms  ({os.path.basename(d)})",
          f"   p50 línea base   {1000*pct(base,.5):8.1f} ms      p95 {1000*pct(base,.95):8.1f} ms",
          f"   p50 con chaos    {1000*pct(ch,.5):8.1f} ms      p95 {1000*pct(ch,.95):8.1f} ms",
          f"   latencia añadida {1000*(pct(ch,.5)-pct(base,.5)):8.1f} ms  sobre 200 ms inyectados",
          f"   rollback: vuelve a la línea base a t+{back-tc:.0f} s (nominal {meta['chaos_secs']} s)"
          if back else "   rollback: NO volvió a la línea base en la ventana observada",
          f"   reinicios durante el experimento: {restarts_delta(d,'service-b')}   (control — debe ser 0)", ""]

for label, glb in (("A — path: \"*\"        (health check DENTRO)", "exp2-A-*"),
                   ("B — path: \"/data/*\"  (health check FUERA)",  "exp2-B-*")):
    ds = sorted(glob.glob(f"{gd}/{glb}"))
    if not ds:
        continue
    d = ds[-1]
    try:
        meta, rows = load(d, "exp2_repeat.csv")
    except (FileNotFoundError, ValueError):
        L += [f"── EXPERIMENTO 2{label}: sin datos, la corrida no completo", ""]
        continue
    tc, tbe = meta["t_chaos"], meta["t_base_end"]
    nom = tc + meta["chaos_secs"]
    ch  = [x for x in rows if tc <= x[0] <= nom]
    po  = [x for x in rows if x[0] > nom]
    errs = [x[0] for x in rows if x[1] != "200" and x[0] >= tc]
    lag = (errs[-1] - nom) if errs else None
    rst = restarts_delta(d, "data-service")
    forced = os.path.exists(f"{d}/meta-extra.txt")
    e_ch = sum(1 for x in ch if x[1] != "200")
    e_po = sum(1 for x in po if x[1] != "200")
    L += [f"── EXPERIMENTO 2{label}   ({os.path.basename(d)})",
          f"   error rate durante el chaos   {100*e_ch/len(ch):5.1f} %   ({e_ch}/{len(ch)})",
          f"   error rate después del TTL    {100*e_po/len(po) if po else 0:5.1f} %   ({e_po}/{len(po)})",
          f"   último error                  t+{errs[-1]-tc:6.1f} s   (nominal {meta['chaos_secs']} s)"
          if errs else "   sin errores registrados",
          f"   desfase del rollback          {lag:+6.1f} s" if lag is not None else "",
          f"   reinicios del pod objetivo    {rst}",
          f"   finalizer forzado en limpieza: {'SÍ' if forced else 'no'}", ""]
    rows_tbl.append((label.split("—")[0].strip(), 100*e_ch/len(ch), lag, rst, forced))

if len(rows_tbl) == 2:
    a, b = rows_tbl
    L += ["═══ COMPARACIÓN A vs B — ¿funciona la remediación #1? ═══", ""]
    L += [f"                                   A (path \"*\")   B (path \"/data/*\")",
          f"   error rate inyectado            {a[1]:8.1f} %     {b[1]:10.1f} %",
          f"   desfase del rollback            {a[2]:+8.1f} s     {b[2]:+10.1f} s"
          if a[2] is not None and b[2] is not None else "   desfase del rollback: ver arriba",
          f"   reinicios del pod objetivo      {a[3]:8d}       {b[3]:10d}",
          f"   hubo que forzar el finalizer    {'SÍ' if a[4] else 'no':>8}       {'SÍ' if b[4] else 'no':>10}",
          ""]
    # Si A no produjo errores es que el chaos no se inyecto: la
    # comparacion no vale, aunque B se vea impecable.
    if a[1] < 1.0:
        L += ["   COMPARACION INVALIDA: la corrida A no inyecto (0 % de error).",
              "   Revisar exp2-A-*/samples/chaos-status.txt: si el phase es",
              "   'Not Injected', el experimento de control nunca ocurrio y no",
              "   se puede concluir nada sobre la remediacion. Repetir A.", ""]
        veredicto = None
    else:
        veredicto = (b[3] == 0 and b[2] is not None and b[2] < 30 and not b[4])
    if veredicto is not None:
        L += ["   VEREDICTO: la remediación FUNCIONA — con el health check fuera del",
              "   blast radius el pod no reinicia y el rollback por TTL cierra limpio."
              if veredicto else
              "   VEREDICTO: la remediación NO cerró limpio; revisar samples/chaos-status.txt",
              ""]

L += [f"Evidencia completa en: {gd}"]
txt = "\n".join(x for x in L if x is not None)
open(f"{gd}/REPORTE.txt", "w").write(txt + "\n")
print(txt)
PY

log ""
log "Game Day terminado. Reporte: $GD/REPORTE.txt"
