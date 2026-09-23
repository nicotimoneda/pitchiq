<div align="center">

# ⚽ PitchIQ

**Informes tácticos con LLM donde inventarse una cifra es imposible por construcción — y una evaluación que no se maquilla ni a sí misma.**

[![CI](https://github.com/nicotimoneda/pitchiq/actions/workflows/ci.yml/badge.svg)](https://github.com/nicotimoneda/pitchiq/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![StatsBomb](https://img.shields.io/badge/datos-StatsBomb%20Open%20Data-D50032)

[English](README.md) · **Español** · [📊 Evaluación honesta](EVALUATION.md)

</div>

---

<div align="center">
<img src="assets/demo.gif" width="90%" alt="Recorrido por la web: buscador de equipos, informe con cifras verificadas, defensa, ficha de partido y mapa de estilos"/>
</div>

## Qué es

Un pipeline que computa métricas tácticas deterministas sobre StatsBomb Open Data (115 equipos, desde temporadas completas de club hasta todas las selecciones de tres torneos internacionales, masculinos y femenino) y genera un informe con LLM donde **el modelo no puede calcular ni inventar números**: solo redacta sobre las salidas de las herramientas, y un validador coteja después cada cifra del texto contra la evidencia. La [evaluación](EVALUATION.md) mide todo lo medible sin key — incluido el hallazgo incómodo de que un "fix" de embeddings del propio proyecto resultó ser una regresión de −20 puntos al medirlo. Ese es el estándar del repo: números antes que sensaciones, también contra uno mismo.

## Cómo se comprueba

Cada cifra pasa tres controles independientes antes de que alguien la lea:

- **Contra la evidencia.** Cada número de un informe se empareja con la métrica que lo produjo, y un validador automático marca cualquiera sin respaldo.
- **Contra una fuente pública.** En los 13 equipos de club, los datos publicados se contrastan partido a partido con [Understat](https://understat.com). Los goles coinciden en 481 de 481 partidos, el xG correlaciona 0,94 y el PPDA clásico ordena a los equipos igual (Spearman 0,97). El mismo ejercicio mostró que el PPDA de la web, que cuenta las presiones, mide otra cosa; ahora está documentado en vez de oculto. [Detalle](EVALUATION.md#validación-externa-understat-481-partidos-sin-key)
- **Contra sí mismo.** Los cambios se miden antes de quedarse. Uno que parecía una mejora costaba 20 puntos de precisión en la búsqueda y se revirtió.

## El recorrido (M1–M7)

| Milestone | Qué añadió | Estado |
|---|---|---|
| **M1** | Ingesta con cache + zonas de recuperación + PPDA + CLI de heatmap | ✅ |
| **M2** | Métricas 360: compacidad (convex hull), altura de línea, soporte de presión | ✅ |
| **M3** | Córners: zonas de saque, box load, primer contacto, xG, MOI (proxy) | ✅ |
| **M4** | LangGraph + validador de grounding: cifras del LLM verificadas una a una | ✅ |
| **M5** | RAG interpretativo (glosario sin números, en revisión) + eval RAGAS | ✅ |
| **M6** | Arquitectura precomputada: FastAPI mínima + Docker sin ML + Render | ✅ |
| **M7** | [Evaluación honesta consolidada](EVALUATION.md) + kit factual del blog | ✅ |

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
uv run python scripts/generate_report.py --team "Bayer Leverkusen"
# → reports/informe_*.md + reports/informe_*.json + ratio de grounding por consola
```

Los tests mockean el `LLMClient`: ni CI ni la suite tocan la red o el LLM real.

### RAG interpretativo (M5): contexto, nunca cifras

Sobre el pipeline anterior, una capa RAG (Qdrant local + embeddings `sentence-transformers`, todo sin API key) recupera conceptos de un **glosario táctico** y se los pasa al redactor como contexto interpretativo: qué significa en fútbol un PPDA bajo, un bloque compacto o un MOI corto. Tres garantías:

1. **El RAG no aporta números.** El glosario tiene un validador que **rechaza cualquier entrada con dígitos**; las cifras siguen saliendo solo de las herramientas y el validador de grounding de M4 se aplica sin cambios sobre el informe final. Hay un test explícito de que el contexto RAG no rompe el grounding.
2. **⚠️ El glosario está EN REVISIÓN.** Lo redactó una IA como borrador: todas las entradas llevan `revisado: false` y sus interpretaciones **no son autoritativas hasta revisión humana**. Ninguna entrada cita fuentes que no se puedan garantizar (campo `fuente: pendiente de revisión humana`). El propio informe arrastra esta advertencia.
3. **Evaluación medible.** `scripts/eval_rag.py` evalúa fidelidad y relevancia de contexto con RAGAS sobre un set de preguntas de interpretación. Usa un LLM juez de Anthropic → **cuesta llamadas de API y queda fuera de CI**. Corre en un entorno aislado (ragas es incompatible con langchain 1.x):

```bash
uv run python scripts/build_index.py                            # índice vectorial local
ANTHROPIC_API_KEY=sk-ant-... uv run --script scripts/eval_rag.py  # evaluación RAGAS
```

### Arquitectura precomputada (M6): generar una vez, servir estático

La web pública **no genera nada**: separa la GENERACIÓN (cara, con LLM, en local) del SERVIDO (barato, estático, en producción).

```
LOCAL (humano)                                PRODUCCIÓN (Render, sin key)
──────────────────────────────                ─────────────────────────────────
scripts/precompute.py                         app FastAPI mínima (gzip)
  ├─ --demo-data: métricas (SIN key)            ├─ GET /                   web de análisis
  │    → teams/<slug>.json + og/<slug>.png      ├─ GET /api/equipos        equipos publicados
  ├─ informe M4+M5 (CON key, 1 llamada)         ├─ GET /api/equipos/{slug} datos de un equipo
  │    → report.md + evidence.json              ├─ GET /api/report         informe del LLM
  └─ artefactos → app/static/report/            ├─ GET /api/evidence       grounding cifra a cifra
        │                                       ├─ GET /og/{slug}.png      vista previa al compartir
        └── git commit ───────────────────▶     └─ GET /health
```

La web es una herramienta de análisis por equipo con **115 equipos**: La Liga y Premier League 2015/16 completas, todas las selecciones de la Euro 2024, el Mundial 2022 y la Eurocopa femenina 2025, y el Leverkusen 23/24, el Barça 20/21 y el PSG 22/23.

- **Contexto en cada cifra.** Cada métrica se muestra como percentil frente a su liga o torneo, y el informe enumera solo los **puntos fuertes y débiles** del equipo: se lee como un informe del próximo rival.
- **Informe**: resumen con cada cifra verificada contra las métricas (pasa el cursor para ver de dónde sale).
- **Ataque**: mapa de tiros por xG, dominio territorial, pases y conducciones progresivos y entradas al último tercio por carril.
- **Presión, Defensa y Balón parado**: mapas de campo y medias móviles de 5 partidos, con el PPDA en sus dos definiciones (con presiones y la clásica de las fuentes públicas).
- **Jugadores**: tabla ordenable de toda la plantilla (totales o por 90 minutos): goles, xG, pases clave, acciones progresivas, presiones y acciones defensivas.
- **Partidos**: rendimiento por campo, por mitad de temporada, según la fuerza del rival y según el marcador (ganando, empatando, perdiendo), tabla filtrable y ficha de cada partido con su propio enlace.
- **Comparar**: mapa de estilos de los 115 equipos (PPDA clásico frente a dominio territorial) y comparación uno a uno.
- **Además**: escudos con los colores de cada club y banderas de las selecciones, exportar partidos y jugadores a CSV, exportar a PDF, tema claro/oscuro, en **español e inglés**, vista previa al compartir y carga bajo demanda de cada equipo.

Qué equipos se publican lo decide [`scripts/publicacion.yaml`](scripts/publicacion.yaml): por competición de StatsBomb Open Data, una lista de equipos o los N primeros de la clasificación, con nombres en español. Donde no hay datos de posiciones (La Liga 2015/16), la sección de Defensa lo indica y esas métricas no se estiman. Una tarea semanal de GitHub Actions compara el catálogo de StatsBomb y abre una issue si publica temporadas nuevas.

**Por qué así:** la app de producción no lleva `ANTHROPIC_API_KEY` (imposible filtrarla: no existe allí), no importa torch/langgraph/anthropic (imagen mínima, el CI lo verifica), y cada visita cuesta cero llamadas de LLM. Las gráficas y el informe son artefactos independientes: la web enseña datos reales aunque el informe todavía no exista. El pipeline de generación completo sigue en el repo para quien clone y ponga su key.

```bash
# paso humano, en local:
uv run python scripts/precompute.py --demo-data                    # gráficas reales, sin key
ANTHROPIC_API_KEY=sk-ant-... uv run python scripts/precompute.py   # + informe del LLM
git add app/static/report && git commit    # los artefactos se versionan

# tests de la web en un navegador real (también en CI):
uv run playwright install chromium && uv run pytest -m e2e

# servir en local con Docker:
docker build -t pitchiq-app . && docker run --rm -p 8000:8000 pitchiq-app
# → http://localhost:8000  (sin artefactos reales sirve fixtures de muestra, con aviso)
```

El deploy en Render usa `render.yaml` (web service Docker, health check en `/health`, **sin variables secretas**).

## Detalle de las métricas

### Las tres métricas espaciales (M2)

| Métrica | Qué mide | Sin datos suficientes |
|---|---|---|
| `defensive_compactness` | Dispersión del bloque de compañeros visibles en acciones defensivas: área del convex hull + anchura (rango y) × profundidad (rango x). Menos área = más compacto. | < 3 visibles → NaN (hull indefinido) |
| `defensive_line_height` | Media de x de los 4 compañeros visibles más retrasados (portero excluido) durante acciones defensivas. | < 4 visibles → NaN (no se estima una línea con menos jugadores de los que la definen) |
| `pressing_support` | Compañeros visibles a ≤ radio (por defecto 10 m) de la posición del evento Pressure (proxy del balón), sin contar al presionador. | Conteo mínimo: solo visibles |

> ⚠️ **Caveat crítico de los datos 360**: los freeze-frames solo capturan a los jugadores dentro del **área visible de la retransmisión**, no siempre los 22. Todas las métricas espaciales se computan sobre los jugadores **visibles** y son una **aproximación**: nunca se asumen 11 por frame, y cuando no hay suficientes visibles para definir una métrica, el valor es NaN — no se inventa. Además, 360 es freeze-frame (foto en el instante de cada evento), no tracking continuo.

> 📏 **Unidades: todo en metros.** StatsBomb da las coordenadas en yardas sobre un campo normalizado de 120 × 80. Todo lo publicado (salidas de herramientas que lee el LLM, web y verificador) se convierte a metros (109,7 × 73,2 m) y las áreas a m²; los umbrales se definen en metros (apoyo en la presión a 10 m, robo alto a 40 m).

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
uv run python scripts/build_recovery_map.py --match-id 3895052 --team "Bayer Leverkusen"

# M2: resumen espacial 360 — un partido o la temporada entera
uv run python scripts/build_shape_report.py --match-id 3895052 --team "Bayer Leverkusen"
uv run python scripts/build_shape_report.py --team "Bayer Leverkusen"

# M3: resumen de córners (ataque + defensa)
uv run python scripts/build_setpiece_report.py --team "Bayer Leverkusen"
# → figures/corners_*.png
```

La primera ejecución descarga de StatsBomb; las siguientes leen del cache en `data/cache/`. La temporada completa son ~34 descargas de eventos + 360 la primera vez.

## Stack

Python 3.11 · uv · statsbombpy · pandas / numpy / scipy · mplsoccer · pydantic v2 · LangGraph · anthropic (proveedor intercambiable) · Qdrant local · sentence-transformers · RAGAS (eval, fuera de CI) · pytest · ruff · GitHub Actions

## Evaluación y material del proyecto

- [**EVALUATION.md**](EVALUATION.md) — qué afirma el sistema (y qué no), todas las limitaciones sin maquillar y los números: grounding 1.0, comparación de embeddings antes/después, generalización a la Euro 2024.
- [`docs/blog_kit.md`](docs/blog_kit.md) — material factual en crudo para el post (los hallazgos con números y un esquema); la prosa final la escribe el autor.
- `uv run python scripts/run_eval.py` regenera la evaluación sin key, y `uv run python scripts/validacion_externa.py` el contraste con Understat.

## Créditos

Datos: [StatsBomb Open Data](https://github.com/statsbomb/open-data), usados bajo sus [términos de uso](https://github.com/statsbomb/open-data/blob/master/LICENSE.pdf). Gracias a StatsBomb por liberar datos de eventos y 360 de calidad profesional.
