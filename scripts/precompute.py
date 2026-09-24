"""Precómputo de los artefactos que sirve la app pública (paso HUMANO, en local).

La app FastAPI de producción no genera nada: solo sirve lo que este script deja
en app/static/report/. Hay dos tipos de artefacto:

- teams/<slug>.json: las métricas y gráficas de cada equipo publicado (lista
  en scripts/publicacion.yaml). Solo métricas deterministas, SIN key.
- informes/<slug>.json: el informe del analista IA (ES + EN), el dossier de
  cifras que pudo citar y su verificación. Con el LLM: la API si hay
  ANTHROPIC_API_KEY o, si no, el CLI `claude` con la suscripción.

El humano corre esto en local, revisa el resultado y COMMITEA los artefactos.

Uso:
    uv run python scripts/precompute.py --demo-data     # métricas de los equipos (sin LLM)
    uv run python scripts/precompute.py                 # informes de todos los equipos
    uv run python scripts/precompute.py --equipos bayer-leverkusen-2023-24 --solo-faltan
    uv run python scripts/precompute.py --sample        # fixtures sintéticas (sin LLM)
"""

import argparse
import json
import math
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


def clasificacion(matches, directo: bool = False) -> "list[str]":
    """Equipos ordenados por la clasificación que dan los resultados.

    Empates a puntos: diferencia de goles y goles a favor (Premier). Con
    ``directo=True`` manda antes el enfrentamiento directo entre los empatados,
    puntos y luego diferencia en esos partidos (La Liga).
    """
    tabla = _tabla(matches)
    directos: dict[str, list[int]] = {}
    if directo:
        por_puntos: dict[int, list[str]] = {}
        for t, fila in tabla.items():
            por_puntos.setdefault(fila[0], []).append(t)
        for grupo in (g for g in por_puntos.values() if len(g) > 1):
            entre = matches[matches["home_team"].isin(grupo) & matches["away_team"].isin(grupo)]
            mini = _tabla(entre)
            directos.update({t: mini.get(t, [0, 0, 0])[:2] for t in grupo})
    return sorted(tabla, key=lambda t: (-tabla[t][0], *[-v for v in directos.get(t, [0, 0])],
                                        -tabla[t][1], -tabla[t][2], t))


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
    tabla = conf.get("traducciones") or {}
    traducir = _traductor(tabla)
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
        orden = clasificacion(matches, directo=bloque.get("desempate") == "directo")
        completa = temporada_completa(matches)
        if bloque.get("equipos") == "todos":
            equipos = list(orden)
        elif "equipos" in bloque:
            equipos = list(bloque["equipos"])
        else:
            equipos = orden[: int(bloque["top"])]
        puestos = {t: i + 1 for i, t in enumerate(orden)} if completa else {}
        for equipo in equipos:
            entradas.append({
                "equipo": equipo, "nombre": traducir(equipo), "traducciones": tabla,
                "competition_id": cid, "season_id": sid,
                "competicion": competicion, "temporada": temporada,
                "slug": _slugify(f"{traducir(equipo)} {temporada}"),
                # el puesto solo tiene sentido si la temporada está completa
                "posicion": orden.index(equipo) + 1 if completa else None,
                "n_equipos": len(orden) if completa else None,
                "puestos": puestos,
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


INFORMES_DIR = REPORT_DIR / "informes"  # informes del analista IA, uno por equipo

# Informe de muestra, con citas como las escribe el modelo (tests y CI, sin LLM)
SAMPLE_INFORME = {
    "es": ("### Veredicto\n\nInforme de MUESTRA escrito sin LLM para tests y CI. "
           "El equipo ganó {resultados.victorias} de {resultados.partidos} partidos, presiona "
           "con un PPDA de {metrica.ppda} y defiende con la línea a {metrica.altura} m "
           "de su portería.\n\n### Balón parado\n\nLanzó {corners.a_favor} córners."),
    "en": ("### Verdict\n\nSAMPLE report written without an LLM for tests and CI. "
           "The team won {resultados.victorias} of {resultados.partidos} matches, presses "
           "with a PPDA of {metrica.ppda} and defends with its line {metrica.altura} m "
           "from its own goal.\n\n### Set pieces\n\nIt took {corners.a_favor} corners."),
}


class _PlantillaLLM:
    """LLM falso para la muestra: devuelve el texto fijo del idioma pedido."""

    model_used = None

    def complete(self, system: str, user: str) -> str:
        return SAMPLE_INFORME["en" if "inglés" in user else "es"]


def informe(team: dict, todos: "list[dict]", llm, retriever=None, sample: bool = False) -> dict:
    """Informe del analista en español e inglés, con su dossier y su verificación."""
    from pitchiq.agent.report import generate_report

    out = {"slug": team["slug"], "equipo": team["nombre"], "generated_at": date.today().isoformat(),
           "sample": sample, "modelo": None}
    for idioma in ("es", "en"):
        rep = generate_report(team, todos, llm=llm, idioma=idioma, retriever=retriever)
        out["dossier"], out["contexto"] = rep.dossier, rep.context
        out["modelo"] = getattr(llm, "model_used", None)
        out[idioma] = {
            "markdown": rep.markdown,
            "citas": sum(f.grounded for f in rep.grounding.figures),
            "sin_respaldo": [f.text for f in rep.grounding.ungrounded],
            "reintentos": rep.retries_used,
        }
    return out


def _sample_team(slug: str, nombre: str, orden: int, desplaz: float) -> dict:
    """Equipo sintético con la misma forma que los reales."""
    rivales = ["Rival A", "Rival B", "Rival C", "Rival D"]
    estados = {"ganando": {"minutos": 40.0, "xg_favor": 0.5, "xg_contra": 0.3},
               "empatando": {"minutos": 45.0, "xg_favor": 0.8, "xg_contra": 0.4},
               "perdiendo": {"minutos": 5.0, "xg_favor": 0.1, "xg_contra": 0.1}}
    partidos = [
        {"fecha": f"2026-01-0{i + 1}", "rival": r, "local": i % 2 == 0,
         "goles_favor": 2, "goles_contra": 1,
         "altura_linea": None if i == 2 else 50.0 + i, "ppda": 2.5, "ppda_clasico": 10.0 + i,
         "xg_favor": 1.4, "xg_contra": 0.8, "tiros": 3, "field_tilt": 55.0 + desplaz / 10,
         "progresivos": 40 + i, "centros": 10, "acciones_defensivas": 200, "robos_altos": 3,
         "robos_altos_tiro": 1, "entradas": {"izquierda": 5, "centro": 3, "derecha": 4},
         "estados": estados, "rival_puesto": i + 1,
         "zonas": [[1 + ix + iy for ix in range(6)] for iy in range(5)]}
        for i, r in enumerate(rivales)
    ]
    tiros = [{"x": 100.0 + i, "y": 40.0, "xg": 0.3, "gol": i % 3 == 0, "penalti": False, "p": i % 4}
             for i in range(12)]
    return {
        "identidad": {},
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
                "team": nombre, "hull_area_media_m2": 420.0 + desplaz,
                "anchura_media": 32.0, "profundidad_media": 22.0,
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
                "indice_orientacion_hombre": 2.74,
                "pct_primer_contacto_concedido": 40.0, "xg_en_contra": 0.5,
            },
        },
        "zonas_recuperacion": [[10 + 3 * ix + iy for ix in range(6)] for iy in range(5)],
        "bloque_densidad": [
            [round(math.exp(-((ix - 10) ** 2 + (iy - 8) ** 2) / 40), 3) for ix in range(24)]
            for iy in range(16)
        ],
        "partidos": partidos,
        "corners": [
            {"x": 115.0, "y": 40.0, "desde_arriba": False, "zona": "centro", "p": 0},
            {"x": 118.0, "y": 78.0, "desde_arriba": True, "zona": "corto", "p": 1},
        ],
        "tiros": tiros,
        "jugadores": [
            {"nombre": "Ana Muestra", "posicion": "Center Forward", "partidos": 4, "minutos": 360,
             "goles": 3, "asistencias": 1, "tiros": 10, "xg": 2.1, "pases_clave": 5, "progresivos": 30,
             "presiones": 40, "acciones_defensivas": 50, "recuperaciones": 12},
            {"nombre": "Bea Ejemplo", "posicion": "Center Back", "partidos": 4, "minutos": 350,
             "goles": 0, "asistencias": 0, "tiros": 1, "xg": 0.1, "pases_clave": 1, "progresivos": 45,
             "presiones": 25, "acciones_defensivas": 80, "recuperaciones": 30},
        ],
        "agregados": agregados(partidos, tiros),
    }


def build_sample() -> None:
    """Genera las fixtures sintéticas de sample/ (sin key, para tests y CI)."""
    sample_dir = REPORT_DIR / "sample"
    teams_dir, informes_dir = sample_dir / "teams", sample_dir / "informes"
    teams_dir.mkdir(parents=True, exist_ok=True)
    informes_dir.mkdir(parents=True, exist_ok=True)
    equipos = [_sample_team("equipo-muestra", "Equipo Muestra", 0, 0.0),
               _sample_team("equipo-rival", "Equipo Rival", 1, 10.0)]
    for team in equipos:
        (teams_dir / f"{team['slug']}.json").write_text(
            json.dumps(team, ensure_ascii=False), encoding="utf-8"
        )
    inf = informe(equipos[0], equipos, _PlantillaLLM(), sample=True)
    inf["generated_at"] = "2026-01-01"
    (informes_dir / "equipo-muestra.json").write_text(
        json.dumps(inf, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"fixtures de muestra en {sample_dir}")


IDENTIDAD = config.ROOT_DIR / "scripts" / "identidad_equipos.yaml"


def identidad(equipo: str) -> dict:
    """Bandera (selecciones) o colores (clubes) para el escudo de la web; {} si no hay."""
    import yaml

    datos = yaml.safe_load(IDENTIDAD.read_text(encoding="utf-8"))
    base = equipo.removesuffix(" Women's")
    if base in datos.get("banderas", {}) or equipo in datos.get("banderas", {}):
        return {"bandera": datos["banderas"].get(equipo) or datos["banderas"][base]}
    if equipo in datos.get("colores", {}):
        fondo, texto, borde = datos["colores"][equipo]
        return {"colores": {"fondo": fondo, "texto": texto, "borde": borde}}
    return {}


def _jugadores_temporada(jugadores: dict) -> "list[dict]":
    """Jugadores con minutos, ordenados por minutos, con su posición más jugada."""
    out = []
    for nombre, j in jugadores.items():
        if j["minutos"] <= 0:
            continue
        pos = max(j["posiciones"], key=j["posiciones"].get) if j["posiciones"] else None
        fila = {"nombre": nombre, "posicion": pos, "partidos": j["partidos"]}
        fila.update({k: round(v, 2) if isinstance(v, float) else v
                     for k, v in j.items() if k not in ("posiciones", "partidos")})
        fila["minutos"] = round(fila["minutos"])
        out.append(fila)
    return sorted(out, key=lambda f: -f["minutos"])


def agregados(partidos: list, tiros: list) -> dict:
    """Medias por partido de la temporada: lo que usan los percentiles y la comparativa."""
    import numpy as np

    def media(clave):
        vals = [p[clave] for p in partidos if p.get(clave) is not None]
        return round(float(np.mean(vals)), 2) if vals else None

    n = max(1, len(partidos))
    ra = sum(p.get("robos_altos") or 0 for p in partidos)
    entradas = {k: sum((p.get("entradas") or {}).get(k, 0) for p in partidos)
                for k in ("izquierda", "centro", "derecha")}
    tot_e = sum(entradas.values()) or 1
    xg_sin_pen = [t["xg"] for t in tiros if not t["penalti"]]
    return {
        "partidos": len(partidos),
        "goles_favor": media("goles_favor"), "goles_contra": media("goles_contra"),
        "xg_favor": media("xg_favor"), "xg_contra": media("xg_contra"),
        "tiros": media("tiros"),
        "xg_por_tiro": round(float(np.mean(xg_sin_pen)), 3) if xg_sin_pen else None,
        "field_tilt": media("field_tilt"), "progresivos": media("progresivos"),
        "centros": media("centros"), "robos_altos": round(ra / n, 2),
        "robos_altos_tiro_pct": round(100 * sum(p.get("robos_altos_tiro") or 0 for p in partidos) / ra, 1) if ra else None,
        "ppda_clasico": media("ppda_clasico"), "acciones_defensivas": media("acciones_defensivas"),
        "carriles_pct": {k: round(100 * v / tot_e, 1) for k, v in entradas.items()},
    }


def build_team_data(entry: dict, orden: int) -> None:
    """Exporta las métricas y gráficas de un equipo publicado (sin key)."""
    import warnings

    warnings.filterwarnings("ignore", category=RuntimeWarning)  # medias de listas vacías sin 360
    import numpy as np

    from pitchiq.agent import tools as agent_tools
    from pitchiq.data.loader import has_360, load_events, load_frames, load_matches
    from pitchiq.metrics.attack import attack_summary, game_states
    from pitchiq.metrics.attack import shots as team_shots
    from pitchiq.metrics.frames import merge_frames_events, visible_teammates
    from pitchiq.metrics.players import CAMPOS, player_stats
    from pitchiq.metrics.pressing import defensive_actions, high_turnovers, ppda, ppda_classic
    from pitchiq.metrics.set_pieces import delivery_zone, find_corners
    from pitchiq.metrics.spatial import defensive_line_height

    team = entry["equipo"]
    traducir = _traductor(entry.get("traducciones") or {})
    competition_id, season_id = entry["competition_id"], entry["season_id"]
    matches = load_matches(competition_id=competition_id, season_id=season_id)
    matches = matches[
        (matches["home_team"] == team) | (matches["away_team"] == team)
    ].sort_values("match_date").reset_index(drop=True)

    recovery = np.zeros((5, 6), dtype=int)  # filas = ancho (y), columnas = largo (x)
    block = np.zeros((16, 24))  # densidad de posiciones visibles al defender
    per_match, corner_ends, tiros = [], [], []
    jugadores: dict[str, dict] = {}
    puestos = entry.get("puestos") or {}

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
        clasico = ppda_classic(events, team)
        rival = m["away_team"] if home else m["home_team"]
        shots = events[(events["type"] == "Shot") & (events["period"] < 5)]
        xg = shots.groupby("team")["shot_statsbomb_xg"].sum()
        robos = high_turnovers(events, team)
        ataque = attack_summary(events, team)
        for s in team_shots(events, team):
            tiros.append({**s, "p": i_match})
        for nombre, st in player_stats(events, team).items():
            acc = jugadores.setdefault(nombre, {"posiciones": {}, "partidos": 0, **dict.fromkeys(CAMPOS, 0)})
            if st["minutos"] > 0:
                acc["partidos"] += 1
                pos = st["posicion"] or "?"
                acc["posiciones"][pos] = acc["posiciones"].get(pos, 0) + st["minutos"]
            for k in CAMPOS:
                acc[k] += st[k]
        per_match.append({
            "fecha": str(m["match_date"])[:10],
            "rival": traducir(rival),
            "rival_en": nombre_en(rival),
            "local": bool(home),
            "goles_favor": int(m["home_score"] if home else m["away_score"]),
            "goles_contra": int(m["away_score"] if home else m["home_score"]),
            "altura_linea": None if np.isnan(line) else round(config.a_metros(float(line)), 1),
            "ppda": round(float(match_ppda), 2) if np.isfinite(match_ppda) else None,
            # definición clásica (sin presiones), solo para la validación externa
            "ppda_clasico": round(float(clasico), 2) if np.isfinite(clasico) else None,
            "xg_favor": round(float(xg.get(team, 0.0)), 2),
            "xg_contra": round(float(xg.drop(team, errors="ignore").sum()), 2),
            "acciones_defensivas": int(len(actions)),
            "robos_altos": robos["n"],
            "robos_altos_tiro": robos["con_tiro"],
            "zonas": grid.T.astype(int).tolist(),
            "tiros": sum(1 for s in tiros if s["p"] == i_match),
            "field_tilt": ataque["field_tilt"],
            "progresivos": ataque["progresivos"],
            "entradas": ataque["entradas_ultimo_tercio"],
            "centros": ataque["centros"],
            "estados": game_states(events, team),
            "rival_puesto": puestos.get(rival),
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
        "identidad": identidad(team),
        "herramientas": {k: v.model_dump() for k, v in tools.items()},
        "zonas_recuperacion": recovery.tolist(),
        "bloque_densidad": (block / max(block.max(), 1)).round(3).tolist(),
        "partidos": per_match,
        "corners": corner_ends,
        "tiros": tiros,
        "jugadores": _jugadores_temporada(jugadores),
    }
    payload["agregados"] = agregados(per_match, tiros)
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
    kpis.append(("Altura defensa", _es(altura, 1) + " m") if altura is not None
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
    import io

    from PIL import Image

    buf = io.BytesIO()
    fig.savefig(buf, facecolor=bg)
    plt.close(fig)
    # paleta de 64 colores: ~4 veces menos peso y sin diferencia visible en la tarjeta
    Image.open(buf).convert("RGB").quantize(64).save(out_dir / f"{payload['slug']}.png", optimize=True)


def build_og_all() -> None:
    """Regenera las imágenes de vista previa desde los JSON ya exportados."""
    for f in sorted(TEAMS_DIR.glob("*.json")):
        build_og_image(json.loads(f.read_text(encoding="utf-8")))
        print(f"og: {f.stem}", flush=True)


def _construir(args: tuple) -> str:
    entry, orden = args
    build_team_data(entry, orden)
    return entry["slug"]


def _al_dia(slug: str) -> bool:
    """True si el JSON del equipo ya tiene el formato actual (para no recalcularlo)."""
    f = TEAMS_DIR / f"{slug}.json"
    if not f.exists():
        return False
    datos = json.loads(f.read_text(encoding="utf-8"))
    return all(k in datos for k in ("agregados", "identidad", "jugadores", "tiros"))


def build_demo_data(jobs: int = 1, solo_faltan: bool = False) -> None:
    """Exporta todos los equipos de publicacion.yaml (sin key), borrando los retirados."""
    entradas = equipos_a_publicar()
    print(f"publicando {len(entradas)} equipos", flush=True)
    TEAMS_DIR.mkdir(parents=True, exist_ok=True)
    vigentes = {e["slug"] for e in entradas}
    for viejo in [*TEAMS_DIR.glob("*.json"), *OG_DIR.glob("*.png")]:
        if viejo.stem not in vigentes:
            viejo.unlink()
    tareas = []
    for i, e in enumerate(entradas):
        if solo_faltan and _al_dia(e["slug"]):
            # no se recalcula, pero el orden de publicación puede haber cambiado
            f = TEAMS_DIR / f"{e['slug']}.json"
            datos = json.loads(f.read_text(encoding="utf-8"))
            if datos.get("orden") != i:
                datos["orden"] = i
                f.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
        else:
            tareas.append((e, i))
    if jobs <= 1:
        for t in tareas:
            _construir(t)
        return
    from concurrent.futures import ProcessPoolExecutor

    # cada equipo es independiente: en paralelo el precómputo baja de horas a minutos
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        for _ in pool.map(_construir, tareas):
            pass


def build_informes(slugs: "list[str] | None" = None, solo_faltan: bool = False) -> None:
    """Informes del analista IA (ES + EN) de los equipos publicados.

    Usa la API si hay ANTHROPIC_API_KEY y, si no, el CLI `claude` con la sesión de
    la suscripción. Cada informe se guarda en cuanto termina: se puede cortar y
    reanudar con --solo-faltan.
    """
    from pitchiq.agent.llm import cliente_por_defecto
    from pitchiq.rag.retriever import open_default_retriever

    todos = [json.loads(f.read_text(encoding="utf-8")) for f in sorted(TEAMS_DIR.glob("*.json"))]
    if not todos:
        raise SystemExit("no hay métricas de equipos: uv run python scripts/precompute.py --demo-data")
    elegidos = [t for t in todos if not slugs or t["slug"] in slugs]
    if slugs and len(elegidos) != len(slugs):
        faltan = set(slugs) - {t["slug"] for t in elegidos}
        raise SystemExit(f"equipos no publicados: {', '.join(sorted(faltan))}")
    INFORMES_DIR.mkdir(parents=True, exist_ok=True)
    if solo_faltan:
        elegidos = [t for t in elegidos if not (INFORMES_DIR / f"{t['slug']}.json").exists()]

    llm = cliente_por_defecto()
    retriever = open_default_retriever()
    if retriever is None:
        print("aviso: sin índice del glosario (scripts/build_index.py); se redacta sin contexto RAG")
    try:
        for i, team in enumerate(elegidos, 1):
            inf = informe(team, todos, llm, retriever)
            (INFORMES_DIR / f"{team['slug']}.json").write_text(
                json.dumps(inf, ensure_ascii=False, indent=1), encoding="utf-8")
            estado = " · ".join(f"{k}: {inf[k]['citas']} citas, {len(inf[k]['sin_respaldo'])} sin respaldo, "
                                f"{inf[k]['reintentos']} reintentos" for k in ("es", "en"))
            print(f"[{i}/{len(elegidos)}] {team['slug']} — {estado}")
    finally:
        if retriever is not None:
            retriever.close()


def main() -> None:
    """Punto de entrada del CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--equipos", type=str, default="",
                        help="slugs separados por comas (informes); por defecto, todos")
    parser.add_argument("--sample", action="store_true",
                        help="genera solo las fixtures sintéticas (sin key)")
    parser.add_argument("--demo-data", action="store_true",
                        help="exporta solo las métricas de los equipos (sin key)")
    parser.add_argument("--jobs", type=int, default=1, help="equipos en paralelo (--demo-data)")
    parser.add_argument("--solo-faltan", action="store_true",
                        help="no recalcula los equipos ya exportados con el formato actual")
    parser.add_argument("--og", action="store_true",
                        help="regenera solo las imágenes de vista previa (sin key)")
    args = parser.parse_args()

    if args.sample:
        build_sample()
    elif args.demo_data:
        build_demo_data(jobs=args.jobs, solo_faltan=args.solo_faltan)
    elif args.og:
        build_og_all()
    else:
        slugs = [x.strip() for x in args.equipos.split(",") if x.strip()]
        build_informes(slugs or None, solo_faltan=args.solo_faltan)


if __name__ == "__main__":
    main()
