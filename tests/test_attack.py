"""Tests de ataque, estado del marcador y jugadores con eventos sintéticos (sin red)."""

import math

import pandas as pd

from pitchiq.metrics.attack import attack_summary, es_progresivo, game_states, shots
from pitchiq.metrics.players import player_stats

BASE = {"index": 0, "period": 1, "minute": 0, "second": 0, "team": "A", "player": None,
        "type": "Pass", "location": None, "pass_end_location": None, "pass_outcome": None,
        "carry_end_location": None, "pass_cross": None, "pass_shot_assist": None,
        "pass_goal_assist": None, "shot_outcome": None, "shot_statsbomb_xg": None,
        "shot_type": None, "tactics": None, "substitution_replacement": None, "position": None,
        "duel_type": None}


def _ev(rows):
    return pd.DataFrame([{**BASE, "index": i, **r} for i, r in enumerate(rows)])


def test_progresivo_por_zonas_en_metros():
    # campo rival: 10 m (10,9 yardas) más cerca de portería
    assert es_progresivo([90, 40], [102, 40])
    assert not es_progresivo([90, 40], [98, 40])
    # campo propio: hacen falta 30 m (32,8 yardas)
    assert not es_progresivo([10, 40], [40, 40])
    assert es_progresivo([10, 40], [46, 40])  # 36 yardas = 32,9 m en campo propio
    assert es_progresivo([40, 40], [60, 40])  # cruza el medio con 20 yardas (18,3 m)


def test_resumen_de_ataque_tilt_carriles_y_centros():
    events = _ev([
        {"location": [85, 10]}, {"location": [90, 40]}, {"location": [100, 70]},   # A último tercio
        {"team": "B", "location": [95, 40]},                                          # B último tercio
        {"location": [70, 10], "pass_end_location": [85, 10]},                       # entrada izquierda
        {"location": [70, 40], "pass_end_location": [95, 40], "pass_cross": True},   # entrada centro, centro
        {"location": [70, 70], "pass_end_location": [90, 70], "pass_outcome": "Incomplete"},
    ])
    r = attack_summary(events, "A")
    assert r["field_tilt"] == 75.0  # 3 de 4 pases en último tercio son de A (sin contar entradas)  # noqa: E501
    assert r["entradas_ultimo_tercio"] == {"izquierda": 1, "centro": 1, "derecha": 0}
    assert r["centros"] == 1 and r["centros_completados"] == 1


def test_estados_del_marcador_asignan_minutos_y_xg():
    events = _ev([
        {"minute": 0, "location": [60, 40]},
        {"minute": 10, "type": "Shot", "location": [110, 40], "shot_outcome": "Goal", "shot_statsbomb_xg": 0.4},
        {"minute": 30, "team": "B", "type": "Shot", "location": [100, 40], "shot_statsbomb_xg": 0.2},
        {"minute": 45, "location": [60, 40]},
    ])
    e = game_states(events, "A")
    assert math.isclose(e["empatando"]["minutos"], 10.0)
    assert math.isclose(e["ganando"]["minutos"], 35.0)
    assert e["empatando"]["xg_favor"] == 0.4  # el tiro del gol cuenta en el estado previo
    assert e["ganando"]["xg_contra"] == 0.2
    assert [s["gol"] for s in shots(events, "A")] == [True]


def test_minutos_y_estadisticas_por_jugador():
    xi = {"lineup": [{"player": {"name": "Ana"}, "position": {"name": "Center Forward"}},
                     {"player": {"name": "Bea"}, "position": {"name": "Goalkeeper"}}]}
    events = _ev([
        {"type": "Starting XI", "tactics": xi},
        {"minute": 20, "player": "Ana", "type": "Shot", "location": [110, 40],
         "shot_outcome": "Goal", "shot_statsbomb_xg": 0.5},
        {"minute": 30, "player": "Bea", "type": "Pressure", "location": [50, 40]},
        {"minute": 60, "player": "Ana", "type": "Substitution", "substitution_replacement": "Cris"},
        {"minute": 90, "player": "Cris", "type": "Pass", "location": [90, 40],
         "pass_end_location": [105, 40], "pass_shot_assist": True},
    ])
    p = player_stats(events, "A")
    assert p["Ana"]["minutos"] == 60.0 and p["Ana"]["goles"] == 1 and p["Ana"]["xg"] == 0.5
    assert p["Cris"]["minutos"] == 30.0 and p["Cris"]["pases_clave"] == 1 and p["Cris"]["progresivos"] == 1
    assert p["Bea"]["minutos"] == 90.0 and p["Bea"]["presiones"] == 1


def test_minutos_cuentan_el_descuento_de_cada_parte():
    # la 1.ª parte acaba en el 48' (3' de descuento) y el reloj de la 2.ª vuelve a empezar en 45'
    xi = {"lineup": [{"player": {"name": "Ana"}, "position": {"name": "Center Forward"}},
                     {"player": {"name": "Bea"}, "position": {"name": "Goalkeeper"}}]}
    events = _ev([
        {"type": "Starting XI", "tactics": xi},
        {"period": 1, "minute": 0, "location": [60, 40]},
        {"period": 1, "minute": 47, "player": "Ana", "type": "Substitution", "substitution_replacement": "Cris"},
        {"period": 1, "minute": 48, "location": [60, 40]},
        {"period": 2, "minute": 45, "location": [60, 40]},
        {"period": 2, "minute": 90, "location": [60, 40]},
    ])
    p = player_stats(events, "A")
    assert p["Bea"]["minutos"] == 93.0  # 48 de la 1.ª parte + 45 de la 2.ª
    assert p["Ana"]["minutos"] == 47.0
    assert p["Cris"]["minutos"] == 46.0  # 1' de descuento de la 1.ª + la 2.ª entera
