"""Tests de las utilidades puras del precómputo (sin red)."""

import importlib.util
import math

import pandas as pd

from pitchiq import config

_spec = importlib.util.spec_from_file_location(
    "precompute", config.ROOT_DIR / "scripts" / "precompute.py"
)
precompute = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(precompute)


def test_clasificacion_por_puntos_diferencia_y_goles():
    matches = pd.DataFrame(
        [
            {"home_team": "A", "away_team": "B", "home_score": 2, "away_score": 0},
            {"home_team": "C", "away_team": "A", "home_score": 1, "away_score": 1},
            {"home_team": "B", "away_team": "C", "home_score": 3, "away_score": 0},
        ]
    )
    # A: 4 pts (+2) · B: 3 pts (+1) · C: 1 pt (-3)
    assert precompute.clasificacion(matches) == ["A", "B", "C"]


def test_slug_y_temporada():
    assert precompute._slugify("Atlético Madrid 2015/16") == "atletico-madrid-2015-16"
    assert precompute._temporada_corta("2015/2016") == "2015/16"
    assert precompute._temporada_corta("2024") == "2024"


def test_sin_nan_convierte_a_null_sin_tocar_el_resto():
    datos = {"a": math.nan, "b": [1.5, math.nan], "c": {"d": 0.0, "e": "x"}}
    assert precompute._sin_nan(datos) == {"a": None, "b": [1.5, None], "c": {"d": 0.0, "e": "x"}}


def test_temporada_completa_detecta_doble_vuelta():
    equipos = ["A", "B", "C"]
    completa = pd.DataFrame(
        [{"home_team": h, "away_team": a, "home_score": 1, "away_score": 0}
         for h in equipos for a in equipos if h != a]
    )
    assert precompute.temporada_completa(completa)
    # solo los partidos de un equipo (como la Bundesliga 2023/24 del Leverkusen)
    parcial = completa[(completa["home_team"] == "A") | (completa["away_team"] == "A")]
    assert not precompute.temporada_completa(parcial.iloc[:3])


_cat_spec = importlib.util.spec_from_file_location(
    "check_catalogo", config.ROOT_DIR / "scripts" / "check_catalogo.py"
)
check_catalogo = importlib.util.module_from_spec(_cat_spec)
_cat_spec.loader.exec_module(check_catalogo)


def test_catalogo_detecta_temporadas_nuevas_y_360_nuevo():
    base = {"competition_id": 1, "competition_name": "Liga", "season_name": "2024",
            "competition_gender": "male", "match_updated": "x"}
    antes = check_catalogo.resumen([
        {**base, "season_id": 1, "match_available_360": None},
    ])
    ahora = check_catalogo.resumen([
        {**base, "season_id": 1, "match_available_360": "2024-01-01"},
        {**base, "season_id": 2, "season_name": "2025", "match_available_360": None},
    ])
    lineas = check_catalogo.novedades(antes, ahora)
    assert lineas == ["- Ahora con 360: Liga 2024 (`1/1`)", "- Nueva: Liga 2025 (`1/2`)"]
    assert check_catalogo.novedades(ahora, ahora) == []
