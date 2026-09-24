"""Tests de la validación externa (sin red): cruce de partidos y agregados."""

from pitchiq.eval.externa import comparar_equipo, cruzar_partidos, normalizar, resumen


def _nuestro(fecha, local, gf, gc, xg, ppda, clasico):
    return {"fecha": fecha, "local": local, "goles_favor": gf, "goles_contra": gc,
            "xg_favor": xg, "xg_contra": 1.0, "ppda": ppda, "ppda_clasico": clasico}


def _externo(fecha, local, gf, gc, xg, att, dfn):
    return {"fecha": fecha, "local": local, "goles_favor": gf, "goles_contra": gc,
            "xg_favor": xg, "xg_contra": 1.1, "ppda_att": att, "ppda_def": dfn}


def test_normalizar_iguala_nombres_entre_fuentes():
    assert normalizar("Atlético Madrid") == normalizar("Atletico Madrid")
    assert normalizar("Málaga") == "malaga"


def test_cruce_por_fecha_con_margen_de_un_dia_y_campo():
    nuestros = [_nuestro("2020-09-27", True, 4, 0, 2.7, 4.1, 12.0)]
    externos = [_externo("2020-09-26", False, 0, 4, 0.2, 100, 10),
                _externo("2020-09-28", True, 4, 0, 2.5, 90, 9)]
    pares = cruzar_partidos(nuestros, externos)
    assert len(pares) == 1 and pares[0][1]["fecha"] == "2020-09-28"


def test_comparar_y_resumir():
    equipos = []
    for i, escala in enumerate((1.0, 2.0, 3.0)):
        nuestros = [_nuestro(f"2024-01-0{d}", True, 2, 1, 1.0 + d / 10, 2.0 * escala, 10.0 * escala)
                    for d in range(1, 4)]
        externos = [_externo(f"2024-01-0{d}", True, 2, 1, 1.1 + d / 10, int(80 * escala), 10)
                    for d in range(1, 4)]
        equipos.append(comparar_equipo(
            {"nombre": f"E{i}", "competicion": "Liga", "temporada": "2024", "partidos": nuestros}, externos))
    assert equipos[0]["goles_coinciden"] == 3
    assert equipos[0]["ppda_clasico_medio"] == [10.0, 8.0]
    r = resumen(equipos)
    assert r["goles_coinciden"] == r["partidos_cruzados"] == 9
    assert r["ppda_spearman_equipos"] == 1.0
    assert r["ppda_clasico_spearman_equipos"] == 1.0
    assert r["xg_partido_diferencia_media"] == -0.1


def test_equipo_sin_datos_no_mete_nan():
    fila = comparar_equipo({"nombre": "E", "competicion": "L", "temporada": "1", "partidos": []}, [])
    assert fila["xg_favor_por_partido"] == [None, None] and fila["ppda_medio"] == [None, None]
