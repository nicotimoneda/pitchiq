"""Helpers de visualización sobre pista mplsoccer."""

import matplotlib

matplotlib.use("Agg")  # sin display: los scripts guardan a fichero

import matplotlib.pyplot as plt
from mplsoccer import Pitch


def plot_zone_heatmap(
    x: "list[float]",
    y: "list[float]",
    grid: tuple[int, int] = (6, 5),
    title: str = "",
    subtitle: str = "",
) -> plt.Figure:
    """Pinta un heatmap de zonas (con conteos anotados) a partir de coordenadas.

    ``x``/``y`` en coordenadas StatsBomb (120x80) del equipo analizado, que
    ataca de izquierda a derecha. ``grid`` = (zonas a lo largo, zonas a lo ancho).
    """
    pitch = Pitch(pitch_type="statsbomb", line_color="#4a4a4a", line_zorder=2)
    fig, ax = pitch.draw(figsize=(10, 7))

    stats = pitch.bin_statistic(x, y, statistic="count", bins=grid)
    pitch.heatmap(stats, ax=ax, cmap="Reds", edgecolors="#ffffff", alpha=0.85)
    pitch.label_heatmap(
        stats,
        ax=ax,
        color="#1a1a1a",
        fontsize=11,
        va="center",
        ha="center",
        str_format="{:.0f}",
    )

    if title:
        ax.set_title(title, fontsize=14, pad=12)
    if subtitle:
        fig.text(0.5, 0.02, subtitle, ha="center", fontsize=10, color="#4a4a4a")
    fig.text(
        0.99, 0.005, "Datos: StatsBomb Open Data", ha="right", fontsize=7, color="#888"
    )
    return fig
