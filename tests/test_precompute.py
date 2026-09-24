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


def test_traductor_quita_sufijo_femenino():
    traducir = precompute._traductor({"Spain": "España"})
    assert traducir("Spain") == "España"
    assert traducir("Spain Women's") == "España"
    assert traducir("Wales Women's") == "Wales"
    assert traducir("Barcelona") == "Barcelona"


def test_nombre_en_limpia_sufijos_de_statsbomb():
    assert precompute.nombre_en("Spain Women's") == "Spain"
    assert precompute.nombre_en("Wales W") == "Wales"
    assert precompute.nombre_en("RB Leipzig") == "RB Leipzig"


def test_identidad_bandera_para_selecciones_y_colores_para_clubes():
    assert precompute.identidad("Spain") == {"bandera": "es"}
    assert precompute.identidad("England Women's") == {"bandera": "gb-eng"}
    assert precompute.identidad("Norway Women's") == {"bandera": "no"}
    assert precompute.identidad("Barcelona")["colores"]["fondo"] == "#a50044"
    assert precompute.identidad("Equipo inventado") == {}


def test_agregados_medias_y_carriles():
    partidos = [
        {"goles_favor": 2, "goles_contra": 0, "xg_favor": 1.5, "xg_contra": 0.5, "tiros": 10,
         "field_tilt": 60.0, "progresivos": 50, "centros": 10, "robos_altos": 4, "robos_altos_tiro": 1,
         "ppda_clasico": 10.0, "acciones_defensivas": 200, "entradas": {"izquierda": 6, "centro": 2, "derecha": 2}},
        {"goles_favor": 0, "goles_contra": 1, "xg_favor": 0.5, "xg_contra": 1.5, "tiros": 6,
         "field_tilt": 40.0, "progresivos": 30, "centros": 6, "robos_altos": 0, "robos_altos_tiro": 0,
         "ppda_clasico": 14.0, "acciones_defensivas": 180, "entradas": {"izquierda": 4, "centro": 4, "derecha": 2}},
    ]
    tiros = [{"xg": 0.1, "penalti": False}, {"xg": 0.76, "penalti": True}, {"xg": 0.3, "penalti": False}]
    a = precompute.agregados(partidos, tiros)
    assert a["goles_favor"] == 1.0 and a["field_tilt"] == 50.0 and a["tiros"] == 8.0
    assert a["xg_por_tiro"] == 0.2  # sin penaltis
    assert a["robos_altos"] == 2.0 and a["robos_altos_tiro_pct"] == 25.0
    assert a["carriles_pct"] == {"izquierda": 50.0, "centro": 30.0, "derecha": 20.0}


def test_clasificacion_desempata_por_enfrentamiento_directo():
    # A y B acaban con 7 puntos; B tiene mejor diferencia total, pero A ganó el duelo directo
    partidos = pd.DataFrame(
        [
            {"home_team": "A", "away_team": "B", "home_score": 1, "away_score": 0},
            {"home_team": "B", "away_team": "A", "home_score": 2, "away_score": 2},
            {"home_team": "A", "away_team": "C", "home_score": 1, "away_score": 0},
            {"home_team": "B", "away_team": "C", "home_score": 6, "away_score": 0},
            {"home_team": "C", "away_team": "B", "home_score": 0, "away_score": 1},
        ]
    )
    assert precompute.clasificacion(partidos) == ["B", "A", "C"]  # Premier: diferencia de goles
    assert precompute.clasificacion(partidos, directo=True) == ["A", "B", "C"]  # La Liga
