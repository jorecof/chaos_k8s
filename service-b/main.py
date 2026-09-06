"""
service-b: FastAPI — Servicio de inventario
Recibe llamadas de service-a, consulta inventario en PostgreSQL.
Continúa el trace distribuido iniciado por service-a mediante W3C TraceContext.
"""

import logging
import os
import time
import random
import psycopg2
import httpx

from fastapi import FastAPI, HTTPException
from pythonjsonlogger import jsonlogger
from contextlib import asynccontextmanager

# ── OTel SDK ─────────────────────────────────────────────────────────────────
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
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

# ── Config ────────────────────────────────────────────────────────────────────
OTEL_ENDPOINT     = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
DB_DSN            = os.getenv("DATABASE_URL", "postgresql://app:secret@postgres:5432/appdb")
PROMETHEUS_PORT   = int(os.getenv("PROMETHEUS_PORT", "9091"))
ENV               = os.getenv("ENVIRONMENT", "production")
APP_VERSION       = os.getenv("APP_VERSION", "1.0.0")
DATA_SERVICE_URL  = os.getenv("DATA_SERVICE_URL", "http://data-service-svc:8002")

# ── OTel Resource ─────────────────────────────────────────────────────────────
resource = Resource.create({
    SERVICE_NAME:    "service-b",
    SERVICE_VERSION: APP_VERSION,
    "deployment.environment": ENV,
    "cloud.provider": os.getenv("CLOUD_PROVIDER", "gcp"),
})

# ── TracerProvider ────────────────────────────────────────────────────────────
tracer_provider = TracerProvider(resource=resource)
tracer_provider.add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint=OTEL_ENDPOINT, insecure=True))
)
trace.set_tracer_provider(tracer_provider)
tracer = trace.get_tracer("service-b", APP_VERSION)

# ── MeterProvider ─────────────────────────────────────────────────────────────
otlp_metric_reader = PeriodicExportingMetricReader(
    OTLPMetricExporter(endpoint=OTEL_ENDPOINT, insecure=True),
    export_interval_millis=15000,
)
meter_provider = MeterProvider(
    resource=resource,
    metric_readers=[ otlp_metric_reader],
)
metrics.set_meter_provider(meter_provider)
meter = metrics.get_meter("service-b", APP_VERSION)

# ── Instrumentos de métricas ──────────────────────────────────────────────────
inventory_requests = meter.create_counter(
    "inventory_requests_total",
    description="Total consultas de inventario procesadas",
    unit="1",
)
inventory_query_duration = meter.create_histogram(
    "inventory_query_duration_seconds",
    description="Latencia de consultas de inventario a PostgreSQL",
    unit="s",
)
cache_hits = meter.create_counter(
    "inventory_cache_hits_total",
    description="Cache hits en consultas de inventario (en memoria)",
    unit="1",
)

# ── Logging estructurado con trace_id ─────────────────────────────────────────
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
        ctx = span.get_span_context()
        if ctx and ctx.is_valid:
            log_record["trace_id"] = format(ctx.trace_id, "032x")
            log_record["span_id"]  = format(ctx.span_id, "016x")
        log_record["service"]     = "service-b"
        log_record["environment"] = ENV

handler = logging.StreamHandler()
handler.setFormatter(OtelJsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
# LoggingHandler reenvía cada log record (via el root logger) al LoggerProvider
# OTel -> mismo trace_id/span_id ya quedan en el registro por el Formatter de
# arriba, y OTel los promueve a atributos reales del LogRecord OTLP.
otel_log_handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
logging.basicConfig(level=logging.INFO, handlers=[handler, otel_log_handler])
logger = logging.getLogger("service-b")

# ── Auto-instrumentación ──────────────────────────────────────────────────────
# FastAPIInstrumentor: extrae automáticamente el header traceparent
# y continúa el trace iniciado por service-a — sin ninguna línea extra de código.
Psycopg2Instrumentor().instrument(tracer_provider=tracer_provider)
# HTTPXClientInstrumentor: inyecta el traceparent saliente hacia data-service —
# sin esto la llamada de abajo rompe la cadena de 4 niveles (módulo A.1, G-01).
HTTPXClientInstrumentor().instrument(tracer_provider=tracer_provider)

# ── Cache en memoria (simulación) ─────────────────────────────────────────────
_inventory_cache: dict[str, dict] = {}

def get_db_connection():
    return psycopg2.connect(DB_DSN)

# ── Cliente hacia data-service (módulo A.1) ───────────────────────────────────
# Remediación #1 de U2 aplicada desde el inicio: presupuesto de tiempo por
# salto (p99 real ~36 ms en U2) y bulkhead, para no repetir D1 (el timeout de
# 10 s contra un p99 de 36 ms que dejaba colgado el threadpool).
_catalog_client = httpx.AsyncClient(
    base_url=DATA_SERVICE_URL,
    timeout=httpx.Timeout(connect=0.25, read=0.8, write=0.25, pool=0.25),
    limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
)

def _normalize(name: str) -> str:
    """LAPTOP-X1 / Laptop X1 -> laptopx1 — inventory.product_id y products.name
    no comparten formato (SKU vs. nombre de catálogo); esto los hace comparables
    sin depender de un mapeo hardcodeado que se rompa con nombres nuevos."""
    return "".join(ch for ch in name.lower() if ch.isalnum())

async def fetch_catalog(product_id: str) -> dict:
    """Enriquece el inventario con precio/categoría desde data-service.
    Degradación elegante (A.1): si data-service falla o excede el presupuesto,
    NUNCA propaga un 500 — responde catalog.status=unavailable y el llamador
    marca el span como degraded. El catálogo es chico (3 productos hoy), así
    que se trae la lista completa y se empareja por nombre normalizado en vez
    de agregar un endpoint de búsqueda nuevo a data-service."""
    try:
        resp = await _catalog_client.get("/data/products", params={"backend": "local"})
        resp.raise_for_status()
        target = _normalize(product_id)
        for p in resp.json().get("products", []):
            if _normalize(p["name"]) == target:
                return {"status": "ok", "price": p["price"], "category": p["category"]}
        return {"status": "not_found"}
    except (httpx.TimeoutException, httpx.HTTPError) as e:
        logger.warning(
            "Catálogo no disponible, degradando",
            extra={"error": str(e), "product_id": product_id},
        )
        return {"status": "unavailable"}

# ── App ───────────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    #start_http_server(PROMETHEUS_PORT)
    logger.info("Prometheus metrics server started", extra={"port": PROMETHEUS_PORT})
    yield
    await _catalog_client.aclose()
    tracer_provider.shutdown()
    meter_provider.shutdown()
    logger_provider.shutdown()

app = FastAPI(
    title="Service B",
    description="Microservicio de inventario — OTel end-to-end lab",
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
    return {"status": "ok", "service": "service-b"}


@app.get("/inventory/{product_id}")
async def get_inventory(product_id: str):
    """
    Retorna disponibilidad de inventario para un producto.
    El trace_id es el MISMO que el de service-a — propagado vía W3C TraceContext.
    El flame graph en Jaeger mostrará este span como hijo del span de service-a.
    """
    start = time.time()
    inventory_requests.add(1, {"product": product_id})

    result = None

    # ── Verificar cache en memoria ────────────────────────────────────────────
    if product_id in _inventory_cache:
        with tracer.start_as_current_span(
            "inventory.cache.hit",
            attributes={"cache.type": "in-memory", "product.id": product_id}
        ):
            cache_hits.add(1, {"product": product_id})
            logger.info("Cache hit", extra={"product_id": product_id})
            result = dict(_inventory_cache[product_id])  # copia — no mutar el cache con el catálogo
    else:
        # ── Custom span: consulta DB de inventario ────────────────────────────
        with tracer.start_as_current_span(
            "inventory.db.fetch",
            kind=trace.SpanKind.CLIENT,
            attributes={
                "db.system":    "postgresql",
                "db.operation": "SELECT",
                "db.name":      "appdb",
                "product.id":   product_id,
            }
        ) as span:
            try:
                conn = get_db_connection()
                cur = conn.cursor()

                # Simular latencia variable de DB (p50=10ms, p99=150ms)
                time.sleep(random.uniform(0.01, 0.15))

                cur.execute(
                    "SELECT product_id, available, warehouse, last_updated "
                    "FROM inventory WHERE product_id = %s",
                    (product_id,)
                )
                row = cur.fetchone()
                conn.close()

                duration = time.time() - start
                inventory_query_duration.record(duration, {"operation": "SELECT"})

                if not row:
                    span.set_status(trace.StatusCode.ERROR, "Product not found")
                    raise HTTPException(status_code=404, detail=f"Product {product_id} not found")

                result = {
                    "product_id":   row[0],
                    "available":    row[1],
                    "warehouse":    row[2],
                    "last_updated": str(row[3]),
                }

                span.set_attribute("inventory.available", result["available"])
                span.set_attribute("inventory.warehouse", result["warehouse"])
                span.set_status(trace.StatusCode.OK)

                # Actualizar cache
                _inventory_cache[product_id] = dict(result)

                logger.info(
                    "Inventory fetched from DB",
                    extra={
                        "product_id": product_id,
                        "available":  result["available"],
                        "duration_s": round(duration, 4),
                    }
                )

            except HTTPException:
                raise
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.StatusCode.ERROR, str(e))
                logger.error("Inventory DB query failed", extra={"error": str(e), "product_id": product_id})
                raise HTTPException(status_code=500, detail="Inventory service error")

    # ── Enriquecer con catálogo desde data-service (módulo A.1, G-01) ──────────
    catalog = await fetch_catalog(product_id)
    result["catalog"] = catalog
    trace.get_current_span().set_attribute("degraded", catalog["status"] != "ok")

    return result


@app.post("/inventory/{product_id}/reserve")
async def reserve_inventory(product_id: str, quantity: int = 1):
    """
    Custom span de lógica de negocio: reservar unidades de inventario.
    Demuestra spans anidados en el mismo servicio.
    """
    with tracer.start_as_current_span(
        "inventory.business.reserve",
        attributes={
            "product.id":        product_id,
            "reservation.units": quantity,
        }
    ) as span:
        logger.info("Reserving inventory", extra={"product_id": product_id, "quantity": quantity})

        # Simular validación de negocio
        with tracer.start_as_current_span("inventory.validate.stock") as val_span:
            time.sleep(random.uniform(0.005, 0.02))
            available = random.randint(0, 100)
            val_span.set_attribute("stock.available", available)

            if available < quantity:
                val_span.set_status(trace.StatusCode.ERROR, "Insufficient stock")
                span.set_status(trace.StatusCode.ERROR, "Reservation failed")
                raise HTTPException(status_code=409, detail="Insufficient stock")

        span.set_attribute("reservation.approved", True)
        span.set_status(trace.StatusCode.OK)

        # Invalidar cache
        _inventory_cache.pop(product_id, None)

        return {"reserved": quantity, "product_id": product_id, "status": "confirmed"}
