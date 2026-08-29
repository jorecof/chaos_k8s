# Chaos Engineering con Chaos Mesh + LitmusChaos
## Migración del laboratorio Docker Compose → GKE

---

---

## Adaptación a un cluster kubeadm local (sin GKE)

Este fork corre el laboratorio completo sobre un **cluster kubeadm propio** (3 VMs
VirtualBox: `kube-cp` 192.168.0.20, `kube-w1` 192.168.0.21, `kube-w2` 192.168.0.22,
Debian 12 arm64, containerd, Calico) en vez de GKE. `scripts/setup.sh` original
asume GCP en varios puntos (cluster GKE, GCR, LoadBalancer, metadata server) que
no existen en un cluster on-prem. Esto es lo que hubo que resolver, en orden.

### 1. Preparación del cluster (antes de tocar el repo)

- `kubectl label node kube-cp rol=observabilidad` — permite anclar ahí cargas
  con estado (Postgres, el registry) vía `nodeSelector`.
- `kubectl taint nodes kube-cp node-role.kubernetes.io/control-plane:NoSchedule-`
  — cluster de 3 nodos, sin quitar el taint el control-plane no agenda pods.
- `export KUBECONFIG=~/.kube/config-lab` (persistido en `~/.zshrc`) — evita
  que `kubectl` caiga de nuevo en un contexto GKE viejo mezclado en el config
  por defecto.
- En las 3 VMs: enmascarar `sleep.target`/`suspend.target` y `IdleAction=ignore`
  en `logind.conf` — por defecto se suspendían solas y los nodos quedaban
  `NotReady`.

### 2. Registry local (reemplaza a GCR)

kubeadm no trae ningún registry. Se agregó:

- **`registry/registry.yaml`** (nuevo) — Deployment `registry:2` + Service
  `NodePort` en el puerto `30500`, con `nodeSelector: rol=observabilidad` y
  `hostPath` para persistencia, anclado a `kube-cp`.
- **`registry/setup-nodes.sh`** (nuevo) — por cada nodo, crea
  `/etc/containerd/certs.d/192.168.0.20:30500/hosts.toml` (`skip_verify = true`,
  HTTP sin TLS) y reinicia containerd para que confíe en el registry. Usa
  `ssh -t` para que `sudo` tenga terminal — sin eso falla con
  `sudo: a terminal is required`.

Build y push de las 3 imágenes, manual (equivalente al paso 3 de `setup.sh`
pero contra el registry local en vez de GCR):

```bash
docker build -t 192.168.0.20:30500/service-a:1.0.0 service-a/
docker push 192.168.0.20:30500/service-a:1.0.0
# ídem service-b y data-service
```

(Requiere agregar `192.168.0.20:30500` a `insecure-registries` en
Docker Desktop → Settings → Docker Engine.)

### 3. Cambios en los manifiestos (`base/`)

| Archivo | Cambio | Por qué |
|---|---|---|
| `base/01-configmaps.yaml` | `detectors: [env, gcp, k8s_node]` → `[env, system]` | `gcp` asume metadata server de GCP; `k8s_node` no es un detector válido de `resourcedetectionprocessor` (es `k8snode`, y requiere RBAC extra) |
| `base/01-configmaps.yaml` | exporter `googlecloud` quitado del pipeline de logs | sin credenciales de GCP en el cluster local |
| `base/02-deployments.yaml` | `image: gcr.io/...` → `image: 192.168.0.20:30500/...` en las 3 imágenes | usar el registry local |
| `base/02-deployments.yaml` | `service-a-svc` y `jaeger-svc`: `LoadBalancer` → `NodePort` | kubeadm no tiene cloud controller que asigne IPs externas |
| `base/02-deployments.yaml` | Postgres: `StatefulSet` + `volumeClaimTemplates` → `Deployment` + `hostPath` (`nodeSelector: rol=observabilidad`) | el PVC dinámico requiere una `StorageClass`, que un kubeadm plano no trae; el PVC se hubiera quedado en `Pending` para siempre |

### 4. LitmusChaos

- `scripts/setup.sh` descarga las `ChaosExperiment` desde
  `hub.litmuschaos.io/api/chaos/3.x.x?file=...` — esa URL del hub devuelve un
  404/HTML y rompe el `kubectl apply`. Se agregó
  **`litmus/pod-delete-experiment.yaml`** (nuevo) con el `ChaosExperiment`
  `pod-delete` embebido directamente (imagen
  `litmuschaos.docker.scarf.sh/litmuschaos/go-runner:3.31.0`, tomada del chart
  oficial `litmus-helm`).
- `litmus/chaosengine-experiment-2.yaml`: los probes usaban `mode: DuringChaos`,
  que no es un valor válido del CRD (`^(SOT|EOT|Edge|Continuous|OnChaos)$`) →
  corregido a `mode: OnChaos`.

Instalación de Chaos Mesh + LitmusChaos (steps 1-4 de GCP quedan comentados en
`main()`; se corre solo la parte de herramientas de chaos, que ya era
containerd-nativa):

```bash
export KUBECONFIG=~/.kube/config-lab
bash scripts/setup.sh --install-chaos-tools
kubectl apply -f litmus/pod-delete-experiment.yaml
```

### 5. Verificación end-to-end

```bash
kubectl -n otel-lab get pods                 # todo Running
curl http://192.168.0.20:$(kubectl -n otel-lab get svc service-a-svc -o jsonpath='{.spec.ports[0].nodePort}')/health
kubectl apply -f litmus/chaosengine-experiment-2.yaml
kubectl -n otel-lab get chaosengine,chaosresult
```

`chaos-mesh/*.yaml` no necesitó cambios: ya usa `chaosDaemon.runtime=containerd`
y `socketPath=/run/containerd/containerd.sock`, compatible con kubeadm tal cual.


## Qué cambió técnicamente

### Antes (Docker Compose — Módulo D)

```python
# chaos_experiments.py — fault DENTRO de la aplicación
CHAOS_LATENCY_MS = int(os.getenv("CHAOS_LATENCY_MS", "0"))

def apply_chaos():
    if CHAOS_LATENCY_MS > 0:
        time.sleep(CHAOS_LATENCY_MS / 1000)   # ← código de la app
```

```python
# data-service/main.py — error DENTRO de la aplicación
if random.random() < CHAOS_ERROR_RATE:
    raise HTTPException(status_code=500)       # ← código de la app
```

### Después (GKE — Chaos Mesh + LitmusChaos)

```yaml
# Chaos Mesh — fault en el KERNEL DE RED
# La app NO tiene ningún time.sleep() ni random()
kind: NetworkChaos
spec:
  action: delay
  delay:
    latency: "200ms"     # ← tc qdisc en el kernel del nodo
```

```yaml
# LitmusChaos — steady state hypothesis formal
probe:
  - name: alert-fired-during-chaos
    type: promProbe        # ← verifica que Prometheus alertó
    mode: DuringChaos      # ← mide el MTTD automáticamente
```

---

## Estructura del proyecto

```
chaos-k8s/
├── base/
│   ├── 00-namespace-rbac.yaml     # Namespace, RBAC, ServiceAccounts
│   ├── 01-configmaps.yaml         # OTel Collector config, DB init SQL
│   └── 02-deployments.yaml        # Todos los Deployments, Services, HPA
│
├── chaos-mesh/
│   ├── experiment-1-network-latency.yaml  # NetworkChaos 200ms en service-b
│   └── experiment-2-http-error.yaml       # HTTPChaos + PodChaos + StressChaos
│
├── litmus/
│   ├── chaosengine-experiment-1.yaml      # ChaosEngine con probes de red
│   └── chaosengine-experiment-2.yaml      # ChaosEngine con pod failure
│
├── monitoring/
│   └── prometheus-config.yaml             # Prometheus + reglas AIOps para GKE
│
└── scripts/
    └── setup.sh                           # Instalación y ejecución completa
```

---

## Prerrequisitos

```bash
# 1. Herramientas necesarias
gcloud --version    # Google Cloud SDK
kubectl version     # Kubernetes CLI
helm version        # Helm 3.x
docker --version    # Docker Desktop

# 2. Autenticación GCP
gcloud auth login
gcloud auth application-default login
gcloud config set project cicdtraining-498421
```

---

## Instalación completa (primera vez)

```bash
chmod +x scripts/setup.sh
./scripts/setup.sh
```

El script ejecuta en orden:
1. Crea el cluster GKE `otel-lab-chaos` en us-central1
2. Construye y publica las imágenes en GCR
3. Despliega el stack OTel base
4. Instala Chaos Mesh via Helm
5. Instala LitmusChaos operator
6. Genera tráfico baseline
7. Ejecuta los 2 experimentos de chaos
8. Muestra el estado final

---

## Ejecutar solo los experimentos (stack ya desplegado)

```bash
./scripts/setup.sh --chaos
```

---

## Experimento 1 — Chaos Mesh: NetworkChaos 200ms en service-b

**Qué hace:** Inyecta 200ms de latencia real a nivel de red en todos los pods de service-b usando `tc qdisc` del kernel Linux.

**Por qué es diferente al laboratorio Docker:**
- No modifica el código de service-b
- La latencia es real de red — OTel la mide como latencia de HTTP, no de CPU
- Rollback automático cuando termina el TTL (5 minutos)
- Blast radius controlado: solo pods con label `app=service-b`

```bash
# Aplicar manualmente
kubectl apply -f k8s/chaos-mesh/experiment-1-network-latency.yaml

# Ver estado
kubectl get networkchaos -n otel-lab

# Eliminar (rollback)
kubectl delete -f k8s/chaos-mesh/experiment-1-network-latency.yaml
```

**Qué verificar en Grafana:**
- Panel 2: Latencia p99 de service-b debe subir > 200ms
- Panel 6: Spans en vuelo aumentan
- Panel 7: Burn rate sube si la latencia causa timeouts

---

## Experimento 2 — LitmusChaos: Pod Failure en data-service

**Qué hace:** LitmusChaos elimina pods de data-service periódicamente y verifica automáticamente que:
1. El sistema estaba saludable ANTES del chaos (steady state)
2. Prometheus detectó el fallo DURANTE el chaos (MTTD < 2 min)
3. El sistema se recuperó DESPUÉS del chaos

```bash
# Aplicar el ChaosEngine
kubectl apply -f k8s/litmus/chaosengine-experiment-2.yaml

# Ver estado del experimento
kubectl get chaosengine -n otel-lab

# Ver resultado con veredicto Pass/Fail
kubectl get chaosresult -n otel-lab
kubectl describe chaosresult otel-lab-pod-failure-pod-delete -n otel-lab
```

**El ChaosResult muestra:**
```yaml
status:
  experimentStatus:
    verdict: Pass     # o Fail si alguna probe falló
    probeSuccessPercentage: "100"
  probeStatuses:
    - name: alert-fired-during-chaos
      status:
        verdict: Passed
        description: "AIOpsCorrelatedAnomaly activa en 47s — MTTD OK"
```

---

## Acceder a los dashboards

```bash
# Jaeger — flame graphs de trazas durante el chaos
kubectl port-forward -n otel-lab svc/jaeger-svc 16686:16686 &
# Abrir: http://localhost:16686

# Prometheus — queries durante el chaos
kubectl port-forward -n otel-lab svc/prometheus-svc 9091:9090 &
# Abrir: http://localhost:9091

# Chaos Mesh Dashboard — estado visual de los experiments
kubectl port-forward -n chaos-mesh svc/chaos-dashboard 2333:2333 &
# Abrir: http://localhost:2333

# LitmusChaos ChaosCenter — resultados y probes
kubectl port-forward -n litmus svc/litmus-frontend-service 9092:9091 &
# Abrir: http://localhost:9092 (admin/litmus)
```

---

## Diferencias técnicas clave

| Aspecto | Docker Compose (antes) | GKE + Chaos Mesh + Litmus (ahora) |
|---|---|---|
| Dónde vive el fault | Código de la app (Python) | Kernel de red (tc qdisc) |
| La app sabe del chaos | Sí (lee variable de entorno) | No — es completamente transparente |
| Tipo de latencia | `time.sleep()` — CPU time | Latencia real de red — medida por OTel |
| Rollback | Restart del contenedor | TTL automático en el CRD |
| Steady state | No existe | ChaosEngine valida antes y después |
| MTTD medido | Script Python con polling | Prometheus probe en el ChaosEngine |
| Veredicto formal | JSON generado manualmente | ChaosResult CRD con Pass/Fail |
| Blast radius | Todo el contenedor | Selector de labels K8s |
| Programación | Manual | Schedule CRD (cron) |

---

## Limpiar el laboratorio

```bash
# Eliminar experiments activos
kubectl delete networkchaos,httpchaos,podchaos --all -n otel-lab
kubectl delete chaosengine --all -n otel-lab

# Desinstalar Chaos Mesh
helm uninstall chaos-mesh -n chaos-mesh

# Desinstalar LitmusChaos
kubectl delete -f https://litmuschaos.github.io/litmus/litmus-operator-v3.8.0.yaml

# Eliminar el cluster GKE (¡cuidado!)
gcloud container clusters delete otel-lab-chaos \
  --region=us-central1 --project=cicdtraining-498421
```

---

## Referencias

- Chaos Mesh docs: https://chaos-mesh.org/docs/
- LitmusChaos docs: https://docs.litmuschaos.io/
- LitmusChaos Hub: https://hub.litmuschaos.io/
- Principles of Chaos Engineering: https://principlesofchaos.org/
- CNCF Chaos Engineering landscape: https://landscape.cncf.io/?group=chaos-engineering
