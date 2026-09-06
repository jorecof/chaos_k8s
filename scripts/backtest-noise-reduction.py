#!/usr/bin/env python3
"""Backtesting B.4 -- reduccion de ruido: conjunto estatico vs dinamico
sobre las series REALES del Game Day canonico (2026-08-30).

Sustitucion metodologica respecto al diseno original (documentada en
docs/U3-notas-implementacion.md): el diseno proponia convertir
results/gameday-final/series-*.json (dumps de Prometheus ya agregados,
rate()/histogram_quantile() aplicados) al formato de `promtool test
rules`. Esos dumps NO llevan el desglose por `outcome` que las reglas
de este modulo necesitan (se generaron antes del fix de G-08/G-09), y
promtool no esta instalado en esta maquina. En su lugar se usan los
CSV crudos por peticion (raw-w*.csv, timestamp/status/latencia por
worker) que SI tienen el detalle necesario -- son la fuente mas fiel
disponible, capturada por el propio cliente de carga. La logica de las
reglas (recording rules + AIOpsCorrelatedAnomaly) se reimplementa aqui
en Python operando sobre esas series, en vez de invocar promtool.

mu/sigma de baseline: la regla real usa avg_over_time/stddev_over_time
sobre 6h de historia (muchas ventanas de 5m independientes). Aqui solo
hay ~90s de trafico base por experimento, insuficiente para estimar
varianza temporal real. Se aproxima sigma con el error estandar de una
proporcion binomial sobre esa base (sqrt(p*(1-p)/n)) -- el analogo
estadistico correcto para una muestra corta, documentado como
limitacion explicita del backtest.
"""
import csv
import glob
import json
import math
import sys

WINDOW_5M = 300.0
STEP = 15.0
LATENCY_SLO = 0.25
FLOOR = 0.01
FOR_STATIC = 60.0
FOR_DYNAMIC = 30.0

EXPERIMENTS = [
    ("E1 (latencia 200ms, service-b)", "exp1-20260830-103316"),
    ("E2-A (error rate 10%, data-service)", "exp2-A-20260830-111232"),
    ("E2-B (error rate 10%, data-service, replica 2)", "exp2-B-20260830-113517"),
]

BASE = "results/gameday-final"


def load_requests(expdir):
    rows = []
    for f in glob.glob(f"{BASE}/{expdir}/raw-w*.csv"):
        with open(f) as fh:
            for line in fh:
                parts = line.strip().split(",")
                if len(parts) < 4:
                    continue
                ts, status, lat = float(parts[0]), int(parts[2]), float(parts[3])
                rows.append((ts, status, lat))
    rows.sort()
    return rows


def load_meta(expdir):
    with open(f"{BASE}/{expdir}/meta.json") as f:
        return json.load(f)


def window_stats(rows, t, window=WINDOW_5M):
    seg = [r for r in rows if t - window < r[0] <= t]
    n = len(seg)
    if n == 0:
        return None
    errs = sum(1 for r in seg if r[1] != 200)
    err_rate = errs / n
    lats = sorted(r[2] for r in seg)
    p99 = lats[min(int(0.99 * (n - 1)), n - 1)]
    return {"n": n, "err_rate": err_rate, "p99": p99}


def baseline_mu_sigma(rows, t_base_start, t_base_end):
    seg = [r for r in rows if t_base_start <= r[0] < t_base_end]
    n = len(seg)
    if n == 0:
        return 0.0, 0.01  # sin datos -- sigma minimo no-cero para evitar division degenerada
    errs = sum(1 for r in seg if r[1] != 200)
    p = errs / n
    sigma = math.sqrt(max(p * (1 - p), 1e-6) / n)
    return p, sigma


def evaluate_rule(rows, t_start, t_end, condition_fn, for_secs):
    """Recorre la ventana a pasos de STEP segundos, aplica condition_fn(t) -> bool,
    y cuenta episodios de firing distintos respetando el 'for:' (duracion minima
    continua antes de disparar). Devuelve lista de (t_first_true, t_fired)."""
    episodes = []
    pending_since = None
    fired = False
    t = t_start
    while t <= t_end:
        ok = condition_fn(t)
        if ok:
            if pending_since is None:
                pending_since = t
            elif not fired and (t - pending_since) >= for_secs:
                episodes.append((pending_since, t))
                fired = True
        else:
            pending_since = None
            fired = False
        t += STEP
    return episodes


def run_experiment(label, expdir):
    meta = load_meta(expdir)
    rows = load_requests(expdir)
    t_base_start, t_base_end = meta["t_base_start"], meta["t_base_end"]
    t_chaos, t_end = meta["t_chaos"], meta["t_end"]
    t_scan_start = t_base_start + WINDOW_5M * 0  # el rolling window ya mira hacia atras
    mu, sigma = baseline_mu_sigma(rows, t_base_start, t_base_end)

    def static_error_cond(t):
        s = window_stats(rows, t)
        return s is not None and s["err_rate"] > FLOOR

    def static_latency_cond(t):
        s = window_stats(rows, t)
        return s is not None and s["p99"] > LATENCY_SLO

    def dynamic_cond(t):
        s = window_stats(rows, t)
        if s is None:
            return False
        return s["err_rate"] > (mu + 2 * sigma) and s["p99"] > LATENCY_SLO and s["err_rate"] > FLOOR

    ep_static_err = evaluate_rule(rows, t_base_end, t_end, static_error_cond, FOR_STATIC)
    ep_static_lat = evaluate_rule(rows, t_base_end, t_end, static_latency_cond, FOR_STATIC)
    ep_dynamic = evaluate_rule(rows, t_base_end, t_end, dynamic_cond, FOR_DYNAMIC)

    total_static = len(ep_static_err) + len(ep_static_lat)
    total_dynamic = len(ep_dynamic)

    def mttd(episodes):
        if not episodes:
            return None
        return episodes[0][1] - t_chaos

    return {
        "label": label,
        "n_requests": len(rows),
        "mu_baseline": mu,
        "sigma_baseline": sigma,
        "static_error_episodes": len(ep_static_err),
        "static_latency_episodes": len(ep_static_lat),
        "static_total": total_static,
        "dynamic_episodes": len(ep_dynamic),
        "mttd_static_error": mttd(ep_static_err),
        "mttd_static_latency": mttd(ep_static_lat),
        "mttd_dynamic": mttd(ep_dynamic),
    }


def main():
    results = [run_experiment(label, expdir) for label, expdir in EXPERIMENTS]

    total_static = sum(r["static_total"] for r in results)
    total_dynamic = sum(r["dynamic_episodes"] for r in results)

    print(f"{'experimento':45s} {'reqs':>5s} {'mu':>8s} {'sigma':>8s} {'estatico':>9s} {'dinamico':>9s} {'MTTD_din':>9s}")
    for r in results:
        mttd_d = f"{r['mttd_dynamic']:.0f}s" if r["mttd_dynamic"] is not None else "no disparo"
        print(f"{r['label']:45s} {r['n_requests']:5d} {r['mu_baseline']:8.4f} {r['sigma_baseline']:8.4f} "
              f"{r['static_total']:9d} {r['dynamic_episodes']:9d} {mttd_d:>9s}")
    print()
    print(f"TOTAL episodios estatico (4 reglas independientes, aqui 2 aplicables con datos disponibles): {total_static}")
    print(f"TOTAL episodios dinamico (AIOpsCorrelatedAnomaly):  {total_dynamic}")
    if total_static > 0:
        print(f"Reduccion: {(1 - total_dynamic / total_static) * 100:.1f}%")

    with open("docs/backtesting-B4-resultados.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    print("\nDetalle guardado en docs/backtesting-B4-resultados.json")


if __name__ == "__main__":
    main()
