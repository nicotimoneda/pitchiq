"""Tests del analista (dossier -> redactar <-> verificar) con el LLM mockeado, sin red."""

import json

import pytest

from pitchiq import config
from pitchiq.agent.dossier import construir_dossier, percentil
from pitchiq.agent.graph import build_graph
from pitchiq.agent.grounding import verificar_citas
from pitchiq.agent.report import generate_report

SAMPLE_TEAMS = config.ROOT_DIR / "app" / "static" / "report" / "sample" / "teams"


@pytest.fixture(scope="module")
def equipos() -> "list[dict]":
    return [json.loads(f.read_text(encoding="utf-8")) for f in sorted(SAMPLE_TEAMS.glob("*.json"))]


class MockLLM:
    """LLM falso: devuelve textos fijos y registra lo que se le pidió."""

    def __init__(self, responses: "list[str]") -> None:
        self.responses = responses
        self.prompts: list[str] = []

    def complete(self, system: str, user: str) -> str:
        self.prompts.append(user)
        return self.responses[min(len(self.prompts) - 1, len(self.responses) - 1)]


def test_dossier_trae_balance_metricas_y_jugadores(equipos):
    d = construir_dossier(equipos[0], equipos)
    assert d["resultados.partidos"]["valor"] == 4
    assert d["metrica.ppda"]["valor"] == 2.48
    assert d["jugador.goles"]["valor"] == 3 and "Ana Muestra" in d["jugador.goles"]["es"]
    # con dos equipos no hay grupo para percentiles (hacen falta cinco)
    assert not any(k.startswith("percentil.") for k in d)


def test_percentil_igual_que_la_web():
    equipos = [{"v": v} for v in (1, 2, 3, 4, 5)]
    get = lambda t: t["v"]  # noqa: E731
    assert percentil(equipos[4], get, 1, equipos) == 100
    assert percentil(equipos[2], get, 1, equipos) == 50
    assert percentil(equipos[0], get, -1, equipos) == 100  # menos es mejor
    assert percentil({"v": None}, get, 1, equipos) is None


def test_citas_validas_inventadas_y_cifras_libres(equipos):
    d = construir_dossier(equipos[0], equipos)
    rep = verificar_citas("Ganó {resultados.victorias}, PPDA {metrica.ppda}.", d)
    assert rep.is_grounded and [f.matched_metric for f in rep.figures] == ["resultados.victorias", "metrica.ppda"]
    rep = verificar_citas("Ganó {resultados.titulos} y 2,48 de PPDA en la 2023/24.", d)
    # clave inexistente y cifra libre (aunque coincida con un valor real); la temporada no cuenta
    assert [f.text for f in rep.ungrounded] == ["{resultados.titulos}", "2,48"]


def test_grafo_redacta_con_el_dossier_y_verifica(equipos):
    llm = MockLLM(["### Veredicto\n\nPPDA de {metrica.ppda}."])
    state = build_graph(llm).invoke({"equipo": equipos[0], "todos": equipos, "idioma": "es"})
    assert state["intentos"] == 1 and state["feedback"] == ""
    # el LLM recibió el dossier con claves y valores formateados, no datos crudos
    assert "{metrica.ppda} = 2,48" in llm.prompts[0]
    assert "partidos\": [" not in llm.prompts[0]


def test_reintenta_con_la_lista_de_fallos(equipos):
    llm = MockLLM(["Ganó 99 duelos y {resultados.titulos}.", "PPDA de {metrica.ppda}."])
    rep = generate_report(equipos[0], equipos, llm=llm)
    assert rep.retries_used == 1 and rep.grounding.is_grounded
    assert "99" in llm.prompts[1] and "{resultados.titulos}" in llm.prompts[1]


def test_fallos_persistentes_quedan_registrados(equipos):
    llm = MockLLM(["Inventé el 99 y lo mantengo."])
    rep = generate_report(equipos[0], equipos, llm=llm, max_retries=1)
    assert len(llm.prompts) == 2 and rep.retries_used == 1
    assert [f.text for f in rep.grounding.ungrounded] == ["99"]


def test_informe_en_ingles(equipos):
    llm = MockLLM(["PPDA of {metrica.ppda}."])
    generate_report(equipos[0], equipos, llm=llm, idioma="en")
    assert "{metrica.ppda} = 2.48" in llm.prompts[0] and "inglés" in llm.prompts[0]


def test_percentil_con_clave_que_no_es_percentil(equipos):
    d = construir_dossier(equipos[0], equipos)
    d["percentil.xg"] = {"valor": 90, "decimales": 0, "es": "p", "en": "p"}
    assert verificar_citas("Está en el percentil {percentil.xg}.", d).is_grounded
    rep = verificar_citas("Está en el percentil {metrica.xg}.", d)
    assert [f.text for f in rep.ungrounded] == ["percentil {metrica.xg}"]
