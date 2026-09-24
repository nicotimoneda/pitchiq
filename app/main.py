"""App pública de PitchIQ: sirve artefactos PRECOMPUTADOS, sin LLM ni key.

Decisión de arquitectura: la generación (cara, con LLM) ocurre una vez en local
vía scripts/precompute.py; esta app solo sirve los artefactos resultantes. Por
eso sus dependencias son mínimas (fastapi, jinja2, markdown) y NO importa
anthropic, langgraph, sentence-transformers ni torch.

Los artefactos son dos piezas independientes, cada una con su fallback a
sample/: las métricas de cada equipo publicado (teams/<slug>.json, sin key) y
el informe del LLM (report.md + evidence.json, con key). Así la web enseña
métricas reales aunque el informe todavía no se haya generado.
"""

import json
import os
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


def _load_report(report_dir: Path) -> "tuple[str, dict, Path, bool]":
    """Informe del LLM y su evidencia (reales si existen; si no, los de sample/)."""
    real = report_dir / "report.md"
    base, is_sample = (report_dir, False) if real.exists() else (report_dir / "sample", True)
    report_md = (base / "report.md").read_text(encoding="utf-8")
    evidence = json.loads((base / "evidence.json").read_text(encoding="utf-8"))
    return report_md, evidence, base, is_sample


PESADOS = ("corners", "bloque_densidad", "partidos", "tiros", "jugadores", "zonas_recuperacion")


def _ligero(team: dict) -> dict:
    """Lo mínimo de cada equipo para buscar, comparar y calcular percentiles en la página.

    El detalle (partidos, tiros, jugadores, mapas) se pide a /api/equipos/{slug}.
    """
    ligero = {k: v for k, v in team.items() if k not in PESADOS}
    ligero.setdefault("agregados", {"partidos": len(team.get("partidos", []))})
    ligero["ligero"] = True
    return ligero


def _markdown_seguro(texto: str) -> str:
    """Markdown del informe del LLM a HTML sin HTML crudo ni enlaces javascript:.

    Se escapan ``&`` y ``<`` (no ``>``, que marca las citas en markdown) y se
    neutralizan los esquemas peligrosos en los enlaces: la salida del modelo es
    el único texto no determinista que llega a la página.
    """
    import re

    html = md.markdown(texto.replace("&", "&amp;").replace("<", "&lt;"), extensions=["extra"])
    return re.sub(r'(href|src)="\s*(javascript|data|vbscript):', r'\1="#', html, flags=re.IGNORECASE)


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
    report_md, evidence, report_base, is_sample_report = _load_report(base)

    # un informe de muestra junto a métricas reales sería incoherente: no se publica
    reports: dict[str, dict] = {}
    if is_sample_data or not is_sample_report:
        owner = next((t for t in teams if t["equipo"] == evidence["team"]), None)
        if owner is not None:
            figures = evidence["grounding"]["figures"]
            reports[owner["slug"]] = {
                "html": _markdown_seguro(report_md),
                "generated_at": evidence["generated_at"],
                "n_figures": len(figures),
                "n_grounded": sum(1 for f in figures if f["grounded"]),
                "sample": is_sample_report,
            }

    # en la página van ligeros todos los equipos (para comparar y el mapa de estilos);
    # los datos pesados de cada uno se piden a /api/equipos/{slug} al elegirlo
    teams_light = [_ligero(t) for t in teams]

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
        if request.url.path.startswith(("/api/equipos/", "/og/")):
            resp.headers.setdefault("Cache-Control", "public, max-age=3600, stale-while-revalidate=86400")
        return resp
    figures_dir = report_base / "figures"
    if figures_dir.exists():
        app.mount("/figures", StaticFiles(directory=figures_dir), name="figures")
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
                "reports": reports,
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

    @app.get("/api/report")
    def api_report() -> dict:
        """Informe del LLM en Markdown con metadatos."""
        return {
            "team": evidence["team"],
            "generated_at": evidence["generated_at"],
            "sample": is_sample_report,
            "grounding_ratio": evidence["grounding"]["ratio"],
            "markdown": report_md,
        }

    @app.get("/api/evidence")
    def api_evidence() -> dict:
        """Evidencia completa del informe: salidas de herramientas + grounding."""
        return evidence

    @app.get("/health")
    def health() -> dict:
        """Health check para el deploy."""
        return {
            "status": "ok",
            "sample_data": is_sample_data,
            "sample_report": is_sample_report,
            "equipos": len(teams),
        }

    return app


app = create_app()
