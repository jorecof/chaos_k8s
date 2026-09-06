#!/usr/bin/env python3
"""mttd-analysis.py -- calcula los 4 sellos de tiempo del modulo D (D.3)
para una corrida ya completada de scripts/run-exp1.sh o run-exp2.sh, y
los agrega a summary.txt del directorio de resultados.

    t_inject  -- de meta.json (t_chaos), ya validado contra el reloj del
                 apiserver por el propio script de la corrida.
    t_signal  -- primer punto de la serie SLI indicada fuera de umbral.
    t_alert   -- primer punto de ALERTS{alertname=...} en estado firing.
    t_notify  -- del log estructurado de alert-enricher (busca el mismo
                 alertname/exported_job y lee su propio campo t_notify).

MTTD = t_notify - t_inject (D.3: el objetivo <120s es sobre la
notificacion, no sobre la deteccion cruda).

Usa el proxy del apiserver (kubectl get --raw .../proxy/...) para todo,
igual que run-exp1.sh/run-exp2.sh -- sin port-forward, sin las carreras
de puertos zombies de siempre.

Uso:
    python3 scripts/mttd-analysis.py <dir-resultados> <alertname> \
        [exported_job] [sli_query] [threshold]

Ejemplos:
    python3 scripts/mttd-analysis.py results/exp1-20260906-153000 \
        ChaosLatencyDetected service-b

    python3 scripts/mttd-analysis.py results/exp2-app-20260906-160000 \
        AIOpsCorrelatedAnomaly data-service
"""
import json
import subprocess
import sys
import urllib.parse
from datetime import datetime, timezone

NS = "otel-lab"


def kubectl_raw(path, timeout=20):
    out = subprocess.run(
        ["kubectl", "-n", NS, "get", "--raw", path],
        capture_output=True, text=True, timeout=timeout,
    )
    if out.returncode != 0:
        return None
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError:
        return None


def prom_query_range(query, start, end, step=5):
    enc = urllib.parse.quote(query, safe="")
    path = (
        f"/api/v1/namespaces/{NS}/services/prometheus-svc:9090/proxy/api/v1/query_range"
        f"?query={enc}&start={start}&end={end}&step={step}"
    )
    return kubectl_raw(path)


def first_crossing(data, threshold):
    if not data or data.get("status") != "success":
        return None
    result = data["data"]["result"]
    if not result:
        return None
    for ts, v in result[0]["values"]:
        try:
            if float(v) >= threshold:
                return float(ts)
        except (TypeError, ValueError):
            continue
    return None


def get_alert_enricher_pod():
    out = subprocess.run(
        ["kubectl", "-n", NS, "get", "pods", "-l", "app=alert-enricher",
         "-o", "jsonpath={.items[0].metadata.name}"],
        capture_output=True, text=True, timeout=15,
    )
    name = out.stdout.strip()
    return name or None


def get_alert_enricher_logs(since_seconds):
    pod = get_alert_enricher_pod()
    if not pod:
        return []
    since_seconds = max(1, int(since_seconds))
    out = subprocess.run(
        ["kubectl", "-n", NS, "logs", pod, f"--since={since_seconds}s"],
        capture_output=True, text=True, timeout=15,
    )
    return out.stdout.splitlines()


def find_t_notify(lines, alertname, exported_job=None):
    best = None
    for line in lines:
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        alert = rec.get("alert")
        if not isinstance(alert, dict):
            continue
        if alert.get("alertname") != alertname:
            continue
        if exported_job and alert.get("exported_job") != exported_job:
            continue
        t_notify_str = alert.get("t_notify")
        if not t_notify_str:
            continue
        try:
            t = datetime.fromisoformat(t_notify_str).timestamp()
        except ValueError:
            continue
        if best is None or t < best:
            best = t
    return best


def fmt(label, t, t_inject):
    if t is None:
        return f"{label}: no detectado"
    return f"{label}: {t:.3f}  (t_inject+{t - t_inject:.1f}s)"


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    out_dir = sys.argv[1]
    alertname = sys.argv[2]
    exported_job = sys.argv[3] if len(sys.argv) > 3 else None
    sli_query = sys.argv[4] if len(sys.argv) > 4 else "sli:latency_p99:5m"
    threshold = float(sys.argv[5]) if len(sys.argv) > 5 else 0.25

    with open(f"{out_dir}/meta.json") as f:
        meta = json.load(f)
    t_inject = meta["t_chaos"]
    t_end = meta["t_end"]

    start = int(t_inject - 30)
    end = int(t_end + 60)

    sig_data = prom_query_range(sli_query, start, end, step=5)
    t_signal = first_crossing(sig_data, threshold)

    alert_query = f'ALERTS{{alertname="{alertname}"}}'
    alert_data = prom_query_range(alert_query, start, end, step=5)
    t_alert = first_crossing(alert_data, 1.0)

    since_seconds = int(datetime.now(timezone.utc).timestamp() - t_inject) + 120
    lines = get_alert_enricher_logs(since_seconds)
    t_notify = find_t_notify(lines, alertname, exported_job)

    result = {
        "alertname": alertname,
        "exported_job": exported_job,
        "sli_query": sli_query,
        "threshold": threshold,
        "t_inject": t_inject,
        "t_signal": t_signal,
        "t_alert": t_alert,
        "t_notify": t_notify,
    }
    if t_notify is not None:
        result["mttd_seconds"] = t_notify - t_inject
        result["mttd_ok"] = result["mttd_seconds"] < 120

    print(json.dumps(result, indent=2, default=str))

    with open(f"{out_dir}/mttd.json", "w") as f:
        json.dump(result, f, indent=2, default=str)

    with open(f"{out_dir}/summary.txt", "a") as f:
        f.write("\n\n=== MTTD -- 4 sellos de tiempo (D.3) ===\n")
        f.write(f"alerta: {alertname}" + (f"  exported_job={exported_job}\n" if exported_job else "\n"))
        f.write(f"t_inject:  {t_inject:.3f}\n")
        f.write(fmt("t_signal", t_signal, t_inject) + "\n")
        f.write(fmt("t_alert", t_alert, t_inject) + "\n")
        f.write(fmt("t_notify", t_notify, t_inject) + "\n")
        if t_notify is not None:
            veredicto = "CUMPLE" if result["mttd_ok"] else "NO cumple"
            f.write(f"MTTD = t_notify - t_inject = {result['mttd_seconds']:.1f}s "
                    f"({veredicto} el objetivo <120s)\n")
        else:
            f.write("MTTD: no calculable -- alert-enricher no proceso esta alerta "
                    "(revisar si la alerta llego a disparar, o si el rango de "
                    "--since del log ya se salio de la retencion del pod)\n")

    print(f"\nAgregado a {out_dir}/summary.txt y {out_dir}/mttd.json")


if __name__ == "__main__":
    main()
