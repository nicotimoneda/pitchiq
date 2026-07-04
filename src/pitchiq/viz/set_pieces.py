"""Visualización de córners: zonas de saque, ocupación del área y primer contacto."""

import matplotlib

matplotlib.use("Agg")  # sin display: los scripts guardan a fichero

from collections import Counter

import matplotlib.pyplot as plt
import numpy as np
from mplsoccer import VerticalPitch

_CAVEAT_360 = "solo jugadores visibles en el freeze-frame 360 (aproximación)"


def _half_pitch() -> "tuple[plt.Figure, plt.Axes, VerticalPitch]":
    """Media pista vertical orientada a la portería atacada (arriba)."""
    pitch = VerticalPitch(
        pitch_type="statsbomb", half=True, line_color="#4a4a4a", line_zorder=2
    )
    fig, ax = pitch.draw(figsize=(8, 7))
    return fig, ax, pitch


def plot_delivery_zones(
    end_locations: np.ndarray, zone_counts: "dict[str, int]", team: str
) -> plt.Figure:
    """Heatmap de localizaciones finales de los saques de córner a favor."""
    fig, ax, pitch = _half_pitch()
    if len(end_locations) >= 3:
        pitch.kdeplot(
            end_locations[:, 0], end_locations[:, 1],
            ax=ax, fill=True, levels=50, cmap="Reds", alpha=0.7, zorder=1,
        )
    if len(end_locations):
        pitch.scatter(
            end_locations[:, 0], end_locations[:, 1],
            ax=ax, s=30, color="#7a0c0c", alpha=0.6, zorder=3,
        )
    resumen = " · ".join(f"{z}: {n}" for z, n in zone_counts.items())
    ax.set_title(f"Saques de córner — {team}", fontsize=13, pad=10)
    fig.text(0.5, 0.03, resumen, ha="center", fontsize=9, color="#4a4a4a")
    fig.text(0.99, 0.005, "Datos: StatsBomb Open Data", ha="right", fontsize=7, color="#888")
    return fig


def plot_box_occupation(
    attackers: "list[int]", defenders: "list[int]", team: str
) -> plt.Figure:
    """Distribución de atacantes vs defensores visibles en el área al sacar."""
    fig, ax = plt.subplots(figsize=(9, 5))
    todos = attackers + defenders
    max_n = max(todos) if todos else 1
    xs = np.arange(0, max_n + 1)
    att_freq = Counter(attackers)
    def_freq = Counter(defenders)
    width = 0.4
    ax.bar(xs - width / 2, [att_freq.get(int(x), 0) for x in xs], width,
           label="atacantes", color="#d62828")
    ax.bar(xs + width / 2, [def_freq.get(int(x), 0) for x in xs], width,
           label="defensores", color="#005ec4")
    ax.set_xlabel("jugadores visibles dentro del área grande")
    ax.set_ylabel("nº de córners")
    ax.set_xticks(xs)
    ax.set_title(f"Ocupación del área en el saque — córners de {team}", fontsize=12)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.text(0.5, 0.005, _CAVEAT_360, ha="center", fontsize=8, color="#4a4a4a")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    return fig


def plot_first_contacts(
    good_xy: np.ndarray, bad_xy: np.ndarray, team: str, attacking: bool = True
) -> plt.Figure:
    """Zonas de primer contacto tras el saque, en clave del equipo analizado.

    ``good_xy`` = contactos favorables al equipo (ganados atacando, despejes
    defendiendo); ``bad_xy`` = desfavorables (perdidos / concedidos).
    """
    fig, ax, pitch = _half_pitch()
    lado = "a favor" if attacking else "en contra"
    etiquetas = ("ganado", "perdido") if attacking else ("despejado", "concedido")
    if len(good_xy):
        pitch.scatter(good_xy[:, 0], good_xy[:, 1], ax=ax, s=60, color="#1a7f37",
                      alpha=0.7, zorder=3, label=f"1er contacto {etiquetas[0]}")
    if len(bad_xy):
        pitch.scatter(bad_xy[:, 0], bad_xy[:, 1], ax=ax, s=60, color="#d62828",
                      marker="X", alpha=0.7, zorder=3, label=f"1er contacto {etiquetas[1]}")
    ax.set_title(f"Primer contacto en córners {lado} — {team}", fontsize=13, pad=10)
    if len(good_xy) or len(bad_xy):
        ax.legend(loc="lower center", fontsize=9)
    fig.text(0.99, 0.005, "Datos: StatsBomb Open Data", ha="right", fontsize=7, color="#888")
    return fig
