"""
排行报告输出
从 attitude_rankings 取数，生成易读的排行文件
"""

import json
import os
from datetime import date, datetime
from typing import List, Dict, Any
from config import settings
from db import AttitudeDB


async def generate_ranking_report(db: AttitudeDB, rank_date: date) -> str:
    """
    从 attitude_rankings 拉取该日排行数据
    输出 JSON 和 Markdown 两种格式
    """
    sql = """
        SELECT * FROM attitude_rankings
        WHERE ranking_date = $1
        ORDER BY total_labeled DESC
    """
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(sql, rank_date)

    rankings = [dict(r) for r in rows]

    # 计算乐观排行和悲观排行
    optimistic = sorted(
        rankings, key=lambda x: x.get("optimism_index", 0) or 0, reverse=True
    )
    pessimistic = sorted(
        rankings, key=lambda x: x.get("pessimism_index", 0) or 0, reverse=True
    )
    hottest = sorted(
        rankings, key=lambda x: x.get("heat_index", 0) or 0, reverse=True
    )

    # 观测数据 — 取最新一批 batch_log 的 batch_id
    batch_logs = await db.get_batch_stats()
    latest_batch_id = None
    if batch_logs:
        # batch_b9367a538ec3_weibo → batch_b9367a538ec3
        parts = batch_logs[0]["batch_id"].rsplit("_", 1)
        latest_batch_id = parts[0] if len(parts) > 1 else batch_logs[0]["batch_id"]
    label_stats = await db.get_label_stats(latest_batch_id)

    # 平台分布
    plat_breakdown = {}
    for s in label_stats:
        p = s["source_platform"]
        if p not in plat_breakdown:
            plat_breakdown[p] = {"total": 0, "llm": 0, "model": 0, "error": 0, "errors": 0}
        plat_breakdown[p]["total"] += s["cnt"]
        plat_breakdown[p][s["label_method"]] += s["cnt"]
        plat_breakdown[p]["errors"] += s["errors"]

    # Token 统计 — 从 raw_response 中提取 [tokens: ...] 元信息
    token_sql = """
        SELECT
            COALESCE(SUM(
                substring(raw_response FROM '\\[tokens: prompt=([0-9]+)')::int
            ), 0)::int as prompt_tok,
            COALESCE(SUM(
                substring(raw_response FROM 'completion=([0-9]+)\\]')::int
            ), 0)::int as completion_tok
        FROM attitude_labels
        WHERE label_method='llm' AND raw_response ~ '\\[tokens:'
    """
    async with db.pool.acquire() as conn:
        tok_row = await conn.fetchrow(token_sql)
    prompt_tok = tok_row["prompt_tok"] if tok_row else 0
    completion_tok = tok_row["completion_tok"] if tok_row else 0
    total_tok = prompt_tok + completion_tok

    # 成本估算 (DeepSeek V4-Flash PackyAPI 参考价)
    # 按 $0.15/M prompt tokens, $0.60/M completion tokens 计算
    COST_PER_1K_PROMPT = 0.00015
    COST_PER_1K_COMPLETION = 0.0006
    estimated_cost = (prompt_tok / 1000 * COST_PER_1K_PROMPT) + (completion_tok / 1000 * COST_PER_1K_COMPLETION)

    # 情感分布
    sentiment_sql = """
        SELECT sentiment_polarity, COUNT(*)::int as cnt
        FROM attitude_labels
        WHERE label_method='llm'
        GROUP BY sentiment_polarity
    """
    async with db.pool.acquire() as conn:
        sent_rows = await conn.fetch(sentiment_sql)
    sent_dist = {r["sentiment_polarity"]: r["cnt"] for r in sent_rows}

    report = {
        "date": rank_date.isoformat(),
        "generated_at": datetime.now().isoformat(),
        "total_topics": len(rankings),
        "observation": {
            "batch_logs": [
                {
                    "batch_id": b["batch_id"],
                    "platform": b["platform"],
                    "total": b["labeled_count"],
                    "llm": b["llm_count"],
                    "model": b["model_count"],
                    "errors": b["failed_count"],
                    "elapsed_s": (
                        (b["finished_at"] - b["started_at"])
                        if b.get("finished_at") and b.get("started_at")
                        else None
                    ),
                    "status": b["status"],
                }
                for b in batch_logs[:10]
            ],
            "platform_breakdown": plat_breakdown,
            "llm_sentiment_distribution": sent_dist,
            "tokens": {"prompt": prompt_tok, "completion": completion_tok, "total": total_tok},
            "estimated_cost_usd": round(estimated_cost, 6),
            "total_labeled": sum(v["total"] for v in plat_breakdown.values()),
            "total_errors": sum(v["errors"] for v in plat_breakdown.values()),
        },
        "rankings": {
            "optimism_top10": [
                {
                    "rank": i + 1,
                    "topic": r.get("topic_name"),
                    "optimism_index": round(r.get("optimism_index", 0), 4),
                    "positive_ratio": round(r.get("positive_ratio", 0), 4),
                    "negative_ratio": round(r.get("negative_ratio", 0), 4),
                    "total_labeled": r.get("total_labeled", 0),
                    "emotions": r.get("emotion_distribution"),
                }
                for i, r in enumerate(optimistic[:10])
            ],
            "pessimism_top10": [
                {
                    "rank": i + 1,
                    "topic": r.get("topic_name"),
                    "pessimism_index": round(r.get("pessimism_index", 0), 4),
                    "positive_ratio": round(r.get("positive_ratio", 0), 4),
                    "negative_ratio": round(r.get("negative_ratio", 0), 4),
                    "total_labeled": r.get("total_labeled", 0),
                    "emotions": r.get("emotion_distribution"),
                }
                for i, r in enumerate(pessimistic[:10])
            ],
            "hottest_top10": [
                {
                    "rank": i + 1,
                    "topic": r.get("topic_name"),
                    "total_labeled": r.get("total_labeled", 0),
                    "optimism_index": round(r.get("optimism_index", 0), 4),
                    "pessimism_index": round(r.get("pessimism_index", 0), 4),
                    "positive_ratio": round(r.get("positive_ratio", 0), 4),
                    "negative_ratio": round(r.get("negative_ratio", 0), 4),
                }
                for i, r in enumerate(hottest[:10])
            ],
            "all_topics": [
                {
                    "topic": r.get("topic_name"),
                    "total": r.get("total_labeled", 0),
                    "positive": r.get("positive_count", 0),
                    "negative": r.get("negative_count", 0),
                    "neutral": r.get("neutral_count", 0),
                    "optimism": round(r.get("optimism_index", 0), 4),
                    "pessimism": round(r.get("pessimism_index", 0), 4),
                    "heat": round(r.get("heat_index", 0), 4),
                }
                for r in rankings
            ],
        },
    }

    # 写 JSON
    date_str = rank_date.isoformat()
    out_dir = os.path.join(settings.OUTPUT_DIR, date_str)
    os.makedirs(out_dir, exist_ok=True)

    json_path = os.path.join(out_dir, "ranking.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # 写 Markdown
    md = _render_markdown(report, rank_date)
    md_path = os.path.join(out_dir, "ranking.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)

    return json_path


def _render_markdown(report: Dict[str, Any], rank_date: date) -> str:
    """生成可读的 Markdown 排行报告"""
    lines = []
    lines.append(f"# 全岗位态度盘点 — {rank_date.isoformat()}\n")

    r = report["rankings"]

    lines.append("## 📈 乐观排行 TOP10\n")
    lines.append("| 排名 | 话题 | 乐观指数 | 积极占比 | 消极占比 | 讨论量 |")
    lines.append("|------|------|----------|----------|----------|--------|")
    for item in r["optimism_top10"]:
        lines.append(
            f"| {item['rank']} | {item['topic']} | {item['optimism_index']:.2%} "
            f"| {item['positive_ratio']:.1%} | {item['negative_ratio']:.1%} "
            f"| {item['total_labeled']} |"
        )

    lines.append("\n## 📉 悲观排行 TOP10\n")
    lines.append("| 排名 | 话题 | 悲观指数 | 积极占比 | 消极占比 | 讨论量 |")
    lines.append("|------|------|----------|----------|----------|--------|")
    for item in r["pessimism_top10"]:
        lines.append(
            f"| {item['rank']} | {item['topic']} | {item['pessimism_index']:.2%} "
            f"| {item['positive_ratio']:.1%} | {item['negative_ratio']:.1%} "
            f"| {item['total_labeled']} |"
        )

    lines.append("\n## 🔥 热度排行 TOP10\n")
    lines.append("| 排名 | 话题 | 讨论量 | 乐观指数 | 悲观指数 |")
    lines.append("|------|------|--------|----------|----------|")
    for item in r["hottest_top10"]:
        lines.append(
            f"| {item['rank']} | {item['topic']} | {item['total_labeled']} "
            f"| {item['optimism_index']:.2%} | {item['pessimism_index']:.2%} |"
        )

    # 观测面板
    obs = report.get("observation", {})
    lines.append(f"\n## 📊 观测面板\n")
    lines.append(f"- **标注总数**: {obs.get('total_labeled', '?')} 条")
    lines.append(f"- **标注错误**: {obs.get('total_errors', '?')} 条")
    tok = obs.get("tokens", {})
    lines.append(f"- **Token 用量**: 输入{tok.get('prompt',0)} / 输出{tok.get('completion',0)} / 总计{tok.get('total',0)}")
    cost = obs.get("estimated_cost_usd", 0)
    lines.append(f"- **预估成本**: ${cost:.6f} USD")
    lines.append("")

    lines.append("### 各平台标注量\n")
    lines.append("| 平台 | 总计 | LLM | 本地模型 | 错误 |")
    lines.append("|------|------|-----|----------|------|")
    for plat, info in sorted(obs.get("platform_breakdown", {}).items()):
        lines.append(
            f"| {plat} | {info['total']} | {info.get('llm', 0)} "
            f"| {info.get('model', 0)} | {info.get('errors', 0)} |"
        )

    lines.append("\n### LLM 情感分布\n")
    sent = obs.get("llm_sentiment_distribution", {})
    total_sent = sum(sent.values()) or 1
    if sent:
        lines.append("| 情感 | 数量 | 占比 |")
        lines.append("|------|------|------|")
        for pol in ["positive", "negative", "neutral"]:
            cnt = sent.get(pol, 0)
            lines.append(f"| {pol} | {cnt} | {cnt*100//total_sent}% |")

    lines.append(f"\n---\n共盘点 {report['total_topics']} 个话题")
    lines.append(f"生成时间: {report['generated_at']}")

    return "\n".join(lines)
