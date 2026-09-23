"""Precómputo de los artefactos que sirve la app pública (paso HUMANO, en local).

La app FastAPI de producción no genera nada: solo sirve lo que este script deja
en app/static/report/. Hay dos tipos de artefacto:

- teams/<slug>.json: las métricas y gráficas de cada equipo publicado (lista
  en scripts/publicacion.yaml). Solo métricas deterministas, SIN key.
- report.md + evidence.json: el informe escrito por el LLM y su evidencia,
  CON key (la única llamada cara).

El humano corre esto en local, revisa el resultado y COMMITEA los artefactos.

Uso:
    uv run python scripts/precompute.py --demo-data     # métricas de los equipos (sin key)
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
TEAMS_DIR = REPORT_DIR / "teams"
OG_DIR = REPORT_DIR / "og"  # imágenes de vista previa al compartir (1200×630)


PUBLICACION = config.ROOT_DIR / "scripts" / "publicacion.yaml"


def _slugify(text: str) -> str:
    """Texto a slug de URL: minúsculas, sin acentos, guiones."""
    import re
    import unicodedata

    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")


def _temporada_corta(season_name: str) -> str:
    """'2015/2016' -> '2015/16'; '2024' se queda igual."""
    parts = str(season_name).split("/")
    return f"{parts[0]}/{parts[1][-2:]}" if len(parts) == 2 else str(season_name)


def clasificacion(matches) -> "list[str]":
    """Equipos ordenados por la clasificación que dan los resultados."""
    tabla = _tabla(matches)
    return sorted(tabla, key=lambda t: (-tabla[t][0], -tabla[t][1], -tabla[t][2], t))


def temporada_completa(matches) -> bool:
    """True si la competición trae (casi) todos los partidos de una liga a doble vuelta."""
    n = len(set(matches["home_team"]) | set(matches["away_team"]))
    return n > 2 and len(matches) >= 0.95 * n * (n - 1)


def _tabla(matches) -> "dict[str, list[int]]":
    """Puntos, diferencia de goles y goles a favor de cada equipo."""
    tabla: dict[str, list[int]] = {}
    for _, m in matches.iterrows():
        for team, gf, gc in ((m["home_team"], m["home_score"], m["away_score"]),
                             (m["away_team"], m["away_score"], m["home_score"])):
            fila = tabla.setdefault(team, [0, 0, 0])  # puntos, diferencia, goles
            fila[0] += 3 if gf > gc else 1 if gf == gc else 0
            fila[1] += int(gf) - int(gc)
            fila[2] += int(gf)
    return tabla


_NOMBRES_RAROS = {"Wales W": "Wales", "WNT Finland": "Finland"}


def nombre_en(nombre: str) -> str:
    """Nombre en inglés para la web: el de StatsBomb sin el sufijo femenino."""
    return _NOMBRES_RAROS.get(nombre, nombre.removesuffix(" Women's"))


def _traductor(tabla: dict):
    """Nombre para la web: la traducción, o el nombre sin el sufijo femenino de StatsBomb."""
    def traducir(nombre: str) -> str:
        base = nombre.removesuffix(" Women's")
        return tabla.get(nombre) or tabla.get(base, base)
    return traducir


def equipos_a_publicar() -> "list[dict]":
    """Resuelve publicacion.yaml a la lista de equipos (con su competición)."""
    import yaml

    from pitchiq.data.loader import load_competitions, load_matches

    conf = yaml.safe_load(PUBLICACION.read_text(encoding="utf-8"))
    traducir = _traductor(conf.get("traducciones") or {})
    catalogo = load_competitions()
    entradas = []
    for bloque in conf["competiciones"]:
        cid, sid = int(bloque["competition_id"]), int(bloque["season_id"])
        fila = catalogo[(catalogo["competition_id"] == cid) & (catalogo["season_id"] == sid)]
        if fila.empty:
            raise SystemExit(f"competición {cid}/{sid} no está en StatsBomb Open Data")
        competicion = bloque.get("nombre") or str(fila.iloc[0]["competition_name"]).replace(
            "1. Bundesliga", "Bundesliga")
        temporada = _temporada_corta(fila.iloc[0]["season_name"])
        matches = load_matches(competition_id=cid, season_id=sid)
        orden = clasificacion(matches)
        completa = temporada_completa(matches)
        if "equipos" in bloque:
            equipos = list(bloque["equipos"])
        else:
            equipos = orden[: int(bloque["top"])]
        for equipo in equipos:
            entradas.append({
                "equipo": equipo, "nombre": traducir(equipo), "traducir": traducir,
                "competition_id": cid, "season_id": sid,
                "competicion": competicion, "temporada": temporada,
                "slug": _slugify(f"{traducir(equipo)} {temporada}"),
                # el puesto solo tiene sentido si la temporada está completa
                "posicion": orden.index(equipo) + 1 if completa else None,
                "n_equipos": len(orden) if completa else None,
            })
    return entradas


def _sin_nan(obj):
    """Sustituye NaN por None en estructuras anidadas (JSON válido, sin inventar)."""
    if isinstance(obj, float) and math.isnan(obj):
        return None
    if isinstance(obj, dict):
        return {k: _sin_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sin_nan(v) for v in obj]
    return obj


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


def _sample_team(slug: str, nombre: str, orden: int, desplaz: float) -> dict:
    """Equipo sintético con la misma forma que los reales."""
    rivales = ["Rival A", "Rival B", "Rival C", "Rival D"]
    return {
        "slug": slug, "equipo": nombre, "nombre": nombre, "orden": orden,
        "competicion": "Liga de muestra", "temporada": "2026",
        "herramientas": {
            "presion": {
                "team": nombre, "n_partidos": 4,
                "acciones_defensivas_totales": 800,
                "acciones_defensivas_por_partido": 200.0 + desplaz,
                "ppda_medio": 2.48, "pct_acciones_campo_rival": 50.0,
            },
            "forma_defensiva": {
                "team": nombre, "hull_area_media_yd2": 500.0 + desplaz,
                "anchura_media": 35.0, "profundidad_media": 24.0,
                "altura_linea_media": 52.9, "soporte_presion_medio": 1.3,
                "partidos_con_360": 3,
            },
            "corners_ataque": {
                "team": nombre, "n_corners": 236,
                "zonas_saque": {"corto": 4, "centro": 3, "primer palo": 2,
                                "segundo palo": 1},
                "box_load_atacantes_medio": 5.0,
                "box_load_defensores_medio": 10.0,
                "pct_primer_contacto_ganado": 60.0, "xg_a_favor": 1.5,
            },
            "corners_defensa": {
                "team": nombre, "n_corners": 5,
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
    }


def build_sample() -> None:
    """Genera las fixtures sintéticas de sample/ (sin key, para tests y CI)."""
    sample_dir = REPORT_DIR / "sample"
    figures_dir = sample_dir / "figures"
    teams_dir = sample_dir / "teams"
    figures_dir.mkdir(parents=True, exist_ok=True)
    teams_dir.mkdir(parents=True, exist_ok=True)

    (sample_dir / "report.md").write_text(SAMPLE_MARKDOWN, encoding="utf-8")
    (sample_dir / "evidence.json").write_text(
        json.dumps(SAMPLE_EVIDENCE, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for team in (
        _sample_team("equipo-muestra", "Equipo Muestra", 0, 0.0),
        _sample_team("equipo-rival", "Equipo Rival", 1, 10.0),
    ):
        (teams_dir / f"{team['slug']}.json").write_text(
            json.dumps(team, ensure_ascii=False), encoding="utf-8"
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


def build_team_data(entry: dict, orden: int) -> None:
    """Exporta las métricas y gráficas de un equipo publicado (sin key)."""
    import warnings

    warnings.filterwarnings("ignore", category=RuntimeWarning)  # medias de listas vacías sin 360
    import numpy as np

    from pitchiq.agent import tools as agent_tools
    from pitchiq.data.loader import has_360, load_events, load_frames, load_matches
    from pitchiq.metrics.frames import merge_frames_events, visible_teammates
    from pitchiq.metrics.pressing import defensive_actions, high_turnovers, ppda
    from pitchiq.metrics.set_pieces import delivery_zone, find_corners
    from pitchiq.metrics.spatial import defensive_line_height

    team = entry["equipo"]
    competition_id, season_id = entry["competition_id"], entry["season_id"]
    matches = load_matches(competition_id=competition_id, season_id=season_id)
    matches = matches[
        (matches["home_team"] == team) | (matches["away_team"] == team)
    ].sort_values("match_date").reset_index(drop=True)

    recovery = np.zeros((5, 6), dtype=int)  # filas = ancho (y), columnas = largo (x)
    block = np.zeros((16, 24))  # densidad de posiciones visibles al defender
    per_match, corner_ends = [], []

    for i_match, (_, m) in enumerate(matches.iterrows()):
        match_id = int(m["match_id"])
        events = load_events(match_id)
        frames = load_frames(match_id) if has_360(m) else None
        home = m["home_team"] == team

        actions = defensive_actions(events, team)
        grid, _, _ = np.histogram2d(actions["x"], actions["y"], bins=[6, 5],
                                    range=[[0, 120], [0, 80]])
        recovery += grid.T.astype(int)

        merged = merge_frames_events(frames, events) if frames is not None else None
        if merged is not None and not merged.empty:
            ids = set(actions["id"])
            for _, frame in merged[merged["event_uuid"].isin(ids)].groupby("event_uuid"):
                xy = visible_teammates(frame, team)
                if len(xy):
                    dens, _, _ = np.histogram2d(xy[:, 0], xy[:, 1], bins=[24, 16],
                                                range=[[0, 120], [0, 80]])
                    block += dens.T

        line = (defensive_line_height(frames, events, team).mean("line_height")
                if frames is not None else float("nan"))
        match_ppda = ppda(events, team)
        rival = m["away_team"] if home else m["home_team"]
        shots = events[(events["type"] == "Shot") & (events["period"] < 5)]
        xg = shots.groupby("team")["shot_statsbomb_xg"].sum()
        robos = high_turnovers(events, team)
        per_match.append({
            "fecha": str(m["match_date"])[:10],
            "rival": entry.get("traducir", str)(rival),
            "rival_en": nombre_en(rival),
            "local": bool(home),
            "goles_favor": int(m["home_score"] if home else m["away_score"]),
            "goles_contra": int(m["away_score"] if home else m["home_score"]),
            "altura_linea": None if np.isnan(line) else round(float(line), 1),
            "ppda": round(float(match_ppda), 2) if np.isfinite(match_ppda) else None,
            "xg_favor": round(float(xg.get(team, 0.0)), 2),
            "xg_contra": round(float(xg.drop(team, errors="ignore").sum()), 2),
            "acciones_defensivas": int(len(actions)),
            "robos_altos": robos["n"],
            "robos_altos_tiro": robos["con_tiro"],
            "zonas": grid.T.astype(int).tolist(),
        })

        attacking, _ = find_corners(events, team)
        for _, c in attacking.iterrows():
            end = c.get("pass_end_location")
            if isinstance(end, (list, tuple)):
                corner_ends.append({
                    "x": round(float(end[0]), 1), "y": round(float(end[1]), 1),
                    "desde_arriba": float(c["location"][1]) > 40,
                    "zona": delivery_zone(c),
                    "p": i_match,
                })

    tools = agent_tools.run_all_tools(team, competition_id=competition_id, season_id=season_id)
    agent_tools._season_data.cache_clear()  # un equipo de liga completa ocupa cientos de MB
    payload = {
        "slug": entry["slug"],
        "equipo": team,
        "nombre": entry.get("nombre", team),
        "con_360": bool(tools["forma_defensiva"].partidos_con_360),
        "posicion": entry.get("posicion"),
        "n_equipos": entry.get("n_equipos"),
        "competicion": entry["competicion"],
        "temporada": entry["temporada"],
        "orden": orden,
        "herramientas": {k: v.model_dump() for k, v in tools.items()},
        "zonas_recuperacion": recovery.tolist(),
        "bloque_densidad": (block / max(block.max(), 1)).round(3).tolist(),
        "partidos": per_match,
        "corners": corner_ends,
    }
    TEAMS_DIR.mkdir(parents=True, exist_ok=True)
    out = TEAMS_DIR / f"{entry['slug']}.json"
    out.write_text(json.dumps(_sin_nan(payload), ensure_ascii=False), encoding="utf-8")
    build_og_image(_sin_nan(payload))
    print(f"{team} ({entry['competicion']} {entry['temporada']}): {len(per_match)} partidos", flush=True)


def _resultados(partidos: list) -> dict:
    gf = sum(p["goles_favor"] for p in partidos)
    gc = sum(p["goles_contra"] for p in partidos)
    v = sum(p["goles_favor"] > p["goles_contra"] for p in partidos)
    e = sum(p["goles_favor"] == p["goles_contra"] for p in partidos)
    return {"pj": len(partidos), "v": v, "e": e, "d": len(partidos) - v - e, "gf": gf, "gc": gc}


def _es(v: float, d: int) -> str:
    return f"{v:.{d}f}".replace(".", ",")


def build_og_image(payload: dict, out_dir=OG_DIR) -> None:
    """Tarjeta 1200×630 para la vista previa del enlace (LinkedIn, WhatsApp...).

    Solo muestra cifras ya exportadas en el JSON del equipo: nada nuevo que verificar.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    from matplotlib.patches import Circle, Rectangle

    disponibles = {f.name for f in font_manager.fontManager.ttflist}
    cond = next((f for f in ("Barlow Condensed", "Avenir Next Condensed", "DIN Condensed")
                 if f in disponibles), "DejaVu Sans")
    bg, ink, ink2, muted, rule, accent = "#0e1310", "#edf2ee", "#b6c0b9", "#8b958f", "#29322c", "#ef4355"

    T, R = payload["herramientas"], _resultados(payload["partidos"])
    fig = plt.figure(figsize=(12, 6.3), dpi=100, facecolor=bg)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, 1200)
    ax.set_ylim(630, 0)
    ax.axis("off")
    # líneas de campo de fondo, a la derecha
    for artist in (Rectangle((800, 40), 460, 550), Circle((800, 315), 90),
                   Rectangle((1090, 170), 170, 290), Rectangle((1200, 250), 60, 130)):
        artist.set(fill=False, edgecolor="#1b261e", linewidth=2)
        ax.add_patch(artist)

    ax.text(70, 78, "Pitch", color=ink, fontsize=30, fontweight="bold", family=cond, va="center")
    ax.text(70 + 88, 78, "IQ", color=accent, fontsize=30, fontweight="bold", family=cond, va="center")
    comp = f"{payload['competicion']} · {payload['temporada']}".upper()
    if payload.get("posicion"):
        comp += f"  ·  {payload['posicion']}.º DE {payload['n_equipos']}"
    ax.text(70, 160, comp, color=accent, fontsize=17, fontweight="bold", va="center")
    nombre = payload["nombre"]
    ax.text(66, 232, nombre, color=ink, fontsize=74 if len(nombre) < 16 else 56,
            fontweight="bold", family=cond, va="center")
    balance = (f"{R['pj']} partidos · {R['v']}V {R['e']}E {R['d']}D · "
               f"{R['gf']}–{R['gc']} goles")
    ax.text(70, 305, balance, color=ink2, fontsize=21, va="center")

    kpis = [("PPDA medio", _es(T["presion"]["ppda_medio"], 2)),
            ("En campo rival", _es(T["presion"]["pct_acciones_campo_rival"], 1) + " %")]
    altura = T["forma_defensiva"].get("altura_linea_media")
    kpis.append(("Altura defensa", _es(altura, 1)) if altura is not None
                else ("Goles/partido", _es(R["gf"] / max(1, R["pj"]), 2)))
    kpis.append(("xG en córners", _es(T["corners_ataque"]["xg_a_favor"], 2)))
    for i, (lab, val) in enumerate(kpis):
        x = 70 + i * 272
        ax.add_patch(Rectangle((x, 380), 252, 150, facecolor="#151b17", edgecolor=rule, linewidth=1.5))
        ax.text(x + 22, 418, lab, color=ink2, fontsize=17, va="center")
        ax.text(x + 20, 482, val, color=ink, fontsize=50, fontweight="bold", family=cond, va="center")
    ax.text(70, 585, "Cada cifra, contrastada con las métricas calculadas · StatsBomb Open Data",
            color=muted, fontsize=15, va="center")
    out_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_dir / f"{payload['slug']}.png", facecolor=bg)
    plt.close(fig)


def build_og_all() -> None:
    """Regenera las imágenes de vista previa desde los JSON ya exportados."""
    for f in sorted(TEAMS_DIR.glob("*.json")):
        build_og_image(json.loads(f.read_text(encoding="utf-8")))
        print(f"og: {f.stem}", flush=True)


def build_demo_data() -> None:
    """Exporta todos los equipos de publicacion.yaml (sin key), borrando los retirados."""
    entradas = equipos_a_publicar()
    print(f"publicando {len(entradas)} equipos", flush=True)
    TEAMS_DIR.mkdir(parents=True, exist_ok=True)
    vigentes = {e["slug"] for e in entradas}
    for viejo in [*TEAMS_DIR.glob("*.json"), *OG_DIR.glob("*.png")]:
        if viejo.stem not in vigentes:
            viejo.unlink()
    for orden, entry in enumerate(entradas):
        build_team_data(entry, orden)


def build_real(team: str) -> None:
    """Genera métricas, figuras y el informe real (requiere ANTHROPIC_API_KEY)."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit(
            "Falta ANTHROPIC_API_KEY: el precómputo genera el informe con el LLM "
            "una única vez, en local. Exporta la key y relanza:\n"
            "  ANTHROPIC_API_KEY=sk-ant-... uv run python scripts/precompute.py\n"
            "Las métricas no necesitan key: uv run python scripts/precompute.py --demo-data"
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

    print("2/4 exportando métricas de los equipos publicados (sin key)...")
    build_demo_data()

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
                        help="exporta solo las métricas de los equipos (sin key)")
    parser.add_argument("--og", action="store_true",
                        help="regenera solo las imágenes de vista previa (sin key)")
    args = parser.parse_args()

    if args.sample:
        build_sample()
    elif args.demo_data:
        build_demo_data()
    elif args.og:
        build_og_all()
    else:
        build_real(args.team)


if __name__ == "__main__":
    main()
