#!/usr/bin/env python3
"""
VoxPop 手动爬取脚本
用法:
  python3 run_crawl.py              # 爬所有平台（需要扫码登录）
  python3 run_crawl.py --platforms zhihu    # 只爬知乎
  python3 run_crawl.py --platforms wb bili  # 只爬微博+B站
"""
import sys, os, subprocess, asyncio

MINDSIDER_DIR = os.path.expanduser("~/MindSpider")

ALL_PLATFORMS = ["wb", "bili", "xhs", "zhihu"]
PLATFORM_NAMES = {
    "wb": "微博",
    "bili": "B站",
    "xhs": "小红书",
    "zhihu": "知乎",
}

if __name__ == "__main__":
    platforms = []
    if "--platforms" in sys.argv:
        idx = sys.argv.index("--platforms") + 1
        platforms = sys.argv[idx:]
    else:
        platforms = ALL_PLATFORMS[:]

    print(f"📢 开始爬取: {', '.join(PLATFORM_NAMES.get(p, p) for p in platforms)}")
    print(f"   需要扫码登录，会弹出浏览器窗口\n")

    cmd = [
        "/usr/bin/python3",
        os.path.join(MINDSIDER_DIR, "main.py"),
        "--deep-sentiment",
        "--platforms",
    ] + platforms

    print(f"执行: {' '.join(cmd)}\n")
    result = subprocess.run(cmd, cwd=MINDSIDER_DIR)

    # 爬完后标记关键词已爬（调用 feedback_keywords 的标记逻辑）
    try:
        import asyncpg
        from datetime import date, datetime

        PLATFORM_CODES = {"wb": "weibo", "bili": "bilibili", "xhs": "xhs", "zhihu": "zhihu"}

        async def mark_crawled():
            conn = await asyncpg.connect(
                host="127.0.0.1", port=5432,
                user="postgres", password="***",
                database="mindspider",
            )
            try:
                # 读当天 daily_topics 的关键词
                today = date.today()
                row = await conn.fetchrow("""
                    SELECT keywords FROM daily_topics
                    WHERE topic_id LIKE 'feedback_%' AND extract_date = $1
                    ORDER BY add_ts DESC LIMIT 1
                """, today)
                if row:
                    import json
                    kws = json.loads(row["keywords"])
                    now = int(datetime.now().timestamp())
                    for p in platforms:
                        db_plat = PLATFORM_CODES.get(p, p)
                        marked = 0
                        for kw in kws:
                            await conn.execute("""
                                INSERT INTO crawled_keywords (keyword, platform, crawl_date, crawled_at)
                                VALUES ($1, $2, $3, $4)
                                ON CONFLICT (keyword, platform, crawl_date) DO NOTHING
                            """, kw, db_plat, today, now)
                            marked += 1
                        print(f"  📝 已标记 {marked} 个关键词在 {PLATFORM_NAMES.get(p,p)} 上今日已爬")
            finally:
                await conn.close()

        asyncio.run(mark_crawled())
    except Exception as e:
        print(f"  ⚠️ 标记关键词失败（不影响爬取结果）: {e}")

    if result.returncode == 0:
        print(f"\n✅ 爬取完成！运行 python3 run_label_cron.py 开始标注")
    else:
        print(f"\n❌ 爬取失败（返回码 {result.returncode}）")
        sys.exit(result.returncode)
