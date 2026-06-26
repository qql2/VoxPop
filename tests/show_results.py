#!/usr/bin/env python3
"""展示 DeepSeek 100条抽检的完整原文 + 标注结果"""
import asyncio, asyncpg, httpx, json, sys
sys.path.insert(0, '/Users/Admin1/VoxPop')
from config import settings

SP = (
    "你是社会舆情分析专家，专攻「全岗位态度盘点」。"
    "分析每条评论中涉及的工作岗位（职业/职位），以及对该岗位表达的态度。\n"
    "规则：\n"
    "1. 只关心「工作岗位/职业/职位」(如警察、老师、医生、程序员、公务员、外卖员……)\n"
    "2. 非工作岗位的对象(如公司、国家、个人、产品)不标记\n"
    "3. 隐含职业指代也要识别(如「穿制服的」→警察、「白大褂」→医生)\n"
    "4. 一条评论可能涉及多个职业，需独立标注\n"
    "5. 没有涉及任何岗位时 has_profession=false\n\n"
    "输出JSON格式，不加额外文字：\n"
    '{"has_profession":true/false,"professions":[{"name":"职业名","sentiment":"positive|negative|neutral","emotion":"...","confidence":0.0-1.0}],"topic":"社会议题或null","brief":"总结或null"}'
)

API_KEY = settings.LLM_API_KEY
API_URL = f"{settings.LLM_BASE_URL}/chat/completions"

async def call_deepseek(text, retries=3):
    for attempt in range(retries):
        if attempt > 0:
            await asyncio.sleep(0.5)
        async with httpx.AsyncClient(timeout=30) as c:
            try:
                r = await c.post(
                    API_URL,
                    headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
                    json={
                        "model": settings.LLM_MODEL,
                        "messages": [{"role": "system", "content": SP}, {"role": "user", "content": text[:800]}],
                        "temperature": 0.1, "max_tokens": 400,
                    },
                )
                if r.status_code != 200:
                    if attempt < retries - 1: continue
                    return {"error": f"HTTP {r.status_code}"}
                data = r.json()
                raw = data["choices"][0]["message"]["content"]
                clean = raw.strip()
                for p in ["```json", "```"]:
                    if clean.startswith(p): clean = clean[len(p):]
                if clean.endswith("```"): clean = clean[:-3]
                clean = clean.strip()
                if not clean:
                    if attempt < retries - 1: continue
                    return {"error": "empty"}
                return json.loads(clean)
            except (json.JSONDecodeError, httpx.TimeoutException, httpx.RequestError) as e:
                if attempt < retries - 1: continue
                return {"error": str(e)[:100]}
            except Exception as e:
                if attempt < retries - 1: continue
                return {"error": str(e)[:100]}
    return {"error": "max retries"}

async def main():
    conn = await asyncpg.connect(
        host=settings.DB_HOST, port=settings.DB_PORT,
        user=settings.DB_USER, password=settings.DB_PASSWORD,
        database=settings.DB_NAME,
    )
    n = 100
    rows = []
    for plat, table in [("weibo", "weibo_note_comment"), ("bilibili", "bilibili_video_comment"), ("xhs", "xhs_note_comment")]:
        per_plat = n // 3
        sql = f"""SELECT c.content, '{plat}' as platform FROM {table} c
                  WHERE length(c.content) > 3 ORDER BY random() LIMIT {per_plat}"""
        plat_rows = await conn.fetch(sql)
        rows = list(rows) + list(plat_rows)
    await conn.close()
    samples = [{"content": r["content"][:500], "platform": r["platform"]} for r in rows[:n]]

    print(f"DeepSeek V4-Flash 100条抽检 — 完整结果\n")

    results = []
    for i, s in enumerate(samples, 1):
        r = await call_deepseek(s["content"])
        has_prof = r.get("has_profession", False)
        profs = r.get("professions", [])
        error = r.get("error")

        results.append({
            "idx": i,
            "platform": s["platform"],
            "content": s["content"],
            "has_profession": has_prof,
            "professions": profs,
            "error": error,
        })

        icon = "❌" if error else ("💼" if has_prof else "  ")
        pstr = json.dumps(profs, ensure_ascii=False) if profs else "[]"
        print(f"[{i:3d}] {icon} [{s['platform']}]")
        print(f"    原文: {s['content']}")
        print(f"    标注: {pstr}")
        if error:
            print(f"    错误: {error}")
        print()

    # Summary
    prof_count = sum(1 for x in results if x["has_profession"])
    err_count = sum(1 for x in results if x["error"])
    print(f"=== 汇总 ===")
    print(f"总: {len(results)}, 有岗位: {prof_count}, 失败: {err_count}")
    print()
    print(f"--- 有岗位的 {prof_count} 条 ---")
    for x in results:
        if x["has_profession"]:
            pstr = json.dumps(x["professions"], ensure_ascii=False)
            print(f"[{x['idx']:3d}] [{x['platform']}] {pstr}")
            print(f"     {x['content']}")
            print()

if __name__ == "__main__":
    asyncio.run(main())
