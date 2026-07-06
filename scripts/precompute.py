"""Precómputo de los artefactos que sirve la app pública (paso HUMANO, en local).

La app FastAPI de producción no genera nada: solo sirve lo que este script deja
en app/static/report/. El flujo es: el humano corre esto en local con su
ANTHROPIC_API_KEY, revisa el resultado y COMMITEA los artefactos.

Uso:
    ANTHROPIC_API_KEY=sk-ant-... uv run python scripts/precompute.py --team "Bayer Leverkusen"
    uv run python scripts/precompute.py --sample   # fixtures sintéticas (sin key)
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import date

from pitchiq import config

REPORT_DIR = config.ROOT_DIR / "app" / "static" / "report"

# Figuras de temporada (M1-M3) que acompañan al informe en la web
SEASON_FIGURES = [
    "defensive_block_{slug}_season.png",
    "line_height_by_match_{slug}.png",
    "corners_delivery_{slug}_temporada.png",
    "corners_box_load_{slug}_temporada.png",
    "corners_first_contact_for_{slug}_temporada.png",
    "corners_first_contact_against_{slug}_temporada.png",
]

SAMPLE_MARKDOWN = """\
# Informe táctico — Equipo Muestra (datos sintéticos)

Este es un informe de MUESTRA generado sin LLM para tests y CI. El equipo
registró un PPDA medio de 2.48 y una altura de línea defensiva de 52.9,
con 236 córners a favor en la temporada.
"""

SAMPLE_EVIDENCE = {
    "team": "Equipo Muestra",
    "generated_at": "2026-01-01",
    "sample": True,
    "model": None,
    "grounding": {
        "ratio": 1.0,
        "figures": [
            {"text": "2.48", "value": 2.48, "grounded": True,
             "matched_metric": "presion.ppda_medio"},
            {"text": "52.9", "value": 52.9, "grounded": True,
             "matched_metric": "forma_defensiva.altura_linea_media"},
            {"text": "236", "value": 236.0, "grounded": True,
             "matched_metric": "corners_ataque.n_corners"},
        ],
    },
    "tool_outputs": {
        "presion": {"team": "Equipo Muestra", "ppda_medio": 2.48},
        "forma_defensiva": {"team": "Equipo Muestra", "altura_linea_media": 52.9},
        "corners_ataque": {"team": "Equipo Muestra", "n_corners": 236},
    },
}


def build_sample() -> None:
    """Genera las fixtures sintéticas de sample/ (sin key, para tests y CI)."""
    sample_dir = REPORT_DIR / "sample"
    figures_dir = sample_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    (sample_dir / "report.md").write_text(SAMPLE_MARKDOWN, encoding="utf-8")
    (sample_dir / "evidence.json").write_text(
        json.dumps(SAMPLE_EVIDENCE, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(4, 2.5))
    ax.bar(["corto", "primer palo", "centro", "segundo palo"], [3, 2, 4, 1],
           color="#d62828")
    ax.set_title("figura de muestra (datos sintéticos)", fontsize=9)
    fig.savefig(figures_dir / "sample_figure.png", dpi=72, bbox_inches="tight")
    print(f"fixtures de muestra en {sample_dir}")


def build_real(team: str) -> None:
    """Genera el informe real + figuras (requiere ANTHROPIC_API_KEY)."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit(
            "Falta ANTHROPIC_API_KEY: el precómputo genera el informe con el LLM "
            "una única vez, en local. Exporta la key y relanza:\n"
            "  ANTHROPIC_API_KEY=sk-ant-... uv run python scripts/precompute.py"
        )

    from pitchiq.agent.report import generate_report
    from pitchiq.rag.retriever import open_default_retriever

    slug = team.lower().replace(" ", "_")
    figures_dir = REPORT_DIR / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    print("1/3 regenerando figuras de temporada (datos cacheados, sin key)...")
    for script, args in [
        ("scripts/build_shape_report.py", ["--team", team]),
        ("scripts/build_setpiece_report.py", ["--team", team]),
    ]:
        subprocess.run([sys.executable, script, *args], check=True,
                       capture_output=True, cwd=config.ROOT_DIR)
    for name in SEASON_FIGURES:
        src = config.FIGURES_DIR / name.format(slug=slug)
        if src.exists():
            shutil.copy(src, figures_dir / src.name)
        else:
            print(f"  aviso: falta {src.name}")

    print("2/3 generando el informe con el LLM (única llamada cara)...")
    retriever = open_default_retriever()
    if retriever is None:
        raise SystemExit(
            "no hay índice vectorial; constrúyelo con "
            "`uv run python scripts/build_index.py`"
        )
    report = generate_report(team, retriever=retriever)
    retriever.close()

    print("3/3 escribiendo artefactos...")
    (REPORT_DIR / "report.md").write_text(report.markdown, encoding="utf-8")
    evidence = {
        "team": report.team,
        "generated_at": date.today().isoformat(),
        "sample": False,
        "model": "claude-opus-4-8",
        "grounding": report.grounding.model_dump(),
        "tool_outputs": report.tool_outputs,
    }
    (REPORT_DIR / "evidence.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"artefactos en {REPORT_DIR} — revísalos y commitéalos")
    print(f"grounding: {report.grounding.ratio:.0%} "
          f"({len(report.grounding.figures)} cifras)")


def main() -> None:
    """Punto de entrada del CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--team", type=str, default=config.DEFAULT_TEAM)
    parser.add_argument("--sample", action="store_true",
                        help="genera solo las fixtures sintéticas (sin key)")
    args = parser.parse_args()

    if args.sample:
        build_sample()
    else:
        build_real(args.team)


if __name__ == "__main__":
    main()
