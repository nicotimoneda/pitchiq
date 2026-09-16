"""Tests de la app pública con TestClient, sobre las fixtures sample/ (sin red)."""

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import REPORT_DIR, create_app

SAMPLE_DIR = REPORT_DIR / "sample"


def _base_con_sample(tmp_path: Path) -> Path:
    """Directorio de artefactos que solo contiene sample/ (sin artefactos reales)."""
    (tmp_path / "sample").symlink_to(SAMPLE_DIR)
    return tmp_path


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """App sin artefactos reales: todo cae a sample/.

    Así los tests no dependen de si los artefactos reales están commiteados.
    """
    return TestClient(create_app(report_dir=_base_con_sample(tmp_path_factory.mktemp("a"))))


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "sample_data": True, "sample_report": True}


def test_index_con_graficas_comprobador_e_informe(client):
    r = client.get("/")
    assert r.status_code == 200
    html = r.text
    # las gráficas interactivas y el comprobador de cifras
    for elemento in ['id="campo-recuperaciones"', 'id="linea"', 'id="texto"', 'id="comparacion"']:
        assert elemento in html
    # los datos se inyectan en la página (no hay llamadas a la API desde el cliente)
    assert '"zonas_recuperacion"' in html
    # el informe de muestra, con su recuento de cifras comprobadas
    assert "3 de 3 cifras comprobadas" in html
    assert "Informe táctico" in html


def test_fallback_a_sample_avisa(client):
    """Sin artefactos reales, la página avisa de que son datos de muestra."""
    assert client.get("/").text.count("Datos de muestra") == 2  # gráficas + informe


def test_api_report_estructura(client):
    data = client.get("/api/report").json()
    assert {"team", "generated_at", "sample", "grounding_ratio", "markdown"} <= set(data)
    assert data["grounding_ratio"] == 1.0
    assert data["markdown"].startswith("#")


def test_api_evidence_estructura(client):
    data = client.get("/api/evidence").json()
    assert {"team", "grounding", "tool_outputs"} <= set(data)
    assert "ratio" in data["grounding"]
    assert all("grounded" in f for f in data["grounding"]["figures"])


def test_api_demo_data_estructura(client):
    data = client.get("/api/demo-data").json()
    assert {"herramientas", "zonas_recuperacion", "bloque_densidad", "partidos",
            "corners", "espana"} <= set(data)
    assert len(data["zonas_recuperacion"]) == 5
    assert all(len(fila) == 6 for fila in data["zonas_recuperacion"])


def test_figuras_estaticas_se_sirven(client):
    r = client.get("/figures/sample_figure.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"


def test_graficas_reales_sin_informe_no_mezcla_la_muestra(tmp_path):
    """Con datos de gráficas reales pero sin informe, no enseña el informe falso."""
    base = _base_con_sample(tmp_path)
    shutil.copy(SAMPLE_DIR / "demo_data.json", base / "demo_data.json")
    client = TestClient(create_app(report_dir=base))

    html = client.get("/").text
    assert "El informe completo, en preparación" in html
    assert "Informe táctico" not in html
    assert "Datos de muestra" not in html
    assert client.get("/health").json()["sample_data"] is False


def test_sin_espana_la_seccion_se_oculta_en_cliente(tmp_path):
    """Si no hay datos de comparación, la página los recibe como null."""
    base = _base_con_sample(tmp_path)
    datos = json.loads((SAMPLE_DIR / "demo_data.json").read_text(encoding="utf-8"))
    datos["espana"] = None
    (base / "demo_data.json").write_text(json.dumps(datos), encoding="utf-8")

    html = TestClient(create_app(report_dir=base)).get("/").text
    assert '"espana": null' in html
    assert 'if (!S) { $("#espana").hidden = true; return; }' in html
