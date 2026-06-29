#!/usr/bin/env python3
"""测试 DeepInfra response_format json_object 模式"""
import asyncio, json, sys
sys.path.insert(0, '/Users/Admin1/VoxPop')
from config import settings
import httpx as async_httpx

SYSTEM = (
    "你是社会舆情分析专家。只输出 JSON，不要有其他文字。\n"
    '格式：{"has_profession": true/false, '
    '"professions": [{"name": "职业名", "sentiment": "positive|negative|neutral", '
    '"emotion": "str", "confidence": 0.0-1.0}], '
    '"topic": "议题或null", "brief": "一句话总结或null"}'
)
USER = (
    "分析这条评论：程序员这行太卷了，35岁就被优化。"
    "规则：只关心工作岗位，隐含指代要识别，职业名称标准化。"
)


async def main():
    async with async_httpx.AsyncClient(timeout=30, limits=async_httpx.Limits(max_connections=50)) as client:
        async def fire(idx):
            try:
                resp = await client.post(
                    f"{settings.LLM_BASE_URL}/chat/completions",
                    headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
                    json={
                        "model": settings.LLM_MODEL,
                        "messages": [
                            {"role": "system", "content": SYSTEM},
                            {"role": "user", "content": USER},
                        ],
                        "response_format": {"type": "json_object"},
                        "temperature": 0.1,
                        "max_tokens": 400,
                    },
                )
                data = resp.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                try:
                    parsed = json.loads(content)
                    ok = isinstance(parsed, dict) and "has_profession" in parsed
                    return (idx, ok, content[:120])
                except json.JSONDecodeError:
                    return (idx, False, f"JSON解析失败: {content[:80]}")
            except Exception as e:
                return (idx, False, f"异常: {type(e).__name__}: {str(e)[:60]}")

        tasks = [fire(i) for i in range(50)]
        results = await asyncio.gather(*tasks)

        ok = sum(1 for r in results if r[1])
        print(f"50 条并发 + response_format json_object:")
        print(f"  成功: {ok}/50 ({ok/50*100:.0f}%)")
        for r in results:
            if not r[1]:
                print(f"  ❌ {r[2]}")


asyncio.run(main())
