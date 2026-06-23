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
        rows = await conn.fetch(sql, rank_date.isoformat())

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

    report = {
        "date": rank_date.isoformat(),
        "generated_at": datetime.now().isoformat(),
        "total_topics": len(rankings),
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

    lines.append(f"\n---\n共盘点 {report['total_topics']} 个话题")
    lines.append(f"生成时间: {report['generated_at']}")

    return "\n".join(lines)
