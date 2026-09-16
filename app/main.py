"""App pública de PitchIQ: sirve artefactos PRECOMPUTADOS, sin LLM ni key.

Decisión de arquitectura: la generación (cara, con LLM) ocurre una vez en local
vía scripts/precompute.py; esta app solo sirve los artefactos resultantes. Por
eso sus dependencias son mínimas (fastapi, jinja2, markdown) y NO importa
anthropic, langgraph, sentence-transformers ni torch.

Los artefactos son dos piezas independientes, cada una con su fallback a
sample/: los datos de las gráficas (demo_data.json, sin key) y el informe del
LLM (report.md + evidence.json, con key). Así la web enseña gráficas reales
aunque el informe todavía no se haya generado.
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


def _pick(report_dir: Path, name: str) -> "tuple[Path, bool]":
    """Ruta del artefacto real si existe; si no, la de sample/ (y si es muestra)."""
    real = report_dir / name
    if real.exists():
        return real, False
    return report_dir / "sample" / name, True


def create_app(report_dir: "Path | None" = None) -> FastAPI:
    """Construye la app sobre un directorio de artefactos (inyectable en tests)."""
    base = report_dir if report_dir is not None else REPORT_DIR

    demo_path, is_sample_data = _pick(base, "demo_data.json")
    demo_data = json.loads(demo_path.read_text(encoding="utf-8"))

    report_path, is_sample_report = _pick(base, "report.md")
    evidence_path = report_path.with_name("evidence.json")
    report_md = report_path.read_text(encoding="utf-8")
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    figures_dir = report_path.parent / "figures"

    # con gráficas reales, un informe de muestra no se enseña: sería incoherente
    show_report = is_sample_data or not is_sample_report
    grounding_figures = evidence["grounding"]["figures"]

    app = FastAPI(title="PitchIQ", docs_url=None, redoc_url=None)
    if figures_dir.exists():
        app.mount("/figures", StaticFiles(directory=figures_dir), name="figures")
    templates = Jinja2Templates(directory=APP_DIR / "templates")

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        """Demo interactiva con datos reales + informe del LLM si está publicado."""
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "demo_data": demo_data,
                "is_sample_data": is_sample_data,
                "is_sample_report": is_sample_report,
                "report_html": (
                    md.markdown(report_md, extensions=["extra"]) if show_report else None
                ),
                "generated_at": evidence["generated_at"],
                "n_figures": len(grounding_figures),
                "n_grounded": sum(1 for f in grounding_figures if f["grounded"]),
            },
        )

    @app.get("/api/report")
    def api_report() -> dict:
        """Informe en Markdown con metadatos."""
        return {
            "team": evidence["team"],
            "generated_at": evidence["generated_at"],
            "sample": is_sample_report,
            "grounding_ratio": evidence["grounding"]["ratio"],
            "markdown": report_md,
        }

    @app.get("/api/evidence")
    def api_evidence() -> dict:
        """Evidencia completa: salidas de herramientas + reporte de grounding."""
        return evidence

    @app.get("/api/demo-data")
    def api_demo_data() -> dict:
        """Datos de las gráficas interactivas (métricas deterministas)."""
        return demo_data

    @app.get("/health")
    def health() -> dict:
        """Health check para el deploy."""
        return {
            "status": "ok",
            "sample_data": is_sample_data,
            "sample_report": is_sample_report,
        }

    return app


app = create_app()
