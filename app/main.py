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
from pathlib import Path

import markdown as md
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
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
                "html": md.markdown(report_md, extensions=["extra"]),
                "generated_at": evidence["generated_at"],
                "n_figures": len(figures),
                "n_grounded": sum(1 for f in figures if f["grounded"]),
                "sample": is_sample_report,
            }

    app = FastAPI(title="PitchIQ", docs_url=None, redoc_url=None)
    figures_dir = report_base / "figures"
    if figures_dir.exists():
        app.mount("/figures", StaticFiles(directory=figures_dir), name="figures")
    templates = Jinja2Templates(directory=APP_DIR / "templates")

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request, equipo: "str | None" = None) -> HTMLResponse:
        """Página de análisis del equipo pedido (por defecto, el primero publicado)."""
        initial = equipo if equipo in by_slug else teams[0]["slug"]
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "teams": teams,
                "reports": reports,
                "initial": initial,
                "initial_team": by_slug[initial],
                "is_sample_data": is_sample_data,
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
