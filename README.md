<div align="center">

# ⚽ PitchIQ

**An AI scouting analyst that can't invent a number.**<br>
It writes the report a coach reads before a match. The model cites the data, the code inserts the values, and a verifier rejects anything else.

[![CI](https://github.com/nicotimoneda/pitchiq/actions/workflows/ci.yml/badge.svg)](https://github.com/nicotimoneda/pitchiq/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-1C3C3C?logo=langgraph&logoColor=white)
![Claude](https://img.shields.io/badge/Claude-Anthropic-D97757?logo=anthropic&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![Tests](https://img.shields.io/badge/tests-119%20passing-1A7F37?logo=pytest&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-1A7F37)

**English** · [Español](README.es.md)

<img src="assets/demo.gif" width="92%" alt="Walkthrough: team overview, the AI report with every figure traced to its source, team search, shot map, player table, a match sheet and the style map"/>

</div>

## How it works

Language models write scouting prose well and statistics badly: they produce numbers that sound right and aren't. PitchIQ is built around that failure.

```
StatsBomb events ──▶ dossier ──▶ writer (LLM) ──▶ verifier ──▶ report
                    ~85 keyed facts   cites {keys},     every key exists?
                    + percentiles     never digits      no hand-typed numbers?
                                          ▲                  │ no
                                          └── exact list of problems (retry)
```

1. **Dossier.** Deterministic Python turns raw StatsBomb events into ~85 facts per team (record, pressing, defensive shape from 360 freeze-frames, set pieces, attack, key players), each ranked as a percentile against comparable teams and stored under a key such as `{metrica.ppda}`.
2. **Writer.** The LLM writes the report in Spanish and English (verdict, in and out of possession, set pieces, key players, *how to hurt them*). It cites keys; the code inserts the values.
3. **Verifier.** A LangGraph node checks every citation. An unknown key or a number typed by hand, even a correct one, sends the draft back with the exact list of problems. Anything that survives the retry is shown as unsupported, never as fact.

In the app, every figure in a report links back to the fact it came from.

<p align="center">
<img src="assets/app/en_report.png" width="92%" alt="AI report for Bayer Leverkusen 2023/24 with verified citations and the trace of how it was written"/>
</p>

<details>
<summary><b>More of the app</b>: shot map, players, match sheet, style map</summary>

Barça 2015/16: 604 shots, 109 goals, first in La Liga for xG per match and territory.
![Attack](assets/app/en_attack.png)

Minutes rebuilt from line-ups and substitutions; Suárez 40 league goals, Messi 26, Neymar 24, straight from the events.
![Players](assets/app/en_players.png)

Every match has its own sheet and link: Real Madrid 0–4 Barcelona.
![Match sheet](assets/app/en_match.png)

The style map of all 67 teams (classic PPDA vs. territorial control); click a dot to compare.
![Style map](assets/app/en_compare.png)

Also: splits by venue, half of the season, opponent strength and game state; CSV and PDF export; light and dark themes.
</details>

## Results

All measured without an API key and reproducible from the repo ([full evaluation](EVALUATION.md), in Spanish).

| Check | Result |
|---|---|
| Figures in the published reports backed by the data | **977 / 977** (8 teams, ES + EN), re-verified from the saved drafts |
| Percentiles in the reports vs. the web page | **1,417 / 1,417** identical (Python and JavaScript implementations) |
| Goals vs. [Understat](https://understat.com), match by match | **1,621 / 1,621** identical (43 clubs) |
| xG vs. Understat, match by match | correlation **0.93** |
| Classic PPDA vs. Understat, team ranking | Spearman **0.93** |

## What I learned

- **The verifier checks numbers, not claims.** A 7B local model ignored the citation rule and typed every figure by hand: all 33 were rejected, as designed. The same draft said Leverkusen had been relegated. No check catches that, so the app always shows the draft and the dossier next to the report.
- **Measure before you "fix".** I switched to multilingual embeddings after eyeballing a few queries. Measured on a set, retrieval got worse (80 % → 60 % top-1), so I reverted it.
- **Models translate what they shouldn't.** Writing in English, Opus sometimes cited `{metrica.shots}` instead of `{metrica.tiros}`. The retry now suggests the real key and the prompt says keys are copied verbatim.

## Quick start

```bash
git clone https://github.com/nicotimoneda/pitchiq.git && cd pitchiq
uv sync
uv run uvicorn app.main:app --port 8000     # → http://localhost:8000
```

The data for all 67 teams ships in the repo: the app runs with no API key and no downloads.

```bash
uv run pytest                                                  # 104 unit tests (no network, LLM mocked)
uv run playwright install chromium && uv run pytest -m e2e     # 15 browser tests
uv run python scripts/precompute.py --demo-data --jobs 6       # rebuild every team from StatsBomb
```

**Writing reports.** The app never calls a model: reports are generated ahead of time, reviewed and committed as files. Pick any backend with environment variables (a local model through Ollama, any OpenAI-compatible API, the Anthropic API, or a Claude subscription through the `claude` CLI) and run:

```bash
uv run python scripts/precompute.py --equipos bayer-leverkusen-2023-24
```

Full guide, in Spanish (what gets saved, how to review it): [`docs/informes.md`](docs/informes.md).

## Data

67 teams from [StatsBomb Open Data](https://github.com/statsbomb/open-data), listed in [`publicacion.yaml`](scripts/publicacion.yaml): La Liga and Premier League 2015/16 (all 40 clubs), Leverkusen 2023/24, Barça 2020/21 and PSG 2022/23 with 360 data, the World Cup 2022 and Euro 2024 semi-finalists, and all 16 teams of the Women's Euro 2025. Recent full men's leagues are not in the free release. Metric definitions and caveats (Spanish): [`docs/metricas.md`](docs/metricas.md).

<details>
<summary><b>Stack and project structure</b></summary>

Python 3.11 · uv · statsbombpy · pandas / numpy / scipy · pydantic v2 · LangGraph · Anthropic (swappable `LLMClient`) · Qdrant · sentence-transformers · RAGAS · FastAPI · Playwright · pytest · ruff · Docker · GitHub Actions

```text
pitchiq/
├── src/pitchiq/
│   ├── data/            # StatsBomb loader with local cache
│   ├── metrics/         # pressing, 360 shape, set pieces, attack, players (pure functions, in metres)
│   ├── agent/           # dossier, LangGraph graph, citation verifier, LLM clients
│   ├── rag/             # tactical glossary (rejects digits), Qdrant retriever, RAGAS eval
│   └── eval/            # grounding, embeddings, generalisation, Understat comparison
├── app/                 # FastAPI + the web app (one template, no build step)
├── scripts/             # precompute.py (metrics and reports), publicacion.yaml, Understat check
├── tests/               # unit tests + e2e/ (Playwright)
└── docs/ · EVALUATION.md
```

Design choices: the retry loop is a conditional edge in LangGraph, so draft, verdict and retries are saved with each report; everything is converted to metres at the source; spatial metrics from 360 freeze-frames are left empty rather than estimated when data is missing; production serves static files and CI checks the Docker image carries no ML libraries.
</details>

## Contact

Nicolás Timoneda · [nicotimoneda@gmail.com](mailto:nicotimoneda@gmail.com) · [@nicotimoneda](https://github.com/nicotimoneda)

MIT license. Data: [StatsBomb Open Data](https://github.com/statsbomb/open-data), used under its [terms](https://github.com/statsbomb/open-data/blob/master/LICENSE.pdf).
