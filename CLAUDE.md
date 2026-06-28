# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

VoxPop is an offline batch processing tool that reads social-media comments (Weibo/Bilibili/Xiaohongshu/Zhihu) from a PostgreSQL database (populated by the separate [MindSpider](https://github.com/qql2/MindSpider) project), runs LLM-based sentiment and attitude labeling, and generates profession sentiment ranking reports (JSON + Markdown).

## Commands

```bash
# Install dependencies
pip install asyncpg openai httpx pydantic-settings

# Initialize DB tables only (idempotent — CREATE IF NOT EXISTS)
python run.py --sql-only

# Label yesterday's comments and generate rankings
python run.py

# Label a specific date
python run.py --date 2026-06-23

# Test run — label only N comments
python run.py --limit 200

# Run Xiaohongshu labeling separately (serial, with its own batch loop)
python run_xhs.py
```

## Architecture

### Data Flow

```
MindSpider (separate repo)  →  PostgreSQL                           →  VoxPop (this repo)
  weibo_note_comment               ├─ attitude_labels (output)          run.py (orchestrator)
  bilibili_video_comment           ├─ attitude_rankings (output)        labeler.py / labeler_fast.py
  xhs_note_comment                 └─ attitude_batch_log (output)       reporter.py
```

### Cascade Labeling Pipeline

Each comment goes through two stages:

1. **Keyword pre-filter** (`_keyword_match`): Checks the comment against `PROFESSION_KEYWORDS` from `professions.py` (22 professions, ~80-200 keywords each). If no keyword matches, the comment is marked `label_method=model`, `sentiment=neutral`, and the LLM is never called. This skips ~60-70% of comments.

2. **LLM labeling**: Only triggered when keywords match. A single DeepSeek prompt extracts profession, sentiment, emotion, attitude tendency, and topic summary — all in one call.

### Key Files

| File | Role |
|------|------|
| `run.py` | CLI entry point. Orchestrates labeling (per-platform fetch + label + insert loop) then ranking aggregation. |
| `labeler_fast.py` | **Primary labeler** — async parallel with `TokenBucket` rate limiting and exponential backoff retry. `batch_label_async()` with configurable concurrency (default 50). |
| `labeler.py` | Sync fallback labeler. Serial, simpler but ~5-10x slower. Used by `run_xhs.py`. Both share the same `_SYSTEM_PROMPT` and cascade logic. |
| `db.py` | `AttitudeDB` class: async PostgreSQL via `asyncpg` pool. `fetch_unlabeled_comments()` uses `LEFT JOIN attitude_labels` to skip already-labeled rows. `compute_rankings()` does the aggregation with a single large INSERT-SELECT query. |
| `config.py` | Pydantic `Settings` — loads from `.env`. Two LLM providers: DeepSeek (`LLM_*`) and Spark Lite (`SPARK_*`). |
| `professions.py` | The 22-profession keyword dictionary. Each profession has a list of canonical names, slang, metonyms, and related objects. |
| `reporter.py` | `generate_ranking_report()` reads `attitude_rankings`, computes optimism/pessimism/heat top-10 lists, extracts token usage from `raw_response` metadata, estimates cost, and writes `outputs/<date>/ranking.json` and `ranking.md`. |
| `schema.sql` | DDL for `attitude_labels`, `attitude_rankings`, `attitude_batch_log`. Uses `ON CONFLICT` upsert for idempotent re-runs. |
| `run_xhs.py` | Standalone XHS labeling script — serial cascade, writes per-comment to DB, then regenerates rankings. |
| `feedback_keywords.py` | Identifies under-sampled professions and generates keyword suggestions for MindSpider. |
| `crawl_zhihu.py` | Standalone Playwright web scraper for Zhihu. Not part of the main pipeline. |
| `sql_query_app.py` | Flask web UI for ad-hoc DB queries. Not part of the main pipeline. |

### Database Conventions

- **Idempotent writes**: `attitude_labels` has a `UNIQUE (source_platform, source_type, source_id)` constraint with `ON CONFLICT DO UPDATE`, but only updates rows where `label_method = 'error'` — successfully labeled rows are never overwritten.
- **Error recovery**: Failed API calls get `label_method='error'`, which the fetch query explicitly includes (`WHERE al.id IS NULL OR al.label_method = 'error'`), so they are retried on the next run.
- **Token tracking**: `labeler_fast.py` extracts token counts from API `usage` response; `labeler.py` embeds them in `raw_response` as `[tokens: prompt=X, completion=Y]` prefix. `reporter.py` parses both sources.

### TokenBucket Auto-Scaling

`labeler_fast.py`'s `TokenBucket` starts at rate=7, capacity=14. On HTTP 429 it scales down by 30% (min 0.5). After 10 consecutive successes it scales up by 0.5 (max 20). This prevents the fast concurrent labeler from overwhelming the API.

### Tests

The `tests/` directory contains exploratory/validation scripts (not a standard test suite). They compare different LLM models, benchmark Spark accuracy, validate prompts, and sample-check labeling output. No `pytest` or `unittest` framework is configured.

## Config

Copy `.env.example` to `.env`. The `.env` values configure:
- `DB_*` — PostgreSQL connection (reuses MindSpider's database)
- `LLM_*` — DeepSeek API (primary labeler)
- `SPARK_*` — Spark Lite API (alternative, not used by default)
- `BATCH_SIZE` — database fetch batch size (default 20)
- `OUTPUT_DIR` — report output directory (default `outputs`)
