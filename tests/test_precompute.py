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
