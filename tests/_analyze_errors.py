#!/usr/bin/env python3
"""分析 error 标签的 raw_response，分类 LLM 出错模式"""
import asyncio, asyncpg
from collections import Counter

async def main():
    conn = await asyncpg.connect(
        host="127.0.0.1", port=5432,
        user="postgres", password="postgres",
        database="mindspider",
    )
    rows = await conn.fetch("""
        SELECT raw_response FROM attitude_labels
        WHERE label_method='error' AND raw_response IS NOT NULL AND raw_response != ''
        ORDER BY id DESC LIMIT 30
    """)
    await conn.close()

    cats = Counter()
    for r in rows:
        t = r["raw_response"]
        if "```" in t or "def " in t or "import " in t:
            cats["写代码"] += 1
            tag = "CODE"
        elif "请提供" in t or "请输入" in t or "请给出" in t:
            cats["反问/请提供评论"] += 1
            tag = "ASK"
        elif "我理解" in t or "我明白" in t or "你的意思" in t:
            cats["跑题对话"] += 1
            tag = "TALK"
        elif "是指" in t or "包括" in t or "以下" in t or "是一个" in t:
            cats["解释说明"] += 1
            tag = "EXPLAIN"
        else:
            cats["其他"] += 1
            tag = "OTHER"
        print(f"[{tag}] {t[:150]}")

    print(f"\n分类统计: {dict(cats)}")

asyncio.run(main())
