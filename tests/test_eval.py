"""Tests del módulo de evaluación consolidada (sin red, sin LLM)."""

import math

from pitchiq.eval.embeddings_compare import top_k_accuracy
from pitchiq.eval.grounding_check import (
    REPORT_DIR,
    _flatten_tool_outputs,
    evaluate_precomputed_report,
)


def test_top_k_accuracy_con_rankings_conocidos():
    rankings = [
        ["PPDA", "soporte de presión", "bloque"],       # esperado: PPDA -> top-1
        ["bloque", "box load", "primer contacto"],      # esperado: box load -> top-2
        ["línea", "compacidad", "zonas"],               # esperado: MOI -> fuera
    ]
    expected = ["PPDA", "box load", "MOI"]
    assert math.isclose(top_k_accuracy(rankings, expected, k=1), 1 / 3)
    assert math.isclose(top_k_accuracy(rankings, expected, k=3), 2 / 3)


def test_flatten_tool_outputs_incluye_anidados():
    flat = _flatten_tool_outputs(
        {"corners": {"team": "A", "n": 5, "zonas": {"corto": 2}, "ok": True}}
    )
    assert flat == {"corners.n": 5.0, "corners.zonas.corto": 2.0}


def test_grounding_del_informe_servido_es_total():
    """El informe precomputado (real o sample) re-valida a ratio 1.0."""
    resultado = evaluate_precomputed_report(REPORT_DIR)
    assert resultado["ratio_grounding"] == 1.0
    assert resultado["cifras_sueltas"] == []
    assert resultado["cifras_en_el_informe"] > 0
