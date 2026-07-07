"""Generalización: las métricas deterministas sobre un torneo distinto (sin key).

Corre el motor de métricas M1-M3 sobre un equipo de la Euro 2024 de StatsBomb
Open Data para demostrar que no está sobreajustado al dataset del Leverkusen.
Los ids de competición/temporada se resuelven dinámicamente del catálogo, no
se hardcodean. Solo métricas: sin LLM, sin RAG, sin key.
"""

import numpy as np

from pitchiq.data.loader import load_events, load_frames
from pitchiq.metrics.pressing import ppda, recovery_zones
from pitchiq.metrics.set_pieces import corner_xg_against, corner_xg_for, find_corners
from pitchiq.metrics.spatial import defensive_compactness, defensive_line_height


def resolve_euro_2024() -> "tuple[int, int]":
    """Busca (competition_id, season_id) de la Euro 2024 en el catálogo abierto."""
    from statsbombpy import sb

    comps = sb.competitions()
    euro = comps[
        comps["competition_name"].str.contains("Euro", case=False)
        & (comps["season_name"] == "2024")
        & (comps["competition_gender"] == "male")
    ]
    if euro.empty:
        raise RuntimeError("no se encontró la Euro 2024 en el catálogo de StatsBomb")
    row = euro.iloc[0]
    return int(row["competition_id"]), int(row["season_id"])


def evaluate_team(team: "str | None" = None) -> dict:
    """Métricas deterministas de un equipo de la Euro 2024 (por defecto, el campeón)."""
    from pitchiq.data.loader import load_matches

    competition_id, season_id = resolve_euro_2024()
    matches = load_matches(competition_id=competition_id, season_id=season_id)

    if team is None:
        # el campeón: ganador del último partido por fecha (la final)
        final = matches.sort_values("match_date").iloc[-1]
        team = (
            final["home_team"]
            if final["home_score"] > final["away_score"]
            else final["away_team"]
        )

    team_matches = matches[
        (matches["home_team"] == team) | (matches["away_team"] == team)
    ]
    ppdas, actions, lines, hulls = [], [], [], []
    corners_for = corners_against = 0
    xg_for = xg_against = 0.0
    con_360 = 0
    for _, m in team_matches.iterrows():
        events = load_events(int(m["match_id"]))
        frames = load_frames(int(m["match_id"]))
        zones = recovery_zones(events, team)
        actions.append(zones.total)
        v = ppda(events, team)
        if np.isfinite(v):
            ppdas.append(v)
        att, dfn = find_corners(events, team)
        corners_for += len(att)
        corners_against += len(dfn)
        xg_for += corner_xg_for(events, team)
        xg_against += corner_xg_against(events, team)
        comp = defensive_compactness(frames, events, team)
        if comp.n_events > 0:
            con_360 += 1
            hulls.append(comp.mean("hull_area"))
            lines.append(defensive_line_height(frames, events, team).mean("line_height"))

    def _mean(xs: list) -> "float | None":
        limpio = [x for x in xs if x is not None and np.isfinite(x)]
        return round(float(np.mean(limpio)), 2) if limpio else None

    return {
        "torneo": "UEFA Euro 2024",
        "competition_id": competition_id,
        "season_id": season_id,
        "equipo": team,
        "n_partidos": int(len(team_matches)),
        "partidos_con_360": con_360,
        "acciones_defensivas_por_partido": _mean(actions),
        "ppda_medio": _mean(ppdas),
        "hull_area_media_m2": _mean(hulls),
        "altura_linea_media": _mean(lines),
        "corners_a_favor": corners_for,
        "corners_en_contra": corners_against,
        "xg_corner_a_favor": round(xg_for, 2),
        "xg_corner_en_contra": round(xg_against, 2),
        "nota": (
            "métricas 360 computadas solo sobre partidos con cobertura de "
            "freeze-frames; la cobertura varía entre torneos y partidos"
        ),
    }
