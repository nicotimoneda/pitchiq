"""Balón parado (M3): detección de córners y métricas de ataque y defensa.

Convenciones StatsBomb: los eventos vienen en la perspectiva del equipo que los
ejecuta (ataca de izquierda a derecha), así que la portería atacada de un córner
se deriva de la posición del saque — no se asume una orientación fija. Los
freeze-frames arrastran el CAVEAT del área visible (ver metrics/frames.py):
conteos e índices se computan sobre jugadores VISIBLES y son aproximaciones.
"""

import pandas as pd

from pitchiq import config

# Columnas mínimas que necesita el análisis de córners
_CORNER_COLS = ["id", "index", "possession", "team", "location", "pass_end_location"]


def find_corners(
    events: pd.DataFrame, team: str
) -> "tuple[pd.DataFrame, pd.DataFrame]":
    """Córners del partido separados en (atacantes del equipo, defensivos = del rival)."""
    if events.empty or "pass_type" not in events.columns:
        vacio = pd.DataFrame(columns=_CORNER_COLS)
        return vacio, vacio.copy()
    corners = events[
        (events["type"] == "Pass") & (events["pass_type"] == "Corner")
    ]
    cols = [c for c in _CORNER_COLS if c in corners.columns]
    attacking = corners.loc[corners["team"] == team, cols].reset_index(drop=True)
    defensive = corners.loc[corners["team"] != team, cols].reset_index(drop=True)
    return attacking, defensive


def corner_frame(merged: pd.DataFrame, corner_id: str) -> pd.DataFrame:
    """Freeze-frame del momento del saque de un córner (vacío si no hay 360)."""
    if merged.empty:
        return merged
    return merged[merged["event_uuid"] == corner_id]


def attacked_goal_x(corner: pd.Series) -> float:
    """Coordenada x de la portería atacada, derivada de la posición del saque."""
    corner_x = float(corner["location"][0])
    return config.PITCH_LENGTH if corner_x > config.PITCH_LENGTH / 2 else 0.0
