"""Validación externa: nuestras métricas frente a una fuente pública (Understat).

Compara, partido a partido, lo que publica la web (``app/static/report/teams``)
con los datos públicos de Understat para los mismos partidos:

- **Goles**: deben coincidir exactamente. Valida la ingesta y el cruce de partidos.
- **xG**: dos modelos distintos (StatsBomb y Understat); se espera parecido, no igual.
- **PPDA**: dos definiciones distintas (la nuestra cuenta las presiones como acción
  defensiva); se espera otra escala pero el mismo orden entre equipos.

Funciones puras sobre diccionarios: sin red. La descarga vive en
``scripts/validacion_externa.py`` y deja una foto versionada en ``eval/external``.
"""

import unicodedata
from datetime import date

import numpy as np
from scipy.stats import pearsonr, spearmanr


def normalizar(nombre: str) -> str:
    """Nombre comparable entre fuentes: sin acentos, minúsculas, solo letras."""
    sin_acentos = unicodedata.normalize("NFD", nombre).encode("ascii", "ignore").decode()
    return "".join(c for c in sin_acentos.lower() if c.isalnum())


def _dia(fecha: str) -> date:
    return date.fromisoformat(fecha[:10])


def cruzar_partidos(nuestros: list, externos: list) -> "list[tuple[dict, dict]]":
    """Empareja partidos por fecha (±1 día por husos horarios) y marcador local/visitante."""
    pares = []
    libres = list(externos)
    for p in nuestros:
        for e in libres:
            if abs((_dia(p["fecha"]) - _dia(e["fecha"])).days) <= 1 and p["local"] == e["local"]:
                pares.append((p, e))
                libres.remove(e)
                break
    return pares


def comparar_equipo(team: dict, externos: list) -> dict:
    """Métricas de un equipo frente a la fuente externa, solo en partidos cruzados."""
    pares = cruzar_partidos(team["partidos"], externos)
    goles_ok = sum(
        p["goles_favor"] == e["goles_favor"] and p["goles_contra"] == e["goles_contra"]
        for p, e in pares
    )
    con_xg = [(p, e) for p, e in pares if p.get("xg_favor") is not None]
    con_ppda = [(p, e) for p, e in pares if p.get("ppda") is not None and e["ppda_def"] > 0]
    con_clasico = [(p, e) for p, e in con_ppda if p.get("ppda_clasico") is not None]
    n = len(pares)

    def media(vals: list) -> "float | None":
        return round(float(np.mean(vals)), 2) if vals else None

    return {
        "equipo": team["nombre"],
        "competicion": f"{team['competicion']} {team['temporada']}",
        "partidos_nuestros": len(team["partidos"]),
        "partidos_cruzados": n,
        "goles_coinciden": goles_ok,
        "goles_favor": [sum(p["goles_favor"] for p, _ in pares), sum(e["goles_favor"] for _, e in pares)],
        "xg_favor_por_partido": [
            media([p["xg_favor"] for p, _ in con_xg]),
            media([e["xg_favor"] for _, e in con_xg]),
        ],
        "xg_contra_por_partido": [
            media([p["xg_contra"] for p, _ in con_xg]),
            media([e["xg_contra"] for _, e in con_xg]),
        ],
        # misma agregación en las dos fuentes: media de los PPDA de cada partido
        "ppda_medio": [
            media([p["ppda"] for p, _ in con_ppda]),
            media([e["ppda_att"] / e["ppda_def"] for _, e in con_ppda]),
        ],
        # la definición clásica (sin presiones) es la comparable con Understat
        "ppda_clasico_medio": [
            round(float(np.mean([p["ppda_clasico"] for p, _ in con_clasico])), 2),
            round(float(np.mean([e["ppda_att"] / e["ppda_def"] for _, e in con_clasico])), 2),
        ] if con_clasico else None,
        "_xg_partido": [(p["xg_favor"], e["xg_favor"]) for p, e in con_xg],
        "_ppda_clasico_partido": [(p["ppda_clasico"], e["ppda_att"] / e["ppda_def"]) for p, e in con_clasico],
    }


def resumen(filas: list) -> dict:
    """Agregados entre equipos: coincidencia de goles y concordancia de xG y PPDA."""
    xg = [par for f in filas for par in f["_xg_partido"]]
    con_ppda = [f for f in filas if f["ppda_medio"][0] is not None and f["ppda_medio"][1] is not None]
    nuestro_ppda = [f["ppda_medio"][0] for f in con_ppda]
    externo_ppda = [f["ppda_medio"][1] for f in con_ppda]
    return {
        "partidos_cruzados": sum(f["partidos_cruzados"] for f in filas),
        "goles_coinciden": sum(f["goles_coinciden"] for f in filas),
        "xg_partido_pearson": round(float(pearsonr(*zip(*xg))[0]), 3),
        "xg_partido_diferencia_media": round(float(np.mean([a - b for a, b in xg])), 3),
        "ppda_spearman_equipos": round(float(spearmanr(nuestro_ppda, externo_ppda)[0]), 3),
        "ppda_ratio_medio": round(float(np.mean([a / b for a, b in zip(nuestro_ppda, externo_ppda)])), 2),
        **_resumen_clasico(filas),
    }


def _resumen_clasico(filas: list) -> dict:
    con = [f for f in filas if f.get("ppda_clasico_medio")]
    if len(con) < 3:
        return {}
    partido = [par for f in con for par in f["_ppda_clasico_partido"]]
    return {
        "ppda_clasico_spearman_equipos": round(float(spearmanr(
            [f["ppda_clasico_medio"][0] for f in con], [f["ppda_clasico_medio"][1] for f in con])[0]), 3),
        "ppda_clasico_pearson_partido": round(float(pearsonr(*zip(*partido))[0]), 3),
    }
