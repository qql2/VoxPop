#!/usr/bin/env python3
"""
用 DeepSeek 为每个职业生成全面的网络用语同义词词典
"""
import os, sys, json, asyncio, httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

API_KEY = settings.LLM_API_KEY
BASE_URL = settings.LLM_BASE_URL
MODEL = settings.LLM_MODEL

# 现有职业，让 DeepSeek 帮助扩展
PROFESSIONS = [
    "程序员", "产品经理", "运营", "设计师",
    "教师", "学生",
    "医生", "护士",
    "警察", "公务员",
    "金融从业者",
    "外卖员", "快递员", "网约车司机",
    "销售", "客服",
    "自媒体", "演员/艺人", "主播",
    "农民工", "保姆/家政", "保安",
    "军人", "律师", "农民",
]


async def expand_keywords(profession: str) -> list:
    prompt = (
        f"你是中文网络用语专家。请为职业「{profession}」生成一份全面的关键词列表。\n\n"
        "要求：\n"
        "1. 包括直接的职业名称\n"
        "2. 包括网络用语、俚语、黑话（如程序员→码农/程序猿/格子衫）\n"
        "3. 包括隐含指代（如医生→白大褂、警察→穿制服的）\n"
        "4. 包括相关活动描述（如教师→备课/批作业/家访）\n"
        "5. 包括相关场景/物品（如程序员→996/秃头/改bug）\n"
        "6. 包括社会调侃用语（如公务员→铁饭碗/上岸）\n"
        "7. 越多越好，覆盖各种表达方式\n\n"
        "只输出JSON数组，不要其他内容。如：[\"关键词1\",\"关键词2\",\"关键词3\"]"
    )

    async with httpx.AsyncClient(timeout=30) as c:
        try:
            r = await c.post(
                f"{BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": MODEL,
                    "messages": [
                        {"role": "system", "content": "你是中文网络用语专家。输出JSON数组，不加额外文字。"},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 500,
                },
            )
            raw = r.json()["choices"][0]["message"]["content"]
            clean = raw.strip()
            if clean.startswith("```json"):
                clean = clean[7:]
            elif clean.startswith("```"):
                clean = clean[3:]
            if clean.endswith("```"):
                clean = clean[:-3]
            return json.loads(clean)
        except Exception as e:
            print(f"  ❌ {profession}: {e}")
            return []


async def main():
    print(f"🔍 用 {MODEL} 为 {len(PROFESSIONS)} 种职业扩充同义词\n")

    all_keywords = {}
    total_original = 0
    total_new = 0

    for i, prof in enumerate(PROFESSIONS, 1):
        print(f"[{i:2d}/{len(PROFESSIONS)}] {prof}...", end=" ", flush=True)
        kw = await expand_keywords(prof)
        all_keywords[prof] = kw
        print(f"{len(kw)} 个关键词")
        total_new += len(kw)

    # 输出
    print(f"\n{'='*60}")
    print(f"📊 共生成 {total_new} 个关键词，分布在 {len(PROFESSIONS)} 种职业")
    print(f"{'='*60}\n")

    for prof, kws in all_keywords.items():
        print(f"# {prof}")
        print(f"PROFESSION_KEYWORDS[\"{prof}\"] = {json.dumps(kws, ensure_ascii=False, indent=2)}")
        print()

    # 去重检查
    all_values = []
    for kws in all_keywords.values():
        all_values.extend(kws)
    dupes = set(k for k in all_values if all_values.count(k) > 1)
    if dupes:
        print(f"⚠️ 跨职业重复关键词: {dupes}")


if __name__ == "__main__":
    asyncio.run(main())
