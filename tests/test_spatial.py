"""Tests de las métricas espaciales con freeze-frames sintéticos (sin red)."""

import math

import pandas as pd

from pitchiq.metrics.spatial import (
    defensive_compactness,
    defensive_line_height,
    pressing_support,
    support_distribution,
)


def _fixture(teammate_locs: list, event_type: str = "Ball Recovery"):
    """Un evento defensivo de 'A' con compañeros visibles en esas posiciones."""
    events = pd.DataFrame(
        [{"id": "e1", "type": event_type, "team": "A", "location": [50.0, 40.0]}]
    )
    rows = [
        {"event_uuid": "e1", "match_id": 1, "teammate": True, "actor": False,
         "keeper": False, "location": loc}
        for loc in teammate_locs
    ]
    # ruido presente en todo frame real: actor, portero propio y rivales
    rows += [
        {"event_uuid": "e1", "match_id": 1, "teammate": True, "actor": True,
         "keeper": False, "location": [50.0, 40.0]},
        {"event_uuid": "e1", "match_id": 1, "teammate": True, "actor": False,
         "keeper": True, "location": [2.0, 40.0]},
        {"event_uuid": "e1", "match_id": 1, "teammate": False, "actor": False,
         "keeper": False, "location": [100.0, 40.0]},
    ]
    return pd.DataFrame(rows), events


def test_compacidad_cuadrado_conocido():
    # cuadrado de 40 x 40: área 1600, anchura (y) 40, profundidad (x) 40
    frames, events = _fixture([[30, 20], [30, 60], [70, 20], [70, 60]])
    result = defensive_compactness(frames, events, "A")
    assert result.n_events == 1
    row = result.per_event.iloc[0]
    assert row["n_visible"] == 4
    assert math.isclose(row["hull_area"], 1600.0)
    assert math.isclose(row["width"], 40.0)
    assert math.isclose(row["depth"], 40.0)
    assert math.isclose(result.mean("hull_area"), 1600.0)


def test_compacidad_menos_de_3_visibles_es_nan():
    frames, events = _fixture([[30, 20], [70, 60]])
    result = defensive_compactness(frames, events, "A")
    assert result.n_events == 1
    assert math.isnan(result.per_event.iloc[0]["hull_area"])
    assert math.isnan(result.mean("hull_area"))


def test_altura_de_linea_excluye_portero():
    # 5 visibles: los 4 más retrasados son x = 10, 20, 30, 40 -> media 25
    # el portero en x=2 (del fixture) NO debe entrar en la línea
    frames, events = _fixture([[10, 10], [20, 20], [30, 30], [40, 40], [90, 40]])
    result = defensive_line_height(frames, events, "A", n_defenders=4)
    assert math.isclose(result.per_event.iloc[0]["line_height"], 25.0)
    assert math.isclose(result.mean("line_height"), 25.0)


def test_altura_de_linea_pocos_visibles_es_nan():
    frames, events = _fixture([[10, 10], [20, 20]])
    result = defensive_line_height(frames, events, "A", n_defenders=4)
    assert math.isnan(result.mean("line_height"))


def test_soporte_de_presion_conteo_en_radio():
    # balón en (50, 40): compañeros a 2 m y 8 m dentro, a 15 m fuera;
    # el actor (presionador) no cuenta
    frames, events = _fixture(
        [[52, 40], [50, 48], [50, 55]], event_type="Pressure"
    )
    result = pressing_support(frames, events, "A", radius=10.0)
    assert result.n_events == 1
    assert result.per_event.iloc[0]["support"] == 2
    assert math.isclose(result.mean("support"), 2.0)
    assert support_distribution(result) == {2: 1}


def test_metricas_sin_frames_no_rompen():
    events = pd.DataFrame(
        [{"id": "e1", "type": "Pressure", "team": "A", "location": [50.0, 40.0]}]
    )
    vacio = pd.DataFrame()
    assert defensive_compactness(vacio, events, "A").n_events == 0
    assert math.isnan(defensive_line_height(vacio, events, "A").mean("line_height"))
    result = pressing_support(vacio, events, "A")
    assert math.isnan(result.mean("support"))
    assert support_distribution(result) == {}
