"""CLI: resumen de córners (ataque + defensa) de un equipo — partido o temporada.

Uso:
    python scripts/build_setpiece_report.py --team "Bayer Leverkusen"                  # temporada
    python scripts/build_setpiece_report.py --team "Bayer Leverkusen" --match-id 3895052
"""

import argparse
from collections import Counter

import numpy as np
import pandas as pd

from pitchiq import config
from pitchiq.data.loader import load_events, load_frames, load_matches
from pitchiq.metrics.frames import merge_frames_events
from pitchiq.metrics.set_pieces import (
    box_load,
    corner_frame,
    corner_xg_against,
    corner_xg_for,
    delivery_zone,
    find_corners,
    first_contact,
    man_orientation_index,
)
from pitchiq.viz.set_pieces import (
    plot_box_occupation,
    plot_delivery_zones,
    plot_first_contacts,
)


def _slug(team: str) -> str:
    """Nombre de equipo a fragmento de nombre de fichero."""
    return team.lower().replace(" ", "_")


def match_corners(match_id: int, team: str) -> "dict[str, list]":
    """Extrae por partido las observaciones de córner a favor y en contra."""
    events = load_events(match_id)
    merged = merge_frames_events(load_frames(match_id), events)
    attacking, defensive = find_corners(events, team)

    obs: dict[str, list] = {
        "zones": [], "ends": [], "att_box": [], "def_box": [],
        "fc_for": [], "fc_against": [], "moi": [],
        "xg_for": [corner_xg_for(events, team)],
        "xg_against": [corner_xg_against(events, team)],
        "n_att": [len(attacking)], "n_def": [len(defensive)],
    }
    for _, c in attacking.iterrows():
        obs["zones"].append(delivery_zone(c))
        end = c.get("pass_end_location")
        if isinstance(end, (list, tuple)):
            obs["ends"].append([float(end[0]), float(end[1])])
        bl = box_load(corner_frame(merged, c["id"]), c)
        if bl is not None:
            obs["att_box"].append(bl.n_attackers)
            obs["def_box"].append(bl.n_defenders)
        fc = first_contact(events, c)
        if fc is not None:
            obs["fc_for"].append((fc.won, fc.location))
    for _, c in defensive.iterrows():
        moi = man_orientation_index(corner_frame(merged, c["id"]), team)
        if not np.isnan(moi):
            obs["moi"].append(moi)
        fc = first_contact(events, c)
        if fc is not None:
            # fc.won = lo ganó el rival que saca => concedido para nosotros
            obs["fc_against"].append((fc.won, fc.location))
    return obs


def _merge_obs(all_obs: "list[dict[str, list]]") -> "dict[str, list]":
    """Concatena las observaciones de varios partidos."""
    merged: dict[str, list] = {}
    for obs in all_obs:
        for k, v in obs.items():
            merged.setdefault(k, []).extend(v)
    return merged


def _pct(part: int, total: int) -> float:
    """Porcentaje seguro (NaN si el total es cero)."""
    return 100.0 * part / total if total else float("nan")


def report(obs: "dict[str, list]", team: str, tag: str) -> None:
    """Imprime el resumen y genera las tres figuras de córners."""
    n_att, n_def = sum(obs["n_att"]), sum(obs["n_def"])
    zone_counts = dict(Counter(obs["zones"]))
    fc_won = sum(1 for won, _ in obs["fc_for"] if won)
    fc_conceded = sum(1 for won, _ in obs["fc_against"] if won)

    print(f"\n{team} — córners ({tag})")
    print(f"  ATAQUE: {n_att} córners · zonas {zone_counts}")
    if obs["att_box"]:
        print(f"    box load medio (visibles): {np.mean(obs['att_box']):.1f} atacantes "
              f"vs {np.mean(obs['def_box']):.1f} defensores "
              f"({len(obs['att_box'])} córners con 360)")
    print(f"    1er contacto ganado: {fc_won}/{len(obs['fc_for'])} "
          f"({_pct(fc_won, len(obs['fc_for'])):.0f} %)")
    print(f"    xG a favor (play_pattern From Corner): {sum(obs['xg_for']):.2f}")
    print(f"  DEFENSA: {n_def} córners")
    if obs["moi"]:
        print(f"    índice de orientación al hombre (PROXY heurístico): "
              f"{np.mean(obs['moi']):.2f} m de media al marcador más cercano "
              f"({len(obs['moi'])} córners con 360)")
    print(f"    1er contacto concedido: {fc_conceded}/{len(obs['fc_against'])} "
          f"({_pct(fc_conceded, len(obs['fc_against'])):.0f} %)")
    print(f"    xG en contra (play_pattern From Corner): {sum(obs['xg_against']):.2f}")

    config.FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    slug = _slug(team)
    ends = np.array(obs["ends"]) if obs["ends"] else np.empty((0, 2))
    figs = {
        f"corners_delivery_{slug}_{tag}.png": plot_delivery_zones(ends, zone_counts, team),
        f"corners_box_load_{slug}_{tag}.png": plot_box_occupation(
            obs["att_box"], obs["def_box"], team
        ),
        f"corners_first_contact_for_{slug}_{tag}.png": plot_first_contacts(
            np.array([loc for won, loc in obs["fc_for"] if won]).reshape(-1, 2),
            np.array([loc for won, loc in obs["fc_for"] if not won]).reshape(-1, 2),
            team, attacking=True,
        ),
        f"corners_first_contact_against_{slug}_{tag}.png": plot_first_contacts(
            np.array([loc for won, loc in obs["fc_against"] if not won]).reshape(-1, 2),
            np.array([loc for won, loc in obs["fc_against"] if won]).reshape(-1, 2),
            team, attacking=False,
        ),
    }
    for name, fig in figs.items():
        out = config.FIGURES_DIR / name
        fig.savefig(out, dpi=150, bbox_inches="tight")
        print(f"  guardado: {out}")


def main() -> None:
    """Punto de entrada del CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--team", type=str, default=config.DEFAULT_TEAM)
    parser.add_argument("--match-id", type=int, default=None)
    args = parser.parse_args()

    if args.match_id is not None:
        report(match_corners(args.match_id, args.team), args.team, str(args.match_id))
        return
    matches = load_matches().sort_values("match_date")
    all_obs = []
    for _, match in matches.iterrows():
        all_obs.append(match_corners(int(match["match_id"]), args.team))
    print(f"{len(matches)} partidos procesados")
    report(_merge_obs(all_obs), args.team, "temporada")


if __name__ == "__main__":
    main()
