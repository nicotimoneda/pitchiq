<div align="center">

# ⚽ PitchIQ

**Un analista de scouting con IA que no puede inventar ni una cifra.**<br>
Escribe el informe que lee un entrenador antes de un partido. El modelo cita los datos, el código pone los valores y un verificador rechaza lo demás.

[![CI](https://github.com/nicotimoneda/pitchiq/actions/workflows/ci.yml/badge.svg)](https://github.com/nicotimoneda/pitchiq/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-1C3C3C?logo=langgraph&logoColor=white)
![Claude](https://img.shields.io/badge/Claude-Anthropic-D97757?logo=anthropic&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![Tests](https://img.shields.io/badge/tests-118%20passing-1A7F37?logo=pytest&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-1A7F37)

[English](README.md) · **Español**

<img src="assets/demo.gif" width="92%" alt="Recorrido por la web: portada del equipo, informe del analista IA con cada cifra trazada a su fuente, buscador, mapa de tiros, jugadores, ficha de partido y mapa de estilos"/>

</div>

## Cómo funciona

Los modelos de lenguaje escriben bien un informe de scouting y mal sus estadísticas: sacan números que suenan bien y no lo son. PitchIQ está construido alrededor de ese fallo.

```
eventos StatsBomb ──▶ dossier ──▶ redactor (LLM) ──▶ verificador ──▶ informe
                     ~85 datos con clave   cita {claves},     ¿existe cada clave?
                     + percentiles         nunca dígitos      ¿cifras escritas a mano?
                                               ▲                    │ no
                                               └── lista exacta de fallos (reintento)
```

1. **Dossier.** Python determinista convierte los eventos de StatsBomb en unos 85 datos por equipo (balance, presión, forma defensiva con datos 360, balón parado, ataque, jugadores clave). Cada uno lleva su percentil frente a equipos comparables y una clave fija, por ejemplo `{metrica.ppda}`.
2. **Redactor.** El LLM escribe el informe en español y en inglés (veredicto, con balón, sin balón, balón parado, jugadores clave y *cómo hacerle daño*). Cita claves y el código pone los valores.
3. **Verificador.** Un nodo de LangGraph revisa cada cita. Una clave que no existe o un número escrito a mano, aunque sea correcto, devuelve el borrador con la lista exacta de fallos. Lo que sobreviva al reintento se enseña como sin respaldo, nunca como cierto.

En la web, cada cifra del informe lleva al dato del que sale.

<p align="center">
<img src="assets/app/es_report.png" width="92%" alt="Informe del analista IA del Bayer Leverkusen 2023/24 con citas verificadas y la traza de cómo se escribió"/>
</p>

<details>
<summary><b>Más de la web</b>: mapa de tiros, jugadores, ficha de partido, mapa de estilos</summary>

Barça 2015/16: 604 tiros, 109 goles, primero de La Liga en xG por partido y en dominio territorial.
![Ataque](assets/app/es_attack.png)

Minutos reconstruidos con alineaciones y cambios; Suárez 40 goles de liga, Messi 26 y Neymar 24, directamente de los eventos.
![Jugadores](assets/app/es_players.png)

Cada partido tiene su ficha y su enlace: Real Madrid 0–4 Barcelona.
![Ficha de partido](assets/app/es_match.png)

El mapa de estilos con los 67 equipos (PPDA clásico frente a dominio territorial); al pulsar un punto se compara.
![Mapa de estilos](assets/app/es_compare.png)

También: rendimiento por campo, por mitad de temporada, según el rival y según el marcador; exportar a CSV y PDF; tema claro y oscuro.
</details>

## Resultados

Todo se mide sin API key y se reproduce desde el repositorio ([evaluación completa](EVALUATION.md)).

| Comprobación | Resultado |
|---|---|
| Cifras de los informes publicados respaldadas por los datos | **977 de 977** (8 equipos, ES + EN), re-verificado desde los borradores guardados |
| Percentiles de los informes frente a los de la web | **1417 de 1417** idénticos (implementaciones en Python y JavaScript) |
| Goles frente a [Understat](https://understat.com), partido a partido | **1.621 de 1.621** idénticos (43 clubes) |
| xG frente a Understat, partido a partido | correlación **0,93** |
| PPDA clásico frente a Understat, orden de equipos | Spearman **0,93** |

## Lo que aprendí

- **El verificador comprueba números, no afirmaciones.** Un modelo local de 7B ignoró la regla de citar y escribió todas las cifras a mano: las 33 se rechazaron, como debía. El mismo borrador decía que el Leverkusen había descendido. Eso no lo detecta ningún check, así que la web enseña siempre el borrador y el dossier junto al informe.
- **Medir antes de «arreglar».** Cambié a embeddings multilingües tras probar unas pocas consultas a ojo. Medido sobre un set, la búsqueda empeoró (80 % → 60 % top-1), así que lo revertí.
- **Los modelos traducen lo que no deben.** Escribiendo en inglés, Opus a veces citaba `{metrica.shots}` en vez de `{metrica.tiros}`. Ahora el reintento sugiere la clave real y el prompt pide copiar las claves tal cual.

## Puesta en marcha

```bash
git clone https://github.com/nicotimoneda/pitchiq.git && cd pitchiq
uv sync
uv run uvicorn app.main:app --port 8000     # → http://localhost:8000
```

Los datos de los 67 equipos vienen en el repositorio: la web funciona sin API key ni descargas.

```bash
uv run pytest                                                  # 103 tests (sin red, LLM simulado)
uv run playwright install chromium && uv run pytest -m e2e     # 15 tests en navegador
uv run python scripts/precompute.py --demo-data --jobs 6       # recalcula todos los equipos desde StatsBomb
```

**Escribir informes.** La web nunca llama a un modelo: los informes se generan antes, se revisan y se suben como archivos. El backend se elige con variables de entorno (un modelo local con Ollama, cualquier API compatible con OpenAI, la API de Anthropic o la suscripción de Claude con el CLI `claude`):

```bash
uv run python scripts/precompute.py --equipos bayer-leverkusen-2023-24
```

Guía completa (qué se guarda y cómo se revisa): [`docs/informes.md`](docs/informes.md).

## Datos

67 equipos de [StatsBomb Open Data](https://github.com/statsbomb/open-data), definidos en [`publicacion.yaml`](scripts/publicacion.yaml): La Liga y la Premier League 2015/16 (los 40 clubes), el Leverkusen 2023/24, el Barça 2020/21 y el PSG 2022/23 con datos 360, los semifinalistas del Mundial 2022 y de la Eurocopa 2024, y las 16 selecciones de la Eurocopa femenina 2025. Las ligas masculinas recientes completas no están en la publicación gratuita. Definiciones de las métricas y salvedades: [`docs/metricas.md`](docs/metricas.md).

<details>
<summary><b>Stack y estructura del proyecto</b></summary>

Python 3.11 · uv · statsbombpy · pandas / numpy / scipy · pydantic v2 · LangGraph · Anthropic (`LLMClient` intercambiable) · Qdrant · sentence-transformers · RAGAS · FastAPI · Playwright · pytest · ruff · Docker · GitHub Actions

```text
pitchiq/
├── src/pitchiq/
│   ├── data/            # carga de StatsBomb con caché local
│   ├── metrics/         # presión, forma 360, balón parado, ataque, jugadores (funciones puras, en metros)
│   ├── agent/           # dossier, grafo de LangGraph, verificador de citas, clientes de LLM
│   ├── rag/             # glosario táctico (rechaza dígitos), retriever Qdrant, evaluación RAGAS
│   └── eval/            # grounding, embeddings, generalización, contraste con Understat
├── app/                 # FastAPI + la web (una plantilla, sin build)
├── scripts/             # precompute.py (métricas e informes), publicacion.yaml, contraste con Understat
├── tests/               # tests unitarios + e2e/ (Playwright)
└── docs/ · EVALUATION.md
```

Decisiones de diseño: el reintento es una arista condicional de LangGraph, así que el borrador, el veredicto y los reintentos se guardan con cada informe; todo se convierte a metros en origen; las métricas espaciales de los freeze-frames 360 se dejan vacías en vez de estimarse cuando faltan datos; producción sirve archivos estáticos y la CI comprueba que la imagen Docker no lleva librerías de ML.
</details>

## Contacto

Nicolás Timoneda · [nicotimoneda@gmail.com](mailto:nicotimoneda@gmail.com) · [@nicotimoneda](https://github.com/nicotimoneda)

Licencia MIT. Datos: [StatsBomb Open Data](https://github.com/statsbomb/open-data), usados según sus [condiciones](https://github.com/statsbomb/open-data/blob/master/LICENSE.pdf).
