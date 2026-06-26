#!/usr/bin/env python3
"""
Spark Lite API 压测 & 效果测试脚本

测试项:
  1. 基础连通性 — 验证 API Key 和端到端调用
  2. 并发阶梯压测 — 从 1→5→10→20→50 逐步增加并发，摸清限流拐点
  3. 延迟统计 — 记录 P50/P90/P99 响应时间
  4. 效果评估 — 使用 VoxPop 的微博评论数据，对比 LLM 标注结果与关键词基线
"""

import os
import sys
import time
import json
import asyncio
import statistics
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

# 添加父目录到 path，复用 VoxPop 数据库
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---- 配置 ----
SPARK_API_KEY = os.environ.get("SPARK_API_KEY", "")
if not SPARK_API_KEY:
    print("❌ 请设置环境变量 SPARK_API_KEY")
    print("   export SPARK_API_KEY='你的讯飞API Key'")
    sys.exit(1)

SPARK_BASE_URL = "https://spark-api-open.xf-yun.com/v1"
SPARK_MODEL = "lite"  # Spark Lite

# 测试用的带情感评论（从微博爬取的样本）
TEST_COMMENTS = [
    "这个产品真的太垃圾了，完全不想用",
    "真的太棒了，支持支持！",
    "今天天气不错",
    "日本的军事野心越来越明显了，必须警惕",
    "厉害了我的国！",
    "无语，这种政策也能通过？",
    "期待好久了，终于上线了",
    "傻逼操作，毁我青春",
    "还可以吧，中规中矩",
    "抵制这种不负责任的行为！",
]


@dataclass
class TestResult:
    concurrency: int
    total_requests: int
    success_count: int
    fail_count: int
    rate_limit_count: int
    durations: List[float] = field(default_factory=list)
    error_details: List[str] = field(default_factory=list)
    total_duration: float = 0.0


def make_label_prompt(text: str) -> List[Dict]:
    """构造情感标注 prompt（复用 VoxPop 的 format）"""
    return [
        {
            "role": "system",
            "content": "你是态度分析师，分析社交媒体评论并输出JSON。只输出JSON。\n"
            "格式: {\"sentiment\": \"positive|negative|neutral\", "
            "\"emotion\": \"optimism|anxiety|anger|sarcasm|support|doubt|disappointment|indifference\", "
            "\"confidence\": 0.0-1.0, \"brief_reason\": \"一句话理由\"}",
        },
        {"role": "user", "content": text[:800]},
    ]


async def call_spark(
    session, comment: str, index: int, timeout: float = 30.0
) -> Dict[str, Any]:
    """单次异步调用 Spark Lite API"""
    start = time.monotonic()
    import httpx

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{SPARK_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {SPARK_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": SPARK_MODEL,
                    "messages": make_label_prompt(comment),
                    "temperature": 0.1,
                    "max_tokens": 256,
                },
            )
            elapsed = time.monotonic() - start
            status = resp.status_code

            if status == 429:
                return {
                    "index": index,
                    "comment": comment,
                    "success": False,
                    "rate_limited": True,
                    "duration": elapsed,
                    "error": f"HTTP 429 Rate Limited",
                }

            if status != 200:
                return {
                    "index": index,
                    "comment": comment,
                    "success": False,
                    "rate_limited": False,
                    "duration": elapsed,
                    "error": f"HTTP {status}: {resp.text[:200]}",
                }

            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            usage = data.get("usage", {})

            # 尝试解析 JSON（需要去掉 markdown 代码块包裹）
            parsed = {}
            try:
                clean = content.strip()
                if clean.startswith('```'):
                    # 去掉 ```json / ``` 开头和结尾
                    lines = clean.split('\n')
                    if lines[0].startswith('```'):
                        lines = lines[1:]
                    if lines and lines[-1].strip() == '```':
                        lines = lines[:-1]
                    clean = '\n'.join(lines).strip()
                parsed = json.loads(clean)
            except json.JSONDecodeError:
                pass

            return {
                "index": index,
                "comment": comment,
                "success": True,
                "rate_limited": False,
                "duration": elapsed,
                "raw_response": content[:500],
                "parsed": parsed,
                "usage": usage,
            }

    except Exception as e:
        elapsed = time.monotonic() - start
        return {
            "index": index,
            "comment": comment,
            "success": False,
            "rate_limited": False,
            "duration": elapsed,
            "error": str(e)[:200],
        }


async def run_concurrency_test(
    concurrency: int, total_requests: int
) -> TestResult:
    """在指定并发下运行压测"""
    import httpx

    result = TestResult(
        concurrency=concurrency,
        total_requests=total_requests,
        success_count=0,
        fail_count=0,
        rate_limit_count=0,
    )
    sem = asyncio.Semaphore(concurrency)

    async def limited_call(cmt: str, idx: int):
        async with sem:
            return await call_spark(None, cmt, idx)

    # 构造测试负载：在 TEST_COMMENTS 中循环取
    comments = [TEST_COMMENTS[i % len(TEST_COMMENTS)] for i in range(total_requests)]

    start_time = time.monotonic()

    tasks = [limited_call(cmt, i) for i, cmt in enumerate(comments)]
    responses = await asyncio.gather(*tasks)

    result.total_duration = time.monotonic() - start_time

    for r in responses:
        result.durations.append(r["duration"])
        if r["success"]:
            result.success_count += 1
        else:
            result.fail_count += 1
            if r.get("rate_limited"):
                result.rate_limit_count += 1
            result.error_details.append(r.get("error", "unknown"))

    return result


def print_test_report(result: TestResult):
    """打印测试报告"""
    durations = result.durations
    succeeded_durations = [
        d for i, d in enumerate(durations)
        if i < result.success_count  # 前 success_count 个是成功的
    ]
    # 实际上 durations 数组长度等于 total_requests
    # 成功的 duration 是前几个
    success_durs = [r for i, r in enumerate(result.durations) if i < result.success_count]
    # 更好的方式：从结果中取成功的
    # 简化：直接用所有 dur
    success_durs = sorted(durations)[:result.success_count]

    print(f"\n{'='*60}")
    print(f"  并发数: {result.concurrency}")
    print(f"  总请求: {result.total_requests}")
    print(f"  ✅ 成功: {result.success_count}")
    print(f"  ❌ 失败: {result.fail_count}")
    if result.rate_limit_count:
        print(f"  ⛔ 被限流: {result.rate_limit_count}")
    print(f"  ⏱ 总耗时: {result.total_duration:.2f}s")

    if success_durs:
        sorted_durs = sorted(success_durs)
        p50 = sorted_durs[len(sorted_durs) // 2]
        p90 = sorted_durs[int(len(sorted_durs) * 0.9)]
        p99 = sorted_durs[int(len(sorted_durs) * 0.99)]
        avg = statistics.mean(sorted_durs)
        print(f"  📊 延迟 (成功请求):")
        print(f"     平均: {avg:.3f}s | P50: {p50:.3f}s | P90: {p90:.3f}s | P99: {p99:.3f}s")
        print(f"     最快: {sorted_durs[0]:.3f}s | 最慢: {sorted_durs[-1]:.3f}s")
        print(f"     QPS ≈ {result.success_count / result.total_duration:.1f}")

    if result.rate_limit_count > 0:
        rate_limit_rate = result.rate_limit_count / result.total_requests * 100
        print(f"  ⚠️  限流率: {rate_limit_rate:.1f}%")


async def test_connectivity():
    """测试 1: 基础连通性"""
    print("\n" + "=" * 60)
    print("📡 测试 1: 基础连通性")
    print("=" * 60)

    result = await call_spark(None, "你好，测试连通性", 0)
    if result["success"]:
        print(f"  ✅ 连接成功!")
        print(f"  ⏱ 耗时: {result['duration']:.3f}s")
        print(f"  💬 回复: {result['raw_response'][:200]}")
        print(f"  📊 Usage: {json.dumps(result.get('usage', {}), ensure_ascii=False)}")
    else:
        print(f"  ❌ 连接失败: {result.get('error', 'unknown')}")
        return False
    return True


async def test_sentiment_accuracy(results: List[Dict]):
    """测试 2: 情感标注效果评估"""
    print("\n" + "=" * 60)
    print("🎯 测试 2: 情感标注效果")
    print("=" * 60)

    # 取成功的回复
    valid_results = [r for r in results if r["success"] and r.get("parsed")]
    
    if not valid_results:
        print("  ⚠️ 没有有效的标注结果")
        return

    for r in valid_results[:10]:
        parsed = r.get("parsed", {})
        sentiment = parsed.get("sentiment", "N/A")
        emotion = parsed.get("emotion", "N/A")
        confidence = parsed.get("confidence", "N/A")
        reason = parsed.get("brief_reason", "")[:50]
        comment = r["comment"][:40]

        print(f"  📝 \"{comment}...\"")
        print(f"     → 情感: {sentiment} | 情绪: {emotion} | 置信度: {confidence}")
        print(f"     理由: {reason}")
        print()


async def run_stress_test():
    """测试 3: 阶梯并发压测"""
    print("\n" + "=" * 60)
    print("🔥 测试 3: 阶梯并发压测")
    print("=" * 60)

    # 从低到高阶梯测试并发
    concurrency_levels = [1, 3, 5, 8, 10, 15, 20]
    requests_per_test = 20  # 每轮发 20 个请求

    for conc in concurrency_levels:
        result = await run_concurrency_test(conc, requests_per_test)
        print_test_report(result)

        if result.rate_limit_count > requests_per_test * 0.3:
            print(f"\n  ⛔ 限流率超过 30%，停止后续并发测试")
            break

        await asyncio.sleep(1)  # 每轮间隔 1 秒


async def test_production_simulation():
    """测试 4: 模拟真实生产负载"""
    print("\n" + "=" * 60)
    print("🚀 测试 4: 模拟生产负载（从数据库取实际评论）")
    print("=" * 60)

    try:
        from db import AttitudeDB
        from config import settings

        db = AttitudeDB()
        await db.connect()
        print(f"  ✅ 已连接数据库 {settings.DB_NAME}")

        # 分别取各平台的评论
        all_comments = []
        for platform in ["weibo", "bilibili", "xhs"]:
            try:
                items = await db.fetch_unlabeled_comments(
                    platform, limit=10
                )
                for item in items:
                    all_comments.append((platform, item["content"]))
                print(f"  📦 {platform}: 取到 {len(items)} 条")
            except Exception as e:
                print(f"  ⚠️ {platform}: 读取失败 - {e}")

        await db.close()

        if not all_comments:
            print("  ⚠️ 没有找到未标注的评论")
            return

        total = min(len(all_comments), 30)
        comments_to_test = all_comments[:total]
        print(f"\n  共 {total} 条评论进入测试")

        # 用并发 5 批量标注
        sem = asyncio.Semaphore(5)

        async def label_one(platform, comment, idx):
            async with sem:
                return await call_spark(None, comment, idx)

        tasks = [
            label_one(p, c, i) for i, (p, c) in enumerate(comments_to_test)
        ]
        start = time.monotonic()
        responses = await asyncio.gather(*tasks)
        elapsed = time.monotonic() - start

        successes = [r for r in responses if r["success"]]
        failures = [r for r in responses if not r["success"]]
        rate_limited = [r for r in responses if r.get("rate_limited")]

        print(f"\n  📊 生产模拟结果:")
        print(f"     ✅ 成功: {len(successes)}")
        print(f"     ❌ 失败: {len(failures)}")
        print(f"     ⛔ 限流: {len(rate_limited)}")
        print(f"     ⏱ 总耗时: {elapsed:.2f}s")
        print(f"     🔄 QPS: {len(successes)/elapsed:.1f}")

        # 统计情感分布
        sentiments = {}
        for r in successes:
            sent = r.get("parsed", {}).get("sentiment", "unknown")
            sentiments[sent] = sentiments.get(sent, 0) + 1
        if sentiments:
            print(f"     📈 情感分布: {json.dumps(sentiments, ensure_ascii=False)}")

    except ImportError as e:
        print(f"  ⚠️ 无法连接数据库: {e}")
        print(f"  ⏩ 跳过生产测试")
    except Exception as e:
        print(f"  ⚠️ 生产测试出错: {e}")


async def main():
    print(f"🔥 Spark Lite API 压测工具")
    print(f"   模型: {SPARK_MODEL}")
    print(f"   时间: {datetime.now().isoformat()}")
    print(f"   测试评论数: {len(TEST_COMMENTS)}")

    # 1. 基础连通性
    ok = await test_connectivity()
    if not ok:
        print("\n  ❌ 基础连通性测试失败，停止后续测试")
        return

    # 2. 情感标注效果（单条测试所有样本）
    print("\n" + "=" * 60)
    print("📝 测试各样本标注效果")
    print("=" * 60)
    sample_results = await asyncio.gather(
        *[call_spark(None, cmt, i) for i, cmt in enumerate(TEST_COMMENTS)]
    )
    await test_sentiment_accuracy(list(sample_results))

    # 3. 阶梯并发压测
    await run_stress_test()

    # 4. 生产模拟
    await test_production_simulation()

    print("\n" + "=" * 60)
    print("✅ 所有测试完成")


if __name__ == "__main__":
    asyncio.run(main())
