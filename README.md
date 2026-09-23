<div align="center">

# ⚽ PitchIQ

**Tactical football reports written by an LLM that cannot make up a number, plus an evaluation that doesn't flatter the project either.**

[![CI](https://github.com/nicotimoneda/pitchiq/actions/workflows/ci.yml/badge.svg)](https://github.com/nicotimoneda/pitchiq/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![StatsBomb](https://img.shields.io/badge/data-StatsBomb%20Open%20Data-D50032)

**English** · [Español](README.es.md) · [📊 Honest evaluation (ES)](EVALUATION.md)

</div>

---

<div align="center">
<img src="assets/demo.gif" width="90%" alt="Walkthrough: team search, the verifier flagging an invented figure, a match sheet and the style map"/>
</div>

## What it is

PitchIQ computes deterministic tactical metrics from StatsBomb Open Data for 25 teams: Bayer Leverkusen 23/24, Barça 20/21, PSG 22/23, La Liga 15/16's top 10, and the semi-finalists of Euro 2024, World Cup 2022 and Women's Euro 2025. It then writes a report with an LLM that **is not allowed to compute or invent numbers**. The model only writes prose around the outputs of deterministic tools, and a validator then checks every figure in the text against that evidence.

The [evaluation](EVALUATION.md) measures everything that can be measured without an API key. That includes an uncomfortable finding: an embeddings "fix" I made turned out to be a **−20 point regression in top-1 retrieval** once measured, so it was reverted. That is the standard of the repo: numbers over impressions, including against myself.

## The web app

The app is available in English and Spanish. It picks the browser's language, and a button switches between them. The data covers clubs, men's national teams and women's national teams.

- **Search** any published team (press `/`). The header shows crest, record, league position, form and key metrics, each with a per-match sparkline.
- **Report**: a summary where every number is highlighted and verified against the computed metrics. Hover a number to see which metric backs it.
- **Try to fool the verifier**: type a sentence with real or invented figures, and the same rule that validates the LLM reports marks each number live.
- **Pressing, Defence, Set pieces**: pitch maps (defensive actions by zone, block density from 360 freeze-frames, corner deliveries) and per-match charts.
- **Matches**: home/away and first/second-half splits, a sortable table, and a **sheet for every match** (xG, PPDA, defensive-action map, corners).
- **Compare**: a style map of all teams (pressing intensity vs. share of actions in the opponent's half) and head-to-head bars.
- **Also**:
  - light and dark themes;
  - **export to PDF**;
  - link previews (Open Graph image per team);
  - per-team data loaded on demand.

## The core feature: 100% grounded reports

```
team ──▶ [deterministic tools] ──▶ [writer node (LLM)] ──▶ grounding validator
            metrics M1–M3              prose only              figure by figure
                                                                    │
                                          unsupported figure? ──▶ 1 retry with feedback
                                                                    │ still there
                                                               flagged in the report
```

- **Automatic and tested.** A report with an invented figure lowers its grounding ratio and triggers a regeneration. If the figure survives, it is flagged as unverified inside the report itself and never published as fact.
- **Swappable provider.** The LLM sits behind a thin `LLMClient` protocol, with a default implementation for Anthropic. Switching provider means implementing one method.
- **Full evidence.** Tool outputs and the figure-by-figure grounding report are stored as JSON next to every report and served at `/api/evidence`.
- **No real LLM in tests or CI.** The suite mocks `LLMClient`.

**Interpretive RAG.** A local Qdrant index over a tactical glossary gives the writer context, such as what a low PPDA means. The glossary validator **rejects any entry containing digits**, so figures can only come from the tools. The glossary is an AI draft marked `revisado: false`, and the report says so until a human reviews it. Retrieval is evaluated with RAGAS and top-k accuracy, which is where the −20 point regression was caught.

## Architecture: generate once, serve static

```
LOCAL (human)                                 PRODUCTION (Render, no API key)
──────────────────────────────                ─────────────────────────────────
scripts/precompute.py                         minimal FastAPI app (gzip)
  ├─ --demo-data: metrics (no key)              ├─ GET /                   analysis web app
  │    → teams/<slug>.json + og/<slug>.png      ├─ GET /api/equipos        published teams
  ├─ LLM report (key, 1 call)                   ├─ GET /api/equipos/{slug} one team's data
  │    → report.md + evidence.json              ├─ GET /api/report         LLM report
  └─ artefacts → app/static/report/             ├─ GET /api/evidence       grounding evidence
        │                                       ├─ GET /og/{slug}.png      share preview
        └── git commit ───────────────────▶     └─ GET /health
```

**Why this design:**
- The production app has no `ANTHROPIC_API_KEY`, so there is nothing to leak.
- It ships without torch, langgraph or anthropic, and CI checks the image for them.
- Every visit costs zero LLM calls.

Which teams are published is decided in [`scripts/publicacion.yaml`](scripts/publicacion.yaml): per StatsBomb competition, either a list of teams or the top N of the computed standings, with Spanish display names. A weekly GitHub Action diffs the StatsBomb catalogue and opens an issue when new seasons or new 360 data appear.

## Quick start

Requires [`uv`](https://github.com/astral-sh/uv).

```bash
uv sync
uv run uvicorn app.main:app --port 8000        # web app on http://localhost:8000

uv run pytest                                  # unit tests (no network, LLM mocked)
uv run playwright install chromium && uv run pytest -m e2e   # browser tests

uv run python scripts/precompute.py --demo-data                    # re-export metrics, no key
ANTHROPIC_API_KEY=sk-ant-... uv run python scripts/precompute.py   # + LLM report
```

The first run downloads from StatsBomb; later runs read from `data/cache/`.

## Metrics

| Area | Metrics |
|---|---|
| Pressing | defensive actions by zone, PPDA, share in the opponent's half, high turnovers (open-play regains within 40 yards of goal) and how many end in a shot |
| Defensive shape (360) | line height, block width/depth, convex-hull area, pressing support |
| Corners | delivery zone, box load, first contact, xG for/against, man-orientation index (a heuristic proxy) |
| Matches | result, xG, PPDA, defensive actions and line height per match |

The caveats are part of the product:
- **360 freeze-frames only include players visible in the broadcast.** Spatial metrics are approximations over visible players, never assume 11, and are left empty rather than estimated when too few players are visible.
- **The PPDA here counts pressures as defensive actions,** so it is lower than Opta-style PPDA. It is consistent across teams, but not comparable with other sources.
- **Distances are in yards.** StatsBomb's pitch is 120 × 80 yards.

## Stack

Python 3.11 · uv · statsbombpy · pandas / numpy / scipy · mplsoccer · pydantic v2 · LangGraph · Anthropic (swappable) · Qdrant · sentence-transformers · RAGAS (outside CI) · FastAPI · Playwright · pytest · ruff · Docker · GitHub Actions

## Credits

Data: [StatsBomb Open Data](https://github.com/statsbomb/open-data), used under its [terms](https://github.com/statsbomb/open-data/blob/master/LICENSE.pdf). Thanks to StatsBomb for releasing professional-grade event and 360 data.
