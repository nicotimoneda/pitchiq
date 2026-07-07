"""Tests de la app pública con TestClient, sobre las fixtures sample/ (sin red)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import REPORT_DIR, create_app

SAMPLE_DIR = REPORT_DIR / "sample"


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """App apuntada a un directorio SIN artefactos reales para forzar sample/.

    Así los tests no dependen de si los artefactos reales están commiteados.
    """
    base: Path = tmp_path_factory.mktemp("artefactos")
    (base / "sample").symlink_to(SAMPLE_DIR)
    return TestClient(create_app(report_dir=base))


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_index_html_con_grounding_y_figura(client):
    r = client.get("/")
    assert r.status_code == 200
    html = r.text
    assert "grounding" in html
    assert "100" in html  # ratio de grounding visible
    assert "/figures/" in html  # al menos una figura enlazada
    # la figura enlazada se sirve de verdad
    r_fig = client.get("/figures/sample_figure.png")
    assert r_fig.status_code == 200
    assert r_fig.headers["content-type"] == "image/png"


def test_api_report_estructura(client):
    r = client.get("/api/report")
    assert r.status_code == 200
    data = r.json()
    assert {"team", "generated_at", "sample", "grounding_ratio", "markdown"} <= set(data)
    assert data["grounding_ratio"] == 1.0
    assert data["markdown"].startswith("#")


def test_api_evidence_estructura(client):
    r = client.get("/api/evidence")
    assert r.status_code == 200
    data = r.json()
    assert {"team", "grounding", "tool_outputs"} <= set(data)
    assert "ratio" in data["grounding"]
    assert all("grounded" in f for f in data["grounding"]["figures"])


def test_fallback_a_sample_avisa(client):
    """Sin artefactos reales, la app avisa de que son datos de muestra."""
    r = client.get("/")
    assert "Datos de muestra" in r.text
    assert client.get("/health").json()["sample"] is True
