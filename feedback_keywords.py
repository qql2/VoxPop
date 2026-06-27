#!/usr/bin/env python3
"""
VoxPop Feedback Loop — 将低样本职业作为爬虫关键词，喂给 MindSpider

用法：
  1. python3 feedback_keywords.py           # 输出低样本职业关键词
  2. python3 feedback_keywords.py --apply   # 写入 daily_topics 表
  3. 然后运行 MindSpider: python3 main.py --deep-sentiment --platforms zhihu

闭环：
  数据标注 → 发现低样本职业 → 作为关键词 → MindSpider 爬取 → 标注 → …
"""

import asyncio, json, os, sys
from datetime import date, datetime

DB_CONFIG = {
    "host": "127.0.0.1", "port": 5432,
    "user": "postgres", "password": "***",
    "database": "mindspider",
}

# professions.py 中定义的 22 种标准职业（作为基准）
STANDARD_PROFESSIONS = [
    "程序员", "产品经理", "运营", "设计师", "教师", "学生",
    "医生", "护士", "警察", "公务员", "金融从业者", "外卖员",
    "快递员", "网约车司机", "销售", "自媒体", "主播", "保姆",
    "保安", "军人", "律师", "农民",
]

async def get_profession_stats():
    """查询每个职业的 LLM 标注样本数"""
    conn = await asyncpg.connect(**DB_CONFIG)
    rows = await conn.fetch("""
        SELECT mentioned_profession, COUNT(*) as cnt
        FROM attitude_labels
        WHERE label_method = 'llm' AND mentioned_profession IS NOT NULL
        GROUP BY mentioned_profession
        ORDER BY cnt ASC
    """)
    await conn.close()
    return {r["mentioned_profession"]: r["cnt"] for r in rows}

async def insert_daily_topic(keywords: list):
    import asyncpg
    """将关键词写入 daily_topics 表，供 MindSpider 读取"""
    conn = await asyncpg.connect(**DB_CONFIG)
    topic_id = f"feedback_{date.today().isoformat()}"
    topic_name = "VoxPop 反馈闭环 — 低样本职业补充爬取"
    description = f"基于 VoxPop 标注结果，补充爬取样本量不足的职业。生成时间: {datetime.now().isoformat()}"
    keywords_json = json.dumps(keywords, ensure_ascii=False)
    now_ts = int(datetime.now().timestamp())
    
    try:
        await conn.execute("""
            INSERT INTO daily_topics (topic_id, topic_name, topic_description, keywords, extract_date, add_ts, last_modify_ts)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (topic_id) DO UPDATE SET
                keywords = $4, topic_description = $3, last_modify_ts = $7
        """, topic_id, topic_name, description, keywords_json, date.today(), now_ts, now_ts)
        print(f"✅ 已写入 daily_topics: topic_id={topic_id}")
        print(f"   关键词数: {len(keywords)}")
    finally:
        await conn.close()

async def main():
    import asyncpg
    
    conn = await asyncpg.connect(**DB_CONFIG)
    rows = await conn.fetch("""
        SELECT mentioned_profession, COUNT(*) as cnt
        FROM attitude_labels
        WHERE label_method = 'llm' AND mentioned_profession IS NOT NULL
        GROUP BY mentioned_profession
        ORDER BY cnt ASC
    """)
    await conn.close()
    
    stats = {r["mentioned_profession"]: r["cnt"] for r in rows}
    
    print("=" * 60)
    print("VoxPop 反馈闭环 — 低样本职业分析")
    print(f"数据库时间: {datetime.now().isoformat()}")
    print("=" * 60)
    
    # 1. 已存在的职业中样本不足的（< 10 条）
    low_sample = {k: v for k, v in stats.items() if v < 10}
    
    # 2. 标准职业中完全不存在的（0 条）
    missing = [p for p in STANDARD_PROFESSIONS if p not in stats]
    
    # 3. 已存在但样本极少的（< 3 条）
    very_low = {k: v for k, v in stats.items() if v < 3}
    
    print(f"\n📊 总计 {len(stats)} 个职业有 LLM 标注数据")
    print(f"  样本不足 (<10): {len(low_sample)} 个")
    print(f"  极少样本 (<3):  {len(very_low)} 个")
    print(f"  完全缺失:       {len(missing)} 个（标准职业中）")
    
    if low_sample:
        print(f"\n🟡 低样本职业 TOP20（最少→最多）:")
        for i, (prof, cnt) in enumerate(sorted(low_sample.items(), key=lambda x: x[1])[:20]):
            print(f"  {i+1:2d}. {prof:20s} → {cnt} 条")
    
    if missing:
        print(f"\n🔴 标准职业中完全缺失的:")
        for prof in missing:
            print(f"  - {prof}")
    
    # 生成关键词建议
    suggest_kw = []
    
    # 优先：缺失的标准职业
    suggest_kw.extend(missing)
    
    # 其次：极少样本的（<3）
    suggest_kw.extend(k for k in sorted(very_low.keys()))
    
    # 再次：样本不足但 ≥3 的（<10）
    for k in sorted(v for v in low_sample.keys() if v not in suggest_kw):
        if len(suggest_kw) < 30:
            suggest_kw.append(k)
    
    # 加上一些通用搜索后缀以提高命中率
    suffixes = [" 职业", " 工作", " 就业", " 现状", " 吐槽"]
    detailed_kw = suggest_kw[:15]  # 只对前15个加后缀
    for kw in detailed_kw:
        for suffix in suffixes:
            if len(suggest_kw) < 30:
                suggest_kw.append(f"{kw}{suffix}")
    
    suggest_kw = suggest_kw[:30]  # 最多 30 个关键词
    
    print(f"\n🎯 建议爬虫关键词（{len(suggest_kw)} 个）:")
    for i, kw in enumerate(suggest_kw):
        print(f"  {i+1:2d}. {kw}")
    
    print(f"\n关键词字符串（可直接复制到 base_config.py）:")
    print(f"  {','.join(suggest_kw)}")
    
    # --apply 参数：写入 daily_topics
    if "--apply" in sys.argv:
        await insert_daily_topic(suggest_kw)
        print(f"\n运行 MindSpider 爬取:")
        print(f"  cd ~/BettaFish/MindSpider")
        print(f"  python3 main.py --deep-sentiment --platforms zhihu")
    else:
        print(f"\n要写入 daily_topics 并触发爬取，加上 --apply 参数:")
        print(f"  python3 feedback_keywords.py --apply")

if __name__ == "__main__":
    asyncio.run(main())
