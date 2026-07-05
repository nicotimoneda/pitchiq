"""Tests del validador de grounding (puros, sin red ni LLM)."""

import math

from pitchiq.agent.grounding import extract_figures, validate_grounding

EVIDENCE = {
    "forma.altura_linea_media": 52.87,
    "presion.ppda_medio": 2.48,
    "corners.n_corners": 236.0,
}


def test_informe_totalmente_respaldado_ratio_1():
    texto = (
        "El equipo sacó 236 córners con un PPDA de 2.48 "
        "y una línea defensiva en 52,9."
    )
    report = validate_grounding(texto, EVIDENCE)
    assert report.ratio == 1.0
    assert report.is_grounded
    assert all(f.matched_metric for f in report.figures)


def test_cifra_inventada_se_detecta_y_baja_el_ratio():
    texto = "El PPDA fue 2.48 y ganaron 99 duelos aéreos."
    report = validate_grounding(texto, EVIDENCE)
    assert not report.is_grounded
    assert [f.text for f in report.ungrounded] == ["99"]
    assert math.isclose(report.ratio, 0.5)


def test_tolerancia_numerica_redondeo():
    # 52.9 es el redondeo de 52.87 -> respaldada
    assert validate_grounding("línea en 52.9", EVIDENCE).is_grounded
    # 53 es el redondeo a enteros -> respaldada
    assert validate_grounding("línea en 53", EVIDENCE).is_grounded
    # 61.0 no es 52.87 bajo ninguna tolerancia -> no respaldada
    assert not validate_grounding("línea en 61.0", EVIDENCE).is_grounded


def test_coma_decimal_y_anios_excluidos():
    figs = extract_figures("En 2024, temporada 2023/24, el PPDA fue 2,48.")
    assert [(t, v) for t, v in figs] == [("2,48", 2.48)]


def test_texto_sin_cifras_es_grounded():
    report = validate_grounding("El equipo presiona alto y es compacto.", EVIDENCE)
    assert report.ratio == 1.0
    assert report.is_grounded
