#!/usr/bin/env python3
"""
全岗位态度盘点 — DeepSeek V4-Flash 效果抽检（100条）
从数据库随机抽取 100 条评论，用 DeepSeek 标注后，
自动分析命中率、情感分布、多职业检出率等指标。
"""
import sys, os, json, asyncio, httpx
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

SPARK_API_KEY = settings.LLM_API_KEY
SPARK_BASE_URL = settings.LLM_BASE_URL
SPARK_MODEL = settings.LLM_MODEL

SYSTEM_PROMPT = (
    "你是社会舆情分析专家，专攻「全岗位态度盘点」。"
    "分析每条评论中涉及的工作岗位（职业/职位），以及对该岗位表达的态度。\n"
    "规则：\n"
    "1. 只关心「工作岗位/职业/职位」(如警察、老师、医生、程序员、公务员、外卖员……)\n"
    "2. 非工作岗位的对象(如公司、国家、个人、产品)不标记\n"
    "3. 隐含职业指代也要识别(如「穿制服的」→警察、「白大褂」→医生)\n"
    "4. 一条评论可能涉及多个职业，需独立标注\n"
    "5. 没有涉及任何岗位时 has_profession=false\n\n"
    "输出JSON格式，不加额外文字：\n"
    "{\"has_profession\":true/false,\"professions\":[{\"name\":\"职业名\",\"sentiment\":\"positive|negative|neutral\",\"emotion\":\"...\",\"confidence\":0.0-1.0}],\"topic\":\"社会议题或null\",\"brief\":\"总结或null\"}"
)


async def call_deepseek(text, retries=3):
    for attempt in range(retries):
        if attempt > 0:
            await asyncio.sleep(0.5)
        async with httpx.AsyncClient(timeout=30) as c:
            try:
                r = await c.post(
                    f"{SPARK_BASE_URL}/chat/completions",
                    headers={"Authorization": f"Bearer {SPARK_API_KEY}", "Content-Type": "application/json"},
                    json={
                        "model": SPARK_MODEL,
                        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": text[:800]}],
                        "temperature": 0.1,
                        "max_tokens": 400,
                    },
                )
                if r.status_code != 200:
                    if attempt < retries - 1:
                        continue
                    return {"error": f"HTTP {r.status_code}"}
                data = r.json()
                raw = data["choices"][0]["message"]["content"]
                clean = raw.strip()
                if clean.startswith("```json"):
                    clean = clean[7:]
                elif clean.startswith("```"):
                    clean = clean[3:]
                if clean.endswith("```"):
                    clean = clean[:-3]
                clean = clean.strip()
                if not clean:
                    if attempt < retries - 1:
                        continue
                    return {"error": "empty"}
                return json.loads(clean)
            except (json.JSONDecodeError, httpx.TimeoutException, httpx.RequestError) as e:
                if attempt < retries - 1:
                    continue
                return {"error": str(e)[:100]}
            except Exception as e:
                if attempt < retries - 1:
                    continue
                return {"error": str(e)[:100]}
    return {"error": "max retries"}


async def fetch_samples(n=100):
    import asyncpg
    conn = await asyncpg.connect(
        host=settings.DB_HOST, port=settings.DB_PORT,
        user=settings.DB_USER, password=settings.DB_PASSWORD,
        database=settings.DB_NAME,
    )
    try:
        # 从三个平台按比例随机抽取
        rows = []
        for plat, table in [("weibo", "weibo_note_comment"), ("bilibili", "bilibili_video_comment"), ("xhs", "xhs_note_comment")]:
            per_plat = n // 3
            sql = f"""SELECT c.content, '{plat}' as platform
                      FROM {table} c
                      WHERE length(c.content) > 3
                      ORDER BY random() LIMIT {per_plat}"""
            plat_rows = await conn.fetch(sql)
            rows = list(rows) + list(plat_rows)
        return [{"content": r["content"][:500], "platform": r["platform"]} for r in rows[:n]]
    finally:
        await conn.close()


async def main():
    n = 100
    print(f"🔍 DeepSeek V4-Flash 100条抽检\n")

    # 1. 抽样本
    print("Step 1: 抽取 100 条评论...")
    samples = await fetch_samples(n)
    print(f"  平台: weibo={sum(1 for s in samples if s['platform']=='weibo')} "
          f"bilibili={sum(1 for s in samples if s['platform']=='bilibili')} "
          f"xhs={sum(1 for s in samples if s['platform']=='xhs')}\n")

    # 2. 标注
    print("Step 2: DeepSeek 标注中...")
    results = []
    for i, s in enumerate(samples, 1):
        r = await call_deepseek(s["content"])
        has_prof = r.get("has_profession", False)
        profs = r.get("professions", [])
        prof_names = [p["name"] for p in profs if isinstance(p, dict) and "name" in p]
        sentiments = [p["sentiment"] for p in profs if isinstance(p, dict) and "sentiment" in p]
        error = r.get("error")

        results.append({
            "idx": i,
            "content": s["content"][:35],
            "platform": s["platform"],
            "has_profession": has_prof,
            "prof_names": prof_names,
            "sentiments": sentiments,
            "error": error,
        })

        if error:
            icon = "❌"
        elif has_prof:
            icon = "💼"
        else:
            icon = "  "
        print(f"  [{i:3d}] {icon} {'|'.join([f'{n}({s})' for n,s in zip(prof_names,sentiments)]) if prof_names else '(无岗位)'} | {s['content'][:30]}...{s['platform'][:3]}")

    # 3. 统计
    print(f"\n{'='*60}")
    print("📊 抽检统计")
    print("="*60)

    errors = [r for r in results if r["error"]]
    prof_comments = [r for r in results if r["has_profession"]]
    no_prof = [r for r in results if not r["has_profession"] and not r["error"]]

    print(f"\n  总样本: {len(results)}")
    print(f"  ❌ 调用失败: {len(errors)}")
    print(f"  💼 涉及岗位: {len(prof_comments)} ({len(prof_comments)*100//len(results)}%)")
    print(f"  ⭕ 无岗位: {len(no_prof)} ({len(no_prof)*100//len(results)}%)")

    # 多职业检出
    multi = [r for r in prof_comments if len(r["prof_names"]) > 1]
    single = [r for r in prof_comments if len(r["prof_names"]) == 1]
    print(f"\n  📈 职业检出详情:")
    print(f"     单职业: {len(single)} 条")
    print(f"     多职业: {len(multi)} 条")
    if multi:
        print(f"     多职业示例:")
        for m in multi[:3]:
            profs_str = ", ".join([f"{n}({s})" for n, s in zip(m["prof_names"], m["sentiments"])])
            print(f"       · {m['content'][:35]}... → {profs_str}")

    # 情感分布
    all_sentiments = []
    for r in prof_comments:
        all_sentiments.extend(r["sentiments"])
    if all_sentiments:
        pos = all_sentiments.count("positive")
        neg = all_sentiments.count("negative")
        neu = all_sentiments.count("neutral")
        print(f"\n  🎯 岗位情感分布 ({len(all_sentiments)} 条标注):")
        print(f"     积极: {pos} ({pos*100//len(all_sentiments)}%)")
        print(f"     消极: {neg} ({neg*100//len(all_sentiments)}%)")
        print(f"     中性: {neu} ({neu*100//len(all_sentiments)}%)")

    # 职业名称统计
    all_profs = {}
    for r in prof_comments:
        for n, s in zip(r["prof_names"], r["sentiments"]):
            if n not in all_profs:
                all_profs[n] = {"total": 0, "positive": 0, "negative": 0, "neutral": 0}
            all_profs[n]["total"] += 1
            all_profs[n][s] = all_profs[n].get(s, 0) + 1

    if all_profs:
        print(f"\n  📋 涉及岗位列表:")
        for name, stat in sorted(all_profs.items(), key=lambda x: -x[1]["total"]):
            print(f"     {name}: {stat['total']}次 (正{stat['positive']}/负{stat['negative']}/中{stat['neutral']})")

    # 按平台分析
    print(f"\n  🌐 各平台岗位覆盖率:")
    for plat_name in ["weibo", "bilibili", "xhs"]:
        plat_results = [r for r in results if r["platform"] == plat_name]
        plat_prof = [r for r in plat_results if r["has_profession"]]
        plat_total = len(plat_results)
        if plat_total:
            print(f"     {plat_name}: {len(plat_prof)}/{plat_total} 有岗位 ({len(plat_prof)*100//plat_total}%)")


if __name__ == "__main__":
    asyncio.run(main())
