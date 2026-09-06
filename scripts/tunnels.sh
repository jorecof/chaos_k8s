#!/bin/bash
# ══════════════════════════════════════════════════════════════════════
# tunnels.sh -- gestiona los port-forwards de las apps de otel-lab sin
# depender de `jobs`/`kill %N` (que solo ven procesos de la MISMA shell
# interactiva -- la causa de casi todos los "address already in use" /
# "lost connection to pod" de esta sesion: un port-forward levantado en
# una pestaña queda invisible desde otra, y uno pegado a un pod que un
# rollout restart recicla se cae solo sin que el job table se entere).
#
# Cada tunnel se trackea por un archivo de PID en $PIDDIR (por defecto
# /tmp/otel-lab-tunnels/), asi que sobrevive a cambios de terminal y se
# puede parar/status desde cualquier lado.
#
# Uso:
#   bash scripts/tunnels.sh start   [nombre ...]   # todos si no se da nombre
#   bash scripts/tunnels.sh stop    [nombre ...]
#   bash scripts/tunnels.sh restart [nombre ...]
#   bash scripts/tunnels.sh status  [nombre ...]
#
# Ejemplos:
#   bash scripts/tunnels.sh start                 # levanta las 7 apps
#   bash scripts/tunnels.sh start prometheus       # solo Prometheus
#   bash scripts/tunnels.sh restart prometheus     # util tras un rollout
#   bash scripts/tunnels.sh stop                   # baja todo
# ══════════════════════════════════════════════════════════════════════
set -u
NS=${NS:-otel-lab}
PIDDIR=${PIDDIR:-/tmp/otel-lab-tunnels}
mkdir -p "$PIDDIR"

# nombre:puerto_local:servicio:puerto_remoto
DEFS=(
  "grafana:3000:grafana-svc:3000"
  "jaeger:16686:jaeger-svc:16686"
  "prometheus:9091:prometheus-svc:9090"
  "alertmanager:9095:alertmanager-svc:9093"
  "alert-enricher:8090:alert-enricher-svc:8080"
  "loki:3100:loki-svc:3100"
  "service-a:8000:service-a-svc:8000"
)

find_def(){
  local name=$1 d n lp svc rp
  for d in "${DEFS[@]}"; do
    IFS=: read -r n lp svc rp <<<"$d"
    if [ "$n" = "$name" ]; then echo "$lp:$svc:$rp"; return 0; fi
  done
  return 1
}

names_or_all(){
  if [ "$#" -eq 0 ]; then
    local d
    for d in "${DEFS[@]}"; do echo "${d%%:*}"; done
  else
    printf '%s\n' "$@"
  fi
}

is_up(){
  local pf="$PIDDIR/$1.pid"
  [ -f "$pf" ] && kill -0 "$(cat "$pf" 2>/dev/null)" 2>/dev/null
}

stop_one(){
  local name=$1 pf="$PIDDIR/$name.pid" pid def lp svc rp
  if [ -f "$pf" ]; then
    pid=$(cat "$pf")
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null
      echo "  [$name] detenido (pid $pid)"
    fi
    rm -f "$pf"
  fi
  # tambien matar cualquier port-forward zombie del mismo servicio que
  # haya quedado de una terminal vieja sin pidfile
  def=$(find_def "$name") || return 0
  IFS=: read -r lp svc rp <<<"$def"
  pkill -f "port-forward -n $NS svc/$svc $lp:$rp" 2>/dev/null
}

start_one(){
  local name=$1 def lp svc rp pid
  def=$(find_def "$name") || { echo "  [$name] nombre desconocido"; return 1; }
  IFS=: read -r lp svc rp <<<"$def"
  stop_one "$name"
  sleep 0.3
  nohup kubectl -n "$NS" port-forward "svc/$svc" "$lp:$rp" \
        > "$PIDDIR/$name.log" 2>&1 &
  pid=$!
  disown "$pid" 2>/dev/null
  echo "$pid" > "$PIDDIR/$name.pid"
  sleep 1.5
  if kill -0 "$pid" 2>/dev/null; then
    echo "  [$name] arriba en localhost:$lp -> svc/$svc:$rp  (pid $pid)"
  else
    echo "  [$name] FALLO al levantar -- ver $PIDDIR/$name.log:"
    tail -n 5 "$PIDDIR/$name.log" 2>/dev/null | sed 's/^/      /'
  fi
}

status_one(){
  local name=$1 def lp svc rp
  if is_up "$name"; then
    def=$(find_def "$name"); IFS=: read -r lp svc rp <<<"$def"
    echo "  [$name] UP    localhost:$lp  (pid $(cat "$PIDDIR/$name.pid"))"
  else
    echo "  [$name] down"
  fi
}

cmd=${1:-status}
[ "$#" -gt 0 ] && shift

case "$cmd" in
  start)
    echo "Levantando tunnels..."
    while read -r n; do start_one "$n"; done < <(names_or_all "$@")
    ;;
  stop)
    echo "Bajando tunnels..."
    while read -r n; do stop_one "$n"; done < <(names_or_all "$@")
    ;;
  restart)
    while read -r n; do stop_one "$n"; start_one "$n"; done < <(names_or_all "$@")
    ;;
  status)
    while read -r n; do status_one "$n"; done < <(names_or_all "$@")
    ;;
  *)
    echo "uso: $0 {start|stop|restart|status} [nombre ...]"
    echo "nombres disponibles: $(names_or_all | tr '\n' ' ')"
    exit 1
    ;;
esac
