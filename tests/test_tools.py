"""Tests de las herramientas del agente con la temporada sintética (sin red)."""

import math

from pitchiq.agent.tools import (
    CornersAttackOutput,
    CornersDefenseOutput,
    PressingOutput,
    ShapeOutput,
    ToolInput,
    corners_attack_tool,
    corners_defense_tool,
    pressing_tool,
    run_all_tools,
    shape_tool,
)


def test_pressing_tool(synthetic_season):
    out = pressing_tool(ToolInput(team="A"))
    assert isinstance(out, PressingOutput)
    assert out.n_partidos == 1
    assert out.acciones_defensivas_totales == 4  # 3 pressures + 1 recovery
    # PPDA: 10 pases del rival / 3 acciones defensivas en zona de presión
    assert math.isclose(out.ppda_medio, round(10 / 3, 2))
    assert math.isclose(out.pct_acciones_campo_rival, 75.0)


def test_shape_tool(synthetic_season):
    out = shape_tool(ToolInput(team="A"))
    assert isinstance(out, ShapeOutput)
    assert out.partidos_con_360 == 1
    # cuadrado de 40x40 yardas StatsBomb, publicado en metros
    assert math.isclose(out.hull_area_media_m2, round(1600 * 0.9144**2))
    assert math.isclose(out.anchura_media, round(40 * 0.9144, 1))
    assert math.isclose(out.profundidad_media, round(40 * 0.9144, 1))
    # los 4 compañeros más retrasados: x = 30, 30, 70, 70 -> media 50 yardas
    assert math.isclose(out.altura_linea_media, round(50 * 0.9144, 1))


def test_corners_attack_tool(synthetic_season):
    out = corners_attack_tool(ToolInput(team="A"))
    assert isinstance(out, CornersAttackOutput)
    assert out.n_corners == 1
    assert out.zonas_saque == {"centro": 1}
    assert math.isclose(out.box_load_atacantes_medio, 2.0)
    assert math.isclose(out.box_load_defensores_medio, 1.0)
    assert math.isclose(out.pct_primer_contacto_ganado, 100.0)
    assert math.isclose(out.xg_a_favor, 0.3)


def test_corners_defense_tool(synthetic_season):
    out = corners_defense_tool(ToolInput(team="A"))
    assert isinstance(out, CornersDefenseOutput)
    assert out.n_corners == 1
    assert math.isclose(out.indice_orientacion_hombre, round(3.5 * 0.9144, 2))  # proxy, en metros
    assert math.isclose(out.pct_primer_contacto_concedido, 0.0)  # A despejó
    assert math.isclose(out.xg_en_contra, 0.1)


def test_numeric_values_identifica_cada_metrica(synthetic_season):
    outputs = run_all_tools("A")
    assert set(outputs) == {"presion", "forma_defensiva", "corners_ataque", "corners_defensa"}
    values = outputs["corners_ataque"].numeric_values()
    # cada cifra queda identificable por nombre (incluidas las anidadas)
    assert values["zonas_saque.centro"] == 1.0
    assert values["xg_a_favor"] == 0.3
    assert all(isinstance(v, float) for v in values.values())


def test_season_data_filtra_partidos_ajenos_al_equipo(monkeypatch):
    """En un torneo la competición trae partidos de otros equipos: no deben contar."""
    import pandas as pd

    from pitchiq.agent import tools

    tools._season_data.cache_clear()
    matches = pd.DataFrame(
        [
            {"match_id": 1, "match_date": "2024-06-01", "home_team": "A", "away_team": "B"},
            {"match_id": 2, "match_date": "2024-06-02", "home_team": "C", "away_team": "D"},
            {"match_id": 3, "match_date": "2024-06-03", "home_team": "E", "away_team": "A"},
        ]
    )
    monkeypatch.setattr(tools, "load_matches", lambda **kwargs: matches)
    monkeypatch.setattr(tools, "load_events", lambda match_id: pd.DataFrame())
    monkeypatch.setattr(tools, "load_frames", lambda match_id: pd.DataFrame())

    data = tools._season_data("A", 55, 282)
    tools._season_data.cache_clear()
    assert [match_id for match_id, _, _ in data] == [1, 3]
