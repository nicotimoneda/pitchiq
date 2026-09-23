"""Tests de la métrica M1 con eventos sintéticos (sin red)."""

import pandas as pd

from pitchiq.metrics.pressing import defensive_actions, ppda, recovery_zones


def _events(rows: list[dict]) -> pd.DataFrame:
    """DataFrame de eventos sintético con las columnas que usa la métrica."""
    base = {"type": None, "team": None, "location": None, "duel_type": None}
    return pd.DataFrame([{**base, **row} for row in rows])


def test_zonas_conteos_correctos():
    events = _events(
        [
            # dos acciones en la zona (0, 0): esquina inferior izquierda
            {"type": "Ball Recovery", "team": "A", "location": [10, 10]},
            {"type": "Duel", "team": "A", "duel_type": "Tackle", "location": [10, 10]},
            # zona superior derecha
            {"type": "Pressure", "team": "A", "location": [110, 70]},
            # centro de la pista
            {"type": "Interception", "team": "A", "location": [65, 40]},
            # ruido que NO debe contar:
            {"type": "Duel", "team": "A", "duel_type": "Aerial Lost", "location": [10, 10]},
            {"type": "Ball Recovery", "team": "B", "location": [10, 10]},
            {"type": "Pass", "team": "A", "location": [10, 10]},
            {"type": "Pressure", "team": "A", "location": None},
        ]
    )
    zones = recovery_zones(events, "A", grid=(6, 5))

    assert zones.n_x == 6 and zones.n_y == 5
    assert zones.total == 4
    assert zones.counts[0][0] == 2  # (10, 10) -> primera zona en x e y
    assert zones.counts[4][5] == 1  # (110, 70) -> última zona en x e y
    assert zones.counts[2][3] == 1  # (65, 40) -> zona central


def test_ppda_ejemplo_juguete():
    events = _events(
        # 2 acciones defensivas de A en zona de presión (x >= 48)
        [{"type": "Pressure", "team": "A", "location": [60, 40]}] * 2
        # 1 acción fuera de la zona (x < 48): no cuenta para PPDA
        + [{"type": "Ball Recovery", "team": "A", "location": [10, 40]}]
        # 10 pases del rival en su zona de construcción (x <= 72)
        + [{"type": "Pass", "team": "B", "location": [50, 40]}] * 10
        # 2 pases del rival ya en campo contrario (x > 72): no cuentan
        + [{"type": "Pass", "team": "B", "location": [100, 40]}] * 2
    )
    assert ppda(events, "A") == 10 / 2


def test_equipo_sin_acciones_defensivas_no_rompe():
    events = _events([{"type": "Pass", "team": "B", "location": [50, 40]}])
    zones = recovery_zones(events, "A", grid=(6, 5))
    assert zones.total == 0
    assert all(c == 0 for row in zones.counts for c in row)
    assert ppda(events, "A") == float("inf")
    assert defensive_actions(events, "A").empty


def test_eventos_sin_columna_duel_type_no_rompe():
    events = pd.DataFrame(
        [{"type": "Pressure", "team": "A", "location": [60, 40]}]
    )
    assert recovery_zones(events, "A").total == 1


def test_robos_altos_cuenta_posesiones_de_juego_abierto_cerca_del_area():
    from pitchiq.metrics.pressing import high_turnovers

    filas = [
        # posesión 1: robo alto que acaba en tiro
        (1, 1, "A", "Regular Play", "A", "Ball Recovery", [95.0, 40.0]),
        (2, 1, "A", "Regular Play", "A", "Pass", [96.0, 38.0]),
        (3, 1, "A", "Regular Play", "A", "Shot", [108.0, 40.0]),
        # posesión 2: robo en campo propio, no cuenta
        (4, 2, "A", "Regular Play", "A", "Interception", [30.0, 20.0]),
        # posesión 3: robo alto sin tiro (el primer evento con x es del rival)
        (5, 3, "A", "From Counter", "B", "Dispossessed", None),
        (6, 3, "A", "From Counter", "A", "Ball Recovery", [85.0, 10.0]),
        # posesión 4: córner cerca del área, no es un robo
        (7, 4, "A", "From Corner", "A", "Pass", [120.0, 0.0]),
        # posesión 5: del rival
        (8, 5, "B", "Regular Play", "B", "Pass", [100.0, 40.0]),
    ]
    events = pd.DataFrame(filas, columns=["index", "possession", "possession_team",
                                          "play_pattern", "team", "type", "location"])
    assert high_turnovers(events, "A") == {"n": 2, "con_tiro": 1}
    assert high_turnovers(events, "B") == {"n": 1, "con_tiro": 0}
    assert high_turnovers(pd.DataFrame(), "A") == {"n": 0, "con_tiro": 0}
