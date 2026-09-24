"""Estadísticas por jugador de un equipo en un partido (eventos StatsBomb).

Los minutos se reconstruyen con la alineación (evento Starting XI), los cambios
(Substitution) y las expulsiones: titular desde el minuto 0, suplente desde que
entra, y hasta que sale o termina el partido. Funciones puras, sin red.
"""

import pandas as pd

from pitchiq.metrics.attack import _col, es_progresivo
from pitchiq.metrics.pressing import defensive_actions

CAMPOS = ("minutos", "goles", "asistencias", "tiros", "xg", "pases_clave", "progresivos",
          "presiones", "acciones_defensivas", "recuperaciones")


def _reloj(events: pd.DataFrame):
    """Reloj continuo del partido y su duración total.

    StatsBomb reinicia el minuto en cada parte (45', 90', 105'), así que el
    descuento de una parte se solaparía con el inicio de la siguiente. Se encadena
    cada parte desde su primer hasta su último evento.
    """
    ev = events[_col(events, "period") < 5]
    t = ev["minute"].astype(float) + ev["second"].astype(float) / 60
    inicio, offset, acumulado = {}, {}, 0.0
    for periodo, tp in t.groupby(ev["period"]):
        inicio[periodo], offset[periodo] = float(tp.min()), acumulado
        acumulado += float(tp.max() - tp.min())

    def absoluto(r) -> float:
        p = r.get("period")
        tr = float(r["minute"]) + float(r["second"]) / 60
        return tr - inicio.get(p, 0.0) + offset.get(p, 0.0)

    return absoluto, (acumulado if inicio else 90.0)


def _expulsado(r) -> bool:
    for col in ("bad_behaviour_card", "foul_committed_card"):
        v = r.get(col)
        if isinstance(v, str) and ("Red" in v or "Second Yellow" in v):
            return True
    return False


def player_stats(events: pd.DataFrame, team: str) -> "dict[str, dict]":
    """Estadísticas del partido por jugador del equipo, con su posición principal."""
    reloj, fin = _reloj(events)
    jugadores: dict[str, dict] = {}

    def fila(nombre: str) -> dict:
        return jugadores.setdefault(nombre, {"posicion": None, "_entra": None, "_sale": None,
                                             **dict.fromkeys(CAMPOS, 0)})

    xi = events[(events["type"] == "Starting XI") & (events["team"] == team)]
    for tac in xi["tactics"]:
        for p in (tac or {}).get("lineup", []):
            f = fila(p["player"]["name"])
            f["_entra"], f["posicion"] = 0.0, p["position"]["name"]
    ev = events[events["team"] == team]
    for _, r in ev[ev["type"] == "Substitution"].iterrows():
        t = reloj(r)
        fila(r["player"])["_sale"] = t
        entra = fila(r["substitution_replacement"])
        entra["_entra"] = t
        entra["posicion"] = entra["posicion"] or r.get("position")
    for _, r in ev.iterrows():
        if _expulsado(r) and r.get("player") in jugadores:
            jugadores[r["player"]]["_sale"] = reloj(r)

    con_jugador = ev[ev["player"].notna()]
    for nombre, g in con_jugador.groupby("player"):
        f = fila(nombre)
        tiros = g[(g["type"] == "Shot") & (_col(g, "period") < 5)]
        f["tiros"] = int(len(tiros))
        f["goles"] = int((_col(tiros, "shot_outcome") == "Goal").sum())
        f["xg"] = round(float(_col(tiros, "shot_statsbomb_xg").fillna(0).sum()), 2)
        pases = g[g["type"] == "Pass"]
        f["asistencias"] = int((_col(pases, "pass_goal_assist") == True).sum())  # noqa: E712
        f["pases_clave"] = int(((_col(pases, "pass_shot_assist") == True)  # noqa: E712
                                | (_col(pases, "pass_goal_assist") == True)).sum())  # noqa: E712
        buenos = pases[_col(pases, "pass_outcome").isna()]
        conducciones = g[g["type"] == "Carry"]
        f["progresivos"] = int(
            sum(es_progresivo(a, b) for a, b in zip(buenos["location"], _col(buenos, "pass_end_location")))
            + sum(es_progresivo(a, b) for a, b in zip(conducciones["location"], _col(conducciones, "carry_end_location")))
        )
        f["presiones"] = int((g["type"] == "Pressure").sum())
        f["recuperaciones"] = int((g["type"] == "Ball Recovery").sum())
        if not f["posicion"]:
            pos = g["position"].dropna()
            f["posicion"] = pos.mode().iloc[0] if not pos.empty else None
    # presiones y recuperaciones ya tienen su columna: aquí solo entradas e intercepciones
    acciones = defensive_actions(events, team)
    acciones = acciones[~acciones["type"].isin(("Pressure", "Ball Recovery"))]
    for nombre, n in acciones.groupby("player").size().items():
        fila(nombre)["acciones_defensivas"] = int(n)

    for f in jugadores.values():
        entra, sale = f.pop("_entra"), f.pop("_sale")
        f["minutos"] = round(max(0.0, (sale if sale is not None else fin) - entra), 1) if entra is not None else 0.0
    return jugadores
