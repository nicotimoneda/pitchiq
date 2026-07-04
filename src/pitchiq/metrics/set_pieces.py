"""Balón parado (M3): detección de córners y métricas de ataque y defensa.

Convenciones StatsBomb: los eventos vienen en la perspectiva del equipo que los
ejecuta (ataca de izquierda a derecha), así que la portería atacada de un córner
se deriva de la posición del saque — no se asume una orientación fija. Los
freeze-frames arrastran el CAVEAT del área visible (ver metrics/frames.py):
conteos e índices se computan sobre jugadores VISIBLES y son aproximaciones.
"""

import numpy as np
import pandas as pd
from pydantic import BaseModel

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


# ---------------------------------------------------------------------------
# Córner atacante
# ---------------------------------------------------------------------------

# Área grande y palos, relativos a la portería atacada (y de la portería: 36-44)
_BOX_DEPTH = 18.0
_BOX_Y = (18.0, 62.0)
_POSTS_Y = (36.0, 44.0)

# Regla de atribución de xG a córner (explícita también en el README):
# un remate se atribuye a córner si su play_pattern es "From Corner".
CORNER_PLAY_PATTERN = "From Corner"

# Tipos de evento que NO son un contacto con el balón (se saltan al buscar
# el primer contacto tras el saque)
_NO_CONTACT_TYPES = {"Pressure", "Dribbled Past", "Dispossessed", "Injury Stoppage"}


def _in_box(x: float, y: float, goal_x: float) -> bool:
    """True si (x, y) cae dentro del área grande de la portería en ``goal_x``."""
    return abs(x - goal_x) <= _BOX_DEPTH and _BOX_Y[0] <= y <= _BOX_Y[1]


def delivery_zone(corner: pd.Series) -> str:
    """Clasifica el saque por su localización final: corto / primer palo / centro / segundo palo.

    "corto" = el balón no acaba dentro del área grande. Primer/segundo palo se
    definen respecto al lado desde el que se saca. "desconocido" si el evento
    no trae localización final.
    """
    end = corner.get("pass_end_location")
    if end is None or (isinstance(end, float) and np.isnan(end)):
        return "desconocido"
    end_x, end_y = float(end[0]), float(end[1])
    if not _in_box(end_x, end_y, attacked_goal_x(corner)):
        return "corto"
    if _POSTS_Y[0] <= end_y <= _POSTS_Y[1]:
        return "centro"
    from_bottom = float(corner["location"][1]) < config.PITCH_WIDTH / 2
    is_near_side = end_y < _POSTS_Y[0] if from_bottom else end_y > _POSTS_Y[1]
    return "primer palo" if is_near_side else "segundo palo"


class BoxLoad(BaseModel):
    """Jugadores visibles dentro del área grande en el momento del saque.

    Conteos sobre VISIBLES (área visible del 360): son cotas inferiores.
    """

    n_attackers: int
    n_defenders: int

    @property
    def differential(self) -> int:
        """Atacantes menos defensores visibles en el área."""
        return self.n_attackers - self.n_defenders


def box_load(frame: pd.DataFrame, corner: pd.Series) -> "BoxLoad | None":
    """Cuenta atacantes y defensores visibles en el área grande al sacar; None sin 360."""
    if frame.empty:
        return None
    goal_x = attacked_goal_x(corner)
    players = frame[frame["location"].notna() & ~frame["actor"].astype(bool)]
    n_att = n_def = 0
    for _, p in players.iterrows():
        x, y = float(p["location"][0]), float(p["location"][1])
        if _in_box(x, y, goal_x):
            if p["teammate"]:
                n_att += 1
            else:
                n_def += 1
    return BoxLoad(n_attackers=n_att, n_defenders=n_def)


class FirstContact(BaseModel):
    """Primer contacto con el balón tras el saque de córner."""

    team: str
    event_type: str
    location: "tuple[float, float]"  # en la perspectiva del equipo que saca
    won: bool  # True si el primer contacto es del equipo que saca


def first_contact(events: pd.DataFrame, corner: pd.Series) -> "FirstContact | None":
    """Equipo y localización del primer contacto tras el saque (None si no lo hay).

    Busca el siguiente evento con contacto de balón por índice (puede abrir una
    posesión nueva si la defensa la gana limpia); si el contacto es del rival,
    su localización se espeja a la perspectiva del equipo que saca.
    """
    after = events[
        (events["index"] > corner["index"])
        & ~events["type"].isin(_NO_CONTACT_TYPES)
        & events["location"].notna()
    ]
    if "ball_receipt_outcome" in after.columns:
        # una recepción fallida no es un toque real
        after = after[
            ~((after["type"] == "Ball Receipt*")
              & (after["ball_receipt_outcome"] == "Incomplete"))
        ]
    after = after.sort_values("index")
    if after.empty:
        return None
    contact = after.iloc[0]
    x, y = float(contact["location"][0]), float(contact["location"][1])
    if contact["team"] != corner["team"]:  # espejar a la perspectiva del saque
        x, y = config.PITCH_LENGTH - x, config.PITCH_WIDTH - y
    return FirstContact(
        team=contact["team"],
        event_type=contact["type"],
        location=(x, y),
        won=contact["team"] == corner["team"],
    )


def corner_xg_for(events: pd.DataFrame, team: str) -> float:
    """xG del equipo en remates atribuidos a córner (play_pattern "From Corner")."""
    if events.empty or "shot_statsbomb_xg" not in events.columns:
        return 0.0
    shots = events[
        (events["type"] == "Shot")
        & (events["team"] == team)
        & (events["play_pattern"] == CORNER_PLAY_PATTERN)
    ]
    return float(shots["shot_statsbomb_xg"].sum())
