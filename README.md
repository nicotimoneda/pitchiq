<div align="center">

# ⚽ PitchIQ

**Informes tácticos de equipo donde cada afirmación está anclada a una métrica computada — no inventada por el LLM.**

[![CI](https://github.com/nicotimoneda/pitchiq/actions/workflows/ci.yml/badge.svg)](https://github.com/nicotimoneda/pitchiq/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![StatsBomb](https://img.shields.io/badge/datos-StatsBomb%20Open%20Data-D50032)
![Ruff](https://img.shields.io/badge/lint-ruff-D7FF64?logo=ruff&logoColor=black)
![Estado](https://img.shields.io/badge/estado-M2%20·%20en%20construcción-E8A317)

</div>

---

## Qué es

Los informes tácticos generados con LLMs tienden a afirmar cosas que los datos no sostienen. PitchIQ ataca ese problema desde la base: un pipeline que computa métricas espaciales sobre datos de eventos reales y que, en milestones posteriores, generará informes donde **cada afirmación es trazable a un número computado**. Nada de "presiona alto" sin un PPDA y un mapa de zonas detrás.

## Estado actual: M2

Proyecto en construcción. Lo que hay hoy:

- **Ingesta** de StatsBomb Open Data (partidos, eventos, freeze-frames 360) con cache local en disco.
- **Métricas de eventos (M1)**: zonas de recuperación en rejilla 6×5 + PPDA como escalar de intensidad de presión.
- **Métricas espaciales 360 (M2)**: compacidad del bloque, altura de línea defensiva y soporte de presión.
- **Visualización**: heatmap de zonas, bloque defensivo medio y altura de línea por partido, vía dos CLIs.
- Tests sintéticos en CI (los de red excluidos con el marker `network`) y lint en verde.

### Las tres métricas espaciales (M2)

| Métrica | Qué mide | Sin datos suficientes |
|---|---|---|
| `defensive_compactness` | Dispersión del bloque de compañeros visibles en acciones defensivas: área del convex hull + anchura (rango y) × profundidad (rango x). Menos área = más compacto. | < 3 visibles → NaN (hull indefinido) |
| `defensive_line_height` | Media de x de los 4 compañeros visibles más retrasados (portero excluido) durante acciones defensivas. | < 4 visibles → NaN (no se estima una línea con menos jugadores de los que la definen) |
| `pressing_support` | Compañeros visibles a ≤ radio (default 10) de la posición del evento Pressure (proxy del balón), sin contar al presionador. | Conteo mínimo: solo visibles |

> ⚠️ **Caveat crítico de los datos 360**: los freeze-frames solo capturan a los jugadores dentro del **área visible de la retransmisión**, no siempre los 22. Todas las métricas espaciales se computan sobre los jugadores **visibles** y son una **aproximación**: nunca se asumen 11 por frame, y cuando no hay suficientes visibles para definir una métrica, el valor es NaN — no se inventa. Además, 360 es freeze-frame (foto en el instante de cada evento), no tracking continuo.

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
# → figures/defensive_block_*.png + figures/line_height_by_match_*.png
```

La primera ejecución descarga de StatsBomb; las siguientes leen del cache en `data/cache/`. La temporada completa son ~34 descargas de eventos + 360 la primera vez.

## Stack

Python 3.11 · uv · statsbombpy · pandas / numpy / scipy · mplsoccer · pydantic v2 · pytest · ruff · GitHub Actions

## Roadmap

- [x] **M1** — Ingesta con cache + zonas de recuperación + PPDA + CLI de visualización
- [x] **M2** — Métricas espaciales 360: compacidad, altura de línea, soporte de presión
- [ ] **M3** — Balón parado: métricas de córners y faltas con freeze-frames
- [ ] **M4** — Capa de agentes + RAG: informe táctico con afirmaciones ancladas a métricas
- [ ] **M5** — API FastAPI + Docker + deploy
- [ ] **M6** — Evaluación del sistema + blog post

## Créditos

Datos: [StatsBomb Open Data](https://github.com/statsbomb/open-data), usados bajo sus [términos de uso](https://github.com/statsbomb/open-data/blob/master/LICENSE.pdf). Gracias a StatsBomb por liberar datos de eventos y 360 de calidad profesional.
