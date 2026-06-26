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
import os
import asyncio
import argparse
import time as _time
from datetime import date, timedelta
from pathlib import Path

from config import settings
from db import AttitudeDB
from labeler import batch_cascade_label, generate_batch_id
from reporter import generate_ranking_report


async def init_database(db: AttitudeDB):
    """执行 schema.sql 建表"""
    schema_path = Path(__file__).parent / "schema.sql"
    sql = schema_path.read_text()

    async with db.pool.acquire() as conn:
        await conn.execute(sql)
    print("[✓] 数据库表已就绪")


async def run_labeling(db: AttitudeDB, target_date: date, limit: int = 0):
    """标注流程 — 带观测"""
    batch_id = generate_batch_id()
    t0 = _time.time()

    total_labeled = 0
    total_llm = 0
    total_model = 0
    total_errors = 0
    total_fetched = 0
    platform_stats = {}

    for platform in ["weibo", "bilibili", "xhs"]:
        cursor = 0
        plat_llm = 0
        plat_model = 0
        plat_errors = 0
        plat_total = 0
        plat_prompt_tokens = 0
        plat_completion_tokens = 0

        while True:
            items = await db.fetch_unlabeled_comments(
                platform, after_id=cursor, limit=min(limit or 500, 500)
            )
            if not items:
                break

            if limit and total_labeled + len(items) > limit:
                items = items[: limit - total_labeled]
                if not items:
                    break

            labels, batch_errors, batch_prompt_tokens, batch_completion_tokens = batch_cascade_label(items, batch_id)
            await db.insert_labels(labels)

            llm_count = sum(1 for l in labels if l.get("label_method") == "llm")
            model_count = sum(1 for l in labels if l.get("label_method") == "model")

            total_labeled += len(labels)
            total_llm += llm_count
            total_model += model_count
            total_errors += batch_errors
            total_fetched += len(items)
            plat_llm += llm_count
            plat_model += model_count
            plat_errors += batch_errors
            plat_total += len(labels)
            plat_prompt_tokens += batch_prompt_tokens
            plat_completion_tokens += batch_completion_tokens

            print(
                f"  [{platform}] 已标 {total_labeled} 条 "
                f"(本地{model_count} / LLM{llm_count}"
                f"{f' / 错误{batch_errors}' if batch_errors else ''})"
            )

            cursor = max(items, key=lambda x: x["source_id"])["source_id"]

            if limit and total_labeled >= limit:
                break

        # 写 batch_log（每平台一条）
        date_scope = target_date.isoformat()
        await db.write_batch_log(
            f"{batch_id}_{platform}", platform, date_scope,
            plat_total, plat_total, plat_llm, plat_model, plat_errors
        )
        platform_stats[platform] = {
            "total": plat_total, "llm": plat_llm,
            "model": plat_model, "errors": plat_errors,
            "prompt_tokens": plat_prompt_tokens,
            "completion_tokens": plat_completion_tokens,
        }
        await db.finish_batch_log(f"{batch_id}_{platform}")

    elapsed = _time.time() - t0
    print(f"\n[✓] 标注完成：共 {total_labeled} 条 "
          f"(本地{total_model} / LLM{total_llm}"
          f"{f' / 错误{total_errors}' if total_errors else ''}) "
          f"耗时 {elapsed:.0f}s")

    total_prompt = sum(p.get("prompt_tokens", 0) for p in platform_stats.values())
    total_completion = sum(p.get("completion_tokens", 0) for p in platform_stats.values())
    return {
        "batch_id": batch_id,
        "total": total_labeled,
        "llm": total_llm,
        "model": total_model,
        "errors": total_errors,
        "elapsed_s": round(elapsed, 1),
        "prompt_tokens": total_prompt,
        "completion_tokens": total_completion,
        "platforms": platform_stats,
    }


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
        run_stats = await run_labeling(db, target_date, limit=args.limit)

        print("\nStep 3/3: 排行聚合...")
        await run_ranking(db, target_date)

        print(f"\n输出目录: {settings.OUTPUT_DIR}/{target_date.isoformat()}/")

    except Exception as e:
        print(f"\n❌ 运行失败: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
