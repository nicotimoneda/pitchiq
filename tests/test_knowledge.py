"""Tests del glosario táctico (sin red)."""

import pytest
from pydantic import ValidationError

from pitchiq.rag.knowledge import (
    ConceptEntry,
    load_glossary,
    review_status,
    unreviewed_count,
)


def test_glosario_carga_y_valida():
    entries = load_glossary()
    assert len(entries) >= 10
    conceptos = " ".join(e.concepto.lower() for e in entries)
    for esperado in ["ppda", "recuperación", "convex hull", "línea defensiva",
                     "soporte", "córner", "box load", "primer contacto", "xg",
                     "orientación al hombre"]:
        assert esperado in conceptos


def test_todas_las_entradas_empiezan_sin_revisar():
    entries = load_glossary()
    assert all(not e.revisado for e in entries)
    # y ninguna fabrica una fuente: vacía o pendiente de revisión
    assert all(
        e.fuente in ("", "pendiente de revisión humana") for e in entries
    )


def test_contador_de_no_revisadas():
    entries = load_glossary()
    assert unreviewed_count(entries) == len(entries)
    assert "EN REVISIÓN" in review_status(entries)
    # si el humano revisa una, el contador baja
    entries[0] = entries[0].model_copy(update={"revisado": True})
    assert unreviewed_count(entries) == len(entries) - 1


def test_el_glosario_no_puede_contener_cifras():
    with pytest.raises(ValidationError, match="dígitos"):
        ConceptEntry(
            concepto="x",
            definicion="una rejilla de 6 por 5 celdas",
            interpretacion="ok",
        )
    with pytest.raises(ValidationError, match="dígitos"):
        ConceptEntry(
            concepto="x",
            definicion="ok",
            interpretacion="un radio de 10 metros",
        )


def test_moi_definido_como_proxy():
    moi = next(e for e in load_glossary() if "orientación al hombre" in e.concepto)
    assert "proxy" in moi.definicion.lower()
    assert "no es un clasificador" in moi.definicion.lower()
