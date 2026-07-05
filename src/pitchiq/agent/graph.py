"""Grafo LangGraph: ejecutar herramientas -> redactar el informe con el LLM.

El principio rector está codificado aquí: el nodo de herramientas es determinista
(el LLM no calcula nada) y el nodo de redacción recibe SOLO las salidas de las
herramientas, con instrucción explícita de no inventar ni derivar cifras.
"""

import json
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from pitchiq.agent.llm import LLMClient
from pitchiq.agent.tools import TOOLS, run_all_tools


class ReportState(TypedDict, total=False):
    """Estado compartido del grafo."""

    team: str
    tool_outputs: dict[str, dict]  # nombre de herramienta -> salida serializada
    evidence: dict[str, float]  # métrica -> valor (para el grounding)
    feedback: str  # cifras no respaldadas de una pasada anterior (reintento)
    draft: str  # borrador del informe en Markdown


WRITER_SYSTEM = """\
Eres un analista táctico de fútbol. Redactas informes de equipo en español, \
en prosa clara y profesional, en formato Markdown.

REGLAS NO NEGOCIABLES sobre las cifras:
- Usa ÚNICAMENTE los valores numéricos provistos en las salidas de herramientas.
- NO calcules, derives ni redondees cifras nuevas (nada de sumas, restas, \
porcentajes o promedios propios). Puedes escribir un valor con coma decimal \
(52,9) o con punto (52.9), pero el número debe ser exactamente uno de los dados.
- Si un dato no está en las salidas, no lo menciones.
- El "índice de orientación al hombre" es un PROXY heurístico sobre jugadores \
visibles: preséntalo siempre como aproximación, nunca como clasificador exacto.
- Las métricas 360 se computan sobre jugadores visibles del freeze-frame: son \
aproximaciones, y así debe leerse el informe.
"""


def _writer_prompt(state: ReportState) -> str:
    """Construye el prompt de usuario para el nodo de redacción."""
    descripciones = "\n".join(
        f"- {name}: {desc}" for name, (desc, _) in TOOLS.items()
    )
    prompt = (
        f"Redacta un informe táctico del {state['team']} (temporada 2023/24) "
        "de 4 a 6 párrafos con tres secciones: presión, forma defensiva y "
        "córners (ataque y defensa). Cada afirmación debe apoyarse en las "
        "cifras provistas.\n\n"
        f"Qué mide cada herramienta:\n{descripciones}\n\n"
        "Salidas de las herramientas (única fuente de cifras permitida):\n"
        f"{json.dumps(state['tool_outputs'], ensure_ascii=False, indent=2)}"
    )
    if state.get("feedback"):
        prompt += (
            "\n\nATENCIÓN: tu borrador anterior contenía cifras que no están en "
            f"las salidas de herramientas: {state['feedback']}. Reescribe el "
            "informe usando solo los valores provistos."
        )
    return prompt


def build_graph(llm: LLMClient):
    """Compila el grafo: run_tools -> write_report."""

    def run_tools(state: ReportState) -> ReportState:
        """Nodo determinista: ejecuta las herramientas y recoge salidas y evidencia."""
        outputs = run_all_tools(state["team"])
        evidence: dict[str, float] = {}
        for name, out in outputs.items():
            for metric, value in out.numeric_values().items():
                evidence[f"{name}.{metric}"] = value
        return {
            "tool_outputs": {k: v.model_dump() for k, v in outputs.items()},
            "evidence": evidence,
        }

    def write_report(state: ReportState) -> ReportState:
        """Nodo de redacción: el LLM escribe SOLO con las salidas provistas."""
        return {"draft": llm.complete(WRITER_SYSTEM, _writer_prompt(state))}

    graph = StateGraph(ReportState)
    graph.add_node("run_tools", run_tools)
    graph.add_node("write_report", write_report)
    graph.add_edge(START, "run_tools")
    graph.add_edge("run_tools", "write_report")
    graph.add_edge("write_report", END)
    return graph.compile()
