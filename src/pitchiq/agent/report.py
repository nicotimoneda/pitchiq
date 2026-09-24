"""Orquestador de alto nivel: equipo -> informe de scouting con citas verificadas."""

from pydantic import BaseModel

from pitchiq.agent.graph import build_graph
from pitchiq.agent.grounding import GroundingReport
from pitchiq.agent.llm import LLMClient, cliente_por_defecto


class GroundedReport(BaseModel):
    """Informe final: Markdown con citas {clave} + dossier + verificación."""

    team: str
    idioma: str
    markdown: str  # tal cual lo escribió el modelo, con las citas sin sustituir
    dossier: "dict[str, dict]"
    context: "dict[str, list[str]]"
    grounding: GroundingReport
    retries_used: int


def generate_report(
    team: dict,
    todos: "list[dict]",
    llm: "LLMClient | None" = None,
    idioma: str = "es",
    max_retries: int = 1,
    retriever=None,
) -> GroundedReport:
    """Ejecuta el grafo del analista para un equipo publicado.

    Si tras los reintentos quedan fallos, el informe sale igualmente pero la
    verificación los recoge y la web marca esas cifras como sin respaldo: nunca
    se publica una cifra inventada como si estuviera verificada.
    """
    app = build_graph(llm if llm is not None else cliente_por_defecto(),
                      retriever=retriever, max_retries=max_retries)
    state = app.invoke({"equipo": team, "todos": todos, "idioma": idioma})
    return GroundedReport(
        team=team["nombre"],
        idioma=idioma,
        markdown=state["draft"],
        dossier=state["dossier"],
        context=state.get("context", {}),
        grounding=GroundingReport.model_validate(state["verificacion"]),
        retries_used=state["intentos"] - 1,
    )
