"""Recuperación de conceptos del glosario para contexto interpretativo.

El retriever alimenta al redactor con QUÉ SIGNIFICAN las métricas, nunca con
sus valores: las cifras del informe siguen saliendo solo de las herramientas.
"""

from pitchiq.rag.knowledge import ConceptEntry
from pitchiq.rag.store import COLLECTION, INDEX_DIR, VectorStore


class Retriever:
    """Recuperación de conceptos relevantes sobre el store vectorial."""

    def __init__(self, store: VectorStore) -> None:
        self._store = store

    def retrieve_concepts(self, query: str, k: int = 3) -> "list[ConceptEntry]":
        """Las k entradas de glosario más relevantes para la consulta."""
        return self._store.search(query, k=k)

    def close(self) -> None:
        """Libera el índice en disco."""
        self._store.close()


def open_default_retriever() -> "Retriever | None":
    """Abre el retriever sobre el índice por defecto; None si aún no está construido."""
    if not (INDEX_DIR / "collection" / COLLECTION).exists():
        return None
    return Retriever(VectorStore())
