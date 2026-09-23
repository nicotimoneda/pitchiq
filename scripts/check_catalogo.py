"""Compara el catálogo de StatsBomb Open Data con la última foto versionada.

Uso:
    uv run python scripts/check_catalogo.py            # imprime las novedades (markdown)
    uv run python scripts/check_catalogo.py --update   # además actualiza la foto

Solo lee `competitions.json` (unos KB): sirve para una tarea semanal barata que
avisa cuando StatsBomb publica temporadas nuevas, sobre todo con datos 360.
"""

import argparse
import json
import sys
import urllib.request

from pitchiq import config

URL = "https://raw.githubusercontent.com/statsbomb/open-data/master/data/competitions.json"
FOTO = config.ROOT_DIR / "scripts" / "catalogo_statsbomb.json"


def _clave(c: dict) -> str:
    return f"{c['competition_id']}/{c['season_id']}"


def resumen(catalogo: list) -> dict:
    """Una entrada por competición/temporada, con lo que interesa vigilar."""
    return {
        _clave(c): {
            "competicion": c["competition_name"],
            "temporada": c["season_name"],
            "genero": c.get("competition_gender"),
            "con_360": bool(c.get("match_available_360")),
            "actualizado": c.get("match_updated"),
        }
        for c in catalogo
    }


def novedades(antes: dict, ahora: dict) -> "list[str]":
    """Líneas markdown con temporadas nuevas y temporadas que ganan 360."""
    lineas = []
    for k, c in sorted(ahora.items(), key=lambda kv: (not kv[1]["con_360"], kv[0])):
        nombre = f"{c['competicion']} {c['temporada']} (`{k}`)"
        if k not in antes:
            lineas.append(f"- Nueva: {nombre}" + (" **con 360**" if c["con_360"] else ""))
        elif c["con_360"] and not antes[k]["con_360"]:
            lineas.append(f"- Ahora con 360: {nombre}")
    return lineas


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update", action="store_true", help="guarda la foto nueva")
    args = parser.parse_args()

    with urllib.request.urlopen(URL, timeout=60) as r:  # noqa: S310 (URL fija)
        ahora = resumen(json.load(r))
    antes = json.loads(FOTO.read_text(encoding="utf-8")) if FOTO.exists() else {}
    lineas = novedades(antes, ahora)
    if lineas:
        print("\n".join(lineas))
    if args.update:
        FOTO.write_text(json.dumps(ahora, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                        encoding="utf-8")
    sys.exit(0)


if __name__ == "__main__":
    main()
