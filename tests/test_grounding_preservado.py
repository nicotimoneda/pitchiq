"""Test explícito de M5: el contexto RAG NO rompe el grounding de M4.

El RAG aporta interpretación (texto sin cifras); las cifras siguen saliendo de
las herramientas y el validador de grounding se aplica igual sobre el informe.
"""

import re

from pitchiq.rag.knowledge import ConceptEntry
from pitchiq.agent.report import generate_report


class FakeRetriever:
    """Retriever falso: sirve entradas de glosario sin tocar disco ni red."""

    def __init__(self) -> None:
        self.queries: list[str] = []
        self._entries = [
            ConceptEntry(
                concepto="PPDA",
                definicion="Pases del rival por acción defensiva propia en zona de presión.",
                interpretacion="Un valor bajo indica presión intensa tras pérdida.",
            ),
            ConceptEntry(
                concepto="primer contacto",
                definicion="Quién toca primero el balón tras el saque de córner.",
                interpretacion="Ganarlo es casi condición necesaria para rematar.",
            ),
        ]

    def retrieve_concepts(self, query: str, k: int = 3) -> "list[ConceptEntry]":
        self.queries.append(query)
        return self._entries[:k]


class EchoLLM:
    """LLM falso que redacta con cifras de las tools + interpretación del RAG."""

    def __init__(self) -> None:
        self.last_prompt = ""

    def complete(self, system: str, user: str) -> str:
        self.last_prompt = user
        return (
            "El equipo registró 4 acciones defensivas con un PPDA de 3.33, un "
            "valor bajo que indica presión intensa tras pérdida. En córners, "
            "ganar el primer contacto es casi condición necesaria para rematar, "
            "y generó 0.3 xG a favor."
        )


def test_contexto_rag_no_rompe_el_grounding(synthetic_season):
    retriever = FakeRetriever()
    report = generate_report("A", llm=(llm := EchoLLM()), retriever=retriever)

    # el redactor recibió el contexto interpretativo del RAG
    assert "CONTEXTO INTERPRETATIVO" in llm.last_prompt
    assert retriever.queries  # se recuperó por sección
    # ... y el informe sigue 100 % grounded: el RAG no metió cifras
    assert report.grounding.is_grounded
    assert report.grounding.ratio == 1.0
    assert report.retries_used == 0
    # el informe queda marcado con la advertencia de glosario en revisión
    assert "EN REVISIÓN" in report.markdown


def test_el_contexto_inyectado_no_contiene_cifras(synthetic_season):
    retriever = FakeRetriever()
    llm = EchoLLM()
    generate_report("A", llm=llm, retriever=retriever)
    contexto = llm.last_prompt.split("CONTEXTO INTERPRETATIVO")[1]
    assert not re.search(r"\d", contexto), "el contexto RAG contiene cifras"


def test_sin_retriever_el_flujo_m4_sigue_igual(synthetic_season):
    llm = EchoLLM()
    report = generate_report("A", llm=llm)
    assert "CONTEXTO INTERPRETATIVO" not in llm.last_prompt
    assert "EN REVISIÓN" not in report.markdown
    assert report.grounding.is_grounded
