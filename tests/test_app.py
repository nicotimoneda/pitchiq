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


def _copiar_equipos_como_reales(base: Path) -> Path:
    """Copia los equipos de muestra a teams/ para simular métricas reales publicadas."""
    shutil.copytree(SAMPLE_DIR / "teams", base / "teams")
    return base / "teams"


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """App sin artefactos reales: todo cae a sample/."""
    return TestClient(create_app(report_dir=_base_con_sample(tmp_path_factory.mktemp("a"))))


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "sample_data": True, "sample_report": True, "equipos": 2}


def test_index_con_selector_secciones_y_datos(client):
    r = client.get("/")
    assert r.status_code == 200
    html = r.text
    # selector con todos los equipos publicados, agrupados por competición
    assert '<optgroup label="Liga de muestra 2026">' in html
    assert 'value="equipo-muestra"' in html and 'value="equipo-rival"' in html
    for seccion in ['id="informe"', 'id="ataque"', 'id="presion"', 'id="defensa"',
                    'id="balon-parado"', 'id="jugadores"', 'id="partidos"', 'id="comparar"']:
        assert seccion in html
    # los datos de todos los equipos se inyectan en la página (sin llamadas desde el cliente)
    # de todos los equipos viajan solo los datos ligeros (percentiles, comparar);
    # los pesados solo del equipo inicial, el resto se pide a la API
    ligeros = json.loads(html.split("const TEAMS = ", 1)[1].split(";\n", 1)[0])
    inicial = json.loads(html.split("const INICIAL_COMPLETO = ", 1)[1].split(";\n", 1)[0])
    assert all("agregados" in t and "partidos" not in t and "corners" not in t for t in ligeros)
    assert {"partidos", "corners", "tiros", "jugadores", "zonas_recuperacion"} <= set(inicial)
    # el informe del LLM (muestra) viaja con su recuento de cifras verificadas
    assert '"n_grounded": 3' in html
    assert "Datos de muestra" in html


def test_equipo_inicial_por_query(client):
    html = client.get("/?equipo=equipo-rival").text
    assert "<title>PitchIQ · Equipo Rival</title>" in html
    assert 'const INITIAL = "equipo-rival";' in html
    # un slug desconocido cae al primer equipo publicado
    assert 'const INITIAL = "equipo-muestra";' in client.get("/?equipo=no-existe").text


def test_api_equipos(client):
    equipos = client.get("/api/equipos").json()
    assert [e["slug"] for e in equipos] == ["equipo-muestra", "equipo-rival"]
    assert {"slug", "nombre", "competicion", "temporada"} == set(equipos[0])

    detalle = client.get("/api/equipos/equipo-rival").json()
    assert {"herramientas", "zonas_recuperacion", "bloque_densidad", "partidos", "corners"} <= set(detalle)
    assert client.get("/api/equipos/no-existe").status_code == 404


def test_api_report_y_evidence(client):
    report = client.get("/api/report").json()
    assert {"team", "generated_at", "sample", "grounding_ratio", "markdown"} <= set(report)
    assert report["markdown"].startswith("#")
    evidence = client.get("/api/evidence").json()
    assert {"team", "grounding", "tool_outputs"} <= set(evidence)
    assert all("grounded" in f for f in evidence["grounding"]["figures"])


def test_figuras_estaticas_se_sirven(client):
    r = client.get("/figures/sample_figure.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"


def test_metricas_reales_sin_informe_no_mezcla_la_muestra(tmp_path):
    """Con métricas reales pero sin informe real, no se publica el informe de muestra."""
    base = _base_con_sample(tmp_path)
    _copiar_equipos_como_reales(base)
    client = TestClient(create_app(report_dir=base))

    html = client.get("/").text
    assert "const REPORTS = {};" in html
    assert "Datos de muestra" not in html
    assert client.get("/health").json()["sample_data"] is False


def test_equipo_sin_datos_360_llega_como_null(tmp_path):
    """Sin posiciones 360, las métricas espaciales viajan como null (no se estiman)."""
    base = _base_con_sample(tmp_path)
    teams = _copiar_equipos_como_reales(base)
    path = teams / "equipo-rival.json"
    datos = json.loads(path.read_text(encoding="utf-8"))
    for campo in ("altura_linea_media", "anchura_media", "hull_area_media_m2"):
        datos["herramientas"]["forma_defensiva"][campo] = None
    path.write_text(json.dumps(datos), encoding="utf-8")

    detalle = TestClient(create_app(report_dir=base)).get("/api/equipos/equipo-rival").json()
    assert detalle["herramientas"]["forma_defensiva"]["altura_linea_media"] is None


def test_vista_previa_para_compartir(tmp_path):
    """Con imagen de vista previa exportada, la página lleva las etiquetas Open Graph."""
    base = _base_con_sample(tmp_path)
    teams = _copiar_equipos_como_reales(base)
    (base / "og").mkdir()
    (base / "og" / "equipo-rival.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    client = TestClient(create_app(report_dir=base))

    html = client.get("/?equipo=equipo-rival").text
    assert '<meta property="og:image" content="http://testserver/og/equipo-rival.png">' in html
    assert 'content="http://testserver/?equipo=equipo-rival"' in html
    assert client.get("/og/equipo-rival.png").status_code == 200
    # sin imagen para ese equipo no se anuncia ninguna
    assert "og:image" not in client.get("/?equipo=equipo-muestra").text
    assert teams.exists()


def test_descargas_csv(client):
    r = client.get("/api/equipos/equipo-muestra/partidos.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    lineas = r.text.lstrip("\ufeff").splitlines()
    assert lineas[0].startswith("fecha;rival;local;goles_favor")
    assert len(lineas) == 5  # cabecera + 4 partidos
    assert "1,4" in lineas[1]  # coma decimal para Excel en español
    j = client.get("/api/equipos/equipo-muestra/jugadores.csv")
    assert "Ana Muestra" in j.text
    assert client.get("/api/equipos/no-existe/partidos.csv").status_code == 404
