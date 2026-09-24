"""Tests de la web en un navegador real (Playwright), sobre las fixtures sample/.

Excluidos por defecto; se lanzan con `uv run pytest -m e2e` (CI los corre en su job).
"""

import re
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import expect

from app.main import REPORT_DIR, create_app

pytestmark = pytest.mark.e2e


def _puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def servidor(tmp_path_factory):
    base: Path = tmp_path_factory.mktemp("web")
    (base / "sample").symlink_to(REPORT_DIR / "sample")
    port = _puerto_libre()
    server = uvicorn.Server(uvicorn.Config(create_app(report_dir=base), port=port, log_level="warning"))
    hilo = threading.Thread(target=server.run, daemon=True)
    hilo.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    hilo.join(timeout=5)


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    # la web elige idioma por el navegador: los tests fijan español salvo que pidan ?lang=en
    return {**browser_context_args, "locale": "es-ES"}


@pytest.fixture
def pagina(page, servidor):
    errores: list[str] = []
    page.on("pageerror", lambda e: errores.append(str(e)))
    page.goto(servidor + "/")
    yield page
    assert errores == [], f"errores de JavaScript: {errores}"


def test_informe_del_analista_con_citas_trazadas(pagina):
    assert pagina.locator("#t-nombre").inner_text() == "Equipo Muestra"
    # el informe del analista manda: cada cifra es una cita resuelta, sin cifras libres
    expect(pagina.locator("#informe-ia-body .cifra.cita")).to_have_count(5)
    assert pagina.locator("#informe-ia-body .cifra.sin").count() == 0
    assert pagina.locator("#resumen-panel").is_hidden()
    expect(pagina.locator("#traza li")).to_have_count(4)
    assert "5 / 5" in pagina.locator("#verif-num").inner_text().replace("\n", " ")
    pagina.locator('#informe-ia-body .cifra[data-k="metrica.ppda"]').focus()
    expect(pagina.locator("#tip")).to_contain_text("metrica.ppda")


def test_equipo_sin_informe_usa_el_resumen_verificado(pagina, servidor):
    pagina.goto(servidor + "/?equipo=equipo-rival")
    assert pagina.locator("#informe-ia").is_hidden()
    assert pagina.locator("#resumen .cifra").count() > 5
    assert pagina.locator("#resumen .cifra.sin").count() == 0
    assert "Cifras verificadas" in pagina.locator("#verif-badge").inner_text()


def test_buscador_cambia_de_equipo_y_la_url(pagina):
    pagina.locator("#buscador-btn").click()
    pagina.locator("#buscador-input").fill("rival")
    pagina.keyboard.press("Enter")
    expect(pagina.locator("#t-nombre")).to_have_text("Equipo Rival")
    expect(pagina).to_have_url(re.compile("equipo=equipo-rival"))
    assert pagina.locator("#buscador-pop").is_hidden()


def test_ficha_de_partido_se_abre_y_navega(pagina):
    pagina.locator("#tabla tbody tr").first.click()
    ficha = pagina.locator("#ficha")
    assert ficha.is_visible()
    assert "J1" in pagina.locator("#ficha-meta").inner_text()
    pagina.locator("#ficha-next").click()
    assert "J2" in pagina.locator("#ficha-meta").inner_text()
    pagina.keyboard.press("Escape")
    assert ficha.is_hidden()


def test_ordenar_la_tabla_por_ppda(pagina):
    pagina.locator('#tabla th[data-k="ppda"] button').click()
    valores = [float(t.replace(",", ".")) for t in pagina.locator("#tabla tbody td:nth-child(8)").all_inner_texts()
               if t.strip() != "—"]
    assert valores == sorted(valores)


def test_tema_se_recuerda_al_recargar(pagina):
    pagina.locator("#btn-tema").click()  # automático -> claro
    assert pagina.evaluate("document.documentElement.dataset.theme") == "light"
    pagina.reload()
    assert pagina.evaluate("document.documentElement.dataset.theme") == "light"


def test_movil_sin_scroll_horizontal(browser, servidor):
    ctx = browser.new_context(viewport={"width": 375, "height": 800})
    p = ctx.new_page()
    p.goto(servidor + "/")
    assert p.evaluate("document.documentElement.scrollWidth") <= 375
    p.locator("#buscador-btn").click()
    assert p.evaluate("document.documentElement.scrollWidth") <= 375
    ctx.close()


def test_version_en_ingles_con_cifras_verificadas(pagina, servidor):
    pagina.goto(servidor + "/?lang=en")
    expect(pagina.locator("#h-informe")).to_have_text("Report")
    assert "Figures verified" in pagina.locator("#verif-badge").inner_text()
    expect(pagina.locator("#informe-ia-body h3").first).to_have_text("Verdict")
    assert pagina.locator('#informe-ia-body .cifra[data-k="metrica.ppda"]').inner_text() == "2.48"
    assert pagina.evaluate("document.documentElement.lang") == "en"
    # el botón vuelve al español y lo recuerda
    pagina.locator("#btn-lang").click()
    expect(pagina.locator("#h-informe")).to_have_text("Informe")


def test_cambiar_de_rival_en_ingles_no_deja_textos_en_espanol(pagina, servidor):
    pagina.goto(servidor + "/?lang=en")
    pagina.locator("#comparar").scroll_into_view_if_needed()
    rival = pagina.locator("#rival option").first.get_attribute("value")
    pagina.locator("#rival").select_option(rival)
    expect(pagina.locator("#estilos-nota")).to_contain_text("click one to compare")
    expect(pagina.locator("#key-estilos")).to_contain_text("(compared)")
    expect(pagina.locator("#key-estilos")).not_to_contain_text("otras competiciones")


def test_filtro_de_partidos_reduce_la_tabla(pagina):
    # Partidos se dibuja diferido (al acercarse o en ratos libres): se espera a que aparezca
    expect(pagina.locator("#tabla tbody tr")).to_have_count(4)
    pagina.locator('#filtro-seg button[data-f="local"]').click()
    expect(pagina.locator("#tabla tbody tr")).to_have_count(2)
    assert "2 de 4" in pagina.locator("#filtro-nota").inner_text()


def test_jugadores_por_90_y_posicion(pagina):
    expect(pagina.locator("#tabla-jug tbody tr")).to_have_count(2)
    pagina.locator('#jug-pos button[data-p="DEF"]').click()
    expect(pagina.locator("#tabla-jug tbody tr")).to_have_count(1)
    assert "Bea Ejemplo" in pagina.locator("#tabla-jug tbody").inner_text()
    pagina.locator('#jug-modo button[data-m="p90"]').click()
    assert "con 270 minutos" in pagina.locator("#jugadores-nota").inner_text()


def test_contexto_segun_el_marcador(pagina):
    pagina.locator('#ctx-seg button[data-c="marcador"]').click()
    texto = pagina.locator("#splits").inner_text()
    assert "Ganando" in texto and "Perdiendo" in texto


def test_percentiles_y_puntos_fuertes(pagina):
    assert pagina.locator("#pct-ataque .pct-row").count() > 0 or pagina.locator("#pct-ataque .pct-head").count() == 1
    assert pagina.locator("#fuertes li").count() >= 1


def test_enlace_directo_a_una_ficha(page, servidor):
    page.goto(servidor + "/?equipo=equipo-muestra#partido-2")
    expect(page.locator("#ficha")).to_be_visible()
    assert "J2" in page.locator("#ficha-meta").inner_text()
    page.keyboard.press("Escape")
    expect(page).not_to_have_url(re.compile("#partido"))


def test_secciones_diferidas_se_dibujan_solas(pagina):
    # sin hacer scroll, las secciones de abajo acaban dibujadas en ratos libres
    expect(pagina.locator("#compare-grid .bar-group").first).to_be_attached()
    expect(pagina.locator("#zonas .bar-row").first).to_be_attached()
