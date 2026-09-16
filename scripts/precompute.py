"""Precómputo de los artefactos que sirve la app pública (paso HUMANO, en local).

La app FastAPI de producción no genera nada: solo sirve lo que este script deja
en app/static/report/. Hay dos tipos de artefacto:

- demo_data.json: los datos de las gráficas interactivas. Solo métricas
  deterministas sobre la caché de StatsBomb, SIN key.
- report.md + evidence.json: el informe escrito por el LLM y su evidencia,
  CON key (la única llamada cara).

El humano corre esto en local, revisa el resultado y COMMITEA los artefactos.

Uso:
    uv run python scripts/precompute.py --demo-data     # gráficas reales (sin key)
    ANTHROPIC_API_KEY=sk-ant-... uv run python scripts/precompute.py   # todo
    uv run python scripts/precompute.py --sample        # fixtures sintéticas (sin key)
"""

import argparse
import json
import math
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


def _sample_demo_data() -> dict:
    """Datos de gráficas sintéticos, con la misma forma que los reales."""
    rivales = ["Equipo B", "Equipo C", "Equipo D", "Equipo E"]
    return {
        "equipo": "Equipo Muestra",
        "temporada": "muestra",
        "herramientas": {
            "presion": {
                "team": "Equipo Muestra", "n_partidos": 4,
                "acciones_defensivas_totales": 800,
                "acciones_defensivas_por_partido": 200.0,
                "ppda_medio": 2.48, "pct_acciones_campo_rival": 50.0,
            },
            "forma_defensiva": {
                "team": "Equipo Muestra", "hull_area_media_yd2": 500.0,
                "anchura_media": 35.0, "profundidad_media": 24.0,
                "altura_linea_media": 52.9, "soporte_presion_medio": 1.3,
                "partidos_con_360": 3,
            },
            "corners_ataque": {
                "team": "Equipo Muestra", "n_corners": 236,
                "zonas_saque": {"corto": 4, "centro": 3, "primer palo": 2,
                                "segundo palo": 1},
                "box_load_atacantes_medio": 5.0,
                "box_load_defensores_medio": 10.0,
                "pct_primer_contacto_ganado": 60.0, "xg_a_favor": 1.5,
            },
            "corners_defensa": {
                "team": "Equipo Muestra", "n_corners": 5,
                "indice_orientacion_hombre": 3.0,
                "pct_primer_contacto_concedido": 40.0, "xg_en_contra": 0.5,
            },
        },
        "zonas_recuperacion": [[10 + 3 * ix + iy for ix in range(6)] for iy in range(5)],
        "bloque_densidad": [
            [round(math.exp(-((ix - 10) ** 2 + (iy - 8) ** 2) / 40), 3) for ix in range(24)]
            for iy in range(16)
        ],
        "partidos": [
            {"fecha": f"2026-01-0{i + 1}", "rival": r, "local": i % 2 == 0,
             "goles_favor": 2, "goles_contra": 1,
             "altura_linea": None if i == 2 else 50.0 + i, "ppda": 2.5}
            for i, r in enumerate(rivales)
        ],
        "corners": [
            {"x": 115.0, "y": 40.0, "desde_arriba": False, "zona": "centro"},
            {"x": 118.0, "y": 78.0, "desde_arriba": True, "zona": "corto"},
        ],
        "espana": {
            "equipo": "Equipo Comparado", "n_partidos": 3, "partidos_con_360": 3,
            "acciones_defensivas_por_partido": 210.0, "ppda_medio": 2.2,
            "hull_area_media_yd2": 520.0, "altura_linea_media": 54.0,
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
    (sample_dir / "demo_data.json").write_text(
        json.dumps(_sample_demo_data(), ensure_ascii=False), encoding="utf-8"
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


def build_demo_data(team: str) -> None:
    """Exporta los datos reales de las gráficas interactivas (sin key)."""
    import numpy as np

    from pitchiq.agent.tools import run_all_tools
    from pitchiq.data.loader import load_events, load_frames, load_matches
    from pitchiq.metrics.frames import merge_frames_events, visible_teammates
    from pitchiq.metrics.pressing import defensive_actions, ppda
    from pitchiq.metrics.set_pieces import delivery_zone, find_corners
    from pitchiq.metrics.spatial import defensive_line_height

    matches = load_matches().sort_values("match_date").reset_index(drop=True)
    recovery = np.zeros((5, 6), dtype=int)  # filas = ancho (y), columnas = largo (x)
    block = np.zeros((16, 24))  # densidad de posiciones visibles al defender
    per_match, corner_ends = [], []

    for _, m in matches.iterrows():
        match_id = int(m["match_id"])
        events, frames = load_events(match_id), load_frames(match_id)
        home = m["home_team"] == team

        actions = defensive_actions(events, team)
        grid, _, _ = np.histogram2d(actions["x"], actions["y"], bins=[6, 5],
                                    range=[[0, 120], [0, 80]])
        recovery += grid.T.astype(int)

        merged = merge_frames_events(frames, events)
        if not merged.empty:
            ids = set(actions["id"])
            for _, frame in merged[merged["event_uuid"].isin(ids)].groupby("event_uuid"):
                xy = visible_teammates(frame, team)
                if len(xy):
                    dens, _, _ = np.histogram2d(xy[:, 0], xy[:, 1], bins=[24, 16],
                                                range=[[0, 120], [0, 80]])
                    block += dens.T

        line = defensive_line_height(frames, events, team).mean("line_height")
        match_ppda = ppda(events, team)
        per_match.append({
            "fecha": str(m["match_date"])[:10],
            "rival": m["away_team"] if home else m["home_team"],
            "local": bool(home),
            "goles_favor": int(m["home_score"] if home else m["away_score"]),
            "goles_contra": int(m["away_score"] if home else m["home_score"]),
            "altura_linea": None if np.isnan(line) else round(float(line), 1),
            "ppda": round(float(match_ppda), 2) if np.isfinite(match_ppda) else None,
        })

        attacking, _ = find_corners(events, team)
        for _, c in attacking.iterrows():
            end = c.get("pass_end_location")
            if isinstance(end, (list, tuple)):
                corner_ends.append({
                    "x": round(float(end[0]), 1), "y": round(float(end[1]), 1),
                    "desde_arriba": float(c["location"][1]) > 40,
                    "zona": delivery_zone(c),
                })

    generalization = config.ROOT_DIR / "eval" / "results" / "generalization.json"
    espana = (
        json.loads(generalization.read_text(encoding="utf-8"))
        if generalization.exists() else None
    )
    payload = {
        "equipo": team,
        "temporada": "2023/24",
        "herramientas": {k: v.model_dump() for k, v in run_all_tools(team).items()},
        "zonas_recuperacion": recovery.tolist(),
        "bloque_densidad": (block / max(block.max(), 1)).round(3).tolist(),
        "partidos": per_match,
        "corners": corner_ends,
        "espana": espana,
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORT_DIR / "demo_data.json"
    out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"datos de gráficas en {out} ({len(per_match)} partidos)")


def build_real(team: str) -> None:
    """Genera gráficas, figuras y el informe real (requiere ANTHROPIC_API_KEY)."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit(
            "Falta ANTHROPIC_API_KEY: el precómputo genera el informe con el LLM "
            "una única vez, en local. Exporta la key y relanza:\n"
            "  ANTHROPIC_API_KEY=sk-ant-... uv run python scripts/precompute.py\n"
            "Las gráficas no necesitan key: uv run python scripts/precompute.py --demo-data"
        )

    from pitchiq.agent.report import generate_report
    from pitchiq.rag.retriever import open_default_retriever

    slug = team.lower().replace(" ", "_")
    figures_dir = REPORT_DIR / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    print("1/4 regenerando figuras de temporada (datos cacheados, sin key)...")
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

    print("2/4 exportando datos de las gráficas interactivas (sin key)...")
    build_demo_data(team)

    print("3/4 generando el informe con el LLM (única llamada cara)...")
    retriever = open_default_retriever()
    if retriever is None:
        raise SystemExit(
            "no hay índice vectorial; constrúyelo con "
            "`uv run python scripts/build_index.py`"
        )
    report = generate_report(team, retriever=retriever)
    retriever.close()

    print("4/4 escribiendo artefactos...")
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
    parser.add_argument("--demo-data", action="store_true",
                        help="exporta solo los datos de las gráficas (sin key)")
    args = parser.parse_args()

    if args.sample:
        build_sample()
    elif args.demo_data:
        build_demo_data(args.team)
    else:
        build_real(args.team)


if __name__ == "__main__":
    main()
