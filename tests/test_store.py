"""Tests del store vectorial con entradas sintéticas (embeddings locales, sin LLM)."""

import pytest

from pitchiq.rag.knowledge import ConceptEntry
from pitchiq.rag.store import VectorStore

ENTRADAS = [
    ConceptEntry(
        concepto="presión tras pérdida",
        definicion="Recuperar el balón inmediatamente después de perderlo, "
        "presionando al poseedor rival en campo contrario.",
        interpretacion="Más presión implica recuperaciones más altas.",
    ),
    ConceptEntry(
        concepto="bloque bajo",
        definicion="Defender con todas las líneas replegadas cerca del área propia.",
        interpretacion="Cede la iniciativa y busca defender el espacio a la espalda.",
    ),
    ConceptEntry(
        concepto="saque de esquina al primer palo",
        definicion="Córner dirigido a la zona del poste más cercano al lanzador.",
        interpretacion="Busca remates de cabeza en corto o prolongaciones.",
    ),
]


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    """Store temporal con las entradas sintéticas indexadas."""
    s = VectorStore(path=tmp_path_factory.mktemp("index"))
    assert s.index_entries(ENTRADAS) == 3
    yield s
    s.close()


def test_recupera_la_entrada_mas_relevante(store):
    top = store.search("presionar al rival nada más perder el balón", k=1)
    assert top[0].concepto == "presión tras pérdida"

    top = store.search("córner lanzado al poste cercano", k=1)
    assert top[0].concepto == "saque de esquina al primer palo"


def test_k_limita_los_resultados(store):
    assert len(store.search("defensa", k=2)) == 2


def test_busqueda_sin_indice_falla_claro(tmp_path):
    s = VectorStore(path=tmp_path / "vacio")
    with pytest.raises(RuntimeError, match="build_index"):
        s.search("cualquier cosa")
    s.close()
