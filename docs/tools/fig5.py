#!/usr/bin/env python3
"""Fig. 5 — cadena causal del crash-loop y del rollback fallido."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

SURF = "#fcfcfb"; INK = "#0b0b0b"; SEC = "#52514e"; MUTED = "#898781"
BLUE = "#2a78d6"; CRIT = "#d03b3b"
FILL = "#eaf1fc"; FILLC = "#fbeded"

plt.rcParams.update({"font.family": "DejaVu Sans", "figure.facecolor": SURF,
                     "savefig.facecolor": SURF})

fig = plt.figure(figsize=(7.2, 3.9))
ax = fig.add_axes([0.012, 0.01, 0.976, 0.98])
ax.set_xlim(0, 100); ax.set_ylim(0, 54); ax.axis("off")

BW, BH = 30.0, 14.5
XS = [0.0, 35.0, 70.0]

def box(x, y, n, head, body, crit=False):
    ax.add_patch(FancyBboxPatch((x, y), BW, BH,
                 boxstyle="round,pad=0,rounding_size=1.3", linewidth=1.3,
                 edgecolor=CRIT if crit else BLUE,
                 facecolor=FILLC if crit else FILL, zorder=3))
    ax.text(x + 1.8, y + BH - 3.4, n, fontsize=9, fontweight="bold",
            color=CRIT if crit else BLUE, zorder=4, va="center")
    ax.text(x + 5.2, y + BH - 3.4, head, fontsize=8.8, fontweight="bold",
            color=INK, zorder=4, va="center")
    ax.text(x + 1.8, y + BH - 6.2, body, fontsize=7.4, color=SEC, zorder=4,
            va="top", linespacing=1.5)

def arrow(x1, y1, x2, y2, color=None, ls="-", rad=0.0):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2),
                 connectionstyle=f"arc3,rad={rad}", arrowstyle="-|>",
                 mutation_scale=12, linewidth=1.3, linestyle=ls,
                 color=color or MUTED, zorder=2))

TOP, BOT = 26.0, 4.0
box(XS[0], TOP, "1", 'path: "*"',
    'El HTTPChaos intercepta\nTODAS las responses del\npod — incluida GET /health')
box(XS[1], TOP, "2", "livenessProbe",
    "El health check también se\naborta: 3 fallos × 20 s y\nkubelet mata el contenedor")
box(XS[2], TOP, "3", "restart",
    "El reinicio destruye el netns\ny con él las reglas iptables\ndel tproxy")
box(XS[1], BOT, "5", "sin rollback",
    "Queda en Injected/Wait y el\nfinalizer bloquea el borrado:\nintervención manual", crit=True)
box(XS[2], BOT, "4", "recover falla", crit=True,
    body="chaos-daemon no encuentra\nel tproxy: cada Recover falla\ncon «unexpected EOF»")

arrow(XS[0] + BW, TOP + BH / 2, XS[1], TOP + BH / 2)
arrow(XS[1] + BW, TOP + BH / 2, XS[2], TOP + BH / 2)
arrow(XS[2] + BW / 2, TOP, XS[2] + BW / 2, BOT + BH, color=CRIT)
arrow(XS[2], BOT + BH / 2, XS[1] + BW, BOT + BH / 2, color=CRIT)

ax.add_patch(FancyArrowPatch((XS[1], BOT + BH / 2), (XS[0] + BW / 2, TOP),
             connectionstyle="arc3,rad=0.28", arrowstyle="-|>",
             mutation_scale=12, linewidth=1.2, linestyle=(0, (5, 3)),
             color=MUTED, zorder=2))
ax.text(15.5, 13.0, "Chaos Mesh reinyecta sobre\nel contenedor nuevo:\nel ciclo se repite cada 77 s",
        fontsize=7.8, color=SEC, ha="center", va="center", style="italic")

ax.text(0, 52.5, "Por qué el Experimento 2 no hizo rollback",
        fontsize=11.5, fontweight="bold", color=INK, va="top")
ax.text(0, 47.5, "Cadena causal reconstruida con la evidencia: reinicios del pod objetivo cada 77 s y fallas más allá del duration",
        fontsize=8.2, color=SEC, va="top")

fig.savefig("/home/claude/figs/fig5-mecanismo.png", dpi=200)
print("ok")
