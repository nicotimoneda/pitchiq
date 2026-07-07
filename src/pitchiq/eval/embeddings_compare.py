"""Comparación de modelos de embeddings para el retrieval en español (sin key).

Cuantifica la mejora del cambio de M6 (all-MiniLM-L6-v2 -> multilingüe) con
top-k accuracy sobre el set de preguntas de evaluación: ¿está el concepto
esperado entre los k más cercanos a la pregunta?
"""

import numpy as np

from pitchiq.rag.eval import EVAL_QUESTIONS
from pitchiq.rag.knowledge import ConceptEntry, load_glossary

MODELS = {
    "all-MiniLM-L6-v2 (M5, inglés)": "sentence-transformers/all-MiniLM-L6-v2",
    "paraphrase-multilingual-MiniLM-L12-v2 (M6)": (
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    ),
}


def top_k_accuracy(
    ranked_concepts: "list[list[str]]", expected: "list[str]", k: int
) -> float:
    """Fracción de preguntas cuyo concepto esperado aparece en el top-k."""
    hits = sum(
        any(exp.lower() in c.lower() for c in ranking[:k])
        for ranking, exp in zip(ranked_concepts, expected)
    )
    return hits / len(expected)


def _rank_all(model_name: str, entries: "list[ConceptEntry]") -> "list[list[str]]":
    """Para cada pregunta del set, los conceptos ordenados por similitud coseno."""
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_name)
    corpus = model.encode([e.as_context() for e in entries], normalize_embeddings=True)
    queries = model.encode(
        [q["pregunta"] for q in EVAL_QUESTIONS], normalize_embeddings=True
    )
    order = np.argsort(-(queries @ corpus.T), axis=1)
    return [[entries[j].concepto for j in row] for row in order]


def compare_models() -> dict:
    """Top-1 y top-3 accuracy de cada modelo sobre el set de preguntas."""
    entries = load_glossary()
    expected = [q["concepto_esperado"] for q in EVAL_QUESTIONS]
    results = {}
    for label, model_name in MODELS.items():
        rankings = _rank_all(model_name, entries)
        results[label] = {
            "top1_accuracy": round(top_k_accuracy(rankings, expected, k=1), 3),
            "top3_accuracy": round(top_k_accuracy(rankings, expected, k=3), 3),
        }
    return {"n_preguntas": len(EVAL_QUESTIONS), "modelos": results}
