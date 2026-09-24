"""Grafo LangGraph del analista: dossier -> contexto -> redactar <-> verificar.

El principio rector está codificado aquí: el dossier es determinista (el LLM no
calcula nada), el redactor no escribe cifras sino citas a claves del dossier, y
un verificador comprueba cada cita. Si hay citas inventadas o cifras libres, el
grafo vuelve al redactor con la lista exacta de fallos (hasta ``max_retries``).
"""

import json
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from pitchiq.agent.dossier import construir_dossier, formatear
from pitchiq.agent.grounding import verificar_citas
from pitchiq.agent.llm import LLMClient


class ReportState(TypedDict, total=False):
    """Estado compartido del grafo."""

    equipo: dict  # datos precomputados del equipo (teams/<slug>.json)
    todos: "list[dict]"  # todos los equipos publicados (para los percentiles)
    idioma: str  # "es" | "en"
    dossier: "dict[str, dict]"  # clave -> valor y etiquetas: única fuente de cifras
    context: "dict[str, list[str]]"  # sección -> conceptos interpretativos (RAG)
    draft: str  # borrador en Markdown, con citas {clave}
    verificacion: dict  # GroundingReport serializado de la última pasada
    feedback: str  # fallos de la pasada anterior (reintento)
    intentos: int  # llamadas al redactor


# Consultas de recuperación por sección: el RAG aporta QUÉ SIGNIFICAN las
# métricas de cada sección, nunca sus valores.
SECTION_QUERIES = {
    "ataque": "dominio territorial, acciones progresivas, calidad de las ocasiones (xG por tiro)",
    "presión": "presión tras pérdida, PPDA, robos altos, zonas de recuperación del balón",
    "forma defensiva": "compacidad del bloque, altura de la línea defensiva, soporte de presión",
    "córners": "saques de córner, ocupación del área, primer contacto, marcaje al hombre o zonal",
}

IDIOMAS = {"es": "español", "en": "inglés (británico, terminología de fútbol)"}

WRITER_SYSTEM = """\
Eres el analista jefe de un cuerpo técnico de fútbol. Escribes el informe de \
scouting de un equipo para el entrenador que va a enfrentarse a él: directo, \
táctico y accionable, en Markdown.

REGLA DE CIFRAS (no negociable): NUNCA escribas un dígito. Toda cifra del \
informe se escribe como una cita a una clave del dossier entre llaves, por \
ejemplo "presiona con un PPDA de {metrica.ppda}". El sistema sustituye cada \
cita por su valor exacto y rechaza el informe si aparece un dígito suelto o \
una clave que no existe.
- Solo puedes citar claves que aparezcan en el dossier, tal cual.
- No calcules nada: ni diferencias, ni sumas, ni porcentajes, ni medias. Si \
quieres comparar, usa los percentiles del dossier o palabras ("muy por \
encima", "de los más bajos") solo cuando los percentiles lo respalden.
- Cita el valor junto a su unidad correcta según la etiqueta (%, m, m²).
- Tampoco escribas cantidades con letras para esquivar la regla.

Ejemplo correcto: "Ganó {resultados.victorias} de sus {resultados.partidos} \
partidos y su xG por partido, {metrica.xg}, está en el percentil \
{percentil.xg} de su grupo."
Ejemplo INCORRECTO (será rechazado): "Ganó 28 de sus 34 partidos." \
Aunque el número sea verdad, escribirlo a mano es un error: usa siempre la cita.

REGLA DE FUENTES: usa solo el dossier y el contexto interpretativo. No uses \
conocimiento externo del equipo (entrenador, sistema, fichajes, lesiones, \
resultados conocidos): el lector tiene que poder comprobar cada afirmación.

Criterio de lectura de percentiles: 90 o más, élite en su grupo; 75 o más, \
punto fuerte; 25 o menos, punto débil; 10 o menos, carencia clara. En los \
rasgos de estilo el percentil describe, no califica. Las métricas de \
posiciones (altura de línea, bloque, distancia al marcador) son aproximaciones \
sobre los jugadores visibles: preséntalas así.

Estructura, con estos encabezados de nivel 3 (###) y sin numerarlos:
- Veredicto: dos o tres frases con la identidad del equipo y su nivel.
- Con balón: cómo ataca y por dónde.
- Sin balón: presión, bloque y lo que concede.
- Balón parado.
- Jugadores clave.
- Cómo hacerle daño: tres o cuatro viñetas con un plan de partido concreto \
contra este equipo, cada una apoyada en una debilidad o un rasgo del dossier.
Entre 350 y 500 palabras. Sin introducciones ni despedidas.
"""


def _writer_prompt(state: ReportState) -> str:
    """Prompt de usuario del redactor: dossier, contexto y fallos a corregir."""
    team, idioma = state["equipo"], state.get("idioma", "es")
    lineas = "\n".join(
        f"{{{k}}} = {formatear(e, idioma)} — {e[idioma]}" for k, e in state["dossier"].items()
    )
    prompt = (
        f"Equipo: {team['nombre']} · {team['competicion']} {team['temporada']}.\n"
        f"Idioma del informe: {IDIOMAS[idioma]}.\n\n"
        f"DOSSIER (única fuente de cifras; cita las claves entre llaves):\n{lineas}"
    )
    if state.get("context"):
        bloques = "\n".join(
            f"[{seccion}]\n" + "\n".join(f"- {c}" for c in conceptos)
            for seccion, conceptos in state["context"].items()
        )
        prompt += (
            "\n\nCONTEXTO INTERPRETATIVO (glosario táctico EN REVISIÓN, no "
            "autoritativo): úsalo SOLO para explicar qué significan los valores "
            f"en términos futbolísticos. No es fuente de cifras.\n{bloques}"
        )
    if state.get("feedback"):
        prompt += (
            "\n\nATENCIÓN: el verificador rechazó tu borrador anterior por "
            f"{state['feedback']}. Reescríbelo entero corrigiendo esos puntos: "
            "cada cifra, como cita a una clave existente del dossier."
        )
    return prompt


def _nombres(team: dict) -> "list[str]":
    """Nombres propios con dígitos del equipo, que no cuentan como cifras."""
    return [team.get("nombre", ""), team.get("equipo", ""), team.get("competicion", "")]


def build_graph(llm: LLMClient, retriever=None, max_retries: int = 1):
    """Compila el grafo: dossier -> contexto (si hay RAG) -> redactar <-> verificar."""

    def dossier(state: ReportState) -> ReportState:
        """Nodo determinista: todas las cifras que el informe puede citar."""
        return {"dossier": construir_dossier(state["equipo"], state["todos"]), "intentos": 0}

    def retrieve_context(state: ReportState) -> ReportState:
        """Nodo RAG: conceptos interpretativos por sección (nunca cifras)."""
        return {"context": {
            seccion: [e.as_context() for e in retriever.retrieve_concepts(query, k=3)]
            for seccion, query in SECTION_QUERIES.items()
        }}

    def redactar(state: ReportState) -> ReportState:
        """Nodo LLM: escribe el informe citando claves, sin cifras propias."""
        return {"draft": llm.complete(WRITER_SYSTEM, _writer_prompt(state)),
                "intentos": state["intentos"] + 1}

    def verificar(state: ReportState) -> ReportState:
        """Nodo determinista: cada cita debe existir y no puede haber cifras libres."""
        rep = verificar_citas(state["draft"], state["dossier"], ignore=_nombres(state["equipo"]))
        fallos = [f.text for f in rep.ungrounded]
        feedback = ""
        if fallos:
            inventadas = [t for t in fallos if t.startswith("{")]
            libres = [t for t in fallos if not t.startswith("{")]
            partes = []
            if inventadas:
                partes.append("citar claves que no existen: " + ", ".join(inventadas))
            if libres:
                partes.append("escribir cifras sueltas: " + ", ".join(libres))
            feedback = " y ".join(partes)
        return {"verificacion": json.loads(rep.model_dump_json()), "feedback": feedback}

    def siguiente(state: ReportState) -> str:
        return "redactar" if state["feedback"] and state["intentos"] <= max_retries else END

    graph = StateGraph(ReportState)
    graph.add_node("dossier", dossier)
    graph.add_node("redactar", redactar)
    graph.add_node("verificar", verificar)
    graph.add_edge(START, "dossier")
    if retriever is not None:
        graph.add_node("retrieve_context", retrieve_context)
        graph.add_edge("dossier", "retrieve_context")
        graph.add_edge("retrieve_context", "redactar")
    else:
        graph.add_edge("dossier", "redactar")
    graph.add_edge("redactar", "verificar")
    graph.add_conditional_edges("verificar", siguiente, ["redactar", END])
    return graph.compile()
