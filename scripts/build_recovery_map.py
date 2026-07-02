"""CLI: genera el mapa de zonas de recuperación de un equipo en un partido.

Uso:
    python scripts/build_recovery_map.py --match-id 3895052 --team "Bayer Leverkusen"
"""

import argparse

from pitchiq import config
from pitchiq.data.loader import load_events
from pitchiq.metrics.pressing import defensive_actions, ppda, recovery_zones
from pitchiq.viz.pitch import plot_zone_heatmap


def main() -> None:
    """Carga el partido, computa zonas + PPDA y guarda el heatmap en figures/."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--match-id", type=int, required=True)
    parser.add_argument("--team", type=str, default=config.DEFAULT_TEAM)
    parser.add_argument("--grid", type=int, nargs=2, default=(6, 5))
    args = parser.parse_args()

    events = load_events(args.match_id)
    if args.team not in set(events["team"].dropna()):
        raise SystemExit(
            f"'{args.team}' no juega el partido {args.match_id} "
            f"(equipos: {sorted(set(events['team'].dropna()))})"
        )

    actions = defensive_actions(events, args.team)
    zones = recovery_zones(events, args.team, grid=tuple(args.grid))
    match_ppda = ppda(events, args.team)

    fig = plot_zone_heatmap(
        actions["x"].tolist(),
        actions["y"].tolist(),
        grid=tuple(args.grid),
        title=f"Zonas de recuperación — {args.team}",
        subtitle=(
            f"Partido {args.match_id} · {zones.total} acciones defensivas · "
            f"PPDA {match_ppda:.2f} · ataca →"
        ),
    )

    config.FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    out = config.FIGURES_DIR / f"recovery_map_{args.match_id}.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"guardado: {out}")
    print(f"acciones defensivas: {zones.total} | PPDA: {match_ppda:.2f}")


if __name__ == "__main__":
    main()
