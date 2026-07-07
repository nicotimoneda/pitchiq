"""CLI: evaluación consolidada sin key (grounding, embeddings, generalización).

Los resultados se guardan en eval/results/ y alimentan EVALUATION.md.
La parte RAGAS (requiere key) se corre aparte: uv run --script scripts/eval_rag.py

Uso:
    uv run python scripts/run_eval.py [--skip-generalization]
"""

import argparse
import json

from pitchiq import config

RESULTS_DIR = config.ROOT_DIR / "eval" / "results"


def _save(name: str, payload: dict) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"{name}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"-> {path}")


def main() -> None:
    """Corre las tres evaluaciones que no necesitan API key."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-generalization", action="store_true",
                        help="salta la descarga de la Euro 2024 (necesita red)")
    args = parser.parse_args()

    print("1/3 grounding del informe precomputado...")
    from pitchiq.eval.grounding_check import evaluate_precomputed_report

    grounding = evaluate_precomputed_report()
    _save("grounding", grounding)
    print(f"   ratio: {grounding['ratio_grounding']:.2f} "
          f"({grounding['cifras_respaldadas']}/{grounding['cifras_en_el_informe']} "
          f"cifras, artefactos {grounding['artefactos']})")

    print("2/3 comparación de embeddings (descarga ambos modelos la primera vez)...")
    from pitchiq.eval.embeddings_compare import compare_models

    embeddings = compare_models()
    _save("embeddings", embeddings)
    for label, r in embeddings["modelos"].items():
        print(f"   {label}: top-1 {r['top1_accuracy']:.0%} · top-3 {r['top3_accuracy']:.0%}")

    if args.skip_generalization:
        print("3/3 generalización: saltada (--skip-generalization)")
        return
    print("3/3 generalización sobre la Euro 2024 (descarga datos de StatsBomb)...")
    from pitchiq.eval.generalization import evaluate_team

    general = evaluate_team()
    _save("generalization", general)
    print(f"   {general['equipo']}: {general['n_partidos']} partidos, "
          f"PPDA {general['ppda_medio']}, línea {general['altura_linea_media']}, "
          f"{general['partidos_con_360']} con 360")


if __name__ == "__main__":
    main()
