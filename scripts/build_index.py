"""CLI: construye el índice vectorial del glosario táctico.

Uso:
    python scripts/build_index.py
"""

from pitchiq.rag.knowledge import load_glossary, review_status
from pitchiq.rag.store import INDEX_DIR, VectorStore


def main() -> None:
    """Indexa el glosario completo en el store local."""
    entries = load_glossary()
    print(review_status(entries))
    store = VectorStore()
    n = store.index_entries(entries)
    store.close()
    print(f"indexadas {n} entradas en {INDEX_DIR}")


if __name__ == "__main__":
    main()
