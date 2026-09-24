"""El contexto RAG NO rompe el grounding: aporta interpretación, nunca cifras."""

import json
import re

from pitchiq import config
from pitchiq.agent.report import generate_report
from pitchiq.rag.knowledge import ConceptEntry

SAMPLE_TEAMS = config.ROOT_DIR / "app" / "static" / "report" / "sample" / "teams"


def _equipos() -> "list[dict]":
    return [json.loads(f.read_text(encoding="utf-8")) for f in sorted(SAMPLE_TEAMS.glob("*.json"))]


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
    """LLM falso que redacta con citas del dossier + interpretación del RAG."""

    def __init__(self) -> None:
        self.last_prompt = ""

    def complete(self, system: str, user: str) -> str:
        self.last_prompt = user
        return ("Presiona con un PPDA de {metrica.ppda}, un valor bajo que indica presión "
                "intensa tras pérdida. En córners, ganar el primer contacto es casi "
                "condición necesaria para rematar.")


def test_contexto_rag_no_rompe_el_grounding():
    equipos, retriever, llm = _equipos(), FakeRetriever(), EchoLLM()
    report = generate_report(equipos[0], equipos, llm=llm, retriever=retriever)
    assert "CONTEXTO INTERPRETATIVO" in llm.last_prompt
    assert retriever.queries  # se recuperó por sección
    assert report.grounding.is_grounded and report.retries_used == 0
    assert report.context  # el contexto queda registrado con el informe


def test_el_contexto_inyectado_no_contiene_cifras():
    equipos, llm = _equipos(), EchoLLM()
    generate_report(equipos[0], equipos, llm=llm, retriever=FakeRetriever())
    contexto = llm.last_prompt.split("CONTEXTO INTERPRETATIVO")[1]
    assert not re.search(r"\d", contexto), "el contexto RAG contiene cifras"


def test_sin_retriever_no_hay_contexto():
    equipos, llm = _equipos(), EchoLLM()
    report = generate_report(equipos[0], equipos, llm=llm)
    assert "CONTEXTO INTERPRETATIVO" not in llm.last_prompt
    assert report.context == {} and report.grounding.is_grounded
