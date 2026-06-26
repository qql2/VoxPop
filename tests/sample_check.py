#!/usr/bin/env python3
"""
抽检程序 — 对已标注数据随机抽样，用更强模型（DeepSeek）评估 Spark Lite 准确率

用法：
  python3 tests/sample_check.py                      # 默认抽 30 条
  python3 tests/sample_check.py --sample 50          # 抽 50 条
  python3 tests/sample_check.py --label-method llm   # 只抽 LLM 标注的
  python3 tests/sample_check.py --platform weibo     # 只抽某个平台
"""
import os, sys, json, asyncio, httpx, random, argparse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 从 VoxPop 的配置文件读 API Key
from config import settings

# 用 PackyAPI / DeepSeek 作为评审模型
JUDGE_API_KEY = settings.LLM_API_KEY
JUDGE_BASE_URL = settings.LLM_BASE_URL
JUDGE_MODEL = settings.LLM_MODEL  # deepseek-v4-flash

# 评审 prompt
JUDGE_SYSTEM_PROMPT = (
    "你是情感分析质检员。你将对一条社交媒体评论的情感标注结果进行评审。\n"
    "你要判断 Spark Lite 的标注是否准确，并给出自己的判断。\n"
    "只输出JSON。输出格式：\n"
    "{\"judge_sentiment\": \"positive|negative|neutral\", "
    "\"judge_emotion\": \"optimism|anxiety|anger|sarcasm|support|doubt|disappointment|indifference\", "
    "\"spark_correct\": true|false, "
    "\"confidence\": 0.0-1.0, "
    "\"reason\": \"一句话理由\"}"
)


async def fetch_samples(n: int = 30, platform: str = None, label_method: str = None) -> list:
    """从数据库随机抽样已标注的评论"""
    import asyncpg

    conn = await asyncpg.connect(
        host=settings.DB_HOST, port=settings.DB_PORT,
        user=settings.DB_USER, password=settings.DB_PASSWORD,
        database=settings.DB_NAME,
    )
    try:
        where = ["al.labeled_at IS NOT NULL"]
        if platform:
            where.append(f"al.source_platform = '{platform}'")
        if label_method:
            where.append(f"al.label_method = '{label_method}'")
        where_clause = " AND ".join(where)

        rows = []

        for plat, table in [('weibo', 'weibo_note_comment'), ('bilibili', 'bilibili_video_comment'), ('xhs', 'xhs_note_comment')]:
            if platform and plat != platform:
                continue
            need = n - len(rows)
            if need <= 0:
                break
            sql = f"""
                SELECT al.id as label_id, al.source_platform, al.source_id,
                       al.sentiment_polarity as spark_sentiment,
                       al.emotion_finegrained as spark_emotion,
                       al.attitude_tendency as spark_attitude,
                       al.confidence_score as spark_confidence,
                       al.label_method,
                       c.content
                FROM attitude_labels al
                LEFT JOIN {table} c ON al.source_id = c.id
                WHERE al.source_platform = '{plat}'
                  AND {where_clause}
                  AND c.content IS NOT NULL
                ORDER BY random() LIMIT {need}
            """
            try:
                plat_rows = await conn.fetch(sql)
                rows = list(rows) + list(plat_rows)
            except Exception as e:
                print(f"  ⚠️ {plat} 查询失败: {e}")

        return [
            {
                "label_id": r["label_id"],
                "platform": r["source_platform"],
                "spark_sentiment": r["spark_sentiment"],
                "spark_emotion": r["spark_emotion"],
                "spark_attitude": r["spark_attitude"],
                "spark_confidence": float(r["spark_confidence"]) if r["spark_confidence"] else None,
                "label_method": r["label_method"],
                "content": r["content"][:800],
            }
            for r in rows
        ]
    finally:
        await conn.close()


async def judge_one(sample: dict, idx: int) -> dict:
    """用 DeepSeek 评审一条标注"""
    content = (
        f"## 原始评论\n{sample['content']}\n\n"
        f"## Spark Lite 的标注\n"
        f"- 情感极性: {sample['spark_sentiment']}\n"
        f"- 细粒度情绪: {sample['spark_emotion']}\n"
        f"- 态度倾向: {sample['spark_attitude']}\n"
        f"- 置信度: {sample['spark_confidence']}\n\n"
        f"请评审这个标注是否准确，并给出你的判断。"
    )

    async with httpx.AsyncClient(timeout=30) as client:
        t0 = asyncio.get_event_loop().time()
        try:
            resp = await client.post(
                f"{JUDGE_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {JUDGE_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": JUDGE_MODEL,
                    "messages": [
                        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                        {"role": "user", "content": content},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 256,
                },
            )
            elapsed = asyncio.get_event_loop().time() - t0

            if resp.status_code != 200:
                return {**sample, "idx": idx, "error": f"HTTP {resp.status_code}", "judge_sentiment": None}

            data = resp.json()
            raw = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            # 清洗 JSON
            clean = raw.strip()
            if clean.startswith("```"):
                lines = clean.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                clean = "\n".join(lines).strip()

            parsed = json.loads(clean)
            spark_correct = parsed.get("spark_correct", False)

            return {
                **sample,
                "idx": idx,
                "judge_sentiment": parsed.get("judge_sentiment"),
                "judge_emotion": parsed.get("judge_emotion"),
                "spark_correct": spark_correct,
                "judge_confidence": parsed.get("confidence"),
                "judge_reason": parsed.get("reason", ""),
                "elapsed": round(elapsed, 2),
            }

        except Exception as e:
            return {**sample, "idx": idx, "error": str(e)[:200], "judge_sentiment": None}


async def main():
    parser = argparse.ArgumentParser(description="Spark Lite 标注抽检")
    parser.add_argument("--sample", type=int, default=30, help="抽检条数 (默认30)")
    parser.add_argument("--platform", type=str, choices=["weibo", "bilibili", "xhs"], help="限定平台")
    parser.add_argument("--label-method", type=str, choices=["llm", "model"], help="限定标注方式")
    parser.add_argument("--output", type=str, help="输出文件路径")
    args = parser.parse_args()

    print(f"🔍 Spark Lite 标注抽检")
    print(f"   评审模型: {JUDGE_MODEL}")
    print(f"   抽检数量: {args.sample}\n")

    # Step 1: 随机抽样
    print("Step 1/3: 从数据库随机抽取样本...")
    samples = await fetch_samples(
        n=args.sample,
        platform=args.platform,
        label_method=args.label_method,
    )
    if not samples:
        print("  ❌ 没有找到可抽检的数据")
        return
    print(f"  ✅ 抽取 {len(samples)} 条样本")
    plat_counts = {}
    for s in samples:
        p = s["platform"]
        plat_counts[p] = plat_counts.get(p, 0) + 1
    plat_str = ", ".join(f"{k}{v}条" for k, v in plat_counts.items())
    print(f"    平台分布: {plat_str}")

    # Step 2: 逐条评审
    print("\nStep 2/3: DeepSeek 逐条评审...")
    correct_count = 0
    total = 0
    sentiment_breakdown = {"correct": 0, "wrong": 0, "total": 0}

    for i, sample in enumerate(samples, 1):
        result = await judge_one(sample, i)
        content_preview = sample["content"][:40].replace("\n", " ")

        if result.get("judge_sentiment") is None:
            print(f"  [{i:2d}] ❌ 评审失败: {result.get('error','?')}")
            continue

        total += 1
        is_correct = result.get("spark_correct", False)
        if is_correct:
            correct_count += 1
            sentiment_breakdown["correct"] += 1
        else:
            sentiment_breakdown["wrong"] += 1
        sentiment_breakdown["total"] += 1

        verdict = "✅" if is_correct else "❌"
        print(f"  [{i:2d}] {verdict} Spark: {sample['spark_sentiment']} | Judge: {result['judge_sentiment']} | {content_preview}...")

    # Step 3: 报告生成
    print("\n" + "=" * 60)
    print("📊 抽检报告")
    print("=" * 60)

    accuracy = correct_count / total * 100 if total > 0 else 0
    print(f"\n  ✅ 总体准确率: {accuracy:.1f}% ({correct_count}/{total})")

    print(f"\n  📈 细项分析:")
    plat_counts = {}
    sent_counts = {}
    for s in samples:
        p = s["platform"]
        plat_counts[p] = plat_counts.get(p, 0) + 1
        sv = s["spark_sentiment"]
        sent_counts[sv] = sent_counts.get(sv, 0) + 1
    print(f"    平台分布：{', '.join(f'{k}: {v}' for k, v in plat_counts.items())}")
    print(f"    Spark Lite 情感分布：{', '.join(f'{k}: {v}' for k, v in sorted(sent_counts.items()))}")

    # 写入报告
    output_path = args.output or f"outputs/spotcheck_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    report = {
        "timestamp": datetime.now().isoformat(),
        "judge_model": JUDGE_MODEL,
        "total_samples": total,
        "correct_count": correct_count,
        "accuracy_pct": round(accuracy, 1),
        "details": samples[:10],  # 只存前10条详情避免文件过大
    }
    with open(output_path, "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n  📄 报告已保存: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
