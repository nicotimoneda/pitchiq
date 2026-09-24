"""App pública de PitchIQ: sirve artefactos PRECOMPUTADOS, sin LLM ni key.

Decisión de arquitectura: la generación (cara, con LLM) ocurre una vez en local
vía scripts/precompute.py; esta app solo sirve los artefactos resultantes. Por
eso sus dependencias son mínimas (fastapi, jinja2, markdown) y NO importa
anthropic, langgraph, sentence-transformers ni torch.

Los artefactos son las métricas de cada equipo publicado (teams/<slug>.json)
y el informe del analista IA de cada uno (informes/<slug>.json), con fallback a
sample/ para tests y CI. Un equipo sin informe enseña el resumen determinista.
"""

import json
import os
import re
import secrets
from pathlib import Path

import markdown as md
from fastapi import FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

APP_DIR = Path(__file__).resolve().parent
REPORT_DIR = APP_DIR / "static" / "report"


def _load_teams(report_dir: Path) -> "tuple[list[dict], bool]":
    """Equipos publicados (reales si existen; si no, los de sample/) y si son muestra."""
    for teams_dir, is_sample in ((report_dir / "teams", False),
                                 (report_dir / "sample" / "teams", True)):
        files = sorted(teams_dir.glob("*.json")) if teams_dir.exists() else []
        if files:
            teams = [json.loads(f.read_text(encoding="utf-8")) for f in files]
            return sorted(teams, key=lambda t: t.get("orden", 0)), is_sample
    raise RuntimeError(f"no hay métricas de equipos en {report_dir}")


# Lo que la página lee de cada equipo para buscar, comparar y calcular percentiles
# (METRICAS en index.html). El resto se pide a /api/equipos/{slug} al elegirlo.
CAMPOS_LIGEROS = ("slug", "nombre", "equipo", "competicion", "temporada", "orden",
                  "posicion", "n_equipos", "identidad", "nombre_en", "femenino")
HERRAMIENTAS_LIGERAS = {
    "presion": ("ppda_medio", "pct_acciones_campo_rival"),
    "forma_defensiva": ("altura_linea_media", "anchura_media", "profundidad_media",
                        "hull_area_media_m2", "soporte_presion_medio"),
    "corners_ataque": ("n_corners", "xg_a_favor", "pct_primer_contacto_ganado"),
    "corners_defensa": ("xg_en_contra", "pct_primer_contacto_concedido", "indice_orientacion_hombre"),
}


def _ligero(team: dict) -> dict:
    """Solo los campos que usa la página para todos los equipos (~3 veces menos peso)."""
    ligero = {k: team.get(k) for k in CAMPOS_LIGEROS}
    ligero["herramientas"] = {h: {c: team["herramientas"][h].get(c) for c in cs}
                              for h, cs in HERRAMIENTAS_LIGERAS.items()}
    agregados = team.get("agregados") or {"partidos": len(team.get("partidos", []))}
    ligero["agregados"] = {k: v for k, v in agregados.items() if k != "carriles_pct"}
    return ligero


def _markdown_seguro(texto: str) -> str:
    """Markdown del informe del LLM a HTML sin HTML crudo ni enlaces javascript:.

    Se escapan ``&`` y ``<`` (no ``>``, que marca las citas en markdown) y se
    neutralizan los esquemas peligrosos en los enlaces: la salida del modelo es
    el único texto no determinista que llega a la página.
    """
    html = md.markdown(texto.replace("&", "&amp;").replace("<", "&lt;"), extensions=["extra"])
    html = re.sub(r"<img\b[^>]*>", "", html)  # sin imágenes: nada se carga desde otro servidor
    return re.sub(r'(href|src)="\s*(javascript|data|vbscript):', r'\1="#', html, flags=re.IGNORECASE)


_CITA = re.compile(r"\{([a-z_]+(?:\.[a-z_]+)+)\}")
_TRAS_PERCENTIL = re.compile(r"percentil[e]?\s+(?:de\s+|del\s+|of\s+)?$", re.IGNORECASE)


def _valor(entrada: dict, idioma: str) -> str:
    """Valor de una entrada del dossier como se lee en cada idioma (coma decimal en español)."""
    texto = f"{entrada['valor']:.{entrada['decimales']}f}"
    return texto.replace(".", ",") if idioma == "es" else texto


def _informe_html(texto: str, dossier: dict, idioma: str) -> str:
    """Markdown del modelo a HTML seguro, con cada cita {clave} convertida en su valor trazable."""
    claves: list[str] = []
    marca = "CITA" + secrets.token_hex(8)  # imposible de adivinar: el modelo no puede fabricarla

    def marcar(m: re.Match) -> str:
        k = m.group(1)
        # "percentil {metrica.xg}": la clave existe pero no es un percentil (misma regla que el verificador)
        if not k.startswith("percentil.") and _TRAS_PERCENTIL.search(texto[:m.start()]):
            k = "!" + k
        claves.append(k)
        return f"{marca}X{len(claves) - 1}X"  # sin caracteres de markdown

    def cifra(m: re.Match) -> str:
        k = claves[int(m.group(1))]
        if k.startswith("!"):
            k = k[1:]
            if k in dossier:
                return f'<span class="cifra sin" tabindex="0" data-k="{k}" data-mal="1">{_valor(dossier[k], idioma)}</span>'
        if k not in dossier:  # clave inventada: se enseña tal cual y marcada
            return f'<span class="cifra sin" tabindex="0" data-k="{k}">{{{k}}}</span>'
        return f'<span class="cifra cita" tabindex="0" data-k="{k}">{_valor(dossier[k], idioma)}</span>'

    return re.sub(marca + r"X(\d+)X", cifra, _markdown_seguro(_CITA.sub(marcar, texto)))


def _load_informes(informes_dir: Path) -> "dict[str, dict]":
    """Informes del analista por slug, listos para la página (HTML + fuentes de cada cita)."""
    informes = {}
    for f in sorted(informes_dir.glob("*.json")) if informes_dir.exists() else []:
        inf = json.loads(f.read_text(encoding="utf-8"))
        dossier = inf["dossier"]
        citadas = {k for i in ("es", "en") for k in _CITA.findall(inf[i]["markdown"]) if k in dossier}
        informes[inf["slug"]] = {
            "generated_at": inf["generated_at"], "modelo": inf.get("modelo"), "sample": inf.get("sample", False),
            "n_dossier": len(dossier), "contexto": sorted(inf.get("contexto") or {}),
            "fuentes": {k: [dossier[k]["es"], dossier[k]["en"], _valor(dossier[k], "es"), _valor(dossier[k], "en")]
                        for k in sorted(citadas)},
            **{i: {"html": _informe_html(inf[i]["markdown"], dossier, i), "citas": inf[i]["citas"],
                   "sin_respaldo": inf[i]["sin_respaldo"], "reintentos": inf[i]["reintentos"]}
               for i in ("es", "en")},
        }
    return informes


def _celda_csv(v):
    """Valor de celda: coma decimal y sin fórmulas (un texto que empiece por = + - @ no se ejecuta)."""
    if isinstance(v, float):
        return str(v).replace(".", ",")
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + v
    return v


def _csv(filas: "list[dict]", columnas: "list[str]") -> str:
    """CSV con separador ';' y coma decimal (lo que abre bien Excel en español)."""
    import csv
    import io

    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(columnas)
    for f in filas:
        w.writerow([_celda_csv(f.get(c, "")) for c in columnas])
    return "\ufeff" + buf.getvalue()  # BOM: Excel detecta UTF-8 (tildes)


def create_app(report_dir: "Path | None" = None) -> FastAPI:
    """Construye la app sobre un directorio de artefactos (inyectable en tests)."""
    base = report_dir if report_dir is not None else REPORT_DIR

    teams, is_sample_data = _load_teams(base)
    by_slug = {t["slug"]: t for t in teams}
    # un informe de muestra junto a métricas reales sería incoherente: no se publica
    informes = _load_informes(base / ("sample" if is_sample_data else "") / "informes")
    for slug, inf in informes.items():
        if slug in by_slug:
            by_slug[slug]["informe"] = inf

    # en la página van ligeros todos los equipos (para comparar y el mapa de estilos);
    # los datos pesados de cada uno se piden a /api/equipos/{slug} al elegirlo
    teams_light = [_ligero(t) for t in teams]
    for t in teams_light:
        t["con_informe"] = t["slug"] in informes

    app = FastAPI(title="PitchIQ", docs_url=None, redoc_url=None)
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    @app.middleware("http")
    async def cabeceras_seguridad(request: Request, call_next):
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        # los scripts de la página son inline: la CSP se limita a lo que no los rompe
        resp.headers.setdefault("Content-Security-Policy", "frame-ancestors 'none'; object-src 'none'; base-uri 'none'")
        # datos e imágenes solo cambian con cada despliegue: caché de una hora
        if request.url.path.startswith("/fonts/"):
            resp.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
        elif request.url.path.startswith(("/api/equipos/", "/og/")):
            resp.headers.setdefault("Cache-Control", "public, max-age=3600, stale-while-revalidate=86400")
        return resp
    app.mount("/fonts", StaticFiles(directory=APP_DIR / "static" / "fonts"), name="fonts")
    og_dir = base / "og"
    if og_dir.exists():
        app.mount("/og", StaticFiles(directory=og_dir), name="og")
    templates = Jinja2Templates(directory=APP_DIR / "templates")

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request, equipo: "str | None" = None) -> HTMLResponse:
        """Página de análisis del equipo pedido (por defecto, el primero publicado)."""
        initial = equipo if equipo in by_slug else teams[0]["slug"]
        # PUBLIC_URL fija el dominio de og:url/og:image (no se refleja la cabecera Host)
        base_url = (os.environ.get("PUBLIC_URL") or str(request.base_url)).rstrip("/")
        og_image = (f"{base_url}/og/{initial}.png" if (og_dir / f"{initial}.png").exists()
                    else None)
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "teams": teams,
                "teams_light": teams_light,
                "initial": initial,
                "initial_team": by_slug[initial],
                "is_sample_data": is_sample_data,
                "og_image": og_image,
                "page_url": f"{base_url}/?equipo={initial}",
            },
        )

    @app.get("/api/equipos")
    def api_teams() -> list:
        """Equipos publicados."""
        return [
            {k: t[k] for k in ("slug", "nombre", "competicion", "temporada")}
            for t in teams
        ]

    @app.get("/api/equipos/{slug}")
    def api_team(slug: str) -> dict:
        """Métricas y datos de gráficas de un equipo."""
        if slug not in by_slug:
            raise HTTPException(status_code=404, detail="equipo no publicado")
        return by_slug[slug]

    @app.get("/api/equipos/{slug}/partidos.csv")
    def api_team_csv(slug: str) -> Response:
        """Partidos del equipo en CSV (para Excel)."""
        if slug not in by_slug:
            raise HTTPException(status_code=404, detail="equipo no publicado")
        cols = ["fecha", "rival", "local", "goles_favor", "goles_contra", "xg_favor", "xg_contra",
                "tiros", "field_tilt", "progresivos", "centros", "ppda", "ppda_clasico",
                "acciones_defensivas", "robos_altos", "robos_altos_tiro", "altura_linea"]
        return Response(_csv(by_slug[slug]["partidos"], cols), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{slug}-partidos.csv"'})

    @app.get("/api/equipos/{slug}/jugadores.csv")
    def api_players_csv(slug: str) -> Response:
        """Estadísticas de la temporada por jugador en CSV."""
        if slug not in by_slug:
            raise HTTPException(status_code=404, detail="equipo no publicado")
        cols = ["nombre", "posicion", "partidos", "minutos", "goles", "asistencias", "tiros", "xg",
                "pases_clave", "progresivos", "presiones", "acciones_defensivas", "recuperaciones"]
        return Response(_csv(by_slug[slug].get("jugadores", []), cols), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{slug}-jugadores.csv"'})

    @app.get("/api/equipos/{slug}/informe")
    def api_informe(slug: str) -> dict:
        """Informe del analista tal cual lo escribió el modelo, con su dossier y su verificación."""
        f = base / ("sample" if is_sample_data else "") / "informes" / f"{slug}.json"
        if slug not in informes or not f.exists():
            raise HTTPException(status_code=404, detail="equipo sin informe")
        return json.loads(f.read_text(encoding="utf-8"))

    @app.get("/health")
    def health() -> dict:
        """Health check para el deploy."""
        return {
            "status": "ok",
            "sample_data": is_sample_data,
            "informes": len(informes),
            "equipos": len(teams),
        }

    return app


app = create_app()
