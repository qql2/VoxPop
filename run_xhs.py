#!/usr/bin/env python3
"""跑小红书标注（分批次，每次 100 条）"""
import sys, os, json, asyncio, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings
from labeler import cascade_label, generate_batch_id
import asyncpg
from db import AttitudeDB

BATCH_SIZE = 100


async def main():
    conn = await asyncpg.connect(
        host=settings.DB_HOST, port=settings.DB_PORT,
        user=settings.DB_USER, password=settings.DB_PASSWORD,
        database=settings.DB_NAME,
    )
    try:
        # 获取未标注的小红书评论
        rows = await conn.fetch("""
            SELECT c.id, c.content
            FROM xhs_note_comment c
            LEFT JOIN attitude_labels al
                ON al.source_platform = 'xhs' AND al.source_type = 'comment' AND al.source_id = c.id
            WHERE al.id IS NULL
              AND c.content IS NOT NULL AND length(trim(c.content)) > 0
            ORDER BY c.id
        """)
        total = len(rows)
        print(f"小红书待标注: {total} 条\n")

        batch_id = generate_batch_id()
        total_llm = 0
        total_skip = 0

        for start in range(0, total, BATCH_SIZE):
            batch = rows[start:start + BATCH_SIZE]
            batch_llm = 0
            batch_skip = 0

            for i, r in enumerate(batch):
                cid, content = r["id"], r["content"]
                try:
                    label = cascade_label(content)
                    is_llm = label.get("label_method") == "llm"
                    if is_llm:
                        batch_llm += 1
                    else:
                        batch_skip += 1

                    # 写入 DB
                    label.update({
                        "source_platform": "xhs",
                        "source_type": "comment",
                        "source_id": cid,
                        "parent_id": None,
                        "add_ts": None,
                        "batch_id": batch_id,
                        "labeled_at": None,
                    })

                    
                    db = AttitudeDB()
                    await db.connect()
                    await db.insert_labels([label])
                    await db.close()

                except Exception as e:
                    print(f"  ❌ ID {cid}: {str(e)[:60]}")

                if (i + 1) % 10 == 0:
                    done = start + i + 1
                    print(f"  [{done}/{total}] LLM:{total_llm + batch_llm} 本地:{total_skip + batch_skip}", flush=True)

            total_llm += batch_llm
            total_skip += batch_skip
            print(f"  批次完成 [{start + len(batch)}/{total}] LLM:{total_llm} 本地:{total_skip}", flush=True)

        print(f"\n✅ 小红书完成！LLM:{total_llm} 本地:{total_skip} 共 {total}")

        # 重新跑排行
        
        from datetime import date
        db = AttitudeDB()
        await db.connect()
        await db.compute_rankings(date.today())
        await db.close()
        print("✅ 排行重新聚合完成")

        from reporter import generate_ranking_report
        await generate_ranking_report(date.today())
        print("✅ 报告重新生成")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
