#!/bin/bash
# ════════════════════════════════════════════════════════════════
#
# Instala Istio en modo ambient (sidecarless) sobre el cluster kubeadm
# real y habilita el namespace otel-lab en la malla (modulo A.5, G-07).
#
# Por que ambient y no sidecars: el laboratorio ya tiene 3 servicios
# instrumentados con OTel SDK (trazas/metricas/logs) y el objetivo de
# esta pieza es la observabilidad de RED (L4/L7) independiente del
# codigo de aplicacion -- exactamente lo que separa "instrumentacion"
# de "malla de servicios" en el diseno del laboratorio integrador.
# Ambient evita reinyectar sidecars en pods que ya tienen sus propios
# contenedores (cloud-sql-proxy en data-service, por ejemplo).
#
# Requisitos verificados en este cluster antes de escribir este script:
#   - K8s v1.35.8 (Istio 1.31 soporta 1.32-1.36)
#   - 3 nodos Debian 12 arm64 (Istio publica imagenes multi-arch)
#   - Calico en dataplane Iptables (compatible; el problema documentado
#     de ambient es especifico de Cilium/eBPF)
#   - `istioctl x precheck` limpio
#
# Uso:
#   chmod +x scripts/setup-istio-ambient.sh
#   ./scripts/setup-istio-ambient.sh
# ════════════════════════════════════════════════════════════════

set -euo pipefail

ISTIO_VERSION="1.31.0"
NAMESPACE="otel-lab"
GATEWAY_API_VERSION="v1.5.1"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log()  { echo -e "${BLUE}[$(date +%H:%M:%S)]${NC} $1"; }
ok()   { echo -e "${GREEN}✅ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $1${NC}"; }

# ── 1. istioctl ────────────────────────────────────────────────────
if ! command -v istioctl &>/dev/null; then
  log "Descargando istioctl ${ISTIO_VERSION}..."
  curl -L https://istio.io/downloadIstio | ISTIO_VERSION="${ISTIO_VERSION}" sh -
  export PATH="$PWD/istio-${ISTIO_VERSION}/bin:$PATH"
  warn "istioctl quedó en ./istio-${ISTIO_VERSION}/ (gitignored) — agrega ese bin/ a tu PATH en shells futuros."
else
  ok "istioctl ya disponible: $(istioctl version --remote=false 2>/dev/null)"
fi

# ── 2. Fix de compatibilidad Calico <-> ambient ─────────────────────
# ztunnel redirige trafico dentro del netns de cada pod; el connect-time
# load balancer de Calico (bpfConnectTimeLoadBalancing, default "TCP")
# reescribe las mismas conexiones a nivel de conexion y puede pisarse
# con esa redireccion. istioctl x precheck detecta esto y lo reporta.
# Ref: https://github.com/istio/istio/issues/53750
log "Deshabilitando bpfConnectTimeLoadBalancing en Calico (Felix)..."
kubectl patch felixconfiguration default --type=merge \
  -p '{"spec":{"bpfConnectTimeLoadBalancing":"Disabled"}}'

# ── 3. Precheck ──────────────────────────────────────────────────────
log "Corriendo istioctl x precheck..."
istioctl x precheck

# ── 4. Instalar el profile ambient ──────────────────────────────────
log "Instalando Istio (profile=ambient): istiod + ztunnel + istio-cni..."
istioctl install --set profile=ambient --skip-confirmation

# ── 5. Gateway API CRDs (requeridas para waypoint proxies, L7) ──────
log "Instalando Gateway API CRDs ${GATEWAY_API_VERSION}..."
kubectl apply --server-side \
  -f "https://github.com/kubernetes-sigs/gateway-api/releases/download/${GATEWAY_API_VERSION}/experimental-install.yaml"

# ── 6. Habilitar el namespace del laboratorio en la malla ───────────
log "Habilitando ${NAMESPACE} en el dataplane ambient..."
kubectl label namespace "${NAMESPACE}" istio.io/dataplane-mode=ambient --overwrite

# ── 7. Verificacion ──────────────────────────────────────────────────
log "Verificando..."
kubectl get pods -n istio-system
kubectl get pods -n "${NAMESPACE}" -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.metadata.annotations.ambient\.istio\.io/redirection}{"\n"}{end}'

ok "Istio ambient instalado. Metricas L4 de ztunnel: ver monitoring/prometheus-config.yaml (job 'ztunnel')."
ok "Siguiente pieza: waypoint proxy por namespace para telemetria L7 (istio_requests_total)."
