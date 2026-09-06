# B.4 — Backtesting: ¿reduce ruido el conjunto dinámico? (cierra el tercer punto del módulo B)

## Método y una desviación respecto al diseño

El diseño (`claude/U3-Diseno-Laboratorio-Integrador.md` §B.4) pedía convertir
`results/gameday-final/series-*.json` al formato de `promtool test rules` y
comparar el conjunto estático (4 reglas independientes) contra
`AIOpsCorrelatedAnomaly` sobre la misma ventana.

Dos problemas con eso tal cual estaba planteado:

1. Esos `series-*.json` son dumps de Prometheus ya agregados (`rate()` y
   `histogram_quantile()` aplicados) capturados el 30-ago, **antes** del fix
   de contrato de métricas (G-08/G-09) — no traen el desglose por `outcome`
   que las reglas nuevas necesitan, y Prometheus no conserva ya esos datos
   (el pod se reinició varias veces esta sesión; el storage es `emptyDir`,
   no hay volumen persistente).
2. `promtool` no está instalado en esta máquina.

En su lugar se usó la fuente más fiel que sí existe para esa ventana: los
CSV crudos por petición (`raw-w{1..4}.csv` de cada corrida — timestamp,
worker, status, latencia — medidos por el propio cliente de carga). La
lógica de las reglas (`sli:error_rate:ratio5m`, `sli:latency_p99:5m`,
`AIOpsCorrelatedAnomaly`) se reimplementó en Python
(`scripts/backtest-noise-reduction.py`) operando sobre esas series con
ventanas rodantes de 5 min y paso de 15 s, igual que Prometheus.

**Limitación explícita:** la regla real calcula μ/σ sobre 6 h de historia
(cientos de ventanas de 5 min independientes, `offset 10m`). Aquí solo hay
~90 s de tráfico base por experimento — insuficiente para varianza
temporal real. Se aproximó σ con el error estándar de una proporción
binomial (`sqrt(p·(1-p)/n)`), el análogo estadístico correcto para una
muestra corta. Con una base sin errores, esto da un σ casi nulo — el
umbral dinámico queda prácticamente en "cualquier error por encima del
piso del 1 %", lo cual es razonable para una base de verdad limpia pero
subestima la varianza que existiría en 6 h reales de tráfico de producción.

Las reglas `restarts>0` y `probe_success==0` del conjunto estático no se
pudieron re-evaluar (no hay reinicios ni datos de blackbox en estos CSV
por petición) — se excluyen del conteo, documentado aquí en vez de
inflar artificialmente el lado estático.

## Resultado

| Experimento | Peticiones | μ base | σ base | Alertas estático (error+latencia) | Alertas dinámico (correlada) | MTTD dinámico |
|---|---|---|---|---|---|---|
| E1 — latencia 200 ms, service-b | 1448 | 0.0000 | 0.0001 | **1** (solo latencia) | **0** | no disparó |
| E2-A — error rate 10 %, `path:'*'` | 1252 | 0.0000 | 0.0001 | **2** (error + latencia) | **1** | 137 s |
| E2-B — error rate 10 %, `path:'/data/*'` | 1620 | 0.0000 | 0.0001 | **1** (solo error) | **0** | no disparó |
| **Total** | | | | **4** | **1** | |

Reducción nominal: 75 % menos alertas totales. **Esa cifra es engañosa leída
sola** — hay que mirar qué se dejó de disparar y por qué.

## El hallazgo real: la regla correlacionada solo dispara cuando el fallo *también* eleva la latencia

Revisando por qué el dinámico no disparó en E1 y en E2-B:

- **E1** es un fallo de latencia pura (Chaos Mesh `NetworkChaos delay`) —
  nunca hay error, así que `error_rate:ratio5m` nunca cruza ni siquiera el
  piso del 1 %. `AIOpsCorrelatedAnomaly` exige error_rate **y** p99 **y**
  piso — con error_rate en 0, la condición nunca es verdadera. La regla
  estática de latencia sí dispara (correctamente).

- **E2-B** es la sorpresa: mismo `HTTPChaos abort` al 10 % que E2-A, pero
  con `path: /data/*` en vez de `path: '*'`. Los datos crudos muestran que
  en E2-A los requests abortados **cuelgan** ~9,3 s de media antes de
  fallar (`target: Response` corta la conexión de *vuelta*, después de que
  el cliente ya envió todo — el socket queda esperando), empujando el p99
  por encima del umbral de 250 ms. En E2-B los mismos requests abortados
  fallan **rápido** (mediana 19,6 ms) — el error_rate sube igual (11,8 %
  medido en el cliente, según `summary.txt` de esa corrida) pero el p99
  **nunca** cruza 250 ms, así que la condición de latencia de
  `AIOpsCorrelatedAnomaly` nunca se cumple y la regla se queda callada
  aunque hay un incidente real en curso.

En ambos casos el `summary.txt` de cada corrida ya documentaba el mismo
punto ciego desde el lado de trazas: *"target: Response aborta en el
camino de vuelta: la app ya procesó la request y emitió su span 200 cuando
Chaos Mesh corta la conexión — la telemetría no tiene un hueco, afirma
éxito para requests fallidas."* Es decir: ni Jaeger ni la regla
correlacionada ven este tipo de fallo si no hay señal de latencia que lo
acompañe. Solo la métrica de error rate del lado del contador
(`otelcol_data_requests_total{outcome="error"}`, si el propio handler
marca el resultado) o el side del cliente lo detectan — y en este
mecanismo de chaos concreto, ni siquiera eso: la app no ve el corte, solo
el cliente.

## Conclusión y recomendación

`AIOpsCorrelatedAnomaly` **no reemplaza** una regla simple de
`error_rate > 1%`; la complementa. La correlación (error + latencia + piso)
sirve para **subir la prioridad** de una alerta cuando el fallo es lo
bastante severo como para degradar también la latencia — es decir, para
decidir *page* vs *ticket* (la misma distinción que hace el Alertmanager
del SRE Book: alertas de página al on-call, alertas subcríticas a la cola
de tickets). La reducción de "ruido" que sí es real y deseable es esa:
menos páginas nocturnas por eventos que ya se sabe que son severos,
mientras la regla de error rate simple (sin exigir correlación) sigue
corriendo en background como la señal de cobertura completa que alimenta
el burn-rate (`HighBurnRate_PAGE`) y el ticket queue.

Esto también es la base concreta para el contraste D2-app vs D2-mesh del
módulo D: el propio mecanismo de chaos (`target: Response`, corte de
vuelta) es un blind spot de trazas *y* — según cuán rápido falle la
conexión — puede ser también un blind spot para la regla de correlación
de latencia. Dos capas de "accionable" que fallan por la misma causa raíz.

## Reproducir

```bash
python3 scripts/backtest-noise-reduction.py
```

Detalle completo (episodios, timestamps) en `docs/backtesting-B4-resultados.json`.
