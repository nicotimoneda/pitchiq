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
    assert math.isclose(out.hull_area_media_m2, 1600.0)  # cuadrado 40x40
    assert math.isclose(out.anchura_media, 40.0)
    assert math.isclose(out.profundidad_media, 40.0)
    # los 4 compañeros más retrasados: x = 30, 30, 70, 70 -> media 50
    assert math.isclose(out.altura_linea_media, 50.0)


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
    assert math.isclose(out.indice_orientacion_hombre, 3.5)  # proxy heurístico
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
