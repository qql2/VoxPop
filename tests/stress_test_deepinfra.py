#!/usr/bin/env python3
"""
DeepInfra 压力测试 — 梯度测试并发上限
找到 429 率最低的最高吞吐量
"""
import asyncio, time, json, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import httpx as async_httpx
from config import settings

TEST_PROMPT = "今天天气不错"  # 最短 prompt，减少 token 消耗
TEST_COUNT = 60  # 每轮测试请求数

RATES = [5, 10, 15, 20, 30, 40, 50, 60, 80, 100]  # 测试的并发级别


async def fire_one(client: async_httpx.AsyncClient, idx: int) -> dict:
    """发送单条请求，记录延迟和状态"""
    t0 = time.monotonic()
    try:
        resp = await client.post(
            f"{settings.LLM_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.LLM_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.LLM_MODEL,
                "messages": [{"role": "user", "content": TEST_PROMPT}],
                "max_tokens": 10,
                "temperature": 0,
            },
            timeout=30,
        )
        latency = time.monotonic() - t0
        return {
            "idx": idx,
            "status": resp.status_code,
            "latency": round(latency, 3),
            "body_preview": resp.text[:100] if resp.status_code != 200 else "",
        }
    except Exception as e:
        latency = time.monotonic() - t0
        return {
            "idx": idx,
            "status": 0,
            "latency": round(latency, 3),
            "error": str(e)[:80],
        }


async def test_concurrency(concurrency: int, count: int = TEST_COUNT) -> dict:
    """以指定并发数发送请求，统计结果"""
    limits = async_httpx.Limits(
        max_connections=concurrency + 10,
        max_keepalive_connections=concurrency,
    )
    sem = asyncio.Semaphore(concurrency)

    async def limited_fire(client, idx):
        async with sem:
            return await fire_one(client, idx)

    t0 = time.monotonic()
    async with async_httpx.AsyncClient(timeout=30, limits=limits) as client:
        tasks = [limited_fire(client, i) for i in range(count)]
        results = await asyncio.gather(*tasks)
    elapsed = time.monotonic() - t0

    statuses = {}
    latencies = []
    errors = []
    for r in results:
        s = r["status"]
        statuses[s] = statuses.get(s, 0) + 1
        latencies.append(r["latency"])
        if s == 429:
            errors.append(r)
        elif s != 200:
            errors.append(r)

    latencies.sort()
    n = len(latencies)
    return {
        "concurrency": concurrency,
        "total": count,
        "elapsed_s": round(elapsed, 1),
        "throughput": round(count / elapsed, 1),
        "statuses": statuses,
        "p50_latency": round(latencies[n // 2], 3) if n else 0,
        "p95_latency": round(latencies[int(n * 0.95)], 3) if n > 1 else latencies[0] if n else 0,
        "p99_latency": round(latencies[int(n * 0.99)], 3) if n > 2 else latencies[-1] if n else 0,
        "min_latency": round(latencies[0], 3) if n else 0,
        "max_latency": round(latencies[-1], 3) if n else 0,
    }


async def main():
    print(f"DeepInfra 压力测试")
    print(f"API: {settings.LLM_BASE_URL}")
    print(f"Model: {settings.LLM_MODEL}")
    print(f"每轮 {TEST_COUNT} 条请求\n")

    results = []
    for concurrency in RATES:
        print(f"测试并发={concurrency:>3} ... ", end="", flush=True)
        result = await test_concurrency(concurrency)
        s = result["statuses"]
        ok = s.get(200, 0)
        r429 = s.get(429, 0)
        other = sum(v for k, v in s.items() if k not in (200, 429))
        print(
            f"200={ok:>3}  429={r429:>3}  err={other:>2}  "
            f"吞吐={result['throughput']:>6.1f} req/s  "
            f"p50={result['p50_latency']:>6.3f}s"
        )
        results.append(result)
        if r429 > TEST_COUNT * 0.5:  # 超过 50% 429，不再往上测
            print(f"  → 429 率过高，停止递增测试")
            break
        await asyncio.sleep(2)  # 轮间冷却

    # 汇总
    print(f"\n{'='*70}")
    print(f"{'并发':>5} {'200':>5} {'429':>5} {'错误':>5} {'吞吐/s':>8} {'p50':>8} {'p95':>8} {'p99':>8}")
    print(f"{'-'*70}")
    for r in results:
        s = r["statuses"]
        print(
            f"{r['concurrency']:>5} "
            f"{s.get(200,0):>5} "
            f"{s.get(429,0):>5} "
            f"{sum(v for k,v in s.items() if k not in (200,429)):>5} "
            f"{r['throughput']:>8.1f} "
            f"{r['p50_latency']:>8.3f} "
            f"{r['p95_latency']:>8.3f} "
            f"{r['p99_latency']:>8.3f}"
        )

    # 推荐值
    best = max(
        [r for r in results if r["statuses"].get(429, 0) <= 2],
        key=lambda r: r["throughput"],
        default=None,
    )
    print(f"\n推荐: ", end="")
    if best:
        print(f"并发={best['concurrency']}, 吞吐={best['throughput']} req/s, p50={best['p50_latency']}s")
    else:
        # 取 429 最少且吞吐最高的
        best = min(results, key=lambda r: (r["statuses"].get(429, 0), -r["throughput"]))
        print(f"并发={best['concurrency']}, 吞吐={best['throughput']} req/s (有少量 429)")


if __name__ == "__main__":
    asyncio.run(main())
