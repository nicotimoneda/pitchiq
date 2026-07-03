"""Tests del helper de frames 360 con datos sintéticos (sin red)."""

import numpy as np
import pandas as pd

from pitchiq.metrics.frames import merge_frames_events, visible_teammates


def _frames(rows: list[dict]) -> pd.DataFrame:
    base = {"match_id": 1, "teammate": False, "actor": False, "keeper": False}
    return pd.DataFrame([{**base, **row} for row in rows])


def _events(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_merge_une_frames_y_eventos():
    frames = _frames(
        [
            {"event_uuid": "e1", "teammate": True, "location": [10, 10]},
            {"event_uuid": "e1", "location": [20, 20]},
            {"event_uuid": "e2", "teammate": True, "location": [30, 30]},
            {"event_uuid": "huerfano", "location": [40, 40]},  # sin evento: fuera
        ]
    )
    events = _events(
        [
            {"id": "e1", "type": "Pressure", "team": "A", "location": [50, 40]},
            {"id": "e2", "type": "Ball Recovery", "team": "B", "location": [60, 40]},
            {"id": "e3", "type": "Pass", "team": "A", "location": [70, 40]},
        ]
    )
    merged = merge_frames_events(frames, events)
    assert len(merged) == 3  # el frame huérfano no entra
    assert {"event_type", "event_team", "event_location"} <= set(merged.columns)
    assert set(merged["event_uuid"]) == {"e1", "e2"}
    assert (merged.loc[merged["event_uuid"] == "e1", "event_team"] == "A").all()


def test_merge_con_frames_vacios_no_rompe():
    events = _events([{"id": "e1", "type": "Pass", "team": "A", "location": [1, 1]}])
    assert merge_frames_events(pd.DataFrame(), events).empty
    assert merge_frames_events(_frames([]), pd.DataFrame()).empty


def _merged_frame(event_team: str) -> pd.DataFrame:
    """Frame mergeado de un evento de ``event_team`` con compañeros, rival y portero."""
    frames = _frames(
        [
            {"event_uuid": "e1", "teammate": True, "location": [10, 10]},
            {"event_uuid": "e1", "teammate": True, "location": [20, 20]},
            {"event_uuid": "e1", "teammate": True, "actor": True, "location": [50, 40]},
            {"event_uuid": "e1", "teammate": True, "keeper": True, "location": [5, 40]},
            {"event_uuid": "e1", "teammate": False, "location": [90, 70]},
        ]
    )
    events = _events(
        [{"id": "e1", "type": "Pressure", "team": event_team, "location": [50, 40]}]
    )
    return merge_frames_events(frames, events)


def test_visible_teammates_filtra_rivales_actor_y_portero():
    xy = visible_teammates(_merged_frame("A"), "A")
    assert xy.shape == (2, 2)  # fuera el rival, el actor y el portero
    assert sorted(xy[:, 0].tolist()) == [10.0, 20.0]

    con_portero = visible_teammates(_merged_frame("A"), "A", include_keeper=True)
    assert con_portero.shape == (3, 2)


def test_visible_teammates_espeja_en_evento_rival():
    # evento del rival "B": los jugadores de "A" son teammate=False y se espejan
    xy = visible_teammates(_merged_frame("B"), "A")
    assert xy.shape == (1, 2)
    assert np.allclose(xy[0], [120 - 90, 80 - 70])


def test_frame_sin_companeros_visibles_no_rompe():
    frames = _frames([{"event_uuid": "e1", "teammate": False, "location": [90, 70]}])
    events = _events(
        [{"id": "e1", "type": "Pressure", "team": "A", "location": [50, 40]}]
    )
    xy = visible_teammates(merge_frames_events(frames, events), "A")
    assert xy.shape == (0, 2)
