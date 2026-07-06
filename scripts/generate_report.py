"""CLI: genera el informe táctico grounded de un equipo en reports/.

Uso:
    ANTHROPIC_API_KEY=sk-ant-... python scripts/generate_report.py --team "Bayer Leverkusen"
"""

import argparse
import json
from datetime import date

from pitchiq import config
from pitchiq.agent.report import generate_report
from pitchiq.rag.retriever import open_default_retriever


def main() -> None:
    """Genera el informe .md y la evidencia .json, e informa del grounding."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--team", type=str, default=config.DEFAULT_TEAM)
    args = parser.parse_args()

    retriever = open_default_retriever()
    if retriever is None:
        print(
            "aviso: sin índice vectorial (python scripts/build_index.py); "
            "el informe saldrá sin contexto interpretativo"
        )
    report = generate_report(args.team, retriever=retriever)
    if retriever is not None:
        retriever.close()

    reports_dir = config.ROOT_DIR / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    slug = args.team.lower().replace(" ", "_")
    stem = f"informe_{slug}_{date.today().isoformat()}"

    md_path = reports_dir / f"{stem}.md"
    md_path.write_text(report.markdown, encoding="utf-8")

    evidence = {
        "team": report.team,
        "tool_outputs": report.tool_outputs,
        "grounding": report.grounding.model_dump(),
        "retries_used": report.retries_used,
    }
    json_path = reports_dir / f"{stem}.json"
    json_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    n = len(report.grounding.figures)
    print(f"informe: {md_path}")
    print(f"evidencia: {json_path}")
    print(
        f"grounding: {report.grounding.ratio:.0%} "
        f"({sum(f.grounded for f in report.grounding.figures)}/{n} cifras respaldadas, "
        f"{report.retries_used} reintentos)"
    )
    if not report.grounding.is_grounded:
        print("⚠️ cifras no respaldadas:", [f.text for f in report.grounding.ungrounded])


if __name__ == "__main__":
    main()
