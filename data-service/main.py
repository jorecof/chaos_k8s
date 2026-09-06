"""
data-service: FastAPI — Tercer microservicio del laboratorio integrador
Accede a GCP Cloud SQL (PostgreSQL) y AWS RDS según el cloud provider.
Instrumentado con OTel SDK completo siguiendo OTel DB Semantic Conventions.
"""

import logging
import os
import time
import random
import json
import psycopg2
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pythonjsonlogger import jsonlogger

# ── OTel SDK ──────────────────────────────────────────────────────
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry._logs import set_logger_provider
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor

# ── Config ─────────────────────────────────────────────────────────
OTEL_ENDPOINT   = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
CLOUD_PROVIDER  = os.getenv("CLOUD_PROVIDER", "gcp")
APP_VERSION     = os.getenv("APP_VERSION", "1.0.0")
ENV             = os.getenv("ENVIRONMENT", "production")

# ── Selección de backend de base de datos (módulo A.4, U3) ──────────
# Tres backends en paralelo, elegibles por request con ?backend=. El local
# sigue viniendo de DATABASE_URL tal como estaba; Cloud SQL se arma en partes
# porque llega por el sidecar cloud-sql-proxy en 127.0.0.1, no por una URL
# completa inyectada (ver base/02-deployments.yaml).
DEFAULT_BACKEND = "local"

DB_DSN_LOCAL = os.getenv("DATABASE_URL", "postgresql://app:secret@postgres:5432/appdb")

DB_HOST_GCP     = os.getenv("DB_HOST_GCP", "127.0.0.1")
DB_PORT_GCP     = os.getenv("DB_PORT_GCP", "5432")
DB_NAME_GCP     = os.getenv("GCP_SQL_DB_NAME", "appdb")
DB_USER_GCP     = os.getenv("GCP_SQL_DB_USER", "app")
DB_PASSWORD_GCP = os.getenv("DB_PASSWORD_GCP", "")

# ── OTel Resource ──────────────────────────────────────────────────
# db.system.name/db.namespace ya no van aquí: cambian por request según el
# backend elegido, así que se declaran por span (ver /data/products).
resource = Resource.create({
    SERVICE_NAME:    "data-service",
    SERVICE_VERSION: APP_VERSION,
    "deployment.environment": ENV,
    "cloud.provider": CLOUD_PROVIDER,
})

# ── TracerProvider ─────────────────────────────────────────────────
tracer_provider = TracerProvider(resource=resource)
tracer_provider.add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint=OTEL_ENDPOINT, insecure=True))
)
trace.set_tracer_provider(tracer_provider)
tracer = trace.get_tracer("data-service", APP_VERSION)

# ── MeterProvider ──────────────────────────────────────────────────
meter_provider = MeterProvider(
    resource=resource,
    metric_readers=[
        PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=OTEL_ENDPOINT, insecure=True),
            export_interval_millis=15000,
        )
    ],
)
metrics.set_meter_provider(meter_provider)
meter = metrics.get_meter("data-service", APP_VERSION)

# ── Instrumentos de métricas ───────────────────────────────────────
db_query_duration = meter.create_histogram(
    "db_query_duration_seconds",
    description="Latencia de queries a Cloud SQL / RDS",
    unit="s",
)
db_connections_active = meter.create_up_down_counter(
    "db_connections_active",
    description="Conexiones activas a la base de datos",
    unit="1",
)
db_errors_total = meter.create_counter(
    "db_errors_total",
    description="Total errores de base de datos",
    unit="1",
)
# SLI: disponibilidad del servicio de datos
data_requests_total = meter.create_counter(
    "data_requests_total",
    description="Total requests al data-service",
    unit="1",
)

# ── Logging estructurado ───────────────────────────────────────────
# ── LoggerProvider + OTLP exporter (tercer pilar: logs, G-05) ────────────────
# Mismo Resource y mismo endpoint OTLP que trazas/métricas — el Collector ya
# tenía el pipeline `logs` armado (receiver otlp), solo faltaba quién emitiera.
logger_provider = LoggerProvider(resource=resource)
otlp_log_exporter = OTLPLogExporter(endpoint=OTEL_ENDPOINT, insecure=True)
logger_provider.add_log_record_processor(BatchLogRecordProcessor(otlp_log_exporter))
set_logger_provider(logger_provider)

class OtelJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        span = trace.get_current_span()
        ctx  = span.get_span_context()
        if ctx and ctx.is_valid:
            log_record["trace_id"] = format(ctx.trace_id, "032x")
            log_record["span_id"]  = format(ctx.span_id, "016x")
        log_record["service"]       = "data-service"
        log_record["cloud_provider"] = CLOUD_PROVIDER

handler = logging.StreamHandler()
handler.setFormatter(OtelJsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
# LoggingHandler reenvía cada log record (via el root logger) al LoggerProvider
# OTel -> mismo trace_id/span_id ya quedan en el registro por el Formatter de
# arriba, y OTel los promueve a atributos reales del LogRecord OTLP.
otel_log_handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
logging.basicConfig(level=logging.INFO, handlers=[handler, otel_log_handler])
logger = logging.getLogger("data-service")

# ── Auto-instrumentación ───────────────────────────────────────────
Psycopg2Instrumentor().instrument(tracer_provider=tracer_provider)

# ── DB helpers ─────────────────────────────────────────────────────
def _dsn_for_backend(backend: str) -> tuple[str, str]:
    """Devuelve (dsn, server_address) para el backend pedido."""
    if backend == "local":
        server_address = DB_DSN_LOCAL.split("@")[-1].split("/")[0].split(":")[0]
        return DB_DSN_LOCAL, server_address
    if backend == "cloud-sql":
        if not DB_PASSWORD_GCP:
            raise HTTPException(
                status_code=503,
                detail="Cloud SQL no configurado: falta DB_PASSWORD_GCP (Secret data-service-gcp-sql)",
            )
        dsn = f"postgresql://{DB_USER_GCP}:{DB_PASSWORD_GCP}@{DB_HOST_GCP}:{DB_PORT_GCP}/{DB_NAME_GCP}"
        return dsn, DB_HOST_GCP
    if backend == "rds":
        raise HTTPException(status_code=501, detail="Backend rds pendiente de esta sesión (solo GCP por ahora)")
    raise HTTPException(status_code=400, detail=f"backend desconocido: {backend!r}")


def get_connection(dsn: str):
    """Conecta con presupuesto de tiempo — remediación #1 de U2 (D-01 del
    diseño de U3) aplicada también al salto hacia la base de datos: sin esto,
    un backend WAN degradado cuelga el threadpool en vez de fallar rápido."""
    return psycopg2.connect(dsn, connect_timeout=2, options="-c statement_timeout=2000")

# ── Chaos flags (Módulo D) ─────────────────────────────────────────
CHAOS_LATENCY_MS  = int(os.getenv("CHAOS_LATENCY_MS", "0"))    # inyectar latencia
CHAOS_ERROR_RATE  = float(os.getenv("CHAOS_ERROR_RATE", "0"))  # 0.0-1.0

def apply_chaos():
    """Aplica los experimentos de caos si están configurados."""
    if CHAOS_LATENCY_MS > 0:
        time.sleep(CHAOS_LATENCY_MS / 1000)
        logger.warning("Chaos: latencia inyectada", extra={"latency_ms": CHAOS_LATENCY_MS})

    if CHAOS_ERROR_RATE > 0 and random.random() < CHAOS_ERROR_RATE:
        logger.error("Chaos: error inyectado", extra={"error_rate": CHAOS_ERROR_RATE})
        raise HTTPException(status_code=500, detail="Chaos: error inyectado deliberadamente")

# ── App ────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("data-service iniciando", extra={
        "cloud_provider": CLOUD_PROVIDER,
        "db_dsn_host": DB_DSN_LOCAL.split("@")[-1].split("/")[0],
    })
    yield
    tracer_provider.shutdown()
    meter_provider.shutdown()
    logger_provider.shutdown()

app = FastAPI(
    title="Data Service",
    description="Tercer microservicio — acceso a Cloud SQL / RDS con OTel DB Semantic Conventions",
    version=APP_VERSION,
    lifespan=lifespan,
)

# FastAPIInstrumentor.instrument_app(app) — en versiones >=0.48b0 el patch
# global FastAPIInstrumentor().instrument() ya no engancha instancias nuevas de
# FastAPI; hay que instrumentar la instancia explicitamente para que la
# extraccion del header traceparent entrante funcione.
FastAPIInstrumentor.instrument_app(app, tracer_provider=tracer_provider)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "data-service", "cloud": CLOUD_PROVIDER}


@app.get("/data/products")
async def get_products(category: str = "all", backend: str = DEFAULT_BACKEND):
    """
    Consulta catálogo de productos. Backend seleccionable con
    ?backend=local|cloud-sql|rds (módulo A.4). Implementa OTel DB Semantic
    Conventions estables: db.system.name, db.namespace, db.operation.name,
    db.collection.name, db.query.text, server.address.
    """
    dsn, server_address = _dsn_for_backend(backend)

    start = time.time()
    db_connections_active.add(1)

    with tracer.start_as_current_span(
        "SELECT products",
        kind=trace.SpanKind.CLIENT,
        attributes={
            # ── OTel DB Semantic Conventions (estables) ──────────
            "db.system.name":      "postgresql",
            "db.namespace":        DB_NAME_GCP if backend == "cloud-sql" else "appdb",
            "db.operation.name":   "SELECT",
            "db.collection.name":  "products",
            "server.address":      server_address,
            "db.provider":         backend,
            # Atributos de negocio
            "cloud.provider":      CLOUD_PROVIDER,
            "query.category":      category,
        }
    ) as span:
        try:
            # Chaos dentro del span (módulo D, D-08): el error inyectado debe
            # quedar como StatusCode.ERROR con trace_id resoluble (D2-app);
            # si se dispara antes de abrir el span no hay traza que pivotar.
            apply_chaos()

            conn = get_connection(dsn)
            cur  = conn.cursor()

            query = "SELECT id, name, category, price, stock FROM products"
            params = []
            if category != "all":
                query += " WHERE category = %s"
                params.append(category)
            query += " LIMIT 50"

            # Query parametrizada, sin valores — evita fuga de datos en el span
            span.set_attribute("db.query.text", query)

            cur.execute(query, params)
            rows = cur.fetchall()
            conn.close()

            duration = time.time() - start
            db_query_duration.record(duration, {
                "db.system.name":     "postgresql",
                "db.operation.name":  "SELECT",
                "db.collection.name": "products",
                "server.address":     server_address,
                "db.provider":        backend,
            })

            span.set_attribute("db.response.returned_rows", len(rows))
            span.set_attribute("db.query_duration_ms", round(duration * 1000, 2))
            span.set_status(trace.StatusCode.OK)

            # G-09: outcome real, recién conocido acá — antes se incrementaba
            # sin distinguir éxito/error y no se podía derivar error rate.
            data_requests_total.add(1, {
                "endpoint": "/data/products",
                "db.provider": backend,
                "outcome": "success",
                "http.response.status_code": 200,
            })

            logger.info("Products query completada", extra={
                "rows":     len(rows),
                "category": category,
                "duration": round(duration, 4),
                "backend":  backend,
            })

            return {
                "products":       [{"id": r[0], "name": r[1], "category": r[2],
                                     "price": float(r[3]), "stock": r[4]} for r in rows],
                "count":          len(rows),
                "db_provider":    backend,
                "server_address": server_address,
                "trace_id":       format(trace.get_current_span().get_span_context().trace_id, "032x"),
            }

        except HTTPException as e:
            span.set_status(trace.StatusCode.ERROR, str(e.detail))
            data_requests_total.add(1, {
                "endpoint": "/data/products",
                "db.provider": backend,
                "outcome": "error",
                "http.response.status_code": e.status_code,
            })
            raise
        except Exception as e:
            db_errors_total.add(1, {"operation": "SELECT", "db.provider": backend})
            data_requests_total.add(1, {
                "endpoint": "/data/products",
                "db.provider": backend,
                "outcome": "error",
                "http.response.status_code": 500,
            })
            span.record_exception(e)
            span.set_status(trace.StatusCode.ERROR, str(e))
            logger.error("DB query fallida", extra={"error": str(e), "backend": backend})
            raise HTTPException(status_code=500, detail=f"DB error: {str(e)}")
        finally:
            db_connections_active.add(-1)


@app.get("/data/analytics/{product_id}")
async def get_product_analytics(product_id: str):
    """
    Query analítica más costosa — para demostrar latencia en el flame graph.
    Simula un JOIN con tabla de ventas y cálculo de métricas agregadas.
    """
    apply_chaos()

    with tracer.start_as_current_span(
        "db.query.analytics",
        kind=trace.SpanKind.CLIENT,
        attributes={
            "db.system":     "postgresql",
            "db.operation":  "SELECT",
            "db.sql.table":  "sales",
            "db.statement":  "SELECT AVG(quantity), SUM(revenue) FROM sales WHERE product_id = ?",
            "product.id":    product_id,
            "query.type":    "analytics",
        }
    ) as span:
        # Simular latencia de query analítica (50-300ms)
        simulated_latency = random.uniform(0.05, 0.3)
        time.sleep(simulated_latency)

        span.set_attribute("db.query_duration_ms", round(simulated_latency * 1000, 2))
        span.set_attribute("analytics.simulated", True)

        result = {
            "product_id":     product_id,
            "avg_quantity":   round(random.uniform(1, 10), 2),
            "total_revenue":  round(random.uniform(1000, 50000), 2),
            "query_duration": round(simulated_latency * 1000, 2),
            "trace_id":       format(trace.get_current_span().get_span_context().trace_id, "032x"),
        }
        return result


@app.get("/chaos/status")
async def chaos_status():
    """Estado actual de los experimentos de caos (Módulo D)."""
    return {
        "chaos_latency_ms":  CHAOS_LATENCY_MS,
        "chaos_error_rate":  CHAOS_ERROR_RATE,
        "chaos_active":      CHAOS_LATENCY_MS > 0 or CHAOS_ERROR_RATE > 0,
    }
