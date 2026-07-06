"""Evaluación RAGAS del RAG interpretativo: fidelidad y relevancia de contexto.

FUERA DE CI: usa un LLM juez (Anthropic) y cuesta llamadas de API. Además,
``ragas`` es incompatible con la familia langchain 1.x del entorno principal,
así que esta evaluación corre en un entorno aislado con pins propios vía
``uv run --script scripts/eval_rag.py`` (ver ese script).
"""

import asyncio
import statistics

from pitchiq.rag.retriever import Retriever

JUDGE_MODEL = "claude-opus-4-8"
ANSWER_MODEL = "claude-opus-4-8"

# Set de evaluación: preguntas de interpretación táctica y el concepto del
# glosario que debería recuperarse como contexto para responderlas.
EVAL_QUESTIONS: "list[dict[str, str]]" = [
    {"pregunta": "¿Qué indica un PPDA bajo sobre la presión de un equipo?",
     "concepto_esperado": "PPDA"},
    {"pregunta": "¿Qué significa que un equipo acumule recuperaciones en campo rival?",
     "concepto_esperado": "zonas de recuperación"},
    {"pregunta": "¿Cómo se interpreta un área de convex hull pequeña en el bloque defensivo?",
     "concepto_esperado": "compacidad defensiva"},
    {"pregunta": "¿Qué riesgo asume un equipo que defiende con la línea muy alta?",
     "concepto_esperado": "altura de línea defensiva"},
    {"pregunta": "¿Qué diferencia hay entre presionar mucho y presionar acompañado?",
     "concepto_esperado": "soporte de presión"},
    {"pregunta": "¿Qué busca un equipo que saca muchos córners en corto?",
     "concepto_esperado": "zonas de saque de córner"},
    {"pregunta": "¿Qué implica cargar el área con muchos atacantes en un córner?",
     "concepto_esperado": "box load"},
    {"pregunta": "¿Por qué importa ganar el primer contacto en un córner a favor?",
     "concepto_esperado": "primer contacto"},
    {"pregunta": "¿Un xG de córner alto garantiza goles a balón parado?",
     "concepto_esperado": "xG de córner"},
    {"pregunta": "¿Se puede afirmar con el MOI que un equipo marca al hombre?",
     "concepto_esperado": "índice de orientación al hombre"},
]

_ANSWER_SYSTEM = (
    "Eres un analista táctico. Responde en dos o tres frases usando SOLO el "
    "contexto provisto. No inventes cifras ni conceptos fuera del contexto."
)


def build_samples(retriever: Retriever, client, k: int = 3) -> "list[dict]":
    """Recupera contextos y genera una respuesta corta por pregunta del set."""
    samples = []
    for item in EVAL_QUESTIONS:
        contexts = [
            e.as_context() for e in retriever.retrieve_concepts(item["pregunta"], k=k)
        ]
        response = client.messages.create(
            model=ANSWER_MODEL,
            max_tokens=300,
            system=_ANSWER_SYSTEM,
            messages=[{
                "role": "user",
                "content": "Contexto:\n" + "\n".join(f"- {c}" for c in contexts)
                + f"\n\nPregunta: {item['pregunta']}",
            }],
        )
        answer = "".join(b.text for b in response.content if b.type == "text")
        samples.append(
            {"pregunta": item["pregunta"], "contextos": contexts, "respuesta": answer}
        )
    return samples


async def _score_samples(samples: "list[dict]") -> "dict[str, float]":
    """Puntúa fidelidad y relevancia de contexto con el LLM juez (RAGAS)."""
    import anthropic
    from ragas.llms import llm_factory
    from ragas.metrics.collections import ContextRelevance, Faithfulness

    judge = llm_factory(
        JUDGE_MODEL, provider="anthropic", client=anthropic.AsyncAnthropic()
    )
    faithfulness = Faithfulness(llm=judge)
    relevance = ContextRelevance(llm=judge)

    faith_scores, rel_scores = [], []
    for s in samples:
        faith = await faithfulness.ascore(
            user_input=s["pregunta"],
            response=s["respuesta"],
            retrieved_contexts=s["contextos"],
        )
        rel = await relevance.ascore(
            user_input=s["pregunta"], retrieved_contexts=s["contextos"]
        )
        faith_scores.append(float(faith.value))
        rel_scores.append(float(rel.value))
    return {
        "faithfulness": statistics.mean(faith_scores),
        "context_relevance": statistics.mean(rel_scores),
    }


def run_eval(retriever: Retriever, client) -> "dict[str, float]":
    """Evalúa el RAG completo: recuperación + respuesta + juicio RAGAS."""
    samples = build_samples(retriever, client)
    return asyncio.run(_score_samples(samples))
