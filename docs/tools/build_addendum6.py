#!/usr/bin/env python3
"""addendum_cluster_real_v6.html — Game Day completo, sesión única del 2026-08-30."""
import base64, pathlib

V1  = "/home/claude/v1imgs"
OLD = "/home/claude/figs"
GD  = "/home/claude/gdfigs"
SH  = "/home/claude/shots"

def b64(p):
    return "data:image/png;base64," + base64.b64encode(pathlib.Path(p).read_bytes()).decode()

IMG = {
    "topologia": b64(f"{V1}/p1-1-FormXob.78a7e6f18e7d2e18498a5439dfab10d7.png"),
    "spans":     b64(f"{V1}/p4-3-FormXob.8edd7ddbd0fc9d77a291b42479f161e9.png"),
    "e1graf":    b64(f"{SH}/e1-grafana-latencia.png"),
    "e1scatter": b64(f"{SH}/e1-jaeger-scatter.png"),
    "e1tchaos":  b64(f"{SH}/e1-traza-chaos.png"),
    "e1tnorm":   b64(f"{SH}/e1-traza-normal.png"),
    "e1spans":   b64(f"{GD}/gd8-spans-e1.png"),
    "agrafsli":  b64(f"{SH}/a-grafana-sli.png"),
    "agrafbli":  b64(f"{SH}/a-grafana-blind.png"),
    "jvacio":    b64("/root/.claude/uploads/a1f853ca-a576-52cc-a736-8fa2322e85c2/a277395a-image.png"),
    "j1500":     b64("/root/.claude/uploads/a1f853ca-a576-52cc-a736-8fa2322e85c2/fe6a8693-image.png"),
    "blind":     b64(f"{GD}/gd5-blindspot.png"),
    "replicas":  b64(f"{SH}/b-panel-replicas.png"),
    "bgrafsli":  b64(f"{SH}/b-panel-sli.png"),
    "bgrafbli":  b64(f"{SH}/b-panel-blind.png"),
    "thr":       b64(f"{GD}/gd9-throughput-AB.png"),
    "mec":       b64(f"{OLD}/fig5-mecanismo.png"),
    "rst":       b64(f"{GD}/gd3-restarts-AB.png"),
    "err":       b64(f"{GD}/gd2-errorrate-AB.png"),
    "sondas":    b64(f"{GD}/gd6-sondas-AB.png"),
    "abort":     b64(f"{GD}/gd4-abort-latencia-AB.png"),
}

CSS = """
  @page { size: letter; margin: 18mm 16mm 16mm 16mm; }
  :root {
    --ink:#0b0b0b; --sec:#3c3b39; --muted:#6d6b66; --line:#dedcd5;
    --blue:#1f5fae; --crit:#b8322f; --good:#0d7a55;
    --wash:#f4f7fc; --washc:#fdf3f2; --washg:#f0f8f4;
  }
  * { box-sizing:border-box; }
  body { font-family:"DejaVu Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
         font-size:9.6pt; line-height:1.48; color:var(--ink); margin:0; }
  h1 { font-size:17pt; line-height:1.24; margin:0 0 4pt; letter-spacing:-.2pt; }
  .sub { color:var(--muted); font-size:9pt; margin:0 0 14pt;
         padding-bottom:10pt; border-bottom:1.6pt solid var(--blue); }
  h2 { font-size:12pt; margin:15pt 0 6pt; color:var(--blue); page-break-after:avoid; }
  h3 { font-size:10.2pt; margin:14pt 0 4pt; color:var(--ink); page-break-after:avoid; }
  p { margin:0 0 7pt; text-align:justify; }
  code { font-family:"DejaVu Sans Mono",ui-monospace,monospace; font-size:8.6pt;
         background:#f2f1ec; padding:.5pt 2.5pt; border-radius:2.5px; }
  figure { margin:9pt 0 10pt; page-break-inside:avoid; }
  figure img { width:86%; display:block; margin:0 auto;
               border:.6pt solid var(--line); border-radius:3px; }
  figcaption { font-size:8.2pt; color:var(--muted); margin-top:4.5pt;
               width:86%; margin-left:auto; margin-right:auto; }
  figcaption b { color:var(--sec); }
  table { width:100%; border-collapse:collapse; margin:8pt 0 12pt;
          font-size:8.7pt; page-break-inside:avoid; }
  th { text-align:left; font-size:8pt; text-transform:uppercase; letter-spacing:.4pt;
       color:var(--muted); font-weight:700; border-bottom:1pt solid var(--line);
       padding:5pt 7pt 4pt 0; }
  td { padding:5pt 7pt 5pt 0; border-bottom:.6pt solid var(--line); vertical-align:top; }
  td.num, th.num { text-align:right; font-variant-numeric:tabular-nums; padding-right:14pt; }
  td.a { color:var(--crit); font-weight:700; }
  td.b { color:var(--good); font-weight:700; }
  .callout { background:var(--wash); border-left:2.6pt solid var(--blue);
             padding:8pt 11pt; margin:10pt 0 12pt; page-break-inside:avoid; }
  .callout.crit { background:var(--washc); border-left-color:var(--crit); }
  .callout.good { background:var(--washg); border-left-color:var(--good); }
  .callout p:last-child { margin-bottom:0; }
  .callout .lbl { display:block; font-size:8pt; font-weight:700; text-transform:uppercase;
                  letter-spacing:.5pt; color:var(--blue); margin-bottom:3pt; }
  .callout.crit .lbl { color:var(--crit); }
  .callout.good .lbl { color:var(--good); }
  ol, ul { margin:0 0 8pt; padding-left:15pt; }
  li { margin-bottom:3.5pt; }
  .new { page-break-before:always; }
  .foot { margin-top:11pt; padding-top:7pt; border-top:.6pt solid var(--line);
          font-size:8pt; color:var(--muted); }
"""

BODY = f"""
<h1>Addendum: reproducción del Game Day de Chaos Engineering<br>en cluster kubeadm real</h1>
<p class="sub">MASOBAP2026 · Observabilidad U2 · Fork <code>jorecof/chaos_k8s</code> · versión 6 —
Game Day completo: Experimento 1, Experimento 2 y verificación experimental de la remediación</p>

<p>Este addendum documenta la reproducción del laboratorio de Chaos Engineering original (diseñado
para GKE) sobre un cluster kubeadm propio de 3 nodos, con datos y evidencia reales capturados durante
la ejecución. Esta versión recoge un Game Day completo ejecutado en una sola sesión —tres corridas
consecutivas sobre el mismo cluster, 4 320 peticiones medidas en el cliente— e incorpora dos cosas que
no estaban en las versiones anteriores: un <b>SLI medido fuera del proceso instrumentado</b>, desplegado precisamente
para poder ver lo que la telemetría de la aplicación no ve, y una <b>corrida de control que verifica
la remediación propuesta</b> en lugar de solo enunciarla.</p>

<div class="callout"><span class="lbl">Corrección respecto de la versión 2</span>
<p>La v2 explicaba que las peticiones abortadas «nunca llegan al código de la aplicación». La corrida
instrumentada demuestra que <b>eso es falso</b>: el manifiesto usa <code>target: Response</code>, de
modo que el corte ocurre en el camino de vuelta, después de que la aplicación procesó la petición y
emitió su span. La sección 5.1 desarrolla la explicación correcta, que hace el hallazgo más severo,
no menos.</p></div>

<div class="callout"><span class="lbl">Procedencia de los datos</span>
<p>Todos los números de este documento provienen de una misma sesión del 2026-08-30, ejecutada de
principio a fin sobre el cluster ya estabilizado: <b>Experimento 1 a las 10:33</b> (sección 3),
<b>corrida A del Experimento 2 a las 11:12</b> (secciones 4 a 6) y <b>corrida de control B a las
11:35</b> (sección 7). Las tres usan el mismo perfil de carga —4 workers, una petición cada 1,5 s,
90 s de línea base, 300 s de chaos y 240 s de observación posterior— y las capturas de Grafana y
Jaeger corresponden a la ventana exacta de cada una. La sección 8 documenta por qué hicieron falta
varios intentos antes de conseguir esta sesión limpia.</p></div>

<h2>1. Arquitectura real desplegada</h2>
<p>A diferencia del docker-compose del enunciado original, el laboratorio corre sobre un cluster
kubeadm de 3 VMs (VirtualBox, Debian 12 arm64, containerd 2.3.3, Calico v3.32.1, K8s v1.35). Las
cargas con estado (registry, Postgres, Prometheus, Grafana, Jaeger) quedan ancladas a
<code>kube-cp</code> vía <code>nodeSelector: rol=observabilidad</code>; el otel-collector corre como
DaemonSet (una réplica por nodo) para que el scrape de métricas por pod nunca dependa de a cuál
réplica enruta el Service. A esta topología se le añadió, para esta corrida, un
<b>blackbox exporter</b> que sondea tres endpoints cada 5 s desde dentro del cluster pero fuera de
los procesos instrumentados (sección 5.2).</p>
<figure><img src="{IMG['topologia']}" alt="Topología del cluster">
<figcaption><b>Figura 1.</b> Topología real del cluster y flujo de datos entre componentes.</figcaption></figure>

<h2>2. Verificación de estado estable (antes del chaos)</h2>
<p>Antes de inyectar fallas se revisaron Prometheus, Jaeger y las apps para confirmar comportamiento
normal. Esa revisión encontró y corrigió, sobre el sistema real, tres problemas que hubieran
invalidado cualquier medición posterior:</p>
<table>
<thead><tr><th style="width:26%">Problema</th><th style="width:37%">Causa raíz</th><th>Corrección</th></tr></thead>
<tbody>
<tr><td>Propagación de trace context rota entre service-a y service-b</td>
    <td><code>opentelemetry-instrumentation-fastapi &gt;=0.48b0</code> ya no engancha con el patch
        global <code>instrument()</code> llamado antes de crear la app</td>
    <td><code>FastAPIInstrumentor.instrument_app(app, ...)</code> llamado sobre la instancia,
        después de crearla</td></tr>
<tr><td>Métricas de service-b ausentes o intermitentes en Prometheus</td>
    <td>Prometheus scrapeaba el Service del otel-collector (round-robin sobre 3 réplicas DaemonSet)
        en vez de cada pod</td>
    <td><code>kubernetes_sd_configs (role: pod)</code> + RBAC nuevo (ServiceAccount + ClusterRole)</td></tr>
<tr><td>Duración de traza sin sentido en Jaeger (57m 60s)</td>
    <td>Desfasaje de reloj entre las 3 VMs (NTP desactivado)</td>
    <td><code>timedatectl set-ntp true</code> + restart de <code>systemd-timesyncd</code></td></tr>
</tbody></table>
<p>A esa lista se sumó, durante la preparación de esta corrida, un cuarto problema de observabilidad:
las métricas de las aplicaciones llegan a Prometheus a través del OTel Collector, de modo que su
nombre real lleva el prefijo <code>otelcol_</code> y la etiqueta que identifica al servicio es
<code>exported_job</code>, no <code>job</code>. Los paneles del tablero agregaban los tres servicios
en una sola serie sin filtrar, con lo cual una degradación en un servicio quedaba promediada con los
otros dos. Corregido antes de medir.</p>

<h2 class="new">3. Experimento 1 — NetworkChaos (200 ms ±10 ms sobre service-b)</h2>
<p>Chaos Mesh NetworkChaos, acción <code>delay</code>, <code>direction: to</code>,
<code>duration: 5m</code> con rollback automático por TTL. Carga: cuatro workers en paralelo contra
<code>GET /order/&#123;id&#125;</code> del NodePort de service-a (service-a → service-b → PostgreSQL),
90 s de línea base, 300 s de inyección y 240 s de observación posterior. Total 1 448 peticiones
medidas en el cliente y 1 496 trazas recogidas de Jaeger.</p>
<table>
<thead><tr><th>Fase</th><th class="num">n</th><th class="num">p50</th><th class="num">p95</th><th class="num">p99</th><th class="num">máx</th></tr></thead>
<tbody>
<tr><td>Línea base</td><td class="num">229</td><td class="num">40,1 ms</td><td class="num">76,2 ms</td><td class="num">156,6 ms</td><td class="num">195,4 ms</td></tr>
<tr><td>Chaos activo (0–300 s)</td><td class="num">600</td><td class="num">434,7 ms</td><td class="num">484,1 ms</td><td class="num">536,4 ms</td><td class="num">830,1 ms</td></tr>
<tr><td>Post-rollback</td><td class="num">619</td><td class="num">40,3 ms</td><td class="num">76,4 ms</td><td class="num">105,8 ms</td><td class="num">114,7 ms</td></tr>
</tbody></table>
<p>La latencia añadida en la mediana es de <b>394,7 ms sobre 200 ms inyectados</b>, es decir
<b>1,97×</b>. La cifra no es casual: <code>direction: to</code> aplica el retardo en ambos sentidos
del tráfico del pod, de modo que el round-trip paga el delay dos veces. El sistema no amortigua nada
—propaga la degradación al usuario final en proporción directa— pero tampoco la amplifica: cero
errores en las 1 448 peticiones, throughput constante y ningún reinicio de pod.</p>
<p><b>El rollback por TTL funcionó de forma limpia.</b> La latencia vuelve por debajo del doble de la
línea base en <b>t+301,0 s</b>, un segundo después del instante nominal y sin intervención manual, y
el post-rollback (40,3 ms) es indistinguible de la línea base (40,1 ms): el sistema regresa
exactamente a donde estaba. En el <code>describe</code> del CRD constan los dos
<code>Recover / Succeeded</code> a las 15:39:48 UTC, cinco minutos exactos después del
<code>Apply</code>. Este comportamiento es el punto de comparación que hace significativo lo que
ocurre en el Experimento 2.</p>
<div class="callout"><span class="lbl">Reproducibilidad</span>
<p>El experimento se ejecutó tres veces en sesiones separadas. La amplificación medida fue
<b>2,00× / 1,94× / 1,97×</b> y el desfase del rollback <b>+0,0 s / +0,3 s / +1,0 s</b>. Los datos
que se presentan aquí son los de la tercera corrida, la única en la que además se conservaron
íntegras las trazas de Jaeger (ver sección 8.2).</p></div>

<h3>3.1 Lo que muestra el tablero</h3>
<figure><img src="{IMG['e1graf']}" alt="Grafana durante el Experimento 1">
<figcaption><b>Figura 2.</b> Tablero de Grafana durante la ventana del experimento. El p95 y el p50 de
service-a se disparan a 490 y 350 ms; <b>el p50 y el p95 de service-b permanecen pegados al eje</b>.
El throughput no se altera.</figcaption></figure>
<div class="callout"><span class="lbl">Primera lección de observabilidad</span>
<p>La figura anterior es la debilidad D2 del Plan de Game Day convertida en imagen. Un operador
vigilando la salud de la dependencia habría visto a service-b respondiendo con normalidad durante los
cinco minutos en que el usuario final sufría una degradación de 10×. Detectar este modo de fallo
exige medir extremo a extremo, no por componente.</p></div>

<h3>3.2 El rollback visto por Jaeger</h3>
<figure><img src="{IMG['e1scatter']}" alt="Dispersión de trazas en Jaeger">
<figcaption><b>Figura 3.</b> Diagrama de dispersión de Jaeger: cada punto es una traza real. Dos
bandas separadas —una en torno a 430 ms y otra en torno a 40 ms— con un escalón vertical en el
instante del rollback. Ninguna línea de esta figura la dibujamos nosotros.</figcaption></figure>

<h3>3.3 Dónde vive la latencia: desglose por span</h3>
<p>Con las 1 496 trazas conservadas es posible hacer el desglose sobre la población completa en lugar
de sobre un par de ejemplos escogidos. La tabla siguiente compara la mediana de cada span entre las
600 trazas de la ventana de chaos y las 619 posteriores al rollback.</p>
<table>
<thead><tr><th>Span</th><th class="num">Sin chaos</th><th class="num">Con chaos</th><th class="num">Diferencia</th></tr></thead>
<tbody>
<tr><td><code>GET /order/&#123;order_id&#125;</code> — total percibido</td><td class="num">36,95 ms</td><td class="num">431,55 ms</td><td class="num a">+394,59 ms</td></tr>
<tr><td><code>call.service-b.inventory</code> — envoltura</td><td class="num">25,97 ms</td><td class="num">421,28 ms</td><td class="num a">+395,31 ms</td></tr>
<tr><td><code>GET</code> — cliente httpx hacia service-b</td><td class="num">3,75 ms</td><td class="num">399,51 ms</td><td class="num a">+395,76 ms</td></tr>
<tr><td><code>fetch.order.db</code> — consulta a Postgres</td><td class="num">9,93 ms</td><td class="num">10,24 ms</td><td class="num">+0,31 ms</td></tr>
<tr><td><code>SELECT</code></td><td class="num">2,07 ms</td><td class="num">2,13 ms</td><td class="num">+0,06 ms</td></tr>
<tr><td><code>GET /inventory/&#123;id&#125;</code> — <b>servidor de service-b</b></td><td class="num">0,59 ms</td><td class="num">0,64 ms</td><td class="num b">+0,05 ms</td></tr>
</tbody></table>
<figure><img src="{IMG['e1spans']}" alt="Desglose por span">
<figcaption><b>Figura 4.</b> Los mismos datos en escala logarítmica. Tres spans se desplazan 395 ms;
los otros tres no se mueven.</figcaption></figure>
<p>El span servidor de service-b vale <b>0,59 ms sin chaos y 0,64 ms con chaos</b>: una diferencia de
50 microsegundos, indistinguible del ruido de medición. La base de datos se mueve 310 microsegundos.
La totalidad de los 395 ms añadidos vive en el span cliente, es decir en el trayecto de red entre
service-a y service-b. El blast radius quedó contenido exactamente donde lo declaraba el manifiesto.</p>

<h3>3.4 Dos trazas individuales</h3>
<p>Las dos trazas siguientes ilustran el mismo fenómeno a nivel de petición. Son estructuralmente
idénticas —11 spans, profundidad 5, dos servicios— y difieren únicamente en la duración de un salto.</p>
<figure><img src="{IMG['e1tchaos']}" alt="Traza durante el chaos">
<figcaption><b>Figura 5.</b> Traza <code>4b59d1b</code>, capturada durante la inyección: 435,2 ms
totales, de los cuales 399,63 ms son el span cliente y <b>587 µs</b> el span servidor de
service-b.</figcaption></figure>
<figure><img src="{IMG['e1tnorm']}" alt="Traza después del rollback">
<figcaption><b>Figura 6.</b> Traza <code>518562c</code>, tras el rollback: 76,22 ms totales, 3,48 ms
en el span cliente y <b>618 µs</b> en el span servidor. El servidor tardó lo mismo en ambos
casos.</figcaption></figure>

<h2 class="new">4. Experimento 2 — HTTPChaos: error rate del 10 % en data-service</h2>
<p>El segundo experimento inyecta fallas de aplicación en lugar de latencia de red: un
<code>HTTPChaos</code> con <code>target: Response</code> y <code>abort: true</code> sobre
<code>data-service</code>. La diferencia conceptual con el laboratorio Docker original importa: allí
el error rate se simulaba con <code>if random.random() &lt; 0.1: raise HTTPException(500)</code>
<i>dentro del código</i>; aquí la aplicación no tiene ningún <code>random()</code> y la falla es
completamente externa a ella. Esa diferencia es la que produce el hallazgo principal.</p>

<h3>4.1 Correcciones al manifiesto del enunciado</h3>
<ul>
<li><b>Cuatro objetos de chaos en un solo archivo</b> (HTTPChaos + PodChaos + StressChaos + Schedule):
un <code>kubectl apply</code> los habría inyectado todos a la vez, haciendo imposible atribuir el
efecto observado a una causa. Se separó en <code>experiment-2-http-error.yaml</code> y
<code>experiment-2-alternativas.yaml</code>.</li>
<li><b><code>value: "100"</code> con <code>mode: fixed-percent</code></b>, es decir 100 % de error, no
el 10 % que anunciaban los comentarios del propio archivo.</li>
<li><b>La granularidad del 10 % es imposible con 2 réplicas.</b> HTTPChaos no tiene un campo de
probabilidad por petición: el porcentaje se aplica a la <i>selección de pods</i>, y el pod
seleccionado aborta el 100 % de las suyas. Con 2 réplicas el mínimo alcanzable es 50 %. Se escaló
<code>data-service</code> a 10 réplicas con <code>value: "10"</code> → 1 pod → ~10 % agregado.
Además <code>data-service-svc</code> pasó de <code>ClusterIP</code> a <code>NodePort</code>, porque
<code>kubectl port-forward</code> fija la conexión a un solo pod y habría sesgado la medición a 0 %
o 100 %.</li>
</ul>

<h3>4.2 Incidente de capacidad al escalar</h3>
<div class="callout crit"><span class="lbl">Incidente durante la preparación</span>
<p>Al escalar a 10 réplicas por primera vez, 5 pods se programaron en <code>kube-cp</code>, que ya
corría control-plane, Postgres, registry, Prometheus, Grafana y Jaeger sobre 3,8 GB de RAM. El nodo se
saturó: load average por encima de 100, apiserver OOM-killed y en crash-loop, <code>kubectl</code>
respondiendo con <i>TLS handshake timeout</i>. El diagnóstico hubo que hacerlo por <code>ssh</code> con
<code>crictl ps -a</code>, precisamente porque la API estaba caída.</p>
<p>Corrección: RAM de las 3 VMs aumentada (control-plane 4→8 GB, workers 2→4 GB) y
<code>nodeAffinity</code> con <code>node-role.kubernetes.io/control-plane DoesNotExist</code> en el
Deployment. En las corridas definitivas las 10 réplicas quedaron 5 en <code>kube-w1</code> y 5 en
<code>kube-w2</code>.</p>
<p><b>Lección:</b> el blast radius de un experimento no es solo el que declara el manifiesto de chaos.
Escalar el objetivo es parte del experimento, y sin una restricción de scheduling el daño alcanzó al
plano de control — el componente que uno necesita justamente para observar y revertir.</p></div>

<h3>4.3 Diseño de la corrida</h3>
<p>El Game Day se automatizó en <code>scripts/run-gameday.sh</code>, que encadena los tres
experimentos sin intervención: preflight (aborta si hay objetos de chaos vivos de corridas
anteriores), línea base de 90 s, inyección de 300 s, 240 s de observación posterior al rollback y
limpieza garantizada, con muestreo cada 15 s del estado del CRD y de los reinicios de cada pod, y
recolección de trazas de Jaeger y series de Prometheus al cierre. La carga son cuatro workers en
paralelo, en circuito abierto.</p>
<table>
<thead><tr><th>Corrida</th><th style="width:22%">Único parámetro que cambia</th><th>Qué pone a prueba</th></tr></thead>
<tbody>
<tr><td><b>A</b></td><td><code>path: "*"</code></td><td>El experimento tal como lo define el enunciado: el blast radius incluye <code>GET /health</code>, o sea la <code>livenessProbe</code>.</td></tr>
<tr><td><b>B</b></td><td><code>path: "/data/*"</code></td><td>La remediación propuesta: el health check queda fuera del blast radius. Todo lo demás es idéntico.</td></tr>
</tbody></table>

<h3>4.4 Resultados de la corrida A</h3>
<table>
<thead><tr><th>Fase</th><th class="num">n</th><th class="num">Errores</th><th class="num">p50 OK</th><th class="num">p95 OK</th></tr></thead>
<tbody>
<tr><td>Línea base</td><td class="num">232</td><td class="num">0 — 0,0 %</td><td class="num">17 ms</td><td class="num">34 ms</td></tr>
<tr><td>Chaos activo (0–300 s)</td><td class="num">544</td><td class="num">47 — 8,6 %</td><td class="num">16 ms</td><td class="num">26 ms</td></tr>
<tr><td>Post-rollback (300–540 s)</td><td class="num">476</td><td class="num">26 — 5,5 %</td><td class="num">16 ms</td><td class="num">29 ms</td></tr>
</tbody></table>
<p>El 8,6 % medido contra el 10 % nominal valida el diseño de la selección por pods. La fila inferior
es la que no debería existir: 240 s después del <code>duration</code> configurado el sistema seguía
fallando. La latencia de las peticiones exitosas no se degrada en ninguna fase —la falla es binaria,
así que un SLI de latencia tampoco la habría detectado— y las 73 peticiones fallidas se reparten en
dos poblaciones: 11 cortes instantáneos y 62 que se cuelgan alrededor de 9,3 s.</p>
<div class="callout"><span class="lbl">Reproducibilidad</span>
<p>El experimento se ejecutó dos veces con el mismo manifiesto, en sesiones distintas y sobre
pods distintos. La primera produjo 10,7 % de error, 6 reinicios del pod objetivo, 18 eventos de
recuperación fallida y un desfase de rollback de +234,8 s; la segunda —la que se documenta aquí—
reprodujo las cinco señales sin excepción. Que dos ejecuciones independientes den el mismo cuadro
cualitativo es lo que permite hablar de un hallazgo y no de una anomalía.</p></div>

<h2 class="new">5. Hallazgo 1 — la telemetría de la aplicación afirma éxito</h2>
<p>Durante la ventana del experimento, Jaeger registró <b>1 413 trazas de <code>data-service</code>,
todas con <code>http.status_code = 200</code></b> (2 477 spans etiquetados, cero 4xx y cero 5xx),
mientras el cliente medía 73 peticiones fallidas en ese mismo intervalo. El atributo
<code>error</code> no aparece <b>ni una sola vez</b> en los 2 477 spans.</p>
<figure><img src="{IMG['blind']}" alt="Error rate según cada fuente de telemetría">
<figcaption><b>Figura 7.</b> El mismo intervalo medido por dos fuentes de telemetría distintas, en las
dos corridas del Experimento 2. Los dos hallazgos de este documento son independientes: la remediación
que se verifica en la sección 7 cierra el del rollback y deja este exactamente igual.</figcaption></figure>

<h3>5.1 El mecanismo: el corte ocurre después del span</h3>
<p>La explicación no es que las peticiones no lleguen a la aplicación. El manifiesto usa
<code>target: Response</code>: Chaos Mesh intercepta el <b>camino de vuelta</b>. La petición entra
normalmente, la aplicación la procesa, consulta la base de datos, construye la respuesta, la marca
como 200 y cierra su span — y solo entonces el proxy aborta la conexión, de modo que esos bytes nunca
llegan al cliente.</p>
<p>La corrida de control B lo demuestra sin ambigüedad, porque allí las diez réplicas son estables y
no hay reinicios que confundan la medición: <b>las diez registran el mismo tráfico</b>, en una banda
estrecha en torno a 0,3 req/s, incluida la que tiene el chaos aplicado. El total que contabiliza la
aplicación —<b>2,8 req/s</b>— es incluso <i>superior</i> a las 2,4 req/s que el cliente recibe con
éxito, porque la aplicación también cuenta como atendidas las peticiones cuya respuesta se cortó en
el camino de vuelta.</p>
<figure><img src="{IMG['replicas']}" alt="Tráfico por réplica durante la corrida B">
<figcaption><b>Figura 8.</b> Panel del tablero durante la corrida B (11:37–11:42). La línea superior
es el total registrado por la aplicación; las diez de abajo, una por réplica. Una de ellas está
abortando el 100 % de sus respuestas y es indistinguible de las otras nueve. La caída de las 11:46 es
el reescalado a 2 réplicas al terminar la corrida.</figcaption></figure>
<div class="callout crit"><span class="lbl">Por qué esto es peor que un hueco de datos</span>
<p>Un tablero sin datos delata que algo pasa: el operador ve una serie que se corta y sospecha. Aquí
no hay hueco. La instrumentación produce telemetría completa, puntual y <b>equivocada</b>: 1 413
trazas que afirman que todo salió bien, para un intervalo en el que uno de cada doce usuarios no
recibió respuesta. El sistema de observabilidad no está callado; está dando una respuesta falsa con
plena confianza.</p>
<p>Ninguna cantidad de instrumentación <i>dentro</i> del proceso corrige esto, porque desde el punto
de vista del proceso la petición efectivamente tuvo éxito. La verdad solo existe donde está el
cliente.</p></div>

<h3>5.2 La remediación implementada: un SLI medido fuera del proceso</h3>
<p>Para esta corrida se desplegó un <b>blackbox exporter</b> que sondea cada 5 s tres endpoints:
<code>/data/products</code> y <code>/health</code> de data-service, y <code>/health</code> de
service-a como control fuera del blast radius. Es la única fuente del tablero capaz de ver la falla,
y de paso registra <i>cuál</i> endpoint falla, que resulta ser la clave del segundo hallazgo.</p>
<p>Como detalle operativo, el cliente ve <code>http_code = 000</code> —un corte de conexión, no un
código HTTP—, de modo que un SLI definido como «proporción de respuestas 5xx» tampoco contaría estos
fallos aunque se midiera desde fuera. La definición del indicador importa tanto como el punto donde
se mide.</p>

<h3>5.3 La misma ventana, según cada herramienta</h3>
<figure><img src="{IMG['agrafbli']}" alt="Blind spot en Grafana">
<figcaption><b>Figura 9.</b> A la izquierda, las diez réplicas de data-service procesando tráfico sin
que ninguna baje: la aplicación no percibe la falla. A la derecha, las dos fuentes midiendo el mismo
intervalo — la sonda de borde llega al 16 % de error mientras el APM permanece en 0 % de principio a
fin.</figcaption></figure>
<p>La consulta directa a Jaeger cierra el argumento. Buscando trazas de <code>data-service</code> en
el intervalo del experimento con el filtro <code>error=true</code>, la herramienta responde que no hay
resultados; retirando ese único filtro y dejando todo lo demás idéntico, devuelve el tope de la
consulta. No es que la búsqueda estuviera mal formulada ni que el intervalo fuera el equivocado: en
ese intervalo hay miles de trazas y ninguna registra un error.</p>
<figure><img src="{IMG['jvacio']}" alt="Búsqueda con error=true sin resultados"
style="width:62%; margin:0 auto;">
<figcaption><b>Figura 10.</b> <code>data-service</code> con el filtro <code>error=true</code> sobre la
ventana del experimento: «No trace results».</figcaption></figure>
<figure><img src="{IMG['j1500']}" alt="La misma búsqueda sin el filtro de error">
<figcaption><b>Figura 11.</b> La misma consulta sin el filtro: el intervalo está lleno de trazas, todas
en la banda normal de 15-20 ms. Entre ellas están las 73 peticiones que el cliente nunca recibió, y
nada en la telemetría permite distinguirlas.</figcaption></figure>

<h2 class="new">6. Hallazgo 2 — el rollback automático no ocurrió</h2>
<p>A diferencia del Experimento 1, donde el TTL revirtió la falla en el instante nominal, en la
corrida A el <code>duration: 5m</code> no detuvo nada: el último error se midió en <b>t+466,8 s</b>,
166,8 s más allá del fin nominal. La causa se reconstruyó cruzando el muestreo de pods con los eventos
del CRD, y el SLI de borde la hace visible de un vistazo: <b>en A también falla el health check</b>.</p>
<figure><img src="{IMG['mec']}" alt="Cadena causal del rollback fallido">
<figcaption><b>Figura 12.</b> Cadena causal del crash-loop y del rollback fallido.</figcaption></figure>
<p>El pod objetivo acumuló <b>cinco reinicios</b> durante el experimento; los otros nueve, ninguno.
El muestreo los sitúa en t+82, t+159, t+236, t+313 y t+405 segundos, es decir con intervalos de
<b>77 s constantes</b>. Esa cifra no es casual: es exactamente lo que predice la configuración de la
sonda —<code>livenessProbe: httpGet /health</code> con <code>periodSeconds: 20</code> y
<code>failureThreshold: 3</code>, o sea 60 s de fallos— más la terminación del contenedor y el
arranque del siguiente. El manifiesto declara <code>path: "*"</code>, así que la respuesta del health
check se aborta igual que la del tráfico de negocio y el kubelet concluye, correctamente desde su
punto de vista, que el contenedor está muerto.</p>
<p><b>Dos de esos cinco reinicios ocurrieron después del fin nominal</b>, en t+313 y t+405. El
experimento seguía matando el contenedor casi dos minutos después del instante en que debía haberse
revertido solo.</p>
<figure><img src="{IMG['agrafsli']}" alt="SLI de borde durante la corrida A">
<figcaption><b>Figura 13.</b> El SLI de borde durante la corrida A. Caen las sondas de
<code>/data/products</code> <b>y las de <code>/health</code></b>, mientras
<code>service-a /health</code>, fuera del blast radius, permanece en el 100 %. Cada caída de
<code>/health</code> es un fallo que el kubelet contabiliza para matar el contenedor: la causa del
crash-loop, medida desde fuera. Los picos de 3 s en el panel derecho son sondas agotando el timeout
del exporter.</figcaption></figure>
<p>Cada reinicio destruye el network namespace del contenedor y con él las reglas de iptables que
Chaos Mesh había inyectado. Cuando a los 300 s el controlador intenta revertir, el chaos-daemon ya no
encuentra el tproxy al que dirigirse: el <code>describe</code> registra <b>19 eventos
<code>Recover / Failed</code></b> con <code>apply config: send http request: unexpected EOF</code>,
todos a partir del instante exacto del fin nominal. El record quedó en
<code>phase: Injected/Wait</code> con <code>AllRecovered: False</code>.</p>
<div class="callout crit"><span class="lbl">Efecto secundario: el CRD no se deja borrar</span>
<p>El <code>finalizer</code> de Chaos Mesh espera a que el recovery termine antes de permitir el
borrado del objeto. Como el recovery nunca puede completar, <code>kubectl delete httpchaos</code>
queda colgado indefinidamente. Fue necesario forzarlo con
<code>kubectl patch ... -p '{{"metadata":{{"finalizers":[]}}}}'</code>. Quitar el finalizer borra el
objeto de Kubernetes pero <b>no</b> revierte las reglas inyectadas: lo que realmente las elimina es
destruir el pod, porque se van con su network namespace. La secuencia correcta de limpieza manual es
finalizer → borrar el pod objetivo → reescalar el Deployment, y así quedó implementada en el script
para que ninguna corrida futura deje el cluster sucio.</p></div>

<h2 class="new">7. Verificación experimental de la remediación</h2>
<p>La remediación evidente —sacar el health check del blast radius— se propuso en la versión anterior
de este documento sin comprobarla. La corrida de control B la pone a prueba veintitrés minutos después
de la corrida A, sobre el mismo cluster y con el mismo perfil de carga, cambiando un único campo del
manifiesto: <code>path: "/data/*"</code> en lugar de <code>path: "*"</code>. Todo lo demás
—<code>target: Response</code>, <code>abort: true</code>, <code>mode: fixed-percent</code> con
<code>value: 10</code>, <code>duration: 5m</code>, diez réplicas— queda intacto.</p>
<figure><img src="{IMG['err']}" alt="Error rate por minuto, corridas A y B">
<figcaption><b>Figura 14.</b> Requests abortadas por minuto en cada corrida. La inyección es igual de
efectiva en las dos —de hecho B aborta más—; lo que cambia es qué pasa al vencer el TTL.</figcaption></figure>
<figure><img src="{IMG['rst']}" alt="Reinicios del pod objetivo, corridas A y B">
<figcaption><b>Figura 15.</b> Reinicios acumulados del pod seleccionado, muestreados cada 15 s.
</figcaption></figure>
<table>
<thead><tr><th>Métrica</th><th class="num">A — <code>path: "*"</code></th><th class="num">B — <code>path: "/data/*"</code></th></tr></thead>
<tbody>
<tr><td>Error rate durante la inyección</td><td class="num">8,6 %</td><td class="num">11,8 %</td></tr>
<tr><td>Error rate después del TTL</td><td class="num a">5,5 %</td><td class="num b">0,0 %</td></tr>
<tr><td>Primer error (MTTD del cliente)</td><td class="num">t+9,9 s</td><td class="num">t+6,8 s</td></tr>
<tr><td>Último error observado</td><td class="num a">t+466,8 s</td><td class="num b">t+298,0 s</td></tr>
<tr><td>Desfase del rollback</td><td class="num a">+166,8 s</td><td class="num b">−2,0 s</td></tr>
<tr><td>Reinicios del pod objetivo</td><td class="num a">6</td><td class="num b">0</td></tr>
<tr><td>Eventos <code>Recover / Failed</code></td><td class="num a">19</td><td class="num b">0</td></tr>
<tr><td>Estado final del record</td><td class="num a"><code>Injected/Wait</code></td><td class="num b"><code>Not Injected</code></td></tr>
<tr><td>Condición <code>AllRecovered</code></td><td class="num a">False</td><td class="num b">True</td></tr>
<tr><td>¿Hubo que forzar el finalizer?</td><td class="num a">Sí</td><td class="num b">No</td></tr>
<tr><td>Espera del cliente antes del corte (p50)</td><td class="num a">9,34 s</td><td class="num b">20 ms</td></tr>
<tr><td>Caudal completado durante la ventana</td><td class="num a">1 020 requests</td><td class="num b">1 388 requests</td></tr>
</tbody></table>
<div class="callout good"><span class="lbl">Veredicto</span>
<p>La remediación funciona. Con el health check fuera del blast radius el pod no reinicia ni una sola
vez, Chaos Mesh conserva la referencia al contenedor, el recovery se ejecuta a la primera
(<code>Operation: Recover / Type: Succeeded</code>, <code>RecoveredCount: 1</code>) y el objeto se
borra sin tocar el finalizer. El <b>último error llegó 2,0 s antes del fin nominal</b> y en los 240 s
posteriores el cliente no midió un solo fallo. La inyección no perdió efectividad: 11,8 % de error
contra el 10 % nominal, por encima del 8,6 % de la corrida rota.</p></div>
<figure><img src="{IMG['bgrafsli']}" alt="SLI de borde durante la corrida B">
<figcaption><b>Figura 16.</b> El SLI de borde durante la corrida B, la imagen especular de la que abre
esta comparación. Solo cae <code>/data/products</code> (verde, hasta el 92 %); <code>/health</code> de data-service
—amarillo, oculto bajo el azul— y <code>service-a /health</code> permanecen en el 100 % de principio
a fin. Como el kubelet nunca contabiliza un fallo de liveness, el crash-loop no existe y el rollback
puede ejecutarse.</figcaption></figure>
<figure><img src="{IMG['sondas']}" alt="Sondas fallidas por endpoint, corridas A y B">
<figcaption><b>Figura 17.</b> Las mismas sondas en las dos corridas, sobre el muestreo cada 15 s que
guarda el script. En A fallan tanto el endpoint de negocio como el health check; en B, ninguno de los
tres. La sonda del borde tiene una probabilidad de ~1/10 de dar en la réplica inyectada, así que a
esta resolución detecta unas pocas de las 90 peticiones que sí falló el cliente: el muestreo del SLI
acota lo que se puede ver, y ese es un parámetro de diseño del indicador.</figcaption></figure>

<h3>7.1 El blind spot sobrevive a la remediación</h3>
<p>La corrida B también sirve de control para el primer hallazgo, y el resultado importa: arreglar el
rollback <b>no</b> arregla la ceguera del APM.</p>
<figure><img src="{IMG['bgrafbli']}" alt="Blind spot durante la corrida B">
<figcaption><b>Figura 18.</b> Panel «quién ve la falla» durante la corrida B. La sonda de borde marca
dos mesetas de 4,2 % de error; la serie del APM —proporción de spans 5xx— permanece pegada al 0 %
durante toda la ventana.</figcaption></figure>
<p>En la ventana de B, Jaeger registró <b>1 882 trazas de data-service con 3 381 spans, todos con
<code>http.status_code = 200</code></b>, mientras el cliente medía 90 peticiones fallidas. Cero
errores en la telemetría interna, igual que en A, pero esta vez sin crash-loop, sin reinicios y con el
pod sano de principio a fin. Eso descarta la explicación fácil —«los spans faltan porque el
contenedor se estaba muriendo»— y confirma el mecanismo de la sección 5.1: el corte ocurre después de
que la aplicación cerró su span, así que ninguna instrumentación dentro del proceso puede verlo.</p>

<h3>7.2 Dos beneficios adicionales que no se habían previsto</h3>
<p>La versión 2 de este addendum atribuía al abort un cuelgue de entre 8 y 11 segundos y lo explicaba
como el timeout de retransmisión de TCP. La comparación A/B muestra que esa lectura era incorrecta.</p>
<figure><img src="{IMG['abort']}" alt="Tiempo de espera del cliente antes del corte, A vs B">
<figcaption><b>Figura 19.</b> Tiempo que espera el cliente antes de recibir el corte, en escala
logarítmica.</figcaption></figure>
<p>En la corrida A el cliente espera una mediana de <b>9,34 s</b>; en la B, <b>20 ms</b>. El cuelgue no
lo produce el abort sino el crash-loop: mientras el kubelet está matando y recreando el contenedor,
las conexiones que el Service enruta hacia ese pod quedan colgadas hasta agotar el timeout. Con el pod
sano, el abort es un corte inmediato. La remediación no solo restaura el rollback: convierte un fallo
que bloquea al cliente nueve segundos en uno que corta en veinte milisegundos, <b>477× más rápido</b>.
Un cliente con reintento y timeout corto sobrevive al segundo caso y no al primero.</p>
<p>El segundo beneficio no aparece en ninguna tasa, y por eso conviene señalarlo: esos nueve segundos
de cuelgue <b>también se comen el caudal del sistema</b>.</p>
<figure><img src="{IMG['thr']}" alt="Throughput completado por minuto, A vs B">
<figcaption><b>Figura 20.</b> Requests que el cliente logra completar por segundo, con carga ofrecida
idéntica en las dos corridas.</figcaption></figure>
<div class="callout crit"><span class="lbl">Una trampa en la lectura del error rate</span>
<p>La tabla de arriba dice que A tuvo <b>menos</b> error rate que B —8,6 % contra 11,8 %— y esa lectura
es engañosa. Con la misma carga ofrecida, A completó 1 020 peticiones y B 1 388: el denominador de A
es un <b>27 % más chico</b> porque cada abort mantenía bloqueado uno de los cuatro workers durante
nueve segundos. La tasa de error de A baja porque el sistema <i>atiende menos</i>, no porque falle
menos. Un SLO definido solo sobre proporción de errores premia a la corrida rota; hace falta mirar
también el caudal, o el error rate deja de ser un indicador de salud.</p></div>

<h2>8. Debilidades sistémicas y remediaciones</h2>
<table>
<thead><tr><th style="width:4%">#</th><th style="width:30%">Acción</th><th>Implementación y estado</th></tr></thead>
<tbody>
<tr><td>1</td><td><b>Excluir el health check del blast radius</b></td>
<td><code>path: "/data/*"</code> en vez de <code>path: "*"</code>, o una <code>livenessProbe</code>
de tipo <code>exec</code>/<code>tcpSocket</code> que no atraviese el tproxy.
<b>Verificada experimentalmente</b> en la corrida B (sección 7).</td></tr>
<tr><td>2</td><td><b>SLI de disponibilidad medido fuera del proceso</b></td>
<td>blackbox exporter sondeando cada 5 s, con job propio en Prometheus y dos paneles en el tablero.
<b>Implementada y en uso</b>: es la única fuente que registró la falla.</td></tr>
<tr><td>3</td><td><b>Contar cortes de conexión como fallas</b></td>
<td>El 100 % de los errores llegan al cliente como <code>http_code = 000</code>, no como 5xx. El SLI
debe definirse sobre <code>probe_success</code>, no sobre proporción de 5xx. Pendiente de formalizar
en el SLO.</td></tr>
<tr><td>4</td><td><b>Restricción de scheduling para todo objetivo de chaos</b></td>
<td><code>nodeAffinity</code> excluyendo el control-plane en el Deployment de data-service.
<b>Aplicada</b> tras el incidente de la sección 4.2.</td></tr>
<tr><td>5</td><td><b>Runbook de limpieza y preflight</b></td>
<td>Secuencia finalizer → pod → réplicas, y verificación de que no quedan objetos de chaos vivos antes
de la siguiente corrida. <b>Implementada</b> en <code>run-exp2.sh</code> y
<code>run-gameday.sh</code>.</td></tr>
<tr><td>6</td><td><b>Corregir las queries del tablero</b></td>
<td>Prefijo <code>otelcol_</code> y desglose por <code>exported_job</code>: sin él, una degradación de
un servicio queda promediada con la de los otros dos. <b>Aplicada</b>.</td></tr>
<tr><td>7</td><td><b>Presupuesto de tiempo por salto en el cliente</b></td>
<td>Timeouts de conexión y lectura por dependencia, más reintento acotado. El Experimento 1 muestra
propagación 1:1 sin amortiguación alguna. Pendiente.</td></tr>
</tbody></table>

<h2>9. Conclusiones</h2>
<p>La reproducción sobre infraestructura real confirma la hipótesis de estado estable y, en el
Experimento 1, muestra degradación proporcional a la falla inyectada con recuperación automática en el
instante nominal: los tres pilares de un Game Day —hipótesis, blast radius acotado, rollback
automático— con evidencia real de Prometheus, Grafana y Jaeger.</p>
<p>El Experimento 2 es más valioso precisamente porque <i>no</i> se comportó como el diseño prometía, y
sus dos hallazgos solo aparecen al ejecutar sobre un cluster real:</p>
<ul>
<li><b>La telemetría de la aplicación no se quedó sin datos: registró datos falsos.</b> 1 413 trazas
afirmando 200 OK para un intervalo con 73 peticiones fallidas, y otras 1 882 igual de limpias en la
corrida de control, donde el pod estuvo sano todo el tiempo. Como el corte ocurre en el camino de
vuelta, después de que la aplicación cerró su span, ninguna instrumentación interna al proceso puede
detectarlo. La verificación de disponibilidad tiene que vivir donde vive el cliente.</li>
<li><b>El rollback automático falló, y la causa raíz estaba en el propio experimento:</b> el chaos
alcanzaba al health check, provocando un crash-loop que destruía las reglas que Chaos Mesh necesitaba
para revertirse. La garantía de seguridad de un Game Day —«duración acotada, rollback automático»— es
condicional, y una de sus condiciones es que el objetivo siga vivo.</li>
</ul>
<div style="page-break-inside:avoid">
<p>La corrida de control cierra el ciclo completo: hipótesis, experimento, hallazgo, remediación y
<b>verificación de la remediación</b>. Cambiar un único campo del manifiesto llevó el desfase del
rollback de +166,8 s a −2,0 s, los reinicios de 6 a 0 y los eventos de recuperación fallida de 19 a 0,
sin perder efectividad en la inyección —al contrario, la corrida remediada abortó una proporción
mayor de peticiones—. La misma corrida de control demuestra que el otro hallazgo <i>no</i> se
resuelve con ese cambio: el APM sigue informando 200 para peticiones que nadie recibió. Ese paso final —comprobar que el arreglo arregla— es lo que
separa un informe de incidente de un ejercicio de anti-fragilidad, y es también la razón por la que un
Game Day merece automatizarse: la corrida completa que produjo toda esta evidencia son 40 minutos
desatendidos y un comando.</p>
<p class="foot">Evidencia: <code>results/gameday-final/</code> — tres corridas del 2026-08-30
(<code>exp1-103316</code>, <code>exp2-A-111232</code>, <code>exp2-B-113517</code>), 4 320 peticiones
medidas en el cliente, muestreo de pods, de Prometheus y del CRD cada 15 s, eventos del
<code>describe</code>, sondas del blackbox exporter cada 5 s y trazas de Jaeger de cada ventana.
Corridas reproducibles con <code>scripts/run-exp1.sh</code>, <code>scripts/run-exp2.sh</code> y
<code>scripts/run-gameday.sh</code>.</p>
</div>
"""

HTML = ('<!doctype html>\n<html lang="es"><head><meta charset="utf-8">\n'
        '<title>Addendum v6 — Game Day en cluster kubeadm real</title>\n'
        f'<style>{CSS}</style></head><body>\n{BODY}\n</body></html>')

open("/home/claude/addendum_v6.html", "w").write(HTML)
print("html listo:", len(HTML), "bytes")
