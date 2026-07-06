"""Orquestador de alto nivel: equipo -> informe táctico grounded + evidencia."""

from pydantic import BaseModel, ConfigDict

from pitchiq.agent.graph import build_graph
from pitchiq.agent.grounding import GroundingReport, validate_grounding
from pitchiq.agent.llm import AnthropicClient, LLMClient


class GroundedReport(BaseModel):
    """Informe final: Markdown + evidencia de herramientas + check de grounding."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    team: str
    markdown: str
    tool_outputs: "dict[str, dict]"
    evidence: "dict[str, float]"
    grounding: GroundingReport
    retries_used: int


def generate_report(
    team: str,
    llm: "LLMClient | None" = None,
    max_retries: int = 1,
    retriever=None,
) -> GroundedReport:
    """Ejecuta el grafo, valida el grounding y reintenta una vez si hay cifras sueltas.

    Si se pasa un ``retriever`` (M5), el redactor recibe contexto interpretativo
    del glosario — nunca cifras — y el informe queda marcado con la advertencia
    de glosario en revisión. Si tras el reintento quedan cifras sin respaldo, el
    informe sale marcado con una advertencia explícita al pie — nunca se publica
    una cifra inventada como si estuviera verificada.
    """
    llm = llm if llm is not None else AnthropicClient()
    app = build_graph(llm, retriever=retriever)
    state = app.invoke({"team": team})
    grounding = validate_grounding(state["draft"], state["evidence"])

    retries = 0
    while not grounding.is_grounded and retries < max_retries:
        retries += 1
        # reintento: se re-invoca el grafo con feedback de las cifras sueltas
        # (las herramientas son deterministas y están cacheadas en memoria)
        state = app.invoke(
            {
                "team": team,
                "feedback": ", ".join(f.text for f in grounding.ungrounded),
            }
        )
        grounding = validate_grounding(state["draft"], state["evidence"])

    markdown = state["draft"]
    if state.get("context"):
        markdown += (
            "\n\n> ℹ️ Las interpretaciones tácticas de este informe se apoyan en "
            "un glosario EN REVISIÓN (borrador redactado por IA, pendiente de "
            "revisión humana) y no son autoritativas. Las cifras provienen "
            "exclusivamente de métricas computadas y están validadas por el "
            "check de grounding."
        )
    if not grounding.is_grounded:
        sueltas = ", ".join(f.text for f in grounding.ungrounded)
        markdown += (
            "\n\n> ⚠️ **Aviso del validador de grounding**: las siguientes cifras "
            f"no coinciden con ninguna salida de herramienta: {sueltas}. "
            "Trátalas como no verificadas."
        )

    return GroundedReport(
        team=team,
        markdown=markdown,
        tool_outputs=state["tool_outputs"],
        evidence=state["evidence"],
        grounding=grounding,
        retries_used=retries,
    )
