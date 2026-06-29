#!/usr/bin/env python3
"""
VoxPop 爬虫入口 — 基于调度表（crawl_schedule），只爬到期关键词

用法:
  python3 run_crawl.py                         # 所有平台的到期关键词
  python3 run_crawl.py --platforms zhihu       # 只爬知乎到期关键词
  python3 run_crawl.py --all                   # 无视调度，爬 crawl_schedule 全部

调度逻辑:
  crawl_schedule 表记录每个关键词的 (interval_days, last_crawled_at)
  只有 last_crawled_at + interval_days <= now 的关键词才会被爬取
  爬完后自动更新 last_crawled_at
"""
import sys, os, subprocess, asyncio, json
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import AttitudeDB

MINDSIDER_DIR = os.path.expanduser("~/MindSpider")

ALL_PLATFORMS = ["wb", "bili", "xhs", "zhihu"]
PLATFORM_NAMES = {"wb": "微博", "bili": "B站", "xhs": "小红书", "zhihu": "知乎"}
# MindSpider daily_topics 的 topic_id 前缀
TOPIC_ID_PREFIX = "voxpop_schedule_"


async def run():
    # ---- 解析参数 ----
    platforms = []
    force_all = False
    if "--all" in sys.argv:
        force_all = True
    elif "--platforms" in sys.argv:
        idx = sys.argv.index("--platforms") + 1
        platforms = sys.argv[idx:]
    else:
        platforms = ALL_PLATFORMS[:]

    print(f"📢 爬虫调度启动")
    print(f"   平台: {', '.join(PLATFORM_NAMES.get(p, p) for p in platforms)}")
    if force_all:
        print(f"   模式: --all（忽略调度间隔）")
    print()

    db = AttitudeDB()
    await db.connect()
    today = date.today()
    now_ts = int(datetime.now().timestamp())

    try:
        # ---- Step 1: 读调度表 ----
        due_rows = []
        for p in platforms:
            rows = await db.get_due_keywords(platforms=[p])
            due_rows.extend(rows)

        if not due_rows:
            print("📭 当前没有到期的关键词（所有 keyword 都未到调度间隔）")
            print("   如需强制爬取，加 --all 参数")
            return

        print(f"📋 到期关键词: {len(due_rows)} 条")
        # 按平台分组
        by_platform = {}
        for r in due_rows:
            by_platform.setdefault(r["platform"], []).append(r["keyword"])
        for p, kws in by_platform.items():
            print(f"  {PLATFORM_NAMES.get(p, p):5s}: {len(kws)} 个关键词")

        # ---- Step 2: 写入 daily_topics（MindSpider 从这里读）----
        topic_id = f"{TOPIC_ID_PREFIX}{today.isoformat()}"
        topic_name = f"VoxPop 调度 — {today.isoformat()}"

        for p in platforms:
            kws = by_platform.get(p, [])
            if not kws:
                continue

            # 写入 daily_topics（复用 feedback_keywords 的逻辑）
            import asyncpg
            conn = await asyncpg.connect(
                host="127.0.0.1", port=5432,
                user="postgres", password="***",
                database="mindspider",
            )
            try:
                desc = f"VoxPop 调度爬取。生成时间: {datetime.now().isoformat()}"
                kw_json = json.dumps(kws, ensure_ascii=False)
                await conn.execute("""
                    INSERT INTO daily_topics (topic_id, topic_name, topic_description, keywords, extract_date, add_ts, last_modify_ts)
                    VALUES ($1, $2, $3, $4, $5, $6, $6)
                    ON CONFLICT (topic_id) DO UPDATE SET keywords = $4, topic_description = $3, last_modify_ts = $6
                """, f"{topic_id}_{p}", f"{topic_name}_{p}", desc, kw_json, today, now_ts)
                print(f"  📝 {PLATFORM_NAMES.get(p, p)}: 已写入 {len(kws)} 个关键词到 daily_topics")
            finally:
                await conn.close()

        # ---- Step 3: 调用 MindSpider 爬取 ----
        print(f"\n🚀 启动 MindSpider 爬取...")
        cmd = [
            "/usr/bin/python3",
            os.path.join(MINDSIDER_DIR, "main.py"),
            "--deep-sentiment",
            "--platforms",
        ] + platforms
        print(f"   执行: {' '.join(cmd)}\n")
        result = subprocess.run(cmd, cwd=MINDSIDER_DIR)

        # ---- Step 4: 更新调度表 + 当日去重 ----
        for p in platforms:
            kws = by_platform.get(p, [])
            if not kws:
                continue

            # 更新调度表的 last_crawled_at
            await db.mark_schedule_crawled(kws, p)
            print(f"  ✅ {PLATFORM_NAMES.get(p, p)}: 已更新 {len(kws)} 个关键词的调度时间")

            # 标记当日已爬（crawled_keywords 去重）
            await db.mark_keywords_crawled(kws, p)

        elapsed = int(datetime.now().timestamp()) - now_ts
        if result.returncode == 0:
            print(f"\n✅ 爬取完成！耗时 {elapsed}s")
            print(f"   运行 python3 run_label_cron.py 开始标注")
        else:
            print(f"\n⚠️ MindSpider 返回码 {result.returncode}（数据可能部分入库）")

    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(run())
