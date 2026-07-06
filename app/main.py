"""App pública de PitchIQ: sirve el informe PRECOMPUTADO, sin LLM ni key.

Decisión de arquitectura: la generación (cara, con LLM) ocurre una vez en local
vía scripts/precompute.py; esta app solo sirve los artefactos resultantes. Por
eso sus dependencias son mínimas (fastapi, jinja2, markdown) y NO importa
anthropic, langgraph, sentence-transformers ni torch. Si no hay artefactos
reales commiteados, cae a las fixtures de sample/ con un aviso visible.
"""

import json
from pathlib import Path

import markdown as md
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

APP_DIR = Path(__file__).resolve().parent
REPORT_DIR = APP_DIR / "static" / "report"


def _resolve_artifacts(report_dir: Path) -> "tuple[Path, bool]":
    """Directorio de artefactos a servir y si son los de muestra."""
    if (report_dir / "report.md").exists():
        return report_dir, False
    return report_dir / "sample", True


def create_app(report_dir: "Path | None" = None) -> FastAPI:
    """Construye la app sobre un directorio de artefactos (inyectable en tests)."""
    base = report_dir if report_dir is not None else REPORT_DIR
    artifacts, is_sample = _resolve_artifacts(base)

    report_md = (artifacts / "report.md").read_text(encoding="utf-8")
    evidence = json.loads((artifacts / "evidence.json").read_text(encoding="utf-8"))
    figures_dir = artifacts / "figures"
    figures = sorted(p.name for p in figures_dir.glob("*.png"))

    app = FastAPI(title="PitchIQ", docs_url=None, redoc_url=None)
    app.mount("/figures", StaticFiles(directory=figures_dir), name="figures")
    templates = Jinja2Templates(directory=APP_DIR / "templates")

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        """Informe renderizado a HTML con figuras y ratio de grounding."""
        return templates.TemplateResponse(
            request,
            "report.html",
            {
                "team": evidence["team"],
                "generated_at": evidence["generated_at"],
                "report_html": md.markdown(report_md, extensions=["extra"]),
                "grounding_ratio": evidence["grounding"]["ratio"],
                "n_figures_grounding": len(evidence["grounding"]["figures"]),
                "figures": figures,
                "is_sample": is_sample,
            },
        )

    @app.get("/api/report")
    def api_report() -> dict:
        """Informe en Markdown con metadatos."""
        return {
            "team": evidence["team"],
            "generated_at": evidence["generated_at"],
            "sample": is_sample,
            "grounding_ratio": evidence["grounding"]["ratio"],
            "markdown": report_md,
        }

    @app.get("/api/evidence")
    def api_evidence() -> dict:
        """Evidencia completa: salidas de herramientas + reporte de grounding."""
        return evidence

    @app.get("/health")
    def health() -> dict:
        """Health check para el deploy."""
        return {"status": "ok", "sample": is_sample}

    return app


app = create_app()
