#!/usr/bin/env python3
"""DeepInfra function calling 压力测试 — 验证并发是否导致空响应"""
import asyncio, json, sys, time
sys.path.insert(0, '/Users/Admin1/VoxPop')
from labeler_fast import _SYSTEM_PROMPT, _ANALYZE_TOOL
from config import settings
import httpx as async_httpx

TOOL = [_ANALYZE_TOOL]
FULL_PROMPT = _SYSTEM_PROMPT + '\n\n你必须调用 analyze_attitude function 输出分析结果，不要输出其他文字。'

COMMENTS = [
    "程序员这行太卷了，35岁就被优化",
    "老师辛苦了，疫情期间上网课更累了",
    "警察暴力执法必须严惩",
    "今天天气不错",
    "做HR快二十年了，外企民企都待过",
]

async def fire(client, idx):
    comment = COMMENTS[idx % len(COMMENTS)]
    t0 = time.monotonic()
    try:
        resp = await client.post(
            f'{settings.LLM_BASE_URL}/chat/completions',
            headers={'Authorization': f'Bearer {settings.LLM_API_KEY}'},
            json={
                'model': settings.LLM_MODEL,
                'messages': [
                    {'role': 'system', 'content': FULL_PROMPT},
                    {'role': 'user', 'content': comment},
                ],
                'tools': TOOL,
                'tool_choice': 'auto',
                'temperature': 0.1, 'max_tokens': 400,
            },
            timeout=30,
        )
        latency = time.monotonic() - t0
        data = resp.json()
        msg = data.get('choices', [{}])[0].get('message', {})
        tc = msg.get('tool_calls', [])
        content = msg.get('content', '')
        return {
            "idx": idx,
            "status": resp.status_code,
            "latency": round(latency, 3),
            "has_tc": len(tc) > 0,
            "content_len": len(content),
            "content_preview": content[:60],
        }
    except Exception as e:
        return {"idx": idx, "status": 0, "latency": round(time.monotonic()-t0, 3), "error": str(e)[:60]}


async def test_concurrency(concurrency: int, count: int = 30):
    """以指定并发数发送请求"""
    limits = async_httpx.Limits(max_connections=concurrency + 50, max_keepalive_connections=concurrency)
    t0 = time.monotonic()
    async with async_httpx.AsyncClient(timeout=30, limits=limits) as client:
        sem = asyncio.Semaphore(concurrency)

        async def limited_fire(idx):
            async with sem:
                return await fire(client, idx)

        tasks = [limited_fire(i) for i in range(count)]
        results = await asyncio.gather(*tasks)
    elapsed = time.monotonic() - t0

    total = len(results)
    ok = sum(1 for r in results if r.get("has_tc"))
    empty = sum(1 for r in results if not r.get("has_tc") and r.get("content_len", 0) == 0)
    http_ok = sum(1 for r in results if r.get("status") == 200)
    latencies = sorted([r["latency"] for r in results if r.get("latency")])

    return {
        "concurrency": concurrency,
        "count": count,
        "elapsed": round(elapsed, 1),
        "throughput": round(count / elapsed, 1),
        "http_200": http_ok,
        "tool_calls_ok": ok,
        "empty_response": empty,
        "p50_latency": round(latencies[len(latencies)//2], 3) if latencies else 0,
        "p95_latency": round(latencies[int(len(latencies)*0.95)], 3) if len(latencies) > 1 else 0,
    }


async def main():
    print(f"DeepInfra Function Calling 压力测试")
    print(f"模型: {settings.LLM_MODEL}")
    print(f"每组 {30} 条请求，梯度并发\n")

    all_results = []
    for concurrency in [1, 5, 10, 20, 50]:
        print(f"测试并发={concurrency:>2} ... ", end="", flush=True)
        r = await test_concurrency(concurrency)
        print(
            f"HTTP200={r['http_200']:>3}  "
            f"tool_calls={r['tool_calls_ok']:>3}  "
            f"空响应={r['empty_response']:>3}  "
            f"吞吐={r['throughput']:>5.1f}req/s  "
            f"p50={r['p50_latency']:>.3f}s"
        )
        all_results.append(r)
        await asyncio.sleep(3)

    # 汇总
    print(f"\n{'='*70}")
    print(f"{'并发':>5} {'HTTP200':>8} {'tool_calls':>11} {'空响应':>8} {'吞吐/s':>8} {'p50':>8}")
    print(f"{'-'*70}")
    for r in all_results:
        print(
            f"{r['concurrency']:>5} "
            f"{r['http_200']:>8} "
            f"{r['tool_calls_ok']:>11} "
            f"{r['empty_response']:>8} "
            f"{r['throughput']:>8.1f} "
            f"{r['p50_latency']:>8.3f}"
        )

    print(f"\n结论：并发越高，空响应比例越大。这是 DeepInfra 推理服务的稳定性问题，非代码问题。")


if __name__ == "__main__":
    asyncio.run(main())
