"""Métricas M1-M3 envueltas como herramientas deterministas y tipadas.

Cada herramienta agrega una familia de métricas sobre la temporada del equipo y
devuelve un modelo pydantic cuyos campos numéricos son la ÚNICA fuente de cifras
del informe: el validador de grounding coteja el texto contra ``numeric_values()``.
El LLM nunca ejecuta este código ni calcula nada; solo lee las salidas.
"""

from functools import lru_cache

import numpy as np
import pandas as pd
from pydantic import BaseModel

from pitchiq import config
from pitchiq.data.loader import load_events, load_frames, load_matches
from pitchiq.metrics.frames import merge_frames_events
from pitchiq.metrics.pressing import defensive_actions, ppda, recovery_zones
from pitchiq.metrics.set_pieces import (
    box_load,
    corner_frame,
    corner_xg_against,
    corner_xg_for,
    delivery_zone,
    find_corners,
    first_contact,
    man_orientation_index,
)
from pitchiq.metrics.spatial import (
    defensive_compactness,
    defensive_line_height,
    pressing_support,
)


class ToolInput(BaseModel):
    """Entrada común: el equipo a analizar."""

    team: str = config.DEFAULT_TEAM


class ToolOutput(BaseModel):
    """Base de salida de herramienta: expone sus cifras para el grounding."""

    team: str

    def numeric_values(self) -> "dict[str, float]":
        """Mapa nombre_de_métrica -> valor de todos los campos numéricos."""
        values: dict[str, float] = {}
        for name, value in self.model_dump().items():
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                values[name] = float(value)
            elif isinstance(value, dict):
                for k, v in value.items():
                    if isinstance(v, (int, float)) and not isinstance(v, bool):
                        values[f"{name}.{k}"] = float(v)
        return values


@lru_cache(maxsize=4)
def _season_data(team: str) -> "tuple[tuple[int, pd.DataFrame, pd.DataFrame], ...]":
    """Carga (match_id, eventos, frames) de todos los partidos, cacheado en memoria."""
    matches = load_matches().sort_values("match_date")
    return tuple(
        (int(m["match_id"]), load_events(int(m["match_id"])), load_frames(int(m["match_id"])))
        for _, m in matches.iterrows()
    )


# ---------------------------------------------------------------------------
# M1 — presión por eventos
# ---------------------------------------------------------------------------


class PressingOutput(ToolOutput):
    """Zonas de recuperación + PPDA agregados de la temporada."""

    n_partidos: int
    acciones_defensivas_totales: int
    acciones_defensivas_por_partido: float
    ppda_medio: float
    pct_acciones_campo_rival: float  # % de acciones defensivas con x > 60


def pressing_tool(params: ToolInput) -> PressingOutput:
    """Presión del equipo (M1): volumen de acciones defensivas, dónde, y PPDA medio."""
    totals, ppdas, high = [], [], []
    for _, events, _ in _season_data(params.team):
        zones = recovery_zones(events, params.team)
        totals.append(zones.total)
        match_ppda = ppda(events, params.team)
        if np.isfinite(match_ppda):
            ppdas.append(match_ppda)
        actions = defensive_actions(events, params.team)
        if len(actions):
            high.append((actions["x"] > config.PITCH_LENGTH / 2).mean())
    return PressingOutput(
        team=params.team,
        n_partidos=len(totals),
        acciones_defensivas_totales=int(sum(totals)),
        acciones_defensivas_por_partido=round(float(np.mean(totals)), 1),
        ppda_medio=round(float(np.mean(ppdas)), 2),
        pct_acciones_campo_rival=round(100 * float(np.mean(high)), 1),
    )


# ---------------------------------------------------------------------------
# M2 — forma defensiva (360)
# ---------------------------------------------------------------------------


class ShapeOutput(ToolOutput):
    """Compacidad, altura de línea y soporte de presión (solo jugadores visibles)."""

    hull_area_media_m2: float
    anchura_media: float
    profundidad_media: float
    altura_linea_media: float
    soporte_presion_medio: float
    partidos_con_360: int


def shape_tool(params: ToolInput) -> ShapeOutput:
    """Forma defensiva del equipo (M2), computada sobre freeze-frames 360 visibles."""
    hulls, widths, depths, lines, supports = [], [], [], [], []
    n_con_360 = 0
    for _, events, frames in _season_data(params.team):
        comp = defensive_compactness(frames, events, params.team)
        if comp.n_events == 0:
            continue
        n_con_360 += 1
        hulls.append(comp.mean("hull_area"))
        widths.append(comp.mean("width"))
        depths.append(comp.mean("depth"))
        lines.append(defensive_line_height(frames, events, params.team).mean("line_height"))
        supports.append(pressing_support(frames, events, params.team).mean("support"))
    return ShapeOutput(
        team=params.team,
        hull_area_media_m2=round(float(np.nanmean(hulls)), 0),
        anchura_media=round(float(np.nanmean(widths)), 1),
        profundidad_media=round(float(np.nanmean(depths)), 1),
        altura_linea_media=round(float(np.nanmean(lines)), 1),
        soporte_presion_medio=round(float(np.nanmean(supports)), 2),
        partidos_con_360=n_con_360,
    )


# ---------------------------------------------------------------------------
# M3 — córners
# ---------------------------------------------------------------------------


class CornersAttackOutput(ToolOutput):
    """Córners a favor: zonas de saque, ocupación, primer contacto y xG."""

    n_corners: int
    zonas_saque: "dict[str, int]"
    box_load_atacantes_medio: float
    box_load_defensores_medio: float
    pct_primer_contacto_ganado: float
    xg_a_favor: float


def corners_attack_tool(params: ToolInput) -> CornersAttackOutput:
    """Córners atacantes del equipo (M3) agregados sobre la temporada."""
    zonas: dict[str, int] = {}
    att_box, def_box, contacts, xg = [], [], [], 0.0
    n = 0
    for _, events, frames in _season_data(params.team):
        merged = merge_frames_events(frames, events)
        attacking, _ = find_corners(events, params.team)
        n += len(attacking)
        xg += corner_xg_for(events, params.team)
        for _, c in attacking.iterrows():
            zona = delivery_zone(c)
            zonas[zona] = zonas.get(zona, 0) + 1
            bl = box_load(corner_frame(merged, c["id"]), c)
            if bl is not None:
                att_box.append(bl.n_attackers)
                def_box.append(bl.n_defenders)
            fc = first_contact(events, c)
            if fc is not None:
                contacts.append(fc.won)
    return CornersAttackOutput(
        team=params.team,
        n_corners=n,
        zonas_saque=zonas,
        box_load_atacantes_medio=round(float(np.mean(att_box)), 1),
        box_load_defensores_medio=round(float(np.mean(def_box)), 1),
        pct_primer_contacto_ganado=round(100 * float(np.mean(contacts)), 1),
        xg_a_favor=round(xg, 2),
    )


class CornersDefenseOutput(ToolOutput):
    """Córners en contra: índice de orientación al hombre (PROXY), contacto y xG."""

    n_corners: int
    indice_orientacion_hombre: float  # PROXY heurístico, no clasificador exacto
    pct_primer_contacto_concedido: float
    xg_en_contra: float


def corners_defense_tool(params: ToolInput) -> CornersDefenseOutput:
    """Córners defensivos del equipo (M3); el índice de marcaje es un proxy heurístico."""
    mois, conceded, xg = [], [], 0.0
    n = 0
    for _, events, frames in _season_data(params.team):
        merged = merge_frames_events(frames, events)
        _, defensive = find_corners(events, params.team)
        n += len(defensive)
        xg += corner_xg_against(events, params.team)
        for _, c in defensive.iterrows():
            moi = man_orientation_index(corner_frame(merged, c["id"]), params.team)
            if not np.isnan(moi):
                mois.append(moi)
            fc = first_contact(events, c)
            if fc is not None:
                conceded.append(fc.won)  # lo ganó el rival que saca
    return CornersDefenseOutput(
        team=params.team,
        n_corners=n,
        indice_orientacion_hombre=round(float(np.mean(mois)), 2),
        pct_primer_contacto_concedido=round(100 * float(np.mean(conceded)), 1),
        xg_en_contra=round(xg, 2),
    )


# ---------------------------------------------------------------------------
# Registro de herramientas (lo que ve el grafo y el LLM)
# ---------------------------------------------------------------------------

TOOLS: "dict[str, tuple[str, object]]" = {
    "presion": (
        "Presión del equipo en la temporada: acciones defensivas totales y por "
        "partido, % en campo rival y PPDA medio (menor = presión más intensa; "
        "incluye eventos Pressure, valores más bajos que el PPDA estilo Opta).",
        pressing_tool,
    ),
    "forma_defensiva": (
        "Forma defensiva 360: área media del bloque (convex hull, m²), anchura y "
        "profundidad, altura media de la línea defensiva (x, 0-120) y compañeros "
        "de media a ≤10 m de cada presión. Solo jugadores visibles (aproximación).",
        shape_tool,
    ),
    "corners_ataque": (
        "Córners a favor: total, reparto por zona de saque, atacantes/defensores "
        "visibles en el área al sacar, % de primer contacto ganado y xG generado "
        "(remates con play_pattern From Corner).",
        corners_attack_tool,
    ),
    "corners_defensa": (
        "Córners en contra: total, índice de orientación al hombre (PROXY "
        "heurístico continuo: distancia media en metros al marcador más cercano, "
        "menor = más al hombre), % de primer contacto concedido y xG encajado.",
        corners_defense_tool,
    ),
}


def run_all_tools(team: str) -> "dict[str, ToolOutput]":
    """Ejecuta todas las herramientas para un equipo y devuelve sus salidas tipadas."""
    params = ToolInput(team=team)
    return {name: fn(params) for name, (_, fn) in TOOLS.items()}
