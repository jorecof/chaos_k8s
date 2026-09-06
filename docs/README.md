# Documentación — Laboratorio Integrador de Observabilidad (MASOBAP2026, Unidad 3)

Todo el material de la actividad vive aquí. `entrega/` es lo que se entrega; el resto es soporte,
evidencia e historial.

## `entrega/` — lo que se entrega

| Archivo | Qué es |
|---|---|
| `3-Informe_Integrador_U3_Observabilidad.docx` | **El entregable evaluable de U3.** Arquitectura, diseño, los cinco módulos (A–E), metodología de pruebas y resultados de los experimentos de Chaos Engineering, con la evidencia real (GCP Cloud Monitoring, dashboards, trazas). |
| `2-Anexo_Game_Day_cluster_real_v6.pdf` / `.docx` | **Anexo de evidencia (base de U3, Módulo B/D).** El Game Day reproducido sobre este mismo cluster kubeadm de 3 nodos: Experimento 1 (NetworkChaos), Experimento 2 corrida A y corrida de control B, cinco hallazgos y la remediación verificada experimentalmente — es el insumo real que U3 retoma y extiende. |
| `ENTREGA-FINAL-Observabilidad-U3.md` | Checklist de cierre de la entrega: repo público + tag `v1.0`, alcance sandbox de los experimentos, y autoría (Ernesto Ilich Contreras y Saúl Mauricio González). |

> Nota: el plan de Game Day de unidades anteriores (`1-Plan_Game_Day_Chaos_Engineering`, ejecutado
> sobre el laboratorio `otel-e2e-lab`, un repo distinto) y las figuras/scripts que lo acompañaban ya
> no viven en este repositorio — no aplicaban a este laboratorio integrador.

## `soporte/`

| Archivo | Qué es |
|---|---|
| `RUNBOOK-GameDay-kubeadm.md` | Cómo reproducir los tres experimentos del Game Day sobre un cluster kubeadm. |
| `chaos-gameday-kit.tar.gz` | Kit reproducible del Game Day: scripts, datos crudos y figuras. |

## `historial/`

Versiones anteriores del anexo de Game Day (v2 a v6). La v6 es la vigente y está en `entrega/`.

## Evidencia cruda

Fuera de `docs/`, en `results/gameday-final/`: las tres corridas del 2026-08-30
(`exp1-103316`, `exp2-A-111232`, `exp2-B-113517`) con 4 320 peticiones medidas en el cliente,
muestreo de pods y del CRD cada 15 s, eventos del `describe`, series de Prometheus a 5 s y trazas de
Jaeger de cada ventana. Reproducible con `scripts/run-gameday.sh`.
