"""Visualización de forma defensiva: bloque medio y altura de línea por partido."""

import matplotlib

matplotlib.use("Agg")  # sin display: los scripts guardan a fichero

import matplotlib.pyplot as plt
import numpy as np
from mplsoccer import Pitch

from pitchiq import config


def plot_defensive_block(
    positions: np.ndarray,
    team: str,
    line_height: float | None = None,
    title: str = "",
) -> plt.Figure:
    """Pinta la forma media del bloque defensivo: densidad de posiciones de
    compañeros visibles en acciones defensivas, centroide y línea defensiva media.

    Los freeze-frames son anónimos (sin id de jugador), así que el "bloque medio"
    es la densidad agregada de posiciones visibles, no una media por jugador.
    """
    pitch = Pitch(pitch_type="statsbomb", line_color="#4a4a4a", line_zorder=2)
    fig, ax = pitch.draw(figsize=(10, 7))

    if len(positions) > 0:
        pitch.kdeplot(
            positions[:, 0],
            positions[:, 1],
            ax=ax,
            fill=True,
            levels=60,
            cmap="Reds",
            alpha=0.75,
            zorder=1,
        )
        cx, cy = positions.mean(axis=0)
        ax.scatter(cx, cy, s=180, marker="x", color="#1a1a1a", zorder=3, linewidth=3)
    if line_height is not None and not np.isnan(line_height):
        ax.axvline(line_height, color="#005ec4", linestyle="--", linewidth=2, zorder=3)
        ax.text(
            line_height + 1, 2, f"línea media: {line_height:.1f}",
            color="#005ec4", fontsize=9, va="bottom",
        )

    ax.set_title(title or f"Bloque defensivo — {team}", fontsize=14, pad=12)
    fig.text(
        0.5, 0.02,
        "solo jugadores visibles en el freeze-frame 360 (aproximación) · ataca →",
        ha="center", fontsize=9, color="#4a4a4a",
    )
    fig.text(
        0.99, 0.005, "Datos: StatsBomb Open Data", ha="right", fontsize=7, color="#888"
    )
    return fig


def plot_line_height_by_match(
    line_heights: "list[float]",
    labels: "list[str]",
    team: str,
    title: str = "",
) -> plt.Figure:
    """Grafica la altura media de la línea defensiva partido a partido.

    ``line_heights`` puede contener NaN (partidos sin 360 suficientes): se
    muestran como huecos, no se interpolan.
    """
    fig, ax = plt.subplots(figsize=(12, 5))
    x = np.arange(len(line_heights))
    y = np.asarray(line_heights, dtype=float)

    ax.plot(x, y, marker="o", color="#d62828", linewidth=1.5)
    if np.isfinite(y).any():
        mean = float(np.nanmean(y))
        ax.axhline(mean, color="#4a4a4a", linestyle="--", linewidth=1)
        ax.text(len(y) - 0.5, mean, f" media {mean:.1f}", va="center", fontsize=9)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=90, fontsize=7)
    ax.set_ylabel("altura de línea defensiva (x, 0-120)")
    ax.set_ylim(0, config.PITCH_LENGTH)
    ax.set_title(title or f"Altura de línea defensiva por partido — {team}", fontsize=13)
    ax.grid(axis="y", alpha=0.3)
    fig.text(
        0.5, 0.005,
        "solo jugadores visibles en el freeze-frame 360 (aproximación)",
        ha="center", fontsize=8, color="#4a4a4a",
    )
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    return fig
