"""Tests de la capa de ingesta: descarga (red) y cache (sin red)."""

import pandas as pd
import pytest

from pitchiq import config
from pitchiq.data import loader

MATCH_ID = 3895052  # Bayer Leverkusen 3-2 RB Leipzig, jornada 1


@pytest.mark.network
def test_load_matches_devuelve_34_partidos():
    matches = loader.load_matches()
    assert len(matches) == 34


@pytest.mark.network
def test_load_events_partido_conocido():
    events = loader.load_events(MATCH_ID)
    assert not events.empty
    assert {"type", "team", "player", "location", "minute"} <= set(events.columns)
    # el DataFrame contiene eventos de los dos equipos
    assert set(events["team"].dropna()) == {"Bayer Leverkusen", "RB Leipzig"}


def test_cache_evita_segunda_descarga(tmp_path, monkeypatch):
    """La segunda llamada lee del cache: no vuelve a tocar statsbombpy."""
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
    toy = pd.DataFrame(
        {"match_id": [1, 2], "home_team": ["A", "B"], "away_team": ["B", "A"]}
    )
    monkeypatch.setattr(loader.sb, "matches", lambda **kwargs: toy)

    first = loader.load_matches()
    assert list(first["match_id"]) == [1, 2]

    def _explota(**kwargs):
        raise AssertionError("no debería descargar: el cache existe")

    monkeypatch.setattr(loader.sb, "matches", _explota)
    second = loader.load_matches()
    assert list(second["match_id"]) == [1, 2]


def test_load_frames_sin_360_devuelve_vacio(tmp_path, monkeypatch):
    """Un partido sin datos 360 no rompe: devuelve DataFrame vacío sin cachearlo."""
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)

    def _sin_360(**kwargs):
        raise ValueError("404: no 360 data")

    monkeypatch.setattr(loader.sb, "frames", _sin_360)
    with pytest.warns(UserWarning, match="sin datos 360"):
        frames = loader.load_frames(999999)
    assert frames.empty
    assert not (tmp_path / "frames_999999.json").exists()
