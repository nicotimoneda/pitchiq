"""Dossier del equipo: la única fuente de cifras que puede citar el redactor.

Se construye de forma determinista a partir de los datos precomputados del
equipo (teams/<slug>.json) y del resto de equipos publicados (para los
percentiles). Cada entrada lleva una clave estable, su valor ya redondeado y
una etiqueta en español y en inglés; el LLM cita claves, nunca escribe cifras.

Los percentiles replican la regla de la web (grupoDe/percentil en index.html)
para que el informe y las barras de la página digan lo mismo.
"""

import math

# id, etiqueta ES, etiqueta EN, valor, decimales, unidad, sentido (1 más es mejor,
# -1 menos es mejor, 0 rasgo de estilo). Misma lista y orden que METRICAS en la web.
_AG = lambda t: t.get("agregados") or {}  # noqa: E731
_H = lambda t, h, c: (t.get("herramientas") or {}).get(h, {}).get(c)  # noqa: E731


def _pp(t, v):
    n = _AG(t).get("partidos")
    return v / n if v is not None and n else None


METRICAS = [
    ("xg", "xG por partido", "xG per match", lambda t: _AG(t).get("xg_favor"), 2, "", 1),
    ("goles", "goles por partido", "goals per match", lambda t: _AG(t).get("goles_favor"), 2, "", 1),
    ("tiros", "tiros por partido", "shots per match", lambda t: _AG(t).get("tiros"), 1, "", 1),
    ("xg_tiro", "xG por tiro (sin penaltis)", "xG per shot (non-penalty)", lambda t: _AG(t).get("xg_por_tiro"), 2, "", 1),
    ("tilt", "dominio territorial (% de los pases en el último tercio)", "field tilt (% of final-third passes)", lambda t: _AG(t).get("field_tilt"), 1, "%", 1),
    ("prog", "acciones progresivas por partido", "progressive actions per match", lambda t: _AG(t).get("progresivos"), 1, "", 1),
    ("centros", "centros por partido", "crosses per match", lambda t: _AG(t).get("centros"), 1, "", 0),
    ("ppda", "PPDA con presiones (menos = presión más intensa)", "PPDA incl. pressures (lower = more intense)", lambda t: _H(t, "presion", "ppda_medio"), 2, "", -1),
    ("ppda_c", "PPDA clásico", "classic PPDA", lambda t: _AG(t).get("ppda_clasico"), 2, "", -1),
    ("campo_rival", "% de acciones defensivas en campo rival", "% of defensive actions in the opponent's half", lambda t: _H(t, "presion", "pct_acciones_campo_rival"), 1, "%", 1),
    ("robos", "robos altos por partido (a 40 m o menos de la portería rival)", "high turnovers per match (within 40 m of goal)", lambda t: _AG(t).get("robos_altos"), 2, "", 1),
    ("robos_tiro", "% de robos altos que acaban en tiro", "% of high turnovers ending in a shot", lambda t: _AG(t).get("robos_altos_tiro_pct"), 1, "%", 1),
    ("apoyo", "compañeros a menos de 10 m en cada presión", "teammates within 10 m of each pressure", lambda t: _H(t, "forma_defensiva", "soporte_presion_medio"), 2, "", 1),
    ("goles_c", "goles encajados por partido", "goals conceded per match", lambda t: _AG(t).get("goles_contra"), 2, "", -1),
    ("xg_c", "xG concedido por partido", "xG conceded per match", lambda t: _AG(t).get("xg_contra"), 2, "", -1),
    ("altura", "altura media de la línea defensiva (m desde su portería)", "average defensive line height (m from own goal)", lambda t: _H(t, "forma_defensiva", "altura_linea_media"), 1, "m", 0),
    ("anchura", "anchura media del bloque (m)", "average block width (m)", lambda t: _H(t, "forma_defensiva", "anchura_media"), 1, "m", 0),
    ("prof", "profundidad media del bloque (m)", "average block depth (m)", lambda t: _H(t, "forma_defensiva", "profundidad_media"), 1, "m", 0),
    ("area", "área media del bloque (m²; menos = más compacto)", "average block area (m²; lower = more compact)", lambda t: _H(t, "forma_defensiva", "hull_area_media_m2"), 0, "m²", 0),
    ("corners", "córners a favor por partido", "corners won per match", lambda t: _pp(t, _H(t, "corners_ataque", "n_corners")), 1, "", 1),
    ("xg_corner", "xG en córners por partido", "corner xG per match", lambda t: _pp(t, _H(t, "corners_ataque", "xg_a_favor")), 2, "", 1),
    ("contacto", "% de primer contacto ganado en sus córners", "% first contact won on own corners", lambda t: _H(t, "corners_ataque", "pct_primer_contacto_ganado"), 1, "%", 1),
    ("xg_corner_c", "xG concedido en córners por partido", "corner xG conceded per match", lambda t: _pp(t, _H(t, "corners_defensa", "xg_en_contra")), 2, "", -1),
    ("contacto_c", "% de primer contacto del rival en córners en contra", "% first contact conceded on corners against", lambda t: _H(t, "corners_defensa", "pct_primer_contacto_concedido"), 1, "%", -1),
    ("marcaje", "distancia media al marcador en córners en contra (m, aproximada)", "average distance to marker on corners against (m, approximate)", lambda t: _H(t, "corners_defensa", "indice_orientacion_hombre"), 2, "m", 0),
]

# jugadores: (campo, decimales, etiqueta ES, etiqueta EN) del mejor del equipo en cada cosa
_JUGADORES = [
    ("goles", 0, "goles", "goals"),
    ("asistencias", 0, "asistencias", "assists"),
    ("xg", 2, "xG", "xG"),
    ("pases_clave", 0, "pases clave", "key passes"),
    ("progresivos", 0, "acciones progresivas", "progressive actions"),
    ("presiones", 0, "presiones", "pressures"),
    ("recuperaciones", 0, "recuperaciones", "ball recoveries"),
]


_BALANCE = {
    "partidos": ("partidos jugados", "matches played"),
    "victorias": ("victorias", "wins"),
    "empates": ("empates", "draws"),
    "derrotas": ("derrotas", "losses"),
    "goles_favor": ("goles a favor", "goals scored"),
    "goles_contra": ("goles en contra", "goals conceded"),
}


def _es_seleccion(t: dict) -> bool:
    return bool((t.get("identidad") or {}).get("bandera"))


def _es_femenino(t: dict) -> bool:
    return str(t.get("equipo") or "").endswith(" Women's")


def grupo(team: dict, todos: "list[dict]") -> "tuple[str, str, list[dict]]":
    """Con quién se compara: su competición si tiene 8+ equipos; si no, los de su tipo.

    El tipo separa clubes de selecciones y fútbol masculino de femenino: no se
    compara un semifinalista del Mundial con una selección de la Eurocopa femenina.
    """
    misma = [t for t in todos if t["competicion"] == team["competicion"] and t["temporada"] == team["temporada"]]
    if len(misma) >= 8:
        nombre = f"{team['competicion']} {team['temporada']}"
        return nombre, nombre, misma
    sel, fem = _es_seleccion(team), _es_femenino(team)
    tipo = [t for t in todos if _es_seleccion(t) == sel and _es_femenino(t) == fem]
    if sel and fem:
        return "selecciones femeninas publicadas", "published women's national teams", tipo
    if sel:
        return "selecciones masculinas publicadas", "published men's national teams", tipo
    return "equipos de club publicados", "published club teams", tipo


def percentil(team: dict, get, sentido: int, equipos: "list[dict]") -> "int | None":
    """Percentil del equipo en el grupo (misma fórmula y redondeo que la web)."""
    v = get(team)
    if v is None:
        return None
    vals = [x for x in (get(t) for t in equipos) if x is not None]
    if len(vals) < 5:
        return None
    menos = sum(x < v for x in vals)
    iguales = sum(x == v for x in vals)
    pct = math.floor(100 * (menos + (iguales - 1) / 2) / (len(vals) - 1) + 0.5)  # Math.round
    return 100 - pct if sentido == -1 else pct


def resultados(partidos: "list[dict]") -> dict:
    """Balance de una lista de partidos (como ``resultados`` en la web)."""
    return {
        "partidos": len(partidos),
        "victorias": sum(p["goles_favor"] > p["goles_contra"] for p in partidos),
        "empates": sum(p["goles_favor"] == p["goles_contra"] for p in partidos),
        "derrotas": sum(p["goles_favor"] < p["goles_contra"] for p in partidos),
        "goles_favor": sum(p["goles_favor"] for p in partidos),
        "goles_contra": sum(p["goles_contra"] for p in partidos),
    }


def formatear(entrada: dict, idioma: str = "es") -> str:
    """Valor de una entrada tal y como se escribe en el informe (coma decimal en español)."""
    texto = f"{entrada['valor']:.{entrada['decimales']}f}"
    return texto.replace(".", ",") if idioma == "es" else texto


def construir_dossier(team: dict, todos: "list[dict]") -> "dict[str, dict]":
    """Clave -> {valor, decimales, es, en}: todo lo que el informe puede afirmar con cifras."""
    d: dict[str, dict] = {}

    def add(clave: str, valor, decimales: int, es: str, en: str) -> None:
        if valor is None or (isinstance(valor, float) and math.isnan(valor)):
            return
        d[clave] = {"valor": round(float(valor), decimales), "decimales": decimales, "es": es, "en": en}

    partidos = team.get("partidos", [])
    for k, v in resultados(partidos).items():
        add(f"resultados.{k}", v, 0, *_BALANCE[k])
    if team.get("posicion") is not None:
        add("clasificacion.posicion", team["posicion"], 0, "puesto final en la clasificación", "final league position")
        add("clasificacion.equipos", team["n_equipos"], 0, "equipos en la competición", "teams in the competition")
    for sede, es, en in (("local", "como local", "at home"), ("visitante", "como visitante", "away")):
        r = resultados([p for p in partidos if p["local"] == (sede == "local")])
        for k, (k_es, k_en) in _BALANCE.items():
            add(f"{sede}.{k}", r[k], 0, f"{k_es} {es}", f"{k_en} {en}")

    g_es, g_en, equipos = grupo(team, todos)
    add("grupo.equipos", len(equipos), 0, f"equipos en el grupo de comparación ({g_es})",
        f"teams in the comparison group ({g_en})")
    for mid, es, en, get, dec, unidad, sentido in METRICAS:
        add(f"metrica.{mid}", get(team), dec, es, en)
        pct = percentil(team, get, sentido, equipos)
        matiz_es = " (rasgo de estilo, ni mejor ni peor)" if sentido == 0 else " (100 = el mejor)"
        matiz_en = " (style trait, neither better nor worse)" if sentido == 0 else " (100 = best)"
        add(f"percentil.{mid}", pct, 0, f"percentil de {es} frente a {g_es}{matiz_es}",
            f"percentile for {en} vs {g_en}{matiz_en}")

    ca = (team.get("herramientas") or {}).get("corners_ataque") or {}
    add("corners.a_favor", ca.get("n_corners"), 0, "córners a favor en la temporada", "corners won in the season")
    add("corners.xg_a_favor", ca.get("xg_a_favor"), 2, "xG total generado en córners", "total corner xG")
    cd = (team.get("herramientas") or {}).get("corners_defensa") or {}
    add("corners.en_contra", cd.get("n_corners"), 0, "córners en contra en la temporada", "corners conceded in the season")
    add("corners.xg_en_contra", cd.get("xg_en_contra"), 2, "xG total concedido en córners", "total corner xG conceded")
    carriles = _AG(team).get("carriles_pct") or {}
    for lado, en in (("izquierda", "left"), ("centro", "centre"), ("derecha", "right")):
        add(f"carriles.{lado}", carriles.get(lado), 1, f"% de las llegadas al último tercio por la {lado}"
            if lado != "centro" else "% de las llegadas al último tercio por el centro",
            f"% of final-third entries through the {en}")

    jugadores = team.get("jugadores") or []
    for campo, dec, es, en in _JUGADORES:
        mejor = max(jugadores, key=lambda j: j.get(campo) or 0, default=None)
        if mejor and (mejor.get(campo) or 0) > 0:
            nombre = mejor["nombre"]
            add(f"jugador.{campo}", mejor[campo], dec, f"{es} de {nombre}, el máximo del equipo",
                f"{en} by {nombre}, the team's best")
            add(f"jugador.{campo}.minutos", mejor.get("minutos"), 0, f"minutos jugados por {nombre}",
                f"minutes played by {nombre}")
    return d
