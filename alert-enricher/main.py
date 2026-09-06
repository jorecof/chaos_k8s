"""alert-enricher — recibe webhooks de Alertmanager y los enriquece con
trace_id antes de "notificarlos" (aqui: log estructurado + metrica).

Cierra G-11 (no habia Alertmanager ni enriquecimiento en el cluster).
Ver claude/U3-Diseno-Laboratorio-Integrador.md §B.3.
"""
import json
import logging
import os
import urllib.parse
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from pythonjsonlogger import jsonlogger
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST

LOKI_URL = os.getenv("LOKI_URL", "http://loki-svc:3100")
JAEGER_QUERY_URL = os.getenv("JAEGER_QUERY_URL", "http://jaeger-svc:16686")
JAEGER_EXTERNAL_URL = os.getenv("JAEGER_EXTERNAL_URL", "http://localhost:16686")
GRAFANA_EXTERNAL_URL = os.getenv("GRAFANA_EXTERNAL_URL", "http://localhost:3000")
WINDOW = timedelta(minutes=2)

handler = logging.StreamHandler()
handler.setFormatter(jsonlogger.JsonFormatter("%(asctime)s %(levelname)s %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[handler])
logger = logging.getLogger("alert-enricher")

alert_enriched_total = Counter(
    "alert_enriched_total", "Alertas de Alertmanager procesadas", ["alertname", "enriched"]
)

app = FastAPI(title="alert-enricher")


async def find_trace_id(client: httpx.AsyncClient, exported_job: str, starts_at: datetime) -> str | None:
    """Busca un trace_id en Loki para el servicio y ventana de la alerta."""
    start_ns = int((starts_at - WINDOW).timestamp() * 1e9)
    end_ns = int((starts_at + WINDOW).timestamp() * 1e9)
    try:
        r = await client.get(
            f"{LOKI_URL}/loki/api/v1/query_range",
            params={
                "query": f'{{job="{exported_job}"}} |= "ERROR"',
                "start": start_ns,
                "end": end_ns,
                "limit": 20,
                "direction": "backward",
            },
            timeout=3.0,
        )
        r.raise_for_status()
        for stream in r.json().get("data", {}).get("result", []):
            for _, line in stream.get("values", []):
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                trace_id = payload.get("traceid") or payload.get("trace_id")
                if trace_id:
                    return trace_id
    except httpx.HTTPError as exc:
        logger.warning("loki_query_failed", extra={"error": str(exc)})
    return None


async def find_trace_id_jaeger(client: httpx.AsyncClient, exported_job: str, starts_at: datetime) -> str | None:
    """Fallback: busca trazas con error directo en la API de Jaeger."""
    start_us = int((starts_at - WINDOW).timestamp() * 1e6)
    end_us = int((starts_at + WINDOW).timestamp() * 1e6)
    try:
        r = await client.get(
            f"{JAEGER_QUERY_URL}/api/traces",
            params={
                "service": exported_job,
                "tags": json.dumps({"error": "true"}),
                "start": start_us,
                "end": end_us,
                "limit": 5,
            },
            timeout=3.0,
        )
        r.raise_for_status()
        traces = r.json().get("data", [])
        if traces:
            return traces[0].get("traceID")
    except httpx.HTTPError as exc:
        logger.warning("jaeger_query_failed", extra={"error": str(exc)})
    return None


def grafana_explore_link(exported_job: str, trace_id: str) -> str:
    left = json.dumps(
        {
            "datasource": "loki",
            "queries": [{"expr": f'{{job="{exported_job}"}} | json | traceid="{trace_id}"', "refId": "A"}],
            "range": {"from": "now-1h", "to": "now"},
        }
    )
    return f"{GRAFANA_EXTERNAL_URL}/explore?orgId=1&left={urllib.parse.quote(left)}"


async def enrich_one(client: httpx.AsyncClient, alert: dict) -> dict:
    labels = alert.get("labels", {})
    alertname = labels.get("alertname", "unknown")
    exported_job = labels.get("exported_job", "unknown")
    starts_at = datetime.fromisoformat(alert["startsAt"].replace("Z", "+00:00"))

    trace_id = await find_trace_id(client, exported_job, starts_at)
    if not trace_id:
        trace_id = await find_trace_id_jaeger(client, exported_job, starts_at)

    enriched = trace_id is not None
    result = {
        "t_notify": datetime.now(timezone.utc).isoformat(),
        "alertname": alertname,
        "exported_job": exported_job,
        "status": alert.get("status"),
        "starts_at": alert["startsAt"],
        "playbook": labels.get("playbook", "n/a"),
        "trace_id": trace_id,
        "enriched": enriched,
    }
    if enriched:
        result["jaeger_url"] = f"{JAEGER_EXTERNAL_URL}/trace/{trace_id}"
        result["grafana_logs_url"] = grafana_explore_link(exported_job, trace_id)
        result["runbook"] = "arranque por el pivote trace_id: jaeger_url -> span mas lento -> grafana_logs_url"
    else:
        result["runbook"] = "sin trace_id disponible -- alerta NO accionable por trazas (ver hallazgo D2-mesh)"

    alert_enriched_total.labels(alertname=alertname, enriched=str(enriched).lower()).inc()
    logger.info("alert_enriched", extra={"alert": result})
    return result


@app.post("/webhook")
async def webhook(request: Request):
    payload = await request.json()
    alerts = payload.get("alerts", [])
    async with httpx.AsyncClient() as client:
        results = [await enrich_one(client, a) for a in alerts]
    return {"processed": len(results), "alerts": results}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/metrics")
async def metrics():
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)
