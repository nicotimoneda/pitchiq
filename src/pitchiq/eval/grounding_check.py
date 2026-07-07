"""Evaluación de grounding: re-valida el informe precomputado contra su evidencia.

No confía en el ratio guardado: re-ejecuta el validador de M4 sobre el texto
publicado y la evidencia de herramientas, y reporta el resultado. Sin key.
"""

import json
from pathlib import Path

from pitchiq import config
from pitchiq.agent.grounding import validate_grounding

REPORT_DIR = config.ROOT_DIR / "app" / "static" / "report"


def _flatten_tool_outputs(tool_outputs: dict) -> "dict[str, float]":
    """Aplana las salidas de herramientas a métrica -> valor (como hace el grafo)."""
    evidence: dict[str, float] = {}
    for tool, output in tool_outputs.items():
        for field, value in output.items():
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                evidence[f"{tool}.{field}"] = float(value)
            elif isinstance(value, dict):
                for k, v in value.items():
                    if isinstance(v, (int, float)) and not isinstance(v, bool):
                        evidence[f"{tool}.{field}.{k}"] = float(v)
    return evidence


def evaluate_precomputed_report(report_dir: Path = REPORT_DIR) -> dict:
    """Ratio de grounding real del informe servido (artefactos reales o sample)."""
    base = report_dir if (report_dir / "report.md").exists() else report_dir / "sample"
    text = (base / "report.md").read_text(encoding="utf-8")
    evidence_doc = json.loads((base / "evidence.json").read_text(encoding="utf-8"))

    report = validate_grounding(text, _flatten_tool_outputs(evidence_doc["tool_outputs"]))
    return {
        "artefactos": "sample" if base.name == "sample" else "reales",
        "equipo": evidence_doc["team"],
        "cifras_en_el_informe": len(report.figures),
        "cifras_respaldadas": sum(f.grounded for f in report.figures),
        "ratio_grounding": report.ratio,
        "cifras_sueltas": [f.text for f in report.ungrounded],
    }
