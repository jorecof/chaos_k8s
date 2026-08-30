#!/usr/bin/env python3
"""Figuras del Game Day definitivo — corridas del 2026-08-30 (10:33 / 11:12 / 11:35)."""
import csv, json, os, re, collections, textwrap, statistics as st
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

GD = "/mnt/user-data/uploads/chaos_k8s/results/gameday-final"
E1 = f"{GD}/exp1-20260830-103316"
A  = f"{GD}/exp2-A-20260830-111232"
B  = f"{GD}/exp2-B-20260830-113517"
OUT = "/home/claude/gdfigs"; os.makedirs(OUT, exist_ok=True)

SURF="#fcfcfb"; INK="#0b0b0b"; SEC="#52514e"; MUTED="#898781"
GRID="#e1e0d9"; BASE="#c3c2b7"; BLUE="#2a78d6"; CRIT="#d03b3b"
AQUA="#1baf7a"; BAND="#f4f3f0"

plt.rcParams.update({
    "font.family":"DejaVu Sans","font.size":9,
    "figure.facecolor":SURF,"axes.facecolor":SURF,
    "axes.edgecolor":BASE,"axes.labelcolor":SEC,
    "xtick.color":MUTED,"ytick.color":MUTED,"text.color":INK,
    "axes.grid":True,"grid.color":GRID,"grid.linewidth":0.6,
    "grid.linestyle":"-","axes.axisbelow":True,"savefig.facecolor":SURF,
})

def strip(ax, left=False):
    for s in ("top","right"): ax.spines[s].set_visible(False)
    for s in ("bottom","left"):
        ax.spines[s].set_color(BASE); ax.spines[s].set_linewidth(0.8)
    if left: ax.spines["left"].set_visible(False)
    ax.tick_params(length=0)

def header(fig, t, sub, tw=66, sw=108, gap=0.055):
    """Dibuja titulo + bajada y devuelve el `top` libre para los ejes."""
    tt = textwrap.wrap(t, tw); ss = textwrap.wrap(sub, sw)
    H = fig.get_size_inches()[1]
    lt, ls = 0.235/H, 0.165/H          # alto de linea en fraccion de figura
    y = 0.985
    fig.text(0.012, y, "\n".join(tt), fontsize=11.2, fontweight="bold",
             color=INK, va="top", linespacing=1.25)
    y -= lt*len(tt) + 0.022
    fig.text(0.012, y, "\n".join(ss), fontsize=8.3, color=SEC,
             va="top", linespacing=1.45)
    return y - ls*len(ss) - gap

def load(d, name):
    m = json.load(open(f"{d}/meta.json")); rows = []
    for r in csv.reader(open(f"{d}/{name}")):
        if len(r) >= 4:
            try: rows.append((float(r[0]) - m["t_chaos"], r[2], float(r[3])))
            except ValueError: pass
    return m, rows

def pct(v, q):
    v = sorted(v); return v[min(len(v)-1, int(q*len(v)))] if v else float("nan")

mA, rA = load(A, "exp2_repeat.csv")
mB, rB = load(B, "exp2_repeat.csv")
m1, r1 = load(E1, "exp1_repeat.csv")
NOM = 300.0

# ══ FIG 1 — Experimento 1: latencia por request ═══════════════════════
fig, ax = plt.subplots(figsize=(7.2, 3.6))
fig.subplots_adjust(bottom=0.145, left=0.085, right=0.985)
tb = m1["t_base_end"] - m1["t_chaos"]
ax.axvspan(0, NOM, color="#fdf0ef", zorder=0)
ok = [(t, d) for t, c, d in r1 if c == "200"]
ax.scatter([t for t,_ in ok], [1000*d for _,d in ok], s=6, color=BLUE,
           alpha=0.5, linewidths=0, zorder=3)
ax.axvline(0, color=CRIT, lw=1.4, zorder=4); ax.axvline(NOM, color=CRIT, lw=1.4, zorder=4)
base = [d for t,c,d in r1 if t <= tb and c=="200"]
ch   = [d for t,c,d in r1 if 0 <= t <= NOM and c=="200"]
po   = [d for t,c,d in r1 if t > NOM and c=="200"]
for x, v, lab in ((-80, base, "línea base"), (150, ch, "chaos"), (430, po, "post-rollback")):
    ax.annotate(f"{lab} · p50 {1000*pct(v,.5):.0f} ms", xy=(x, 1000*pct(v,.5)),
                xytext=(x, 700), ha="center", fontsize=8.3, color=SEC,
                arrowprops=dict(arrowstyle="-", color=BASE, lw=0.8))
ax.text(150, 60, "NetworkChaos activo", color=CRIT, fontsize=8.5, fontweight="bold", ha="center")
ax.set_ylim(0, 790); ax.set_xlim(-160, 560); ax.set_yticks([0,200,400,600,800])
ax.set_xlabel("segundos desde la inyección", color=SEC, fontsize=8.5)
ax.yaxis.set_major_formatter(FuncFormatter(lambda v,p: f"{v:.0f} ms"))
strip(ax)
TOP = header(fig, "Experimento 1 — la latencia inyectada se propaga sin amortiguación",
         f"NetworkChaos delay 200 ms ±10 ms sobre service-b · n = {len(r1)} requests · 0 errores · rollback por TTL en t = 300 s (desfase +1,0 s)")
fig.subplots_adjust(top=TOP)
fig.savefig(f"{OUT}/gd1-exp1-latencia.png", dpi=200); plt.close(fig)

# ══ FIG 2 — error rate por minuto, A vs B ═════════════════════════════
fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.5), sharey=True)
fig.subplots_adjust(bottom=0.145, left=0.075, right=0.985, wspace=0.09)
for ax, (rows, ttl, sub) in zip(axes, [
        (rA, 'A — path: "*"', "health check DENTRO del blast radius"),
        (rB, 'B — path: "/data/*"', "health check FUERA del blast radius")]):
    run = [x for x in rows if x[0] >= 0]
    err = collections.Counter(int(t//60) for t,c,_ in run if c != "200")
    tot = collections.Counter(int(t//60) for t,c,_ in run)
    mins = sorted(k for k in tot if tot[k] >= 20)
    vals = [100*err.get(k,0)/tot[k] for k in mins]
    ax.axvspan(4.5, max(mins)+0.5, color=BAND, zorder=0)
    ax.bar(mins, vals, width=0.62, color=BLUE, zorder=3, linewidth=0)
    ax.axvline(4.5, color=CRIT, lw=1.5, zorder=4)
    ax.set_xticks(mins); ax.set_xlabel("minuto desde la inyección", color=SEC, fontsize=8.3)
    ax.set_title(ttl, loc="left", fontsize=9.6, fontweight="bold", color=INK, pad=12)
    ax.text(0, 1.015, sub, transform=ax.transAxes, fontsize=8.2, color=SEC, va="bottom")
    strip(ax, left=True)
axes[0].yaxis.set_major_formatter(FuncFormatter(lambda v,p: f"{v:.0f} %"))
axes[0].set_ylim(0, 20); axes[0].spines["left"].set_visible(False)
axes[0].text(6.6, 16.0, "sigue fallando\n166,8 s después\ndel duration", color=CRIT,
             fontsize=8.6, fontweight="bold", ha="center", va="center")
axes[1].text(6.6, 16.0, "último error\n2,0 s ANTES\ndel fin nominal", color=AQUA,
             fontsize=8.6, fontweight="bold", ha="center", va="center")
axes[0].text(4.3, 19.4, "fin nominal", color=CRIT, fontsize=8, ha="right",
             va="top", fontweight="bold")
TOP = header(fig, "La remediación funciona: el rollback vuelve a cerrar dentro del TTL",
         "Requests abortadas por minuto medidas en el cliente · misma inyección y mismo 10 % nominal en las dos corridas; el único cambio es el campo path del manifiesto", gap=0.135)
for _a in axes: _a.set_position(_a.get_position())
fig.subplots_adjust(top=TOP)
fig.savefig(f"{OUT}/gd2-errorrate-AB.png", dpi=200); plt.close(fig)

# ══ FIG 3 — reinicios del pod objetivo, A vs B ════════════════════════
def restarts(d, tgt):
    m = json.load(open(f"{d}/meta.json")); tc = m["t_chaos"]
    txt = open(f"{d}/samples/pods.txt").read()
    blk = re.split(r"=== t=(\d+) ===", txt)[1:]
    pts = []
    for i in range(0, len(blk), 2):
        t = int(blk[i])
        for ln in blk[i+1].strip().splitlines():
            p = ln.split()
            if len(p) >= 5 and tgt in p[0]:
                pts.append((t - tc, int(p[4]), p[3] == "true"))
    return pts

pA = restarts(A, mA["target"].split("/")[-1])
pB = restarts(B, mB["target"].split("/")[-1])

fig, ax = plt.subplots(figsize=(7.2, 3.7))
fig.subplots_adjust(bottom=0.135, left=0.085, right=0.985)
ax.axvspan(0, NOM, color="#fdf0ef", zorder=0)
ax.axvspan(NOM, 560, color=BAND, zorder=0)
ax.step([t for t,_,_ in pA], [v for _,v,_ in pA], where="post", lw=2.0, color=CRIT,
        zorder=4, label='A — path: "*"')
ax.step([t for t,_,_ in pB], [v for _,v,_ in pB], where="post", lw=2.0, color=AQUA,
        zorder=4, label='B — path: "/data/*"')
nr = [t for t,_,ok in pA if not ok]
if nr:
    ax.axvspan(min(nr), 560, color="#fbeded", zorder=1)
    ax.text(552, 2.9, "el pod deja de\nestar Ready\n(CrashLoopBackOff)",
            color=CRIT, fontsize=8.2, ha="right", va="center", fontweight="bold")
ax.axvline(NOM, color=CRIT, lw=1.3, zorder=5)
ax.text(NOM-8, 7.3, "fin nominal", color=CRIT, fontsize=8, ha="right",
        va="top", fontweight="bold")
ax.text(148, 4.2, "un reinicio cada 77 s:\n3 fallos de liveness × 20 s", color=CRIT,
        fontsize=8.4, ha="center")
ax.text(345, 0.5, "B se mantiene en cero los 543 s completos",
        color=AQUA, fontsize=8.4, ha="center", fontweight="bold")
ax.set_xlim(-10, 560); ax.set_ylim(-0.4, 7.5); ax.set_yticks(range(7))
ax.set_xlabel("segundos desde la inyección", color=SEC, fontsize=8.5)
ax.set_ylabel("reinicios acumulados del pod objetivo", color=SEC, fontsize=8.5)
ax.legend(loc="upper left", frameon=False, fontsize=8.5, labelcolor=SEC,
          bbox_to_anchor=(-0.005, 1.02))
strip(ax)
TOP = header(fig, "El daño colateral desaparece al sacar el health check del blast radius",
         "Contador de restarts del único pod inyectado, muestreado cada 15 s. En A el kubelet lo mata cinco veces dentro de la ventana y una sexta después; en B nunca. El experimento debía degradar un endpoint, no destruir el pod.")
fig.subplots_adjust(top=TOP)
fig.savefig(f"{OUT}/gd3-restarts-AB.png", dpi=200); plt.close(fig)

# ══ FIG 4 — cuánto espera el cliente antes del abort ══════════════════
eA = sorted(d for t,c,d in rA if t >= 0 and c != "200")
eB = sorted(d for t,c,d in rB if t >= 0 and c != "200")
fig, ax = plt.subplots(figsize=(7.2, 3.5))
fig.subplots_adjust(bottom=0.165, left=0.085, right=0.985)
ax.axvspan(0.005, 0.3, color="#eefaf4", zorder=0)
for vals, col, lab in ((eA, CRIT, f'A — path: "*"  (n = {len(eA)})'),
                       (eB, AQUA, f'B — path: "/data/*"  (n = {len(eB)})')):
    ys = [(i+1)/len(vals) for i in range(len(vals))]
    ax.step(vals, ys, where="post", lw=2.2, color=col, label=lab, zorder=4)
ax.set_xscale("log"); ax.set_xlim(0.006, 20); ax.set_ylim(0, 1.04)
ax.set_xticks([0.01, 0.1, 1, 10])
ax.set_xticklabels(["10 ms", "100 ms", "1 s", "10 s"])
ax.yaxis.set_major_formatter(FuncFormatter(lambda v,p: f"{100*v:.0f} %"))
ax.set_xlabel("tiempo que espera el cliente antes de recibir el corte (escala logarítmica)",
              color=SEC, fontsize=8.5)
ax.set_ylabel("requests abortadas acumuladas", color=SEC, fontsize=8.5)
ax.annotate("mediana 9,34 s", xy=(9.34, 0.5), xytext=(6.6, 0.58), fontsize=8.5,
            color=CRIT, fontweight="bold", ha="right", va="center",
            arrowprops=dict(arrowstyle="-", color=BASE, lw=0.9))
ax.annotate("mediana 20 ms", xy=(0.0205, 0.5), xytext=(0.105, 0.36), fontsize=8.5,
            color=AQUA, fontweight="bold", ha="left", va="center",
            arrowprops=dict(arrowstyle="-", color=BASE, lw=0.9))
ax.legend(loc="upper left", frameon=False, fontsize=8.4, labelcolor=SEC,
          bbox_to_anchor=(0.31, 0.99))
strip(ax)
TOP = header(fig, "Fail-fast contra fail-slow: 477× de diferencia en lo que espera el usuario",
         "Distribución acumulada de la duración de cada request abortada. En A el pod está reiniciándose, así que la conexión se queda colgada hasta el timeout del cliente; en B el abort llega inmediato y el usuario puede reintentar.")
fig.subplots_adjust(top=TOP)
fig.savefig(f"{OUT}/gd4-abort-latencia-AB.png", dpi=200); plt.close(fig)

# ══ FIG 9 — el throughput que el error rate esconde ═══════════════════
fig, ax = plt.subplots(figsize=(7.2, 3.7))
fig.subplots_adjust(bottom=0.135, left=0.085, right=0.985)
ax.axvspan(-0.5, 4.5, color="#fdf0ef", zorder=0)
w = 0.38
for off, rows, col, lab in ((-w/2, rA, CRIT, 'A — path: "*"'),
                            (w/2, rB, AQUA, 'B — path: "/data/*"')):
    run = [x for x in rows if x[0] >= 0]
    tot = collections.Counter(int(t//60) for t,c,_ in run)
    mins = sorted(k for k in tot if tot[k] >= 20)
    ax.bar([k+off for k in mins], [tot[k]/60 for k in mins], width=w,
           color=col, zorder=3, linewidth=0, label=lab)
ax.axvline(4.5, color=CRIT, lw=1.5, zorder=4)
ax.text(4.38, 3.05, "fin nominal", color=CRIT, fontsize=8, ha="right",
        va="top", fontweight="bold")
ax.annotate("A pierde un cuarto del caudal: los 4 workers\nquedan bloqueados 9 s por cada abort, y el\nhueco sigue abierto después del fin nominal",
            xy=(5.81, 1.52), xytext=(8.62, 3.88), fontsize=8.4, color=CRIT, ha="right",
            va="top", arrowprops=dict(arrowstyle="-", color=BASE, lw=0.9))
ax.set_xticks(range(9)); ax.set_xlim(-0.6, 8.7); ax.set_ylim(0, 3.95)
ax.set_xlabel("minuto desde la inyección", color=SEC, fontsize=8.5)
ax.set_ylabel("requests completadas por segundo", color=SEC, fontsize=8.5)
ax.legend(loc="upper left", frameon=False, fontsize=8.5, labelcolor=SEC,
          ncol=2, bbox_to_anchor=(-0.005, 1.02))
strip(ax)
TOP = header(fig, "El error rate esconde el daño real: en A también se hunde el caudal",
         "Requests que el cliente logra completar por segundo, con carga ofrecida idéntica en las dos corridas (4 workers cada 1,5 s). A registra 8,6 % de errores contra 11,8 % de B, pero sobre un denominador un 27 % más chico: la tasa mejora porque el sistema atiende menos, no porque falle menos.")
fig.subplots_adjust(top=TOP)
fig.savefig(f"{OUT}/gd9-throughput-AB.png", dpi=200); plt.close(fig)


# ══ FIG 5 — el blind spot, en las dos corridas ════════════════════════
ROWS = [('A — path: "*"', 73, 1020, 0, 1413, 2477),
        ('B — path: "/data/*"', 90, 1388, 0, 1882, 3381)]
fig, ax = plt.subplots(figsize=(7.2, 3.5))
fig.subplots_adjust(bottom=0.055, left=0.245, right=0.985)
ax.set_xlim(0, 100); ax.set_ylim(-0.15, len(ROWS)*2.75); ax.axis("off")
for i, (ttl, ce, cn, ae, an, sp) in enumerate(ROWS):
    ybase = (len(ROWS)-1-i) * 2.75
    ax.text(-0.6, ybase + 1.92, ttl, fontsize=9.6, fontweight="bold",
            color=INK, ha="left", va="center")
    for j, (lab, e, n, unit, col) in enumerate([
            ("Cliente\n(curl, fuera del cluster)", ce, cn, "requests", CRIT),
            ("Jaeger / APM\n(trazas de data-service)", ae, an, "trazas, todas 200", MUTED)]):
        y = ybase + 1.12 - j*0.92
        ax.add_patch(plt.Rectangle((0, y-0.26), 100, 0.52, color=BAND, zorder=1))
        w = 100*e/n
        if w > 0:
            ax.add_patch(plt.Rectangle((0, y-0.26), max(w, 0.4), 0.52, color=col, zorder=2))
        ax.text(-1.4, y, lab, fontsize=8.6, color=SEC, ha="right", va="center",
                linespacing=1.4)
        ax.text(max(w, 0.4)+1.6, y, f"{100*e/n:.1f} %".replace(".", ",")
                + f"   ·   {e} de {n} {unit}", fontsize=9.2, fontweight="bold",
                color=col if e else SEC, va="center", zorder=3)
TOP = header(fig, "El tablero de trazas sigue ciego, y no es culpa del crash-loop",
    "La misma ventana medida por dos fuentes en las dos corridas. En B el pod nunca se reinicia y el rollback "
    "cierra a tiempo, y aun así los 3 381 spans etiquetados salen todos con código 200 y sin el atributo error: "
    "el abort ocurre en el camino de vuelta, después de que la aplicación ya respondió.", gap=0.10)
fig.subplots_adjust(top=TOP)
fig.savefig(f"{OUT}/gd5-blindspot.png", dpi=200); plt.close(fig)

# ══ FIG 6 — sondas del blackbox exporter, A vs B ══════════════════════
def probes(d):
    m = json.load(open(f"{d}/meta.json")); tc = m["t_chaos"]
    txt = open(f"{d}/samples/prom.txt").read()
    blk = re.split(r"=== t=(\d+) ===", txt)[1:]
    out = {}
    for i in range(0, len(blk), 2):
        t = int(blk[i])
        mm = re.search(r"-- borde: probe_success por endpoint --\n(.*)", blk[i+1])
        if not mm: continue
        try: js = json.loads(mm.group(1).splitlines()[0])
        except Exception: continue
        for r in js["data"]["result"]:
            out.setdefault(r["metric"]["instance"], []).append((t-tc, r["value"][1]))
    return out

EP = [("http://data-service-svc:8002/data/products", "data-service /data/products"),
      ("http://data-service-svc:8002/health",        "data-service /health"),
      ("http://service-a-svc:8000/health",           "service-a /health  (control)")]
fig, axes = plt.subplots(2, 1, figsize=(7.2, 5.1), sharex=True)
fig.subplots_adjust(bottom=0.085, left=0.265, right=0.885, hspace=0.42)
for ax, (d, ttl, sub) in zip(axes, [
        (A, 'Corrida A — path: "*"',       "el chaos alcanza también al health check"),
        (B, 'Corrida B — path: "/data/*"', "el health check queda fuera")]):
    P = probes(d)
    ax.axvspan(0, NOM, color="#fdf0ef", zorder=0); ax.axvspan(NOM, 560, color=BAND, zorder=0)
    for i, (inst, lab) in enumerate(EP):
        y = len(EP) - 1 - i
        pts = [(t, v) for t, v in P.get(inst, []) if -20 <= t <= 560]
        okx = [t for t, v in pts if v == "1"]; badx = [t for t, v in pts if v == "0"]
        ax.scatter(okx, [y]*len(okx), s=9, color="#d3d8d1", linewidths=0, zorder=2)
        ax.scatter(badx, [y]*len(badx), s=58, marker="|", color=CRIT, linewidths=1.9, zorder=4)
        ax.text(572, y, f"{len(badx)} fallidas" if badx else "0", fontsize=8.2,
                color=CRIT if badx else MUTED, va="center",
                fontweight="bold" if badx else "normal")
    ax.axvline(0, color=CRIT, lw=1.3, zorder=5); ax.axvline(NOM, color=CRIT, lw=1.3, zorder=5)
    ax.set_yticks(range(len(EP)))
    ax.set_yticklabels([l for _, l in reversed(EP)], fontsize=8.1, color=INK)
    ax.set_ylim(-0.6, len(EP)+0.05); ax.set_xlim(-30, 565)
    ax.grid(axis="y", visible=False)
    ax.set_title(ttl, loc="left", fontsize=9.6, fontweight="bold", color=INK, pad=12)
    ax.text(0, 1.02, sub, transform=ax.transAxes, fontsize=8.2, color=SEC, va="bottom")
    strip(ax, left=True)
axes[0].text(150, 2.48, "chaos activo", color=CRIT, fontsize=8, ha="center", fontweight="bold")
axes[0].text(432, 2.48, "después del duration", color=SEC, fontsize=8, ha="center")
axes[1].set_xlabel("segundos desde la inyección", color=SEC, fontsize=8.5)
TOP = header(fig, "El SLI de borde ve la falla, y explica el crash-loop",
    "Cada marca roja es una sonda del blackbox exporter que devolvió fallo, muestreada cada 15 s. En A el "
    "health check del pod inyectado falla y el kubelet lo mata; en B no falla nunca. service-a, fuera del "
    "blast radius, no se toca en ninguna de las dos corridas.", sw=100, gap=0.135)
fig.subplots_adjust(top=TOP)
fig.savefig(f"{OUT}/gd6-sondas-AB.png", dpi=200); plt.close(fig)

print("ok")
for f in sorted(os.listdir(OUT)): print("  ", f)
tA = len([x for x in rA if x[0] >= 0]); tB = len([x for x in rB if x[0] >= 0])
print(f"A n={tA} err={len(eA)}  B n={tB} err={len(eB)}  ratio caudal={tA/tB:.3f}")
print(f"A p50 abort={st.median(eA):.3f}s  B p50 abort={st.median(eB):.3f}s  factor={st.median(eA)/st.median(eB):.0f}x")
