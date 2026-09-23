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


@pytest.fixture
def pagina(page, servidor):
    errores: list[str] = []
    page.on("pageerror", lambda e: errores.append(str(e)))
    page.goto(servidor + "/")
    yield page
    assert errores == [], f"errores de JavaScript: {errores}"


def test_carga_con_todas_las_cifras_verificadas(pagina):
    assert pagina.locator("#t-nombre").inner_text() == "Equipo Muestra"
    total = pagina.locator("#resumen .cifra").count()
    assert total > 5
    assert pagina.locator("#resumen .cifra.sin").count() == 0
    assert "Cifras verificadas" in pagina.locator("#verif-badge").inner_text()


def test_el_verificador_marca_una_cifra_inventada(pagina):
    caja = pagina.locator("#probar-texto")
    caja.fill("Marcó 999 goles.")
    pagina.wait_for_timeout(300)
    assert pagina.locator("#probar-out .cifra.sin").count() == 1
    assert "sin respaldo" in pagina.locator("#probar-score").inner_text()


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
    valores = [float(t.replace(",", ".")) for t in pagina.locator("#tabla tbody td:nth-child(6)").all_inner_texts()
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
