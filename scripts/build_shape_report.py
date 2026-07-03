"""CLI: resumen espacial (360) de un equipo — por partido o de temporada.

Uso:
    python scripts/build_shape_report.py --team "Bayer Leverkusen"                 # temporada
    python scripts/build_shape_report.py --team "Bayer Leverkusen" --match-id 3895052
"""

import argparse

import numpy as np
import pandas as pd

from pitchiq import config
from pitchiq.data.loader import load_events, load_frames, load_matches
from pitchiq.metrics.frames import merge_frames_events, visible_teammates
from pitchiq.metrics.pressing import defensive_actions
from pitchiq.metrics.spatial import (
    defensive_compactness,
    defensive_line_height,
    pressing_support,
    support_distribution,
)
from pitchiq.viz.shapes import plot_defensive_block, plot_line_height_by_match


def _slug(team: str) -> str:
    """Nombre de equipo a fragmento de nombre de fichero."""
    return team.lower().replace(" ", "_")


def _block_positions(events: pd.DataFrame, frames: pd.DataFrame, team: str) -> np.ndarray:
    """Posiciones de compañeros visibles en las acciones defensivas del equipo."""
    merged = merge_frames_events(frames, events)
    if merged.empty:
        return np.empty((0, 2))
    ids = set(defensive_actions(events, team)["id"])
    chunks = [
        visible_teammates(frame, team)
        for _, frame in merged[merged["event_uuid"].isin(ids)].groupby("event_uuid")
    ]
    chunks = [c for c in chunks if len(c)]
    return np.vstack(chunks) if chunks else np.empty((0, 2))


def match_metrics(match_id: int, team: str, radius: float) -> dict:
    """Computa las tres métricas espaciales de un partido; NaN si no hay 360."""
    events = load_events(match_id)
    frames = load_frames(match_id)
    comp = defensive_compactness(frames, events, team)
    line = defensive_line_height(frames, events, team)
    supp = pressing_support(frames, events, team, radius=radius)
    return {
        "match_id": match_id,
        "n_events_360": comp.n_events,
        "hull_area": comp.mean("hull_area"),
        "width": comp.mean("width"),
        "depth": comp.mean("depth"),
        "line_height": line.mean("line_height"),
        "support": supp.mean("support"),
        "support_dist": support_distribution(supp),
        "_events": events,
        "_frames": frames,
    }


def report_match(match_id: int, team: str, radius: float) -> None:
    """Métricas espaciales de un partido + figura del bloque defensivo."""
    m = match_metrics(match_id, team, radius)
    print(f"partido {match_id} · {team} · {m['n_events_360']} eventos con 360")
    print(f"  compacidad: hull {m['hull_area']:.0f} m² · {m['width']:.1f} ancho × {m['depth']:.1f} prof")
    print(f"  altura de línea: {m['line_height']:.1f} (x, 0-120)")
    print(f"  soporte de presión (≤{radius:g} m): {m['support']:.2f} · dist {m['support_dist']}")

    positions = _block_positions(m["_events"], m["_frames"], team)
    fig = plot_defensive_block(
        positions, team,
        line_height=m["line_height"],
        title=f"Bloque defensivo — {team} (partido {match_id})",
    )
    out = config.FIGURES_DIR / f"defensive_block_{_slug(team)}_{match_id}.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"guardado: {out}")


def report_season(team: str, radius: float) -> None:
    """Agrega las métricas sobre todos los partidos y genera figuras de temporada."""
    matches = load_matches().sort_values("match_date").reset_index(drop=True)
    rows, labels, all_positions = [], [], []
    for _, match in matches.iterrows():
        match_id = int(match["match_id"])
        rival = (
            match["away_team"] if match["home_team"] == team else match["home_team"]
        )
        m = match_metrics(match_id, team, radius)
        rows.append({k: v for k, v in m.items() if not k.startswith("_")})
        labels.append(f"{str(match['match_date'])[:10]} {rival}")
        pos = _block_positions(m["_events"], m["_frames"], team)
        if len(pos):
            all_positions.append(pos)
        print(f"  {labels[-1]}: línea {m['line_height']:.1f} · hull {m['hull_area']:.0f} m²")

    season = pd.DataFrame(rows)
    print(f"\n{team} — temporada ({len(season)} partidos, "
          f"{int(season['n_events_360'].sum())} eventos con 360)")
    print(f"  hull medio: {season['hull_area'].mean():.0f} m² · "
          f"{season['width'].mean():.1f} ancho × {season['depth'].mean():.1f} prof")
    print(f"  altura de línea media: {season['line_height'].mean():.1f}")
    print(f"  soporte de presión medio (≤{radius:g} m): {season['support'].mean():.2f}")

    config.FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    fig = plot_line_height_by_match(
        season["line_height"].tolist(), labels, team
    )
    out_line = config.FIGURES_DIR / f"line_height_by_match_{_slug(team)}.png"
    fig.savefig(out_line, dpi=150, bbox_inches="tight")

    positions = np.vstack(all_positions) if all_positions else np.empty((0, 2))
    fig = plot_defensive_block(
        positions, team,
        line_height=float(season["line_height"].mean()),
        title=f"Bloque defensivo — {team} (temporada 2023/24)",
    )
    out_block = config.FIGURES_DIR / f"defensive_block_{_slug(team)}_season.png"
    fig.savefig(out_block, dpi=150, bbox_inches="tight")
    print(f"guardado: {out_line}\nguardado: {out_block}")


def main() -> None:
    """Punto de entrada del CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--team", type=str, default=config.DEFAULT_TEAM)
    parser.add_argument("--match-id", type=int, default=None)
    parser.add_argument("--radius", type=float, default=10.0)
    args = parser.parse_args()

    config.FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    if args.match_id is not None:
        report_match(args.match_id, args.team, args.radius)
    else:
        report_season(args.team, args.radius)


if __name__ == "__main__":
    main()
