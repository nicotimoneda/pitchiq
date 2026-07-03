"""Merge de freeze-frames 360 con eventos y extracción de jugadores visibles.

CAVEAT: los freeze-frames solo capturan a los jugadores dentro del área visible
de la retransmisión, no siempre los 22. Toda métrica derivada de aquí se computa
sobre los jugadores VISIBLES y es una aproximación; nunca se asumen 11 por frame.
"""

import numpy as np
import pandas as pd

from pitchiq import config

# Columnas del evento que se acoplan a cada fila de freeze-frame
_EVENT_COLS = {"type": "event_type", "team": "event_team", "location": "event_location"}

MERGED_COLUMNS = [
    "event_uuid",
    "match_id",
    "teammate",
    "actor",
    "keeper",
    "location",
    *_EVENT_COLS.values(),
]


def merge_frames_events(frames_df: pd.DataFrame, events_df: pd.DataFrame) -> pd.DataFrame:
    """Une los freeze-frames con su evento (por id de evento), una fila por jugador."""
    if frames_df.empty or events_df.empty:
        return pd.DataFrame(columns=MERGED_COLUMNS)
    ev = events_df[["id", *_EVENT_COLS]].rename(columns=_EVENT_COLS)
    merged = frames_df.merge(ev, left_on="event_uuid", right_on="id", how="inner")
    return merged.drop(columns="id")


def visible_teammates(
    frame: pd.DataFrame, team: str, include_keeper: bool = False
) -> np.ndarray:
    """Posiciones (n, 2) de los compañeros visibles del equipo en un frame mergeado.

    Excluye rivales, al actor del evento y (por defecto) al portero. Las
    coordenadas del freeze-frame vienen en la perspectiva del equipo del evento;
    si el evento es del rival, se espejan a la perspectiva de ``team``.
    """
    if frame.empty:
        return np.empty((0, 2))
    event_team = frame["event_team"].iloc[0]
    players = frame[frame["teammate"] == (event_team == team)]
    players = players[~players["actor"].astype(bool)]
    if not include_keeper:
        players = players[~players["keeper"].astype(bool)]
    players = players[players["location"].notna()]
    if players.empty:
        return np.empty((0, 2))
    xy = np.array(players["location"].tolist(), dtype=float)[:, :2]
    if event_team != team:  # espejar a la perspectiva del equipo analizado
        xy = np.column_stack(
            [config.PITCH_LENGTH - xy[:, 0], config.PITCH_WIDTH - xy[:, 1]]
        )
    return xy
