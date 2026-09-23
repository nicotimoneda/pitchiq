"""Métricas de ataque y de estado del marcador sobre los eventos de un partido.

Funciones puras (sin red ni disco). Coordenadas StatsBomb: campo de 120×80 yardas
y cada equipo ataca hacia x=120, así que "último tercio" es x >= 80 para ambos.
Los umbrales se definen en metros (``config.a_yardas``) y los resultados se
devuelven en unidades sin dimensión (conteos, cuotas) o en xG.
"""

import math

import numpy as np
import pandas as pd

from pitchiq import config

FINAL_THIRD_X = config.PITCH_LENGTH * 2 / 3  # 80 yardas
GOAL = (config.PITCH_LENGTH, config.PITCH_WIDTH / 2)
HALF_X = config.PITCH_LENGTH / 2
# pase o conducción progresiva (criterio de Wyscout, en metros): acercar el balón a la
# portería 30 m en campo propio, 15 m si cruza el medio campo o 10 m en campo rival
PROGRESIVO_M = {"propio": 30.0, "cruza": 15.0, "rival": 10.0}
LANES = ("izquierda", "centro", "derecha")


def _xy(loc) -> "tuple[float, float] | None":
    if isinstance(loc, (list, tuple)) and len(loc) >= 2:
        return float(loc[0]), float(loc[1])
    return None


def _dist_goal(x: float, y: float) -> float:
    return math.hypot(GOAL[0] - x, GOAL[1] - y)


def _col(events: pd.DataFrame, name: str) -> pd.Series:
    return events[name] if name in events.columns else pd.Series(np.nan, index=events.index)


def es_progresivo(start, end) -> bool:
    """True si el movimiento start→end cumple el umbral progresivo de su zona."""
    a, b = _xy(start), _xy(end)
    if a is None or b is None:
        return False
    ganancia = _dist_goal(*a) - _dist_goal(*b)
    if a[0] < HALF_X and b[0] < HALF_X:
        umbral = PROGRESIVO_M["propio"]
    elif a[0] >= HALF_X and b[0] >= HALF_X:
        umbral = PROGRESIVO_M["rival"]
    else:
        umbral = PROGRESIVO_M["cruza"]
    return ganancia >= config.a_yardas(umbral)


def _completados(events: pd.DataFrame, team: str) -> pd.DataFrame:
    """Pases completados y conducciones del equipo, con su inicio y final."""
    is_team = events["team"] == team
    pases = events[is_team & (events["type"] == "Pass") & _col(events, "pass_outcome").isna()]
    pases = pases.assign(fin=_col(pases, "pass_end_location"))
    carries = events[is_team & (events["type"] == "Carry")]
    carries = carries.assign(fin=_col(carries, "carry_end_location"))
    return pd.concat([pases, carries])


def shots(events: pd.DataFrame, team: str) -> "list[dict]":
    """Remates del equipo (sin tanda de penaltis): posición, xG y si fue gol."""
    s = events[(events["team"] == team) & (events["type"] == "Shot") & (_col(events, "period") < 5)]
    out = []
    for _, r in s.iterrows():
        xy = _xy(r["location"])
        if xy is None:
            continue
        out.append({
            "x": round(xy[0], 1), "y": round(xy[1], 1),
            "xg": round(float(r.get("shot_statsbomb_xg") or 0.0), 3),
            "gol": r.get("shot_outcome") == "Goal",
            "penalti": r.get("shot_type") == "Penalty",
        })
    return out


def attack_summary(events: pd.DataFrame, team: str) -> dict:
    """Resumen de ataque de un partido: dominio territorial, progresión y carriles."""
    is_team = events["team"] == team
    pases = events[events["type"] == "Pass"]
    en_ultimo = pases["location"].map(lambda loc: (_xy(loc) or (0, 0))[0] >= FINAL_THIRD_X)
    propios = int((en_ultimo & (pases["team"] == team)).sum())
    ajenos = int((en_ultimo & (pases["team"] != team)).sum())

    mov = _completados(events, team)
    progresivos = int(sum(es_progresivo(a, b) for a, b in zip(mov["location"], mov["fin"])))

    carriles = dict.fromkeys(LANES, 0)
    for a, b in zip(mov["location"], mov["fin"]):
        pa, pb = _xy(a), _xy(b)
        if pa and pb and pa[0] < FINAL_THIRD_X <= pb[0]:
            y = pb[1]
            carriles[LANES[0] if y < 80 / 3 else LANES[1] if y < 160 / 3 else LANES[2]] += 1

    cruces = events[is_team & (events["type"] == "Pass") & (_col(events, "pass_cross") == True)]  # noqa: E712
    return {
        "field_tilt": round(100 * propios / (propios + ajenos), 1) if propios + ajenos else None,
        "progresivos": progresivos,
        "entradas_ultimo_tercio": carriles,
        "centros": int(len(cruces)),
        "centros_completados": int(cruces["pass_outcome"].isna().sum()) if "pass_outcome" in cruces else 0,
    }


def _goles_de(events: pd.DataFrame, team: str) -> pd.Series:
    """Máscara de eventos que suben un gol al marcador de ``team`` (incluye autogoles)."""
    tiro_gol = (events["type"] == "Shot") & (_col(events, "shot_outcome") == "Goal") & (events["team"] == team)
    autogol = (events["type"] == "Own Goal For") & (events["team"] == team)
    return (tiro_gol | autogol) & (_col(events, "period") < 5)


def game_states(events: pd.DataFrame, team: str) -> dict:
    """Minutos y xG a favor/en contra del equipo según vaya ganando, empatando o perdiendo."""
    ev = events[_col(events, "period") < 5].sort_values(["period", "minute", "second", "index"])
    t = ev["minute"].astype(float) + ev["second"].astype(float) / 60
    equipos = [x for x in ev["team"].dropna().unique() if x != team]
    rival = equipos[0] if equipos else None
    propio_goal = _goles_de(ev, team)
    rival_goal = _goles_de(ev, rival) if rival else pd.Series(False, index=ev.index)
    despues = (propio_goal.astype(int) - rival_goal.astype(int)).cumsum()
    nombres = {1: "ganando", 0: "empatando", -1: "perdiendo"}
    # un remate cuenta en el estado previo a él; el tiempo que sigue, en el nuevo
    estado = np.sign(despues.shift(fill_value=0)).map(nombres)
    estado_tiempo = np.sign(despues).map(nombres)

    out = {k: {"minutos": 0.0, "xg_favor": 0.0, "xg_contra": 0.0} for k in ("ganando", "empatando", "perdiendo")}
    # minutos: tiempo entre eventos consecutivos del mismo periodo, asignado al estado vigente
    dt = t.groupby(ev["period"]).diff().shift(-1).fillna(0).clip(lower=0)
    for k in out:
        out[k]["minutos"] = round(float(dt[estado_tiempo == k].sum()), 1)
    tiros = ev[(ev["type"] == "Shot")]
    for idx, r in tiros.iterrows():
        k = estado.loc[idx]
        xg = float(r.get("shot_statsbomb_xg") or 0.0)
        out[k]["xg_favor" if r["team"] == team else "xg_contra"] += xg
    for k in out:
        out[k]["xg_favor"] = round(out[k]["xg_favor"], 2)
        out[k]["xg_contra"] = round(out[k]["xg_contra"], 2)
    return out
