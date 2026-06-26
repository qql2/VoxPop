#!/usr/bin/env python3
"""Debug: test DeepSeek API with a keyword-matched comment"""
import sys, json, httpx, asyncio

sys.path.insert(0, "/Users/Admin1/VoxPop")
from config import settings

API_KEY =settings.LLM_API_KEY

async def test():
    # Simple API test first
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(
            "https://www.packyapi.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "deepseek-v4-flash",
                "messages": [{"role": "user", "content": "说一句话测试"}],
                "temperature": 0.1,
                "max_tokens": 20,
            },
        )
        data = r.json()
        if "choices" in data:
            print(f"✅ API works: \"{data['choices'][0]['message']['content'][:50]}\"")
        else:
            print(f"❌ API error: {json.dumps(data)[:200]}")

asyncio.run(test())
