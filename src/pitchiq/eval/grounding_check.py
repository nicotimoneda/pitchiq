"""Evaluación de grounding: re-verifica los informes publicados contra su dossier.

No confía en lo guardado al generarlos: vuelve a pasar el verificador de citas
sobre el texto que escribió el modelo y el dossier que recibió. Sin key.
"""

import json
from pathlib import Path

from pitchiq import config
from pitchiq.agent.grounding import verificar_citas

REPORT_DIR = config.ROOT_DIR / "app" / "static" / "report"


def evaluate_precomputed_report(report_dir: Path = REPORT_DIR) -> dict:
    """Citas válidas y cifras libres de todos los informes servidos (reales o sample)."""
    real = sorted((report_dir / "informes").glob("*.json"))
    files = real or sorted((report_dir / "sample" / "informes").glob("*.json"))
    total = ok = 0
    sueltas: list[str] = []
    for f in files:
        inf = json.loads(f.read_text(encoding="utf-8"))
        for idioma in ("es", "en"):
            rep = verificar_citas(inf[idioma]["markdown"], inf["dossier"], ignore=[inf["equipo"]])
            total += len(rep.figures)
            ok += sum(x.grounded for x in rep.figures)
            sueltas += [f"{inf['slug']}/{idioma}: {x.text}" for x in rep.ungrounded]
    return {
        "artefactos": "reales" if real else "sample",
        "informes": len(files),
        "cifras_en_el_informe": total,
        "cifras_respaldadas": ok,
        "ratio_grounding": ok / total if total else 1.0,
        "cifras_sueltas": sueltas,
    }
