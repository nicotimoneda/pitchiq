"""M1: zonas de recuperación / acciones defensivas de un equipo y PPDA.

Todas las funciones son puras: reciben el DataFrame de eventos de un partido
(con los dos equipos) y el nombre del equipo a analizar, y no tocan red ni disco.
Coordenadas StatsBomb: pista de 120x80, cada equipo ataca de izquierda a derecha.
"""

import numpy as np
import pandas as pd

from pitchiq import config
from pitchiq.data.schema import ZoneGrid

# Tipos de evento que cuentan como acción defensiva (los duelos solo si son tackle)
DEFENSIVE_TYPES = ("Ball Recovery", "Pressure", "Interception")

# Zona de presión para PPDA: se excluye el 40 % de pista más cercano a la
# propia portería del equipo que defiende (definición estándar de Trainor)
PPDA_DEF_MIN_X = 0.4 * config.PITCH_LENGTH  # acciones defensivas con x >= 48
PPDA_OPP_MAX_X = 0.6 * config.PITCH_LENGTH  # pases rivales con x <= 72 (su campo)


def defensive_actions(events: pd.DataFrame, team: str) -> pd.DataFrame:
    """Filtra las acciones defensivas de un equipo con columnas x, y añadidas."""
    is_team = events["team"] == team
    is_defensive = events["type"].isin(DEFENSIVE_TYPES)
    if "duel_type" in events.columns:
        is_defensive |= (events["type"] == "Duel") & (
            events["duel_type"] == "Tackle"
        )
    actions = events.loc[is_team & is_defensive].copy()
    actions = actions[actions["location"].notna()]
    if actions.empty:
        actions["x"] = pd.Series(dtype=float)
        actions["y"] = pd.Series(dtype=float)
        return actions
    xy = np.array(actions["location"].tolist(), dtype=float)
    actions["x"] = xy[:, 0]
    actions["y"] = xy[:, 1]
    return actions


def recovery_zones(
    events: pd.DataFrame, team: str, grid: tuple[int, int] = (6, 5)
) -> ZoneGrid:
    """Agrega las acciones defensivas del equipo en una rejilla n_x x n_y de zonas."""
    n_x, n_y = grid
    actions = defensive_actions(events, team)
    counts, _, _ = np.histogram2d(
        actions["x"],
        actions["y"],
        bins=[n_x, n_y],
        range=[[0, config.PITCH_LENGTH], [0, config.PITCH_WIDTH]],
    )
    # histogram2d devuelve (n_x, n_y); lo transponemos a filas=y, columnas=x
    return ZoneGrid(
        team=team,
        n_x=n_x,
        n_y=n_y,
        counts=counts.T.astype(int).tolist(),
    )


def ppda(events: pd.DataFrame, team: str) -> float:
    """PPDA del equipo en el partido: pases rivales permitidos por acción defensiva.

    Se computa en la zona de presión estándar (sin el 40 % de pista más
    defensivo): menos PPDA = presión más intensa. Devuelve inf si el equipo
    no registra acciones defensivas en esa zona.

    Nota: usamos el mismo conjunto de acciones defensivas que la rejilla
    (incluye Pressure), así que los valores salen más bajos que el PPDA
    clásico estilo Opta (solo tackles/interceptions/challenges). Es
    consistente entre partidos, que es lo que importa para comparar.
    """
    actions = defensive_actions(events, team)
    n_def = int((actions["x"] >= PPDA_DEF_MIN_X).sum())

    opp_passes = events[
        (events["type"] == "Pass")
        & (events["team"] != team)
        & events["location"].notna()
    ]
    if opp_passes.empty:
        n_passes = 0
    else:
        opp_x = np.array(opp_passes["location"].tolist(), dtype=float)[:, 0]
        n_passes = int((opp_x <= PPDA_OPP_MAX_X).sum())

    if n_def == 0:
        return float("inf")
    return n_passes / n_def
