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
    assert r.json() == {"status": "ok", "sample_data": True, "informes": 1, "equipos": 2}


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
    # el informe del analista viaja con el equipo, con cada cita ya convertida en su valor
    assert inicial["informe"]["es"]["citas"] == 5
    assert '<span class="cifra cita" tabindex="0" data-k="metrica.ppda">2,48</span>' in inicial["informe"]["es"]["html"]
    assert 'data-k="metrica.ppda">2.48</span>' in inicial["informe"]["en"]["html"]
    assert [t["con_informe"] for t in ligeros] == [True, False]
    assert "Datos de muestra" in html


def test_enlaces_internos_de_la_web_existen(client):
    # cada enlace a la API que pinta la plantilla responde (antes quedó uno a /api/evidence, retirada)
    import re
    html = client.get("/").text
    for ruta in set(re.findall(r'href="(/api/[^"]*)"', html)):
        assert client.get(ruta).status_code == 200, ruta


def test_equipo_inicial_por_query(client):
    html = client.get("/?equipo=equipo-rival").text
    assert "<title>PitchIQ</title>" in html
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


def test_api_informe(client):
    inf = client.get("/api/equipos/equipo-muestra/informe").json()
    assert {"dossier", "es", "en", "generated_at", "sample"} <= set(inf)
    assert "{metrica.ppda}" in inf["es"]["markdown"]  # tal cual lo escribió el modelo
    assert client.get("/api/equipos/equipo-rival/informe").status_code == 404


def test_informe_html_escapa_y_marca_claves_inventadas():
    from app.main import _informe_html

    dossier = {"metrica.ppda": {"valor": 2.48, "decimales": 2, "es": "PPDA", "en": "PPDA"}}
    html = _informe_html("<script>x</script> PPDA {metrica.ppda}, {metrica.nada} [a](javascript:alert(1))", dossier, "es")
    assert "<script>" not in html and 'href="#' in html
    assert 'data-k="metrica.ppda">2,48</span>' in html
    assert '<span class="cifra sin" tabindex="0" data-k="metrica.nada">{metrica.nada}</span>' in html
    # "percentil" delante de una clave que no es un percentil: se marca sin respaldo, como en el verificador
    assert 'class="cifra sin" tabindex="0" data-k="metrica.ppda" data-mal="1"' in _informe_html("percentil {metrica.ppda}", dossier, "es")
    # el modelo no puede fabricar el marcador interno ni colar imágenes de otro servidor
    assert "CITA0FIN" in _informe_html("CITA0FIN {metrica.ppda}", dossier, "es")
    assert "<img" not in _informe_html('![x](https://evil.example/t.png) ![y](x" onerror="a)', dossier, "es")


def test_metricas_reales_sin_informe_no_mezcla_la_muestra(tmp_path):
    """Con métricas reales pero sin informe real, no se publica el informe de muestra."""
    base = _base_con_sample(tmp_path)
    _copiar_equipos_como_reales(base)
    client = TestClient(create_app(report_dir=base))

    html = client.get("/").text
    inicial = json.loads(html.split("const INICIAL_COMPLETO = ", 1)[1].split(";\n", 1)[0])
    assert "informe" not in inicial
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


def test_informe_del_llm_sin_html_crudo_ni_javascript():
    from app.main import _markdown_seguro

    html = _markdown_seguro('# T\n\n<img src=x onerror=alert(1)> [x](javascript:alert(1))\n\n> cita')
    assert "<img" not in html and "javascript:" not in html
    assert "<blockquote>" in html and "<h1>" in html


def test_lista_sin_linea_en_blanco_se_ve_como_lista():
    from app.main import _markdown_seguro

    # así la escribe el modelo a veces: la lista pegada a la frase anterior
    html = _markdown_seguro("Son aproximadas:\n- Altura: 48,4 m.\n- Bloque: 32,6 m.\n\nSigue.")
    assert html.count("<li>") == 2 and "<ul>" in html and "- Altura" not in html
    assert _markdown_seguro("1. uno\n2. dos").count("<li>") == 2


def test_csv_no_ejecuta_formulas():
    from app.main import _celda_csv

    assert _celda_csv("=HYPERLINK(1)") == "'=HYPERLINK(1)"
    assert _celda_csv("Real Madrid") == "Real Madrid" and _celda_csv(1.5) == "1,5" and _celda_csv(-2) == -2


def test_cabeceras_de_seguridad(client):
    h = client.get("/").headers
    assert h["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in h["content-security-policy"]


def test_cache_en_datos_de_equipo(client):
    assert "max-age" in client.get("/api/equipos/equipo-muestra").headers["cache-control"]
    assert "cache-control" not in client.get("/health").headers
