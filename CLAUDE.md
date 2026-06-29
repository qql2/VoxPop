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

# --- Web 控制台（推荐）---
python sql_query_app.py
# 访问 http://127.0.0.1:5000

# --- 爬取（手动，需要扫码登录）---
python run_crawl.py                     # 全平台
python run_crawl.py --platforms zhihu   # 指定平台

# --- 标注（自动/手动）---
python run_label_cron.py                # 立即运行
python run_label_cron.py --dry-run      # 预览待标注量
# crontab 每天凌晨 4:00 自动运行

# 旧的入口（仅同步标注，不支持 zhihu）
python run.py --limit 200
python run_xhs.py
```

## Architecture

### Data Flow

```
qql2/MindSpider (爬虫)  →  PostgreSQL                   →  VoxPop (标注)
  weibo_note_comment         ├─ attitude_labels             run_label_cron.py
  bilibili_video_comment     ├─ attitude_rankings           labeler_fast.py
  xhs_note_comment           ├─ attitude_batch_log          sql_query_app.py (控制台)
  zhihu_comment              └─ crawled_keywords            observer.py (通知)
```

### Cascade Labeling Pipeline

1. **Keyword pre-filter** (`_keyword_match`): Checks against `PROFESSION_KEYWORDS` (22 professions, ~800 keywords). No match → `label_method=model`, `sentiment=neutral`, saved immediately without LLM.
2. **LLM labeling**: Only keyword-matched comments reach the API. Single DeepInfra prompt extracts profession, sentiment, emotion, attitude tendency, and topic summary.

### Key Files

| File | Role |
|------|------|
| `sql_query_app.py` | **三合一 Web 控制台** — SQL 查询 + 运行状态 + 一键爬取/标注（Alpine.js + SSE 实时日志） |
| `labeler_fast.py` | **主标注器** — async parallel, TokenBucket 30/s, 3-retry with backoff, pre-filters API items from keyword-only items |
| `run_label_cron.py` | **定时标注入口** — 带护拦（错误率 >50% 停止 + 保留 raw_response）、写入 run_status.json、macOS 通知 |
| `run_crawl.py` | 手动爬取入口，完成后自动标记关键词今日已爬 |
| `observer.py` | 运行状态记录 + macOS Alert/Banner 通知 |
| `db.py` | AttitudeDB — asyncpg pool, fetch/insert/rankings/crawled_keywords |
| `reporter.py` | 排行报告生成 → outputs/<date>/ranking.json + ranking.md |
| `feedback_keywords.py` | 低样本职业分析 + 当日去重写入 daily_topics |
| `professions.py` | 22 种职业关键词词典（~800 关键词） |
| `config.py` | Pydantic Settings — 从 .env 加载 |

### Database Conventions

- **Idempotent writes**: `UNIQUE (source_platform, source_type, source_id)` with `ON CONFLICT DO UPDATE`, only where `attitude_labels.label_method = 'error'`
- **Error recovery**: `label_method='error'` items are re-fetched (`WHERE al.id IS NULL OR al.label_method = 'error'`) and retried
- **posted_at**: Stores original comment publish timestamp (zhihu→publish_time, others→create_time). Supports time-filtered queries (近7天/近30天)
- **crawled_keywords**: Prevents same-day re-crawling of the same keyword

### TokenBucket

`labeler_fast.py`'s `TokenBucket` — rate=30/s, capacity=60, auto-scales on 429 (×0.7, min 1) and success (10 consecutive → +0.5, max 60). Pre-filters separate keyword-matched items from API calls — 0-LLM batches complete instantly.

### Error Handling

- Parse failures → retry 3 times, then `label_method='error'` with `raw_response` preserving API output
- HTTP 429/503 → retry (transient)
- HTTP 4xx (other) → immediate error (won't fix on retry)
- Guardrail (>50% error rate) → saves labels to DB first, then stops
- Debug errors: `SELECT raw_response FROM attitude_labels WHERE label_method='error'` — never call the API live to reproduce

### Web Control Panel

http://127.0.0.1:5000 — Three tabs:
- **🖥️ 控制台**: Platform checkboxes, start/stop crawl & labeling, SSE real-time log
- **📊 查询**: SQL presets (rankings, time filters), clickthrough drill-down to comments
- **📋 运行状态**: Metrics (LLM成功/API失败/本地过滤), last 20 runs history, alerts

### Model

Current: `meta-llama/Meta-Llama-3.1-8B-Instruct` (DeepInfra). Avoid the `-Turbo` variant — quantized version has degraded instruction-following. Uses ~700 tokens input + 400 output per call (0.8% of 131k context window).

## Config

```bash
cp .env.example .env
```

Key values:
- `DB_*` — PostgreSQL (reuses MindSpider's database on port 5432)
- `LLM_*` — DeepInfra API (primary labeler)
- `SPARK_*` — Spark Lite API (alternative, not default)
- `BATCH_SIZE` — DB fetch batch (default 20)
- `OUTPUT_DIR` — report output (default `outputs`)

## Memory

Debugging rules are persisted in `~/.claude/projects/-Users-Admin1-VoxPop/memory/`. Check `MEMORY.md` for rules about error debugging workflows.
