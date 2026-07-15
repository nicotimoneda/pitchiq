"""Store vectorial: Qdrant local (persistido en disco, sin servidor) + embeddings locales.

Los embeddings usan sentence-transformers (modelo pequeño, sin API key). El
índice es un artefacto regenerable con scripts/build_index.py y no se versiona.
"""

from pathlib import Path

from pitchiq import config
from pitchiq.rag.knowledge import ConceptEntry

# Historia de esta constante (ver EVALUATION.md): en M6 se cambió al modelo
# multilingüe tras probar a ojo unas consultas en español; al medirlo en M7
# con top-k accuracy resultó ser una regresión (60 % vs 80 % top-1), así que
# se revirtió. Moraleja: medir sobre el set, no validar con ejemplos sueltos.
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
INDEX_DIR = config.ROOT_DIR / "data" / "index"
COLLECTION = "glosario"


class VectorStore:
    """Índice vectorial del glosario sobre Qdrant embebido."""

    def __init__(
        self, path: "Path | str" = INDEX_DIR, model_name: str = EMBEDDING_MODEL
    ) -> None:
        """Abre (o crea) el índice en disco y carga el modelo de embeddings local."""
        from qdrant_client import QdrantClient
        from sentence_transformers import SentenceTransformer

        Path(path).mkdir(parents=True, exist_ok=True)
        self._client = QdrantClient(path=str(path))
        self._model = SentenceTransformer(model_name)

    def _embed(self, texts: "list[str]") -> "list[list[float]]":
        """Embeddings locales de una lista de textos."""
        return self._model.encode(texts, normalize_embeddings=True).tolist()

    def index_entries(self, entries: "list[ConceptEntry]") -> int:
        """(Re)indexa las entradas del glosario; devuelve cuántas indexó."""
        from qdrant_client.models import Distance, PointStruct, VectorParams

        vectors = self._embed([e.as_context() for e in entries])
        if self._client.collection_exists(COLLECTION):
            self._client.delete_collection(COLLECTION)
        self._client.create_collection(
            COLLECTION,
            vectors_config=VectorParams(size=len(vectors[0]), distance=Distance.COSINE),
        )
        self._client.upsert(
            COLLECTION,
            points=[
                PointStruct(id=i, vector=vec, payload=entry.model_dump())
                for i, (entry, vec) in enumerate(zip(entries, vectors))
            ],
        )
        return len(entries)

    def search(self, query: str, k: int = 3) -> "list[ConceptEntry]":
        """Las k entradas del glosario más relevantes para la consulta."""
        if not self._client.collection_exists(COLLECTION):
            raise RuntimeError(
                "el índice vectorial no existe; constrúyelo con "
                "`python scripts/build_index.py`"
            )
        hits = self._client.query_points(
            COLLECTION, query=self._embed([query])[0], limit=k
        ).points
        return [ConceptEntry.model_validate(h.payload) for h in hits]

    def close(self) -> None:
        """Libera el lock del índice en disco."""
        self._client.close()
