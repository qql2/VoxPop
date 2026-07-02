#!/usr/bin/env python3
"""
VoxPop 爬虫入口 — 自适应间隔调度

用法:
  python3 run_crawl.py                         # 所有平台的到期关键词
  python3 run_crawl.py --platforms zhihu       # 只爬知乎到期关键词
  python3 run_crawl.py --all                   # 无视调度，爬 crawl_schedule 全部

调度逻辑:
  - 爬前/爬后对比 MindSpider 评论表行数，检测是否爬到了新数据
  - 爬到新数据 → interval_days 减 1（最短 1 天，即每天爬）
  - 没爬到数据 / 爬取失败 → interval_days 加 1（最长 14 天）
  - 此机制自动应对平台故障（如 Chrome 崩溃）：失败→间隔拉长→减少重试频率

可观测性:
  - 每次运行写入 run_crawl_history.json
"""
import sys, os, subprocess, asyncio, json
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import AttitudeDB

MINDSIDER_DIR = os.path.expanduser("~/MindSpider")

ALL_PLATFORMS = ["wb", "bili", "xhs", "zhihu"]
PLATFORM_NAMES = {"wb": "微博", "bili": "B站", "xhs": "小红书", "zhihu": "知乎"}
TOPIC_ID_PREFIX = "voxpop_schedule_"
CRAWL_HISTORY_FILE = Path(__file__).parent / "run_crawl_history.json"
MAX_HISTORY = 20


def _append_crawl_history(entry: dict):
    """追加爬取历史到 run_crawl_history.json"""
    history = []
    if CRAWL_HISTORY_FILE.exists():
        try:
            history = json.loads(CRAWL_HISTORY_FILE.read_text())
        except (json.JSONDecodeError, Exception):
            history = []
    history.append(entry)
    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]
    CRAWL_HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2))


async def run():
    # ---- 参数解析 ----
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

    crawl_record = {
        "status": "running",
        "batch_id": f"crawl_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "date": today.isoformat(),
        "elapsed_s": 0,
        "returncode": None,
        "platforms": {},
        "total_due": 0,
    }

    try:
        # ====== Step 1: 读调度表 ======
        due_rows = []
        for p in platforms:
            rows = await db.get_due_keywords(platforms=[p])
            due_rows.extend(rows)

        if not due_rows:
            print("📭 当前没有到期的关键词（所有 keyword 都未到调度间隔）")
            print("   如需强制爬取，加 --all 参数")
            crawl_record["status"] = "no_due"
            _append_crawl_history(crawl_record)
            return

        print(f"📋 到期关键词: {len(due_rows)} 条")
        by_platform = {}
        for r in due_rows:
            by_platform.setdefault(r["platform"], []).append(r["keyword"])
        for p, kws in by_platform.items():
            print(f"  {PLATFORM_NAMES.get(p, p):5s}: {len(kws)} 个关键词")
        crawl_record["total_due"] = len(due_rows)

        # ====== Step 2: 爬前计数（对比爬后判断是否获取到新数据） ======
        print(f"\n📊 爬前平台数据量:")
        before_counts = {}
        for p in platforms:
            cnt = await db.count_platform_rows(p)
            before_counts[p] = cnt
            print(f"  {PLATFORM_NAMES.get(p, p):5s}: {cnt} 条评论")

        # ====== Step 3: 写入 daily_topics（MindSpider 从这里读） ======
        for p in platforms:
            kws = by_platform.get(p, [])
            if not kws:
                continue
            try:
                desc = f"VoxPop 调度爬取。生成时间: {datetime.now().isoformat()}"
                kw_json = json.dumps(kws, ensure_ascii=False)
                async with db.pool.acquire() as conn:
                    await conn.execute("""
                        INSERT INTO daily_topics (topic_id, topic_name, topic_description, keywords, extract_date, add_ts, last_modify_ts)
                        VALUES ($1, $2, $3, $4, $5, $6, $6)
                        ON CONFLICT (topic_id) DO UPDATE SET keywords = $4, topic_description = $3, last_modify_ts = $6
                    """, f"{topic_id}_{p}", f"{topic_name}_{p}", desc, kw_json, today, now_ts)
                    print(f"  📝 {PLATFORM_NAMES.get(p, p)}: 已写入 {len(kws)} 个关键词到 daily_topics")
            except Exception as e:
                print(f"  ⚠️ 写入 daily_topics 失败: {e}")

        # ====== Step 4: 预检 — 清理残留 Chrome 进程（上次崩溃可能留下锁文件） ======
        print(f"\n🔍 预检 — 清理残留 Chrome 进程...")
        # 杀掉残留的 MindSpider Chrome 进程（不影响用户自己的 Chrome）
        killed = subprocess.run(
            ["pkill", "-f", "chrome.*browser_data"],
            capture_output=True, timeout=5,
        )
        if killed.returncode == 0:
            print(f"  🧹 已清理残留 Chrome 进程")
            await asyncio.sleep(1)  # 等端口释放
        else:
            print(f"  ✅ 无残留 Chrome 进程")

        # 清理 Chrome 锁文件（SingletonLock / SingletonCookie 等）
        browser_data_root = os.path.join(MINDSIDER_DIR, "DeepSentimentCrawling", "MediaCrawler", "browser_data")
        for p in platforms:
            for dir_name in [f"{p}_user_data_dir", f"cdp_{p}_user_data_dir"]:
                lock_dir = os.path.join(browser_data_root, dir_name)
                if not os.path.isdir(lock_dir):
                    continue
                lock_files = []
                for root, dirs, files in os.walk(lock_dir):
                    for fname in files:
                        if fname.startswith("Singleton") or fname == "LOCK":
                            lock_files.append(os.path.join(root, fname))
                if lock_files:
                    for lf in lock_files:
                        try:
                            os.remove(lf)
                        except OSError:
                            pass
                    print(f"  🧹 {PLATFORM_NAMES.get(p, p)}: 清理 {len(lock_files)} 个锁文件")

        # ====== Step 5: 调用 MindSpider 爬取（捕获输出判断真实结果） ======
        print(f"\n🚀 启动 MindSpider 爬取...")
        cmd = [
            "/usr/bin/python3",
            os.path.join(MINDSIDER_DIR, "main.py"),
            "--deep-sentiment",
            "--platforms",
        ] + platforms
        print(f"   执行: {' '.join(cmd)}\n")

        result = subprocess.run(cmd, cwd=MINDSIDER_DIR, capture_output=True, text=True)
        elapsed = int(datetime.now().timestamp()) - now_ts
        crawl_record["returncode"] = result.returncode
        crawl_record["elapsed_s"] = elapsed

        # ====== Step 6: 爬后计数 + 自适应调度 ======
        # 真实失败的检测信号：
        # 1) returncode != 0
        # 2) stdout 中有大量 ERROR/失败 但 returncode 却 0（MindSpider 的坑）
        # 3) 爬后行数没变（最可靠的硬证据）
        stdout_lower = (result.stdout or "").lower()
        stderr_lower = (result.stderr or "").lower()
        has_error_output = "error" in stdout_lower or "失败" in result.stdout or "error" in stderr_lower

        print(f"\n📊 爬后平台数据量:")
        after_counts = {}
        new_data_per_platform = {}
        for p in platforms:
            cnt = await db.count_platform_rows(p)
            after_counts[p] = cnt
            new_count = cnt - before_counts.get(p, 0)
            new_data_per_platform[p] = new_count
            print(f"  {PLATFORM_NAMES.get(p, p):5s}: {cnt} 条评论 {'🆕 +' + str(new_count) if new_count > 0 else '(无变化)'}")

        for p in platforms:
            kws = by_platform.get(p, [])
            if not kws:
                continue

            had_new_data = new_data_per_platform.get(p, 0) > 0

            if not had_new_data:
                # 没爬到新数据 → 拉长间隔
                await db.adjust_schedule_interval(kws, p, had_new_data=False)
                print(f"  🔴 {PLATFORM_NAMES.get(p, p)}: 无新数据 → 拉长间隔")
                crawl_record.setdefault("platforms", {})[p] = {
                    "status": "no_data",
                    "new_rows": 0,
                    "adjustment": "lengthened",
                }
            else:
                # 爬到新数据 → 标记已爬 + 缩短间隔
                await db.mark_schedule_crawled(kws, p)
                await db.mark_keywords_crawled(kws, p)
                await db.adjust_schedule_interval(kws, p, had_new_data=True)
                print(f"  ✅ {PLATFORM_NAMES.get(p, p)}: 新数据 {new_data_per_platform[p]} 条 → 缩短间隔")
                crawl_record.setdefault("platforms", {})[p] = {
                    "status": "success",
                    "new_rows": new_data_per_platform[p],
                    "adjustment": "shortened",
                }

            # 读取调整后的 interval_days 做展示
            row = None
            if kws:
                # 取第一个 keyword 作代表展示
                sample_kw = kws[0]
                async with db.pool.acquire() as conn:
                    row_r = await conn.fetchrow(
                        "SELECT interval_days FROM crawl_schedule WHERE keyword=$1 AND platform=$2",
                        sample_kw, p,
                    )
                    if row_r:
                        row = row_r["interval_days"]
            if row:
                crawl_record.setdefault("platforms", {}).setdefault(p, {})["new_interval_days"] = row

        # ====== Step 7: 最终统计 ======
        total_new = sum(new_data_per_platform.values())
        success_platforms = sum(1 for p in platforms if new_data_per_platform.get(p, 0) > 0)

        if total_new > 0:
            crawl_record["status"] = "completed"
            print(f"\n✅ 爬取完成！{success_platforms}/{len(platforms)} 个平台有新数据（共 {total_new} 条）")
            print(f"   耗时 {elapsed}s")
            print(f"   运行 python3 run_label_cron.py 开始标注")
        else:
            crawl_record["status"] = "failed"
            print(f"\n⚠️ 所有平台均未获取到新数据（{'返回码 ' + str(result.returncode) if not has_error_output else '运行输出含错误'}）")
            print(f"   ⚠️ 调度间隔已自动拉长，下次运行间隔更久")
            if result.stdout:
                last_lines = "\n".join(result.stdout.strip().splitlines()[-5:])
                print(f"   📋 MindSpider 最后输出:\n{last_lines}")

        _append_crawl_history(crawl_record)

    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(run())
