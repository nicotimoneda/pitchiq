"""Tests de las métricas de córners con datos sintéticos (sin red)."""

import math

import numpy as np
import pandas as pd

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


def _corner(team: str = "A", loc=None, end=None, index: int = 10) -> pd.Series:
    """Un saque de córner sintético como fila de eventos."""
    return pd.Series(
        {
            "id": "c1",
            "index": index,
            "possession": 5,
            "team": team,
            "type": "Pass",
            "pass_type": "Corner",
            "location": loc or [120.0, 0.1],
            "pass_end_location": end,
        }
    )


def test_find_corners_separa_ataque_y_defensa():
    events = pd.DataFrame(
        [
            _corner(team="A").to_dict(),
            {**_corner(team="B", index=50).to_dict(), "id": "c2"},
            {"id": "p1", "index": 3, "possession": 1, "team": "A", "type": "Pass",
             "pass_type": "Goal Kick", "location": [10, 40], "pass_end_location": [60, 40]},
        ]
    )
    att, dfn = find_corners(events, "A")
    assert list(att["id"]) == ["c1"]  # el goal kick no es córner
    assert list(dfn["id"]) == ["c2"]


def test_find_corners_partido_sin_corners_no_rompe():
    events = pd.DataFrame([{"id": "p1", "type": "Pass", "team": "A"}])
    att, dfn = find_corners(events, "A")
    assert att.empty and dfn.empty


def test_delivery_zone_etiquetas():
    # córner desde abajo (y=0): primer palo = y < 36, segundo palo = y > 44
    assert delivery_zone(_corner(loc=[120, 0.1], end=[118, 30])) == "primer palo"
    assert delivery_zone(_corner(loc=[120, 0.1], end=[116, 40])) == "centro"
    assert delivery_zone(_corner(loc=[120, 0.1], end=[112, 55])) == "segundo palo"
    # fuera del área grande -> corto
    assert delivery_zone(_corner(loc=[120, 0.1], end=[119, 78])) == "corto"
    assert delivery_zone(_corner(loc=[120, 0.1], end=[95, 40])) == "corto"
    # desde arriba (y=80) se invierte el palo
    assert delivery_zone(_corner(loc=[120, 79.9], end=[118, 55])) == "primer palo"
    assert delivery_zone(_corner(loc=[120, 79.9], end=[118, 30])) == "segundo palo"
    # sin localización final
    assert delivery_zone(_corner(end=None)) == "desconocido"


def _frame_rows(rows: list[dict]) -> pd.DataFrame:
    base = {
        "event_uuid": "c1", "match_id": 1, "teammate": False, "actor": False,
        "keeper": False, "event_team": "B", "event_type": "Pass",
        "event_location": [120.0, 0.1],
    }
    return pd.DataFrame([{**base, **r} for r in rows])


def test_box_load_conteos_en_area():
    corner = _corner(team="A")
    frame = _frame_rows(
        [
            # atacantes (teammate del evento): 2 dentro del área, 1 fuera
            {"teammate": True, "location": [110.0, 40.0], "event_team": "A"},
            {"teammate": True, "location": [115.0, 30.0], "event_team": "A"},
            {"teammate": True, "location": [80.0, 40.0], "event_team": "A"},
            # el sacador no cuenta aunque esté cerca del área
            {"teammate": True, "actor": True, "location": [119.0, 20.0], "event_team": "A"},
            # defensores: 1 dentro (el portero cuenta como defensor), 1 fuera
            {"keeper": True, "location": [119.0, 40.0], "event_team": "A"},
            {"location": [60.0, 40.0], "event_team": "A"},
        ]
    )
    bl = box_load(frame, corner)
    assert bl.n_attackers == 2
    assert bl.n_defenders == 1
    assert bl.differential == 1


def test_box_load_sin_frame_devuelve_none():
    assert box_load(pd.DataFrame(), _corner()) is None


def test_first_contact_equipo_y_localizacion():
    corner = _corner(team="A", index=10)
    events = pd.DataFrame(
        [
            corner.to_dict(),
            # presión rival: NO es contacto
            {"id": "x1", "index": 11, "possession": 5, "team": "B",
             "type": "Pressure", "location": [10.0, 40.0]},
            # despeje rival (en SU perspectiva): primer contacto real
            {"id": "x2", "index": 12, "possession": 5, "team": "B",
             "type": "Clearance", "location": [8.0, 34.0]},
            {"id": "x3", "index": 13, "possession": 5, "team": "A",
             "type": "Pass", "location": [90.0, 40.0]},
        ]
    )
    fc = first_contact(events, corner)
    assert fc.team == "B" and not fc.won
    # espejado a la perspectiva del que saca: (120-8, 80-34)
    assert fc.location == (112.0, 46.0)


def test_first_contact_sin_evento_posterior():
    corner = _corner(index=10)
    assert first_contact(pd.DataFrame([corner.to_dict()]), corner) is None


def test_man_orientation_index_media_de_distancias():
    # córner defensivo para "A": saca "B" (evento de B, perspectiva de B)
    # atacantes de B en (100,40) y (110,40); defensores de A en (100,42) y (110,45)
    # distancias al más cercano: 2 y 5 -> media 3.5
    frame = _frame_rows(
        [
            {"teammate": True, "location": [100.0, 40.0]},
            {"teammate": True, "location": [110.0, 40.0]},
            {"teammate": True, "actor": True, "location": [120.0, 0.1]},  # sacador fuera
            {"teammate": False, "location": [100.0, 42.0]},
            {"teammate": False, "location": [110.0, 45.0]},
            # el portero defensor no marca: no cuenta
            {"teammate": False, "keeper": True, "location": [119.0, 40.0]},
        ]
    )
    assert math.isclose(man_orientation_index(frame, "A"), 3.5)


def test_man_orientation_index_sin_visibles_es_nan():
    assert math.isnan(man_orientation_index(pd.DataFrame(), "A"))
    solo_atacantes = _frame_rows([{"teammate": True, "location": [100.0, 40.0]}])
    assert math.isnan(man_orientation_index(solo_atacantes, "A"))


def test_corner_frame_extrae_el_frame_del_saque():
    frame = _frame_rows([{"location": [100.0, 40.0]}])
    assert len(corner_frame(frame, "c1")) == 1
    assert corner_frame(frame, "no-existe").empty


def test_xg_de_corner_por_equipo():
    events = pd.DataFrame(
        [
            {"id": "s1", "type": "Shot", "team": "A", "play_pattern": "From Corner",
             "shot_statsbomb_xg": 0.3},
            {"id": "s2", "type": "Shot", "team": "A", "play_pattern": "Regular Play",
             "shot_statsbomb_xg": 0.5},
            {"id": "s3", "type": "Shot", "team": "B", "play_pattern": "From Corner",
             "shot_statsbomb_xg": 0.1},
        ]
    )
    assert math.isclose(corner_xg_for(events, "A"), 0.3)
    assert math.isclose(corner_xg_against(events, "A"), 0.1)
    assert corner_xg_for(pd.DataFrame(), "A") == 0.0


def test_box_load_con_valores_numpy_nan_en_end_location():
    # pass_end_location NaN (así llega desde el cache JSON) no rompe delivery_zone
    corner = _corner(end=np.nan)
    assert delivery_zone(corner) == "desconocido"
