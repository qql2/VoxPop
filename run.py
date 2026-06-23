#!/usr/bin/env python3
"""
AttitudeEngine — 手动运行入口

用法：
  python run.py                               # 跑昨天的数据
  python run.py --date 2026-06-23             # 跑指定日期
  python run.py --sql-only                    # 只初始化数据库表
  python run.py --limit 200                   # 只标注 200 条（小规模测试）
"""

import sys
import asyncio
import argparse
from datetime import date, timedelta

from config import settings
from db import AttitudeDB
from labeler import batch_cascade_label, generate_batch_id
from reporter import generate_ranking_report


async def init_database(db: AttitudeDB):
    """执行 schema.sql 建表"""
    schema_path = __file__.rsplit("/", 1)[0] + "/schema.sql"
    with open(schema_path, "r") as f:
        sql = f.read()

    async with db.pool.acquire() as conn:
        await conn.execute(sql)
    print("[✓] 数据库表已就绪")


async def run_labeling(db: AttitudeDB, target_date: date, limit: int = 0):
    """标注流程"""
    batch_id = generate_batch_id()
    total_labeled = 0
    total_llm = 0
    total_model = 0

    for platform in ["weibo", "bilibili"]:
        cursor = 0
        while True:
            items = await db.fetch_unlabeled_comments(
                platform, after_id=cursor, limit=min(limit or 500, 500)
            )
            if not items:
                break

            if limit and total_labeled + len(items) > limit:
                items = items[: limit - total_labeled]

            labels = batch_cascade_label(items, batch_id)
            await db.insert_labels(labels)

            llm_count = sum(1 for l in labels if l.get("label_method") == "llm")
            model_count = sum(1 for l in labels if l.get("label_method") == "model")

            total_labeled += len(labels)
            total_llm += llm_count
            total_model += model_count

            print(
                f"  [{platform}] 已标 {total_labeled} 条 "
                f"(本地{model_count} / LLM{llm_count})"
            )

            cursor = max(items, key=lambda x: x["source_id"])["source_id"]

            if limit and total_labeled >= limit:
                break

    print(f"\n[✓] 标注完成：共 {total_labeled} 条 (本地{total_model} / LLM{total_llm})")


async def run_ranking(db: AttitudeDB, target_date: date):
    """排行聚合 + 输出"""
    await db.compute_rankings(target_date)
    print(f"[✓] 排行已聚合到 attitude_rankings")

    json_path = await generate_ranking_report(db, target_date)
    print(f"[✓] 排行报告已输出: {json_path}")


async def main():
    parser = argparse.ArgumentParser(description="VoxPop — 全岗位态度盘点")
    parser.add_argument("--date", type=str, help="目标日期 YYYY-MM-DD，默认昨天")
    parser.add_argument("--limit", type=int, default=0, help="限制标注条数（测试用）")
    parser.add_argument("--sql-only", action="store_true", help="只初始化数据库")
    args = parser.parse_args()

    target_date = (
        date.fromisoformat(args.date) if args.date else date.today() - timedelta(days=1)
    )

    db = AttitudeDB()
    await db.connect()

    try:
        await init_database(db)
        if args.sql_only:
            return

        print(f"\n=== 全岗位态度盘点 [{target_date}] ===\n")

        print("Step 1/3: 爬取 → 已由 MindSpider 完成（跳过）")
        print("Step 2/3: 情感标注...")
        await run_labeling(db, target_date, limit=args.limit)

        print("\nStep 3/3: 排行聚合...")
        await run_ranking(db, target_date)

        print(f"\n输出目录: {settings.OUTPUT_DIR}/{target_date.isoformat()}/")

    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
