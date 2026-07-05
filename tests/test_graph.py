"""Tests del grafo y el orquestador con LLMClient mockeado (sin red ni LLM real)."""

from pitchiq.agent.graph import build_graph
from pitchiq.agent.report import generate_report


class MockLLM:
    """LLM falso: devuelve textos fijos y registra lo que se le pidió."""

    def __init__(self, responses: "list[str]") -> None:
        self.responses = responses
        self.prompts: list[str] = []

    def complete(self, system: str, user: str) -> str:
        self.prompts.append(user)
        return self.responses[min(len(self.prompts) - 1, len(self.responses) - 1)]


def test_grafo_produce_informe_y_estado(synthetic_season):
    llm = MockLLM(["El equipo hizo 4 acciones defensivas con un PPDA de 3.33."])
    app = build_graph(llm)
    state = app.invoke({"team": "A"})

    assert state["draft"].startswith("El equipo hizo 4 acciones")
    assert set(state["tool_outputs"]) == {
        "presion", "forma_defensiva", "corners_ataque", "corners_defensa",
    }
    assert state["evidence"]["presion.acciones_defensivas_totales"] == 4.0
    # el LLM recibió las salidas de las herramientas, no datos crudos
    assert "acciones_defensivas_totales" in llm.prompts[0]
    assert len(llm.prompts) == 1  # una sola llamada, sin red


def test_generate_report_grounded_a_la_primera(synthetic_season):
    llm = MockLLM(["El equipo generó 0.3 xG a favor en 1 córner."])
    report = generate_report("A", llm=llm)
    assert report.grounding.is_grounded
    assert report.retries_used == 0
    assert "⚠️" not in report.markdown


def test_generate_report_reintenta_con_cifra_inventada(synthetic_season):
    llm = MockLLM(
        [
            "El equipo ganó 99 duelos y su PPDA fue 3.33.",  # 99 inventado
            "El PPDA del equipo fue 3.33.",  # reescrito, todo respaldado
        ]
    )
    report = generate_report("A", llm=llm)
    assert report.retries_used == 1
    assert report.grounding.is_grounded
    # el feedback del reintento nombra la cifra inventada
    assert "99" in llm.prompts[1]


def test_generate_report_marca_cifras_persistentes(synthetic_season):
    llm = MockLLM(["Inventé el 99 y lo mantengo."])  # nunca se corrige
    report = generate_report("A", llm=llm, max_retries=1)
    assert not report.grounding.is_grounded
    assert report.retries_used == 1
    assert "Aviso del validador de grounding" in report.markdown
    assert "99" in report.markdown
