"""Compara las métricas publicadas con Understat (fuente pública independiente).

Uso:
    uv run python scripts/validacion_externa.py --descargar   # foto nueva de Understat
    uv run python scripts/validacion_externa.py               # compara con la foto versionada

La descarga guarda en ``eval/external/understat.json`` solo los partidos de los
equipos de club publicados (fecha, goles, xG y PPDA), con la URL y la fecha de
acceso. La comparación no usa red y deja el resultado en
``eval/results/externa.json`` y una tabla en markdown por pantalla.
Las selecciones no entran: Understat no cubre torneos internacionales.
"""

import argparse
import gzip
import json
import urllib.request
from datetime import date

from pitchiq import config
from pitchiq.eval.externa import comparar_equipo, normalizar, resumen

TEAMS_DIR = config.ROOT_DIR / "app" / "static" / "report" / "teams"
FOTO = config.ROOT_DIR / "eval" / "external" / "understat.json"
SALIDA = config.ROOT_DIR / "eval" / "results" / "externa.json"

# competición de la web -> liga y año de inicio de temporada en Understat
LIGAS = {
    ("La Liga", "2015/16"): ("La_liga", 2015),
    ("La Liga", "2020/21"): ("La_liga", 2020),
    ("Bundesliga", "2023/24"): ("Bundesliga", 2023),
    ("Ligue 1", "2022/23"): ("Ligue_1", 2022),
}
# nombres que Understat escribe distinto (tras normalizar)
ALIAS = {"psg": "parissaintgermain", "parissaintgermain": "parissaintgermain"}


def _equipos() -> list:
    return [json.loads(f.read_text(encoding="utf-8")) for f in sorted(TEAMS_DIR.glob("*.json"))]


def _liga(liga: str, anio: int) -> dict:
    url = f"https://understat.com/getLeagueData/{liga}/{anio}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest",
        "Referer": f"https://understat.com/league/{liga}/{anio}",
    })
    with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310 (URL fija)
        crudo = r.read()
    if crudo[:2] == b"\x1f\x8b":
        crudo = gzip.decompress(crudo)
    return json.loads(crudo)["teams"]


def descargar() -> None:
    """Guarda la foto de Understat para los equipos de club publicados."""
    foto = {"fuente": "https://understat.com", "acceso": date.today().isoformat(), "equipos": {}}
    cache: dict = {}
    for team in _equipos():
        clave = (team["competicion"], team["temporada"])
        if clave not in LIGAS:
            continue
        liga, anio = LIGAS[clave]
        if clave not in cache:
            cache[clave] = _liga(liga, anio)
        buscado = ALIAS.get(normalizar(team["equipo"]), normalizar(team["equipo"]))
        externo = next((t for t in cache[clave].values() if normalizar(t["title"]) == buscado), None)
        if externo is None:
            print(f"sin equivalente en Understat: {team['equipo']}")
            continue
        foto["equipos"][team["slug"]] = {
            "understat": f"https://understat.com/league/{liga}/{anio}",
            "nombre_understat": externo["title"],
            "partidos": [
                {"fecha": h["date"][:10], "local": h["h_a"] == "h",
                 "goles_favor": int(h["scored"]), "goles_contra": int(h["missed"]),
                 "xg_favor": round(float(h["xG"]), 3), "xg_contra": round(float(h["xGA"]), 3),
                 "ppda_att": int(h["ppda"]["att"]), "ppda_def": int(h["ppda"]["def"])}
                for h in externo["history"]
            ],
        }
        print(f"{team['nombre']} {team['temporada']}: {len(externo['history'])} partidos")
    FOTO.parent.mkdir(parents=True, exist_ok=True)
    FOTO.write_text(json.dumps(foto, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def _es(v: float, d: int = 2) -> str:
    return f"{v:.{d}f}".replace(".", ",")


def comparar() -> None:
    foto = json.loads(FOTO.read_text(encoding="utf-8"))
    filas = [comparar_equipo(t, foto["equipos"][t["slug"]]["partidos"])
             for t in _equipos() if t["slug"] in foto["equipos"]]
    agregado = resumen(filas)
    SALIDA.write_text(json.dumps(
        {"fuente": foto["fuente"], "acceso": foto["acceso"], "resumen": agregado,
         "equipos": [{k: v for k, v in f.items() if not k.startswith("_")} for f in filas]},
        ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print("| Equipo | Partidos | Goles a favor | xG a favor / partido | PPDA (con presiones) | PPDA clásico |")
    print("|---|---|---|---|---|---|")
    for f in filas:
        print(f"| {f['equipo']} ({f['competicion']}) | {f['partidos_cruzados']} "
              f"| {f['goles_favor'][0]} / {f['goles_favor'][1]} "
              f"| {_es(f['xg_favor_por_partido'][0])} / {_es(f['xg_favor_por_partido'][1])} "
              f"| {_es(f['ppda_medio'][0])} / {_es(f['ppda_medio'][1])} "
              f"| {_es(f['ppda_clasico_medio'][0]) if f['ppda_clasico_medio'] else '—'} / "
              f"{_es(f['ppda_clasico_medio'][1]) if f['ppda_clasico_medio'] else '—'} |")
    print()
    print(json.dumps(agregado, ensure_ascii=False, indent=1))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--descargar", action="store_true", help="renueva la foto de Understat")
    args = parser.parse_args()
    if args.descargar:
        descargar()
    comparar()


if __name__ == "__main__":
    main()
