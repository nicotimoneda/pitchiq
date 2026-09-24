<div align="center">

# ⚽ PitchIQ

**An AI scouting analyst for 67 football teams. It writes the report a coach reads before a match — and it is built so that it cannot invent a number: the model cites figures, the code supplies them, and a verifier rejects anything else.**

[![CI](https://github.com/nicotimoneda/pitchiq/actions/workflows/ci.yml/badge.svg)](https://github.com/nicotimoneda/pitchiq/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-1C3C3C?logo=langgraph&logoColor=white)
![Claude](https://img.shields.io/badge/Claude-Anthropic-D97757?logo=anthropic&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![Tests](https://img.shields.io/badge/tests-117%20passing-1A7F37?logo=pytest&logoColor=white)
![Playwright](https://img.shields.io/badge/e2e-Playwright-2EAD33?logo=playwright&logoColor=white)
![Ruff](https://img.shields.io/badge/lint-ruff-D7FF64?logo=ruff&logoColor=black)
![License](https://img.shields.io/badge/License-MIT-1A7F37)

**English** · [Español](README.es.md)

</div>

---

<div align="center">
<img src="assets/demo.gif" width="92%" alt="Walkthrough: team overview, the AI report with every figure traced to its source, team search, shot map, player table, a match sheet and the style map"/>
</div>

## What it does

Language models write scouting prose well and statistics badly: they produce numbers that sound right and aren't. PitchIQ is an agent designed around that failure mode.

1. **Dossier.** Deterministic Python turns raw StatsBomb events into ~85 facts per team — record, pressing, defensive shape from 360 freeze-frames, set pieces, attack, key players — and ranks each one as a **percentile** against comparable teams. Every fact has a stable key, e.g. `{metrica.ppda}`.
2. **Writer.** Claude writes the report (verdict, in and out of possession, set pieces, key players, *how to hurt them*) in Spanish and English. It is **not allowed to type a digit**: every figure is a citation to a dossier key, and the code inserts the value.
3. **Verifier.** A LangGraph node checks every citation. A key that doesn't exist, or a number typed by hand — even one that happens to be right — sends the draft back to the writer with the exact list of problems. Whatever survives the retries is shown as unsupported, never as fact.
4. **Context.** A RAG step over a tactical glossary tells the writer what the metrics *mean*. The glossary rejects any entry containing digits, so interpretation can never smuggle in a number.

The result is a report where every figure is a link back to the data: hover it and you see which fact it came from.

## The app

A team page opens with its record, form and four key metrics with their percentile. Bayer Leverkusen 2023/24: 34 matches unbeaten, **2.14 xG per match (98th percentile)**:

![Team overview](assets/app/en_overview.png)

The report comes first. Each highlighted figure is a citation the verifier has checked; hovering it shows the dossier entry it came from. The side panel shows how the report was produced (dossier → glossary → draft → verifier) and links to the raw draft and dossier. Eight showcase teams have an AI report; the rest show a deterministic summary that goes through the same check ([how reports are generated](#generating-the-reports)):

![AI report with verified citations and its trace](assets/app/en_report.png)

Attack: shot map sized by xG with goals on top, and each metric against the league. Barça 2015/16: 604 shots, 109 goals, first in La Liga for xG per match and for territory:

![Attack](assets/app/en_attack.png)

Players: minutes rebuilt from line-ups and substitutions, totals or per 90. Barça 2015/16 comes out as it happened — Suárez 40 league goals, Messi 26, Neymar 24 — straight from the events:

![Players](assets/app/en_players.png)

Every match has its own sheet and link (`#partido-12`) — Real Madrid 0–4 Barcelona, with xG, territory, PPDA, the defensive-action map and the shot map:

![Match sheet](assets/app/en_match.png)

And a style map of all 67 teams (classic PPDA vs. territorial control); click any dot to compare head to head:

![Style map](assets/app/en_compare.png)

Also: splits by venue, half of the season, opponent strength and game state; a match filter; CSV export for matches and players; export to PDF; English and Spanish; light and dark themes; crests in club colours and flags for national teams.

## Results

Everything below is measured without an API key and reproducible from the repo ([full evaluation](EVALUATION.md), in Spanish).

| Check | Result |
|---|---|
| Figures in the reports backed by the data | **977 / 977** in the 8 published reports (ES + EN), re-verified from the saved drafts by `scripts/run_eval.py` |
| Percentiles quoted by the agent vs. the web page | **1,417 / 1,417** identical (Python and JavaScript implementations) |
| Goals vs. [Understat](https://understat.com), match by match | **1,621 / 1,621** identical (43 clubs) |
| xG vs. Understat, match by match | correlation **0.93** (different models, same ranking of matches) |
| Classic PPDA vs. Understat, team ranking | Spearman **0.93** |
| The app's PPDA (counts pressures) vs. Understat | Spearman 0.74 — it measures pressing volume; documented, both are shown |
| Retrieval, English vs. multilingual embeddings | **80 % vs 60 %** top-1 — a "fix" of mine that was a regression, measured and reverted |

## Quick start

Requires [`uv`](https://github.com/astral-sh/uv).

```bash
git clone https://github.com/nicotimoneda/pitchiq.git
cd pitchiq
uv sync
uv run uvicorn app.main:app --port 8000     # → http://localhost:8000
```

The computed data for all 67 teams ships in the repo, so the app runs out of the box — no API key, no downloads.

```bash
uv run pytest                                                  # 102 unit tests (no network, LLM mocked)
uv run playwright install chromium && uv run pytest -m e2e     # 15 browser tests
```

## The teams

67 teams from [StatsBomb Open Data](https://github.com/statsbomb/open-data), listed in [`publicacion.yaml`](scripts/publicacion.yaml):

| Competition | Teams | 360 data |
|---|---|---|
| La Liga 2015/16 · Premier League 2015/16 | all 20 of each league, full season | no |
| Bundesliga 2023/24 · La Liga 2020/21 · Ligue 1 2022/23 | Leverkusen, Barça and PSG (only their matches) | yes |
| World Cup 2022 · Euro 2024 | the four semi-finalists of each | yes |
| Women's Euro 2025 | all 16 national teams | yes |

Why no recent full men's leagues: StatsBomb sells those. Its free release has older full seasons and, from recent ones, only the matches of one showcase team. Percentiles are computed against the league when it has at least 8 published teams, and otherwise against the published teams of the same kind: clubs, men's national teams or women's national teams.

To rebuild the data from scratch, `--demo-data` downloads the public events (no account needed) and recomputes every metric deterministically. Same events, same numbers:

```bash
uv run python scripts/precompute.py --demo-data --jobs 6
```

## Generating the reports

The app never calls a model. Reports are written ahead of time on the author's machine, reviewed, and committed as files, so the public site needs no API key and every report can be audited.

**What happens for each team**, once in Spanish and once in English:

1. `construir_dossier` computes ~85 keyed facts and their percentiles from the team's data.
2. The glossary retriever adds what the relevant metrics mean (optional; no digits allowed).
3. The writer drafts the report, citing `{keys}` instead of typing numbers.
4. The verifier checks every citation. If anything fails, the draft goes back once with the exact list of problems. Whatever still fails is saved and shown as *unsupported*.

**Run it:**

```bash
uv run python scripts/build_index.py                                     # glossary index (once; optional)
uv run python scripts/precompute.py --equipos bayer-leverkusen-2023-24   # one or more teams, comma-separated
uv run python scripts/precompute.py --solo-faltan                        # every team still missing a report
```

Each report is saved as soon as it finishes, so a long run can be stopped and resumed with `--solo-faltan`. The console prints the valid citations, unsupported figures and retries for each language.

**Pick the model** with environment variables. The first one that is set wins:

| Backend | Setup | Cost |
|---|---|---|
| Local model ([Ollama](https://ollama.com), LM Studio…) | `PITCHIQ_LLM_URL=http://localhost:11434/v1 PITCHIQ_MODELO=qwen2.5:14b` | free |
| Any OpenAI-compatible API | `PITCHIQ_LLM_URL=… PITCHIQ_MODELO=… PITCHIQ_LLM_KEY=…` | provider's price |
| Anthropic API | `ANTHROPIC_API_KEY=…` (model: `PITCHIQ_MODELO`, default `claude-opus-5-5`) | API price |
| Claude subscription | nothing: uses the `claude` CLI (`claude` → `/login` once; model: Opus, or `PITCHIQ_MODELO`) | your plan |

If you keep keys in a `.env` file, git ignores it. A key is never sent over plain HTTP to a remote server.

**What gets saved** — `app/static/report/informes/<slug>.json`:

| Field | Content |
|---|---|
| `es`, `en` | the draft exactly as the model wrote it (Markdown with `{keys}`), valid citations, unsupported figures, retries |
| `dossier` | every fact the model was allowed to cite, with its value and description |
| `contexto` | the glossary entries it received |
| `modelo`, `generated_at` | which model wrote it and when |

The app renders the draft, swaps each `{key}` for its value and links every figure to its source. The raw file is public at `/api/equipos/<slug>/informe`. Teams without a report show a deterministic summary built from the same dossier, checked the same way.

**Before committing**, re-verify everything that will be served:

```bash
uv run python scripts/run_eval.py --skip-generalization    # re-runs the verifier on every saved draft
```

What varies between runs, and between models, is the prose. What cannot vary is a figure: a weaker model that ignores the citation rule gets its numbers rejected and shown as unsupported. A 7B local model did exactly that in testing, which is the point of the design. What the verifier cannot catch is a qualitative claim with no number in it; that is why the draft and the dossier are always one click away ([details](EVALUATION.md)).

## How it works

| Stage | Method | Detail |
|---|---|---|
| Data | StatsBomb Open Data | events + 360 freeze-frames, cached locally; teams chosen in [`publicacion.yaml`](scripts/publicacion.yaml) |
| Metrics | deterministic Python, all in metres | PPDA (two definitions), high turnovers, defensive block from 360, corners, shots and xG, territory, progressive actions, players, game state |
| Context | percentiles | against the league when it has ≥ 8 published teams, otherwise against published teams of the same kind (clubs, men's or women's national teams) |
| Report | LangGraph + Claude | dossier → glossary → writer ⇄ verifier; the writer cites keys, never writes figures |
| Interpretation | RAG over a tactical glossary | Qdrant + MiniLM; the glossary **rejects any entry with digits**, so numbers only come from tools |
| Serving | FastAPI, precomputed | no API key and no ML libraries in production (CI checks the image); team data loaded on demand |
| Quality | pytest, Playwright, GitHub Actions | unit + browser tests, Docker build, weekly check for new StatsBomb seasons |

```
team data ──▶ dossier ──▶ glossary (RAG) ──▶ writer (LLM) ──▶ verifier ──▶ report
             ~85 keyed facts   meaning,       cites {keys},       every key exists?
             + percentiles     no digits      no digits           no hand-typed numbers?
                                                  ▲                     │ no
                                                  └──── exact list of problems (retry)
```

## Stack

Python 3.11 · uv · statsbombpy · pandas / numpy / scipy · pydantic v2 · LangGraph · Anthropic (swappable `LLMClient`) · Qdrant · sentence-transformers · RAGAS · FastAPI · Playwright · pytest · ruff · Docker · GitHub Actions

## Project structure

```text
pitchiq/
├── src/pitchiq/
│   ├── data/            # StatsBomb loader with local cache
│   ├── metrics/         # pressing, 360 shape, set pieces, attack, players (pure functions)
│   ├── agent/           # dossier, LangGraph graph, citation verifier, LLM clients (API / CLI)
│   ├── rag/             # tactical glossary (no digits), Qdrant retriever, RAGAS eval
│   └── eval/            # grounding, embeddings, generalisation, Understat comparison
├── app/                 # FastAPI + the web app (one template, no build step)
│   └── static/report/   # precomputed data, AI reports per team, share images
├── scripts/
│   ├── publicacion.yaml       # which teams are published
│   ├── precompute.py          # metrics (no LLM) and AI reports (API key or Claude CLI)
│   └── validacion_externa.py  # comparison against Understat
├── tests/               # unit tests + e2e/ (Playwright)
├── docs/metricas.md     # metric definitions and caveats (Spanish)
├── EVALUATION.md        # what the system claims, what it doesn't, and every limitation
└── .github/workflows/   # CI (tests, e2e, Docker) + weekly catalogue check
```

## Design notes

- **The model cites, the code computes.** Checking numbers after the fact still lets a lucky guess through; asking for citations removes the guess. The same keys drive the hover on every figure in the page.
- **Agent logic in the graph, not in a wrapper.** The retry loop is a conditional edge in LangGraph, so the draft, the verdict and the number of retries are part of the state that gets saved with each report.
- **Everything in metres.** StatsBomb works in yards on a normalised 120 × 80 pitch; values are converted at the source (and thresholds defined in metres), not relabelled.
- **Honest caveats in the product.** 360 freeze-frames only show the players on screen, so spatial metrics are approximations and are left empty rather than estimated when data is missing. xG is StatsBomb's model and is not mixed with other sources.
- **No logos.** Official crests are trademarks: clubs get their initials in club colours, national teams their flag.
- **Generate once, serve static.** The app never calls a model: reports are written ahead of time, saved with their dossier, and served as files.

## Contact

Nicolás Timoneda · [nicotimoneda@gmail.com](mailto:nicotimoneda@gmail.com) · [@nicotimoneda](https://github.com/nicotimoneda)

## License

MIT — see [`LICENSE`](LICENSE). Data: [StatsBomb Open Data](https://github.com/statsbomb/open-data), used under its [terms](https://github.com/statsbomb/open-data/blob/master/LICENSE.pdf).
