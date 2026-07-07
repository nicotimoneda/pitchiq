# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "ragas==0.4.3",
#     "langchain-community<0.4",
#     "anthropic>=0.40",
#     "qdrant-client>=1.12",
#     "sentence-transformers>=3.0",
#     "pyyaml>=6.0",
#     "pydantic>=2.0",
# ]
# ///
"""Evaluación RAGAS del RAG interpretativo (FUERA de CI; cuesta llamadas de LLM).

Corre en un entorno aislado con pins propios, porque ragas es incompatible con
la familia langchain 1.x del proyecto:

    ANTHROPIC_API_KEY=sk-ant-... uv run --script scripts/eval_rag.py
"""

import os
import sys
from pathlib import Path


def main() -> None:
    """Comprueba la key, construye el retriever y corre la evaluación RAGAS."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit(
            "Falta la variable de entorno ANTHROPIC_API_KEY: la evaluación RAGAS "
            "usa un LLM juez de Anthropic y cuesta llamadas de API. Expórtala y "
            "relanza:\n  ANTHROPIC_API_KEY=sk-ant-... uv run --script scripts/eval_rag.py"
        )

    # entorno aislado: pitchiq no está instalado, se importa desde src/
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    import anthropic

    from pitchiq.rag.eval import EVAL_QUESTIONS, run_eval
    from pitchiq.rag.retriever import open_default_retriever

    retriever = open_default_retriever()
    if retriever is None:
        raise SystemExit(
            "no hay índice vectorial; constrúyelo antes con "
            "`uv run python scripts/build_index.py`"
        )

    print(f"evaluando {len(EVAL_QUESTIONS)} preguntas (esto llama al LLM real)...")
    scores = run_eval(retriever, anthropic.Anthropic())
    retriever.close()

    print("\nresultados RAGAS (media sobre el set):")
    for metric, value in scores.items():
        print(f"  {metric}: {value:.3f}")

    # consolidación M7: los resultados alimentan EVALUATION.md
    import json

    results_dir = Path(__file__).resolve().parent.parent / "eval" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    out = results_dir / "ragas.json"
    out.write_text(
        json.dumps(
            {"n_preguntas": len(EVAL_QUESTIONS), "metricas": scores},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    print(f"-> {out}")


if __name__ == "__main__":
    main()
