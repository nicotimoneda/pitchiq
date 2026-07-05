"""Fixtures compartidas: una temporada sintética de un partido para el agente."""

import pandas as pd
import pytest


def _synthetic_match() -> "tuple[int, pd.DataFrame, pd.DataFrame]":
    """Un partido A vs B con presión, córners, remates y freeze-frames conocidos."""
    events = pd.DataFrame(
        [
            # presión de A: 3 pressures altas + 1 recovery baja
            {"id": "p1", "index": 1, "possession": 1, "type": "Pressure",
             "team": "A", "location": [70.0, 40.0]},
            {"id": "p2", "index": 2, "possession": 1, "type": "Pressure",
             "team": "A", "location": [70.0, 40.0]},
            {"id": "p3", "index": 3, "possession": 1, "type": "Pressure",
             "team": "A", "location": [70.0, 40.0]},
            {"id": "r1", "index": 4, "possession": 1, "type": "Ball Recovery",
             "team": "A", "location": [30.0, 40.0]},
            # 10 pases del rival en su zona de construcción (para el PPDA)
            *[{"id": f"b{i}", "index": 5, "possession": 1, "type": "Pass",
               "team": "B", "location": [50.0, 40.0]} for i in range(10)],
            # córner a favor de A -> primer contacto ganado (Ball Receipt*)
            {"id": "c1", "index": 10, "possession": 5, "type": "Pass",
             "team": "A", "pass_type": "Corner", "location": [120.0, 0.1],
             "pass_end_location": [115.0, 40.0]},
            {"id": "fc1", "index": 11, "possession": 5, "type": "Ball Receipt*",
             "team": "A", "location": [115.0, 40.0]},
            # córner en contra (saca B) -> despejado por A
            {"id": "c2", "index": 50, "possession": 9, "type": "Pass",
             "team": "B", "pass_type": "Corner", "location": [120.0, 0.1],
             "pass_end_location": [112.0, 40.0]},
            {"id": "fc2", "index": 51, "possession": 9, "type": "Clearance",
             "team": "A", "location": [8.0, 40.0]},
            # remates de córner
            {"id": "s1", "index": 60, "possession": 12, "type": "Shot", "team": "A",
             "play_pattern": "From Corner", "shot_statsbomb_xg": 0.3,
             "location": [110.0, 40.0]},
            {"id": "s2", "index": 61, "possession": 13, "type": "Shot", "team": "B",
             "play_pattern": "From Corner", "shot_statsbomb_xg": 0.1,
             "location": [110.0, 40.0]},
        ]
    )
    base = {"match_id": 1, "teammate": False, "actor": False, "keeper": False}
    frames = pd.DataFrame(
        [
            # frame de una presión de A: cuadrado 40x40 de compañeros
            {**base, "event_uuid": "p1", "teammate": True, "location": [30.0, 20.0]},
            {**base, "event_uuid": "p1", "teammate": True, "location": [30.0, 60.0]},
            {**base, "event_uuid": "p1", "teammate": True, "location": [70.0, 20.0]},
            {**base, "event_uuid": "p1", "teammate": True, "location": [70.0, 60.0]},
            # frame del córner a favor (c1): 2 atacantes y el portero rival en el área
            {**base, "event_uuid": "c1", "teammate": True, "location": [110.0, 40.0]},
            {**base, "event_uuid": "c1", "teammate": True, "location": [115.0, 30.0]},
            {**base, "event_uuid": "c1", "teammate": True, "actor": True,
             "location": [119.0, 20.0]},
            {**base, "event_uuid": "c1", "keeper": True, "location": [119.0, 40.0]},
            {**base, "event_uuid": "c1", "location": [60.0, 40.0]},
            # frame del córner en contra (c2, evento de B): MOI conocido = 3.5
            {**base, "event_uuid": "c2", "teammate": True, "location": [100.0, 40.0]},
            {**base, "event_uuid": "c2", "teammate": True, "location": [110.0, 40.0]},
            {**base, "event_uuid": "c2", "teammate": True, "actor": True,
             "location": [120.0, 0.1]},
            {**base, "event_uuid": "c2", "location": [100.0, 42.0]},
            {**base, "event_uuid": "c2", "location": [110.0, 45.0]},
            {**base, "event_uuid": "c2", "keeper": True, "location": [119.0, 40.0]},
        ]
    )
    return 1, events, frames


@pytest.fixture
def synthetic_season(monkeypatch):
    """Parchea la carga de temporada del agente con el partido sintético."""
    from pitchiq.agent import tools

    match = _synthetic_match()
    monkeypatch.setattr(tools, "_season_data", lambda team: (match,))
    return match
