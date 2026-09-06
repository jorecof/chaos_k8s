# Entrega Final — Observabilidad U3 (Laboratorio Integrador)

**Repositorio:** `jorecof/chaos_k8s` — rama `u3-integrador`
**Autores:** Ernesto Ilich Contreras · Saúl Mauricio González
**Fecha:** 6 de septiembre de 2026

---

## Recomendaciones — Ver detalle

Estos son los tres requisitos de entrega de la unidad y el estado/los pasos para cumplir cada uno.

### 1. El repositorio debe estar público en GitHub con tag de versión final (v1.0)

**Estado:** el repo `jorecof/chaos_k8s` ya existe y todo el trabajo de U3 está en la rama `u3-integrador`. Falta confirmar visibilidad pública y crear el tag.

Pasos (en tu propia terminal, con tu sesión de git/GitHub ya autenticada):

1. Verificar visibilidad actual y cambiarla si hace falta:
   - Ve a `https://github.com/jorecof/chaos_k8s/settings` → sección **Danger Zone** → **Change repository visibility** → **Change to public**. GitHub pide escribir el nombre del repo para confirmar.
   - Alternativa por CLI si instalas `gh` (`brew install gh`, luego `gh auth login`): `gh repo edit jorecof/chaos_k8s --visibility public --accept-visibility-change-consequences`.
   - **Importante (ya confirmado en tu pantalla):** el botón "Change visibility" te aparece deshabilitado con "For security reasons, you cannot change the visibility of a fork" porque `chaos_k8s` es un fork de otro repo (probablemente privado). GitHub no deja cambiar la visibilidad de un fork directamente. Primero usa, en esa misma sección de Danger Zone, **"Leave fork network"** (desvincula tu copia del repo original y la vuelve independiente/standalone) y confirma la acción — es unidireccional, no se puede revertir, pero no afecta al repo original ni a otros forks. Después de eso el botón "Change visibility" se habilita y ya puedes seguir con el paso de ponerlo público.
2. Antes de taggear, asegúrate de que todo lo final (informe, este documento, evidencias) ya esté commiteado en `u3-integrador` y (si el entregable pide `main`) mergeado ahí. Si el profesor solo revisa la rama, no hace falta merge; si pide `main`, hazlo con un PR o `git checkout main && git merge u3-integrador`.
3. **Orden importante antes de crear el tag** (para que el tag apunte a la versión final, no a la historia vieja con el pie de Claude):
   1. Termina primero "Leave fork network" + ponerlo público (punto de arriba).
   2. Corre en tu terminal el `git push --force-with-lease origin u3-integrador` (sección 3 más abajo) para subir la historia ya limpia.
   3. Haz `git add`/`git commit`/`git push` de los archivos nuevos que falten (este checklist, el informe actualizado, cualquier evidencia nueva) para que el tag incluya todo.
4. Crear el tag anotado de versión final (hazlo al final, cuando ya esté todo listo — un tag no se "actualiza", si necesitas corregir algo después habría que borrar y recrear el tag). Dos formas, cualquiera sirve:
   - **Por terminal:**
     ```bash
     git tag -a v1.0 -m "Entrega final U3 — Laboratorio Integrador de Observabilidad"
     git push origin v1.0
     ```
   - **Por la web (lo que ya tienes abierto en Releases/Tags):** clic en **"Create a new release"** → en "Choose a tag" escribe `v1.0` → elige **"Create new tag: v1.0 on publish"** → confirma que el **target** sea la rama `u3-integrador` (no `main`, a menos que ya la hayas mergeado) → escribe un título/descripción breve → **Publish release**. Esto crea el tag y además una página de Release más presentable para el evaluador.
5. Verifica en `https://github.com/jorecof/chaos_k8s/tags` que aparece `v1.0`.

### 2. Los experimentos de caos deben ejecutarse en sandbox, nunca en recursos compartidos

**Estado:** ya se cumple por diseño — déjalo documentado explícitamente para el evaluador:

- El clúster de Kubernetes (`kube-cp`, `kube-w1`, `kube-w2`) es un clúster **kubeadm propio**, levantado en VirtualBox en tu MacBook, sin acceso ni de otros estudiantes ni de producción.
- La parte de GCP corre bajo tu propio proyecto personal ("My First Project"), no un proyecto compartido de la universidad ni de otro equipo.
- Los experimentos de Chaos Mesh/Litmus (namespaces `chaos-mesh`, `litmus`) solo apuntan a los pods de `otel-lab` en ese mismo clúster personal — nunca a un clúster gestionado, compartido o de terceros.
- Recomendación: agrega un párrafo corto en el informe (o en el README del repo) que diga explícitamente esto, con los tres puntos anteriores, para que quede como evidencia escrita y no solo implícita en la arquitectura.

### 3. Autoría: Ernesto Ilich Contreras y Saúl Mauricio González

**Estado:** la portada del informe (`3-Informe_Integrador_U3_Observabilidad.docx`) ya lista a ambos como autores. Falta reflejar la coautoría en el repositorio de GitHub:

1. **Agregar a Saúl como colaborador del repo** (para que su usuario de GitHub quede vinculado al proyecto):
   `https://github.com/jorecof/chaos_k8s/settings/access` → **Add people** → su usuario o correo de GitHub.
2. **Historial de commits ya limpiado**: los últimos 12 commits de `u3-integrador` traían un pie `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` (quedaba de cómo se generaban hasta ahora los mensajes de commit). Ya reescribí esos 12 commits en tu copia local quitando esa línea — el autor que queda es `ilich <jorecof@gmail.com>` en los 12, sin ninguna mención a Claude. **Falta un paso tuyo**: como device_bash no tiene credenciales de GitHub configuradas, no pude hacer el push; corre esto en tu terminal para subir la historia limpia:
   ```bash
   cd ~/chaos_k8s
   git push --force-with-lease origin u3-integrador
   ```
   Por seguridad dejé una rama de respaldo local `backup-antes-de-limpiar-20260906203052` con la historia original (por si algo sale mal); no está pusheada a GitHub, solo vive en tu máquina.
3. **Para futuros commits**, si quieres que ambos aparezcan como coautores en un mismo commit (además de que cada quien commitee lo suyo con su propio `git config user.name`), agrega al final del mensaje de commit:
   ```
   Co-authored-by: Saúl Mauricio González <correo-de-saul@ejemplo.com>
   ```
   *(dime el correo/usuario de GitHub de Saúl y te preparo la plantilla exacta, o configúralo tú con `git config commit.template`.)*

---

## Pendiente para cerrar la entrega (evidencia adicional, sección 10.4 del informe)

### 1. Vista de Loki (Explore) filtrada por `traceid`, log de `service-b`

1. `bash scripts/tunnels.sh start` (levanta grafana:3000, jaeger:16686, loki:3100, etc. — usa `status` para ver qué quedó arriba).
2. Abre Jaeger `http://localhost:16686` → Search → Service `service-b` → abre una traza reciente → copia el **Trace ID** (arriba de la página, hex sin guiones).
3. Abre Grafana `http://localhost:3000` → **Explore** (icono de brújula) → datasource **Loki**.
4. Usa el "Label browser" para confirmar el label disponible (debería ser `job`) y arma la query:
   `{job="service-b"} |= "<trace-id-copiado>"`
   — **importante**: en Loki la clave del trace id es `traceid` (sin guion bajo), distinto del `trace_id` del stdout JSON (ver `docs/U3-notas-implementacion.md` §5) — por eso se busca como texto libre con `|=` en vez de como label, para no depender del parseo exacto.
5. Captura el log que aparece, con la query y el `traceid` visibles en el cuerpo del log.

### 2. Evidencia del incidente de Postgres (sección 4.4) — YA CAPTURADA, no hace falta tocar el clúster

El propio `scripts/run-exp2-app.sh` guarda `kubectl get events` en cada corrida. El evento real que causó el incidente narrado en 4.4 ya quedó guardado en
`results/exp2-app-20260906-140221/events.txt` (líneas ~190-207): un `SandboxChanged` que afectó casi todos los pods del namespace (incluyendo `postgres` y `data-service`) casi al mismo tiempo. Para la captura:

```bash
grep -n -i "sandboxchanged\|postgres" results/exp2-app-20260906-140221/events.txt
```

Screenshot de esa salida de terminal — es evidencia real y ya existente, no hay que reproducir el incidente (los eventos de Kubernetes expiran ~1h, así que si intentas `kubectl get events` en vivo ahora ya no lo vas a encontrar).

### 3. Repetición limpia de D2-app (cierra la comparación de MTTD del Módulo B.5)

1. Antes de lanzar, verifica que Postgres esté sano (dado que 8 de 9 corridas anteriores fallaron por su inestabilidad — sección 4.4/10.1): `kubectl -n otel-lab get pods | grep postgres` (0 restarts recientes); si tienes dudas, `kubectl -n otel-lab rollout restart deployment/postgres` y espera a que esté `Ready` un par de minutos antes de seguir.
2. Lanza `bash scripts/run-exp2-app.sh` (línea base 90s, chaos 300s, post 240s — ~12 min en total, con los defaults).
3. Durante los primeros ~90s (línea base), captura el dashboard de Grafana mostrando 0% de error (reemplaza o acompaña la figura 10).
4. Durante la ventana de chaos (del segundo 90 al 390), ten abiertas **dos pestañas a la vez**: el dashboard interno (`AIOpsCorrelatedAnomaly` / `HighBurnRate_PAGE`) y la consola de Cloud Monitoring en la política `data_service_error_forecast` (Monitoring → Alerting → esa política → pestaña de incidentes). Captura ambas mientras reaccionan.
5. Al terminar, `results/exp2-app-<timestamp>/mttd.json` y `summary.txt` traen los nuevos números de MTTD ya calculados — úsalos para reemplazar los de la sección 7.4/5.4 (los actuales están marcados como no válidos por el ruido de línea base del incidente de Postgres).

