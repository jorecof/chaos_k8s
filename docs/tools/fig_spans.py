#!/usr/bin/env python3
"""Desglose por span, agregado sobre 1 219 trazas del Experimento 1."""
import json, textwrap, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

SURF="#fcfcfb"; INK="#0b0b0b"; SEC="#52514e"; MUTED="#898781"
GRID="#e1e0d9"; BASE="#c3c2b7"; BLUE="#2a78d6"; CRIT="#d03b3b"
plt.rcParams.update({"font.family":"DejaVu Sans","font.size":9,
    "figure.facecolor":SURF,"axes.facecolor":SURF,"axes.edgecolor":BASE,
    "xtick.color":MUTED,"ytick.color":MUTED,"text.color":INK,
    "axes.grid":True,"grid.color":GRID,"grid.linewidth":0.6,
    "axes.axisbelow":True,"savefig.facecolor":SURF})

d = json.load(open("/home/claude/e1_spans.json"))
ORDER = ["total percibido por el cliente",
         "llamada a inventario (envoltura)",
         "span cliente httpx → service-b",
         "consulta a Postgres",
         "SELECT",
         "span servidor de service-b"]
LABEL = {"total percibido por el cliente": "GET /order/{order_id}\ntotal percibido por el cliente",
         "llamada a inventario (envoltura)": "call.service-b.inventory\nenvoltura de la llamada",
         "span cliente httpx → service-b": "GET  (cliente httpx)\nservice-a → service-b",
         "consulta a Postgres": "fetch.order.db\nconsulta a Postgres",
         "SELECT": "SELECT",
         "span servidor de service-b": "GET /inventory/{product_id}\nservidor de service-b"}

fig, ax = plt.subplots(figsize=(7.2, 4.0))
fig.subplots_adjust(top=0.755, bottom=0.115, left=0.315, right=0.90)

for i, k in enumerate(ORDER):
    y = len(ORDER) - 1 - i
    a, b, na, nb = d[k]
    movido = (b - a) > 10
    ax.plot([a, b], [y, y], color=CRIT if movido else BASE,
            lw=2.2 if movido else 1.2, zorder=2, solid_capstyle="round")
    ax.plot([a], [y], "o", ms=8, color=BLUE, mec=SURF, mew=1.6, zorder=4)
    ax.plot([b], [y], "o", ms=8, color=CRIT if movido else MUTED,
            mec=SURF, mew=1.6, zorder=4)
    txt = f"+{b-a:.0f} ms" if movido else f"+{b-a:.2f} ms"
    ax.text(1450, y, txt, fontsize=8.6, va="center",
            color=CRIT if movido else MUTED, fontweight="bold" if movido else "normal")

ax.set_yticks(range(len(ORDER)))
ax.set_yticklabels([LABEL[k] for k in reversed(ORDER)], fontsize=8.2, color=INK)
ax.set_xscale("log")
ax.set_xlim(0.3, 1300)
ax.set_ylim(-0.6, len(ORDER) - 0.4)
ax.set_xticks([1, 10, 100, 1000])
ax.set_xticklabels(["1 ms", "10 ms", "100 ms", "1 s"])
ax.set_xlabel("duración mediana del span (escala logarítmica)", color=SEC, fontsize=8.5)
ax.grid(axis="y", visible=False)
for s in ("top", "right", "left"): ax.spines[s].set_visible(False)
ax.spines["bottom"].set_color(BASE); ax.tick_params(length=0)

ax.plot([], [], "o", ms=8, color=BLUE, label="sin chaos (n = 619)")
ax.plot([], [], "o", ms=8, color=CRIT, label="con chaos activo (n = 600)")
ax.legend(loc="upper left", frameon=False, fontsize=8.4, labelcolor=SEC,
          bbox_to_anchor=(-0.008, 1.03))

t = "Los 395 ms viven en un solo salto: el resto de la traza no se mueve"
s = ("Mediana por span sobre 1 219 trazas reales del Experimento 1, no sobre dos ejemplos. "
     "El span servidor de service-b vale 0,59 ms sin chaos y 0,64 ms con chaos: la dependencia "
     "atiende igual de rápido mientras el usuario espera 431 ms.")
fig.text(0.012, 0.985, t, fontsize=11.2, fontweight="bold", color=INK, va="top")
fig.text(0.012, 0.915, "\n".join(textwrap.wrap(s, 104)), fontsize=8.3, color=SEC, va="top")

os.makedirs("/home/claude/gdfigs", exist_ok=True)
fig.savefig("/home/claude/gdfigs/gd8-spans-e1.png", dpi=200)
print("ok")
