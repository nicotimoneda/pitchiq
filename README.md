<div align="center">

# ⚽ PitchIQ

**Informes tácticos de equipo donde cada afirmación está anclada a una métrica computada — no inventada por el LLM.**

[![CI](https://github.com/nicotimoneda/pitchiq/actions/workflows/ci.yml/badge.svg)](https://github.com/nicotimoneda/pitchiq/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![StatsBomb](https://img.shields.io/badge/datos-StatsBomb%20Open%20Data-D50032)
![Ruff](https://img.shields.io/badge/lint-ruff-D7FF64?logo=ruff&logoColor=black)
![Estado](https://img.shields.io/badge/estado-M4%20·%20en%20construcción-E8A317)

</div>

---

## Qué es

Los informes tácticos generados con LLMs tienden a afirmar cosas que los datos no sostienen. PitchIQ ataca ese problema desde la base: un pipeline que computa métricas espaciales sobre datos de eventos reales y que, en milestones posteriores, generará informes donde **cada afirmación es trazable a un número computado**. Nada de "presiona alto" sin un PPDA y un mapa de zonas detrás.

## La feature central: informes 100 % grounded (M4)

El LLM **no calcula ni inventa números**. Su único papel es redactar sobre las salidas de herramientas deterministas (las métricas de M1–M3, envueltas con esquemas pydantic), y un **validador automático post-generación** extrae cada cifra del texto y la coteja contra las salidas reales:

```
equipo ──▶ [nodo de herramientas]──▶ [nodo de redacción (LLM)] ──▶ validador de grounding
              deterministas              solo redacta                cifra a cifra
                                                                        │
                                              ¿cifra sin respaldo? ──▶ 1 reintento con feedback
                                                                        │ si persiste
                                                                   se marca en el informe
```

- El check es **automático y con test**: un informe con una cifra inventada baja el ratio de grounding, dispara una regeneración y, si persiste, la cifra queda marcada como no verificada en el propio informe. Nunca se publica como cierta.
- El proveedor de LLM es **intercambiable**: una interfaz fina `LLMClient` con implementación por defecto para Anthropic (`claude-opus-4-8`). Cambiar de proveedor = implementar un método.
- La evidencia completa (salidas de herramientas + reporte de grounding cifra a cifra) se guarda como `.json` junto al informe `.md`.

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # solo para generar informes; nunca va al código ni al repo
python scripts/generate_report.py --team "Bayer Leverkusen"
# → reports/informe_*.md + reports/informe_*.json + ratio de grounding por consola
```

Los tests mockean el `LLMClient`: ni CI ni la suite tocan la red o el LLM real.

## Estado actual: M4

Proyecto en construcción. Lo que hay hoy:

- **Ingesta** de StatsBomb Open Data (partidos, eventos, freeze-frames 360) con cache local en disco.
- **Métricas de eventos (M1)**: zonas de recuperación en rejilla 6×5 + PPDA como escalar de intensidad de presión.
- **Métricas espaciales 360 (M2)**: compacidad del bloque, altura de línea defensiva y soporte de presión.
- **Balón parado — córners (M3)**: zonas de saque, ocupación del área, primer contacto, xG a favor/en contra e índice de orientación al hombre (proxy).
- **Agentes + informe grounded (M4)**: grafo LangGraph (herramientas → redacción), wrapper de LLM agnóstico y validador de grounding con reintento.
- **Visualización**: heatmaps de zonas y de saques, bloque defensivo, altura de línea, primer contacto — vía tres CLIs.
- Tests sintéticos en CI (los de red excluidos con el marker `network`; el LLM siempre mockeado) y lint en verde.

### Las tres métricas espaciales (M2)

| Métrica | Qué mide | Sin datos suficientes |
|---|---|---|
| `defensive_compactness` | Dispersión del bloque de compañeros visibles en acciones defensivas: área del convex hull + anchura (rango y) × profundidad (rango x). Menos área = más compacto. | < 3 visibles → NaN (hull indefinido) |
| `defensive_line_height` | Media de x de los 4 compañeros visibles más retrasados (portero excluido) durante acciones defensivas. | < 4 visibles → NaN (no se estima una línea con menos jugadores de los que la definen) |
| `pressing_support` | Compañeros visibles a ≤ radio (default 10) de la posición del evento Pressure (proxy del balón), sin contar al presionador. | Conteo mínimo: solo visibles |

> ⚠️ **Caveat crítico de los datos 360**: los freeze-frames solo capturan a los jugadores dentro del **área visible de la retransmisión**, no siempre los 22. Todas las métricas espaciales se computan sobre los jugadores **visibles** y son una **aproximación**: nunca se asumen 11 por frame, y cuando no hay suficientes visibles para definir una métrica, el valor es NaN — no se inventa. Además, 360 es freeze-frame (foto en el instante de cada evento), no tracking continuo.

### Córners (M3)

| Métrica | Qué mide | Lado |
|---|---|---|
| `delivery_zone` | Clasifica el saque por su destino: corto / primer palo / centro / segundo palo, relativo a la portería atacada (derivada del saque, sin orientación fija) | ataque |
| `box_load` | Atacantes y defensores **visibles** dentro del área grande al sacar + diferencial | ataque |
| `first_contact` | Equipo y localización del primer contacto tras el saque (ganado / perdido / concedido) | ambos |
| `corner_xg_for` / `corner_xg_against` | xG a favor / en contra en remates atribuidos a córner | ambos |
| `man_orientation_index` | **Proxy heurístico** de marcaje: distancia media de cada atacante rival visible a su defensor visible más cercano (portero excluido). Menor = más al hombre, mayor = más zonal | defensa |

Temporada 2023/24 del Leverkusen: 236 córners a favor (68 % de primer contacto ganado, 10,8 xG) y 112 en contra (50 % de primer contacto concedido, 5,0 xG en contra).

**Caveats de M3 — léelos antes de citar un número:**

1. **El índice de orientación al hombre es un proxy heurístico continuo**, no un clasificador de sistema de marcaje: mide proximidad media al marcador más cercano sobre jugadores visibles. Sirve para comparar tendencias entre partidos/equipos, no para afirmar "juega al hombre".
2. **Tamaño de muestra**: 236 córners a favor y 112 en contra en la temporada. Suficiente para patrones agregados (zonas de saque, % primer contacto); justa para subdivisiones finas (p. ej. "segundo palo con salida en corto en la segunda parte").
3. **Regla de atribución de xG a córner**: un remate cuenta como "de córner" si su `play_pattern == "From Corner"` (definición de StatsBomb, codificada en `CORNER_PLAY_PATTERN`). Remates en segundas jugadas largas pueden quedar fuera.
4. **Área visible de los 360** (caveat de arriba): `box_load` y el índice de orientación son cotas/aproximaciones sobre visibles; los córners sin freeze-frame quedan fuera de esas métricas (148/236 y 97/112 con 360 en la temporada).

<div align="center">
<img src="assets/corners_delivery_bayer_leverkusen_temporada.png" width="55%" alt="Zonas de saque de córner del Bayer Leverkusen 2023/24"/>
<img src="assets/corners_first_contact_against_bayer_leverkusen_temporada.png" width="42%" alt="Primer contacto en córners en contra"/>
</div>

<div align="center">
<img src="assets/defensive_block_bayer_leverkusen_season.png" width="70%" alt="Bloque defensivo medio del Bayer Leverkusen 2023/24"/>
<img src="assets/line_height_by_match_bayer_leverkusen.png" width="90%" alt="Altura de línea defensiva por partido"/>
</div>

Los huecos en la gráfica son partidos sin datos 360: se muestran como NaN, no se interpolan.

## Dataset

Sujeto de análisis: **Bayer Leverkusen, temporada del título 2023/24** (Bundesliga, `competition_id=9`, `season_id=281`). Dos caveats honestos:

- Son **los 34 partidos del Leverkusen**, no la liga entera: el sujeto es el equipo, y toda métrica se computa sobre esa muestra.
- Los datos 360 son **freeze-frames** del área visible (ver caveat de arriba), no tracking continuo.

## Quick start

Requiere [`uv`](https://github.com/astral-sh/uv).

```bash
uv sync

# M1: mapa de zonas de recuperación + PPDA de un partido
python scripts/build_recovery_map.py --match-id 3895052 --team "Bayer Leverkusen"

# M2: resumen espacial 360 — un partido o la temporada entera
python scripts/build_shape_report.py --match-id 3895052 --team "Bayer Leverkusen"
python scripts/build_shape_report.py --team "Bayer Leverkusen"

# M3: resumen de córners (ataque + defensa)
python scripts/build_setpiece_report.py --team "Bayer Leverkusen"
# → figures/corners_*.png
```

La primera ejecución descarga de StatsBomb; las siguientes leen del cache en `data/cache/`. La temporada completa son ~34 descargas de eventos + 360 la primera vez.

## Stack

Python 3.11 · uv · statsbombpy · pandas / numpy / scipy · mplsoccer · pydantic v2 · LangGraph · anthropic (proveedor intercambiable) · pytest · ruff · GitHub Actions

## Roadmap

- [x] **M1** — Ingesta con cache + zonas de recuperación + PPDA + CLI de visualización
- [x] **M2** — Métricas espaciales 360: compacidad, altura de línea, soporte de presión
- [x] **M3** — Balón parado: córners (zonas de saque, ocupación, primer contacto, xG, índice de orientación al hombre)
- [x] **M4** — Agentes (LangGraph): informe táctico con cada cifra anclada a una herramienta + validador de grounding
- [ ] **M5** — RAG sobre el corpus de métricas + evaluación con RAGAS
- [ ] **M6** — API FastAPI + Docker + deploy
- [ ] **M7** — Evaluación del sistema + blog post

## Créditos

Datos: [StatsBomb Open Data](https://github.com/statsbomb/open-data), usados bajo sus [términos de uso](https://github.com/statsbomb/open-data/blob/master/LICENSE.pdf). Gracias a StatsBomb por liberar datos de eventos y 360 de calidad profesional.
