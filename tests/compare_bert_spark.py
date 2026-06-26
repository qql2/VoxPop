#!/usr/bin/env python3
"""
三端情感标注对比抽检：BERT vs Spark Lite vs DeepSeek(评审)

流程：
  1. 从数据库随机抽检 N 条评论
  2. 分别用 BERT 模型和 Spark Lite 标注
  3. 用 DeepSeek 作为评审，判断两者谁更准
  4. 输出对比报告
"""
import os, sys, json, asyncio, httpx, argparse, warnings
from datetime import datetime
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---- API & DB 配置 ----
from config import settings

SPARK_API_KEY = settings.SPARK_API_KEY
SPARK_BASE_URL = settings.SPARK_BASE_URL
SPARK_MODEL = settings.SPARK_MODEL

JUDGE_API_KEY = settings.LLM_API_KEY
JUDGE_BASE_URL = settings.LLM_BASE_URL
JUDGE_MODEL = settings.LLM_MODEL

# ---- BERT 模型（懒加载） ----
_bert_model = None
_bert_tokenizer = None


def get_bert_model():
    global _bert_model, _bert_tokenizer
    if _bert_model is None:
        import torch
        from transformers import AutoTokenizer, AutoModelForSequenceClassification

        model_name = "wsqstar/GISchat-weibo-100k-fine-tuned-bert"
        print("  加载 BERT 微博情感模型...")
        _bert_tokenizer = AutoTokenizer.from_pretrained(model_name)
        _bert_model = AutoModelForSequenceClassification.from_pretrained(model_name)
        _bert_model.eval()
    return _bert_model, _bert_tokenizer


def bert_predict(text: str) -> dict:
    """BERT 预测，带置信度阈值判断中性"""
    import torch
    model, tokenizer = get_bert_model()
    inputs = tokenizer(text[:512], max_length=512, truncation=True, return_tensors="pt")
    for k, v in inputs.items():
        if isinstance(v, torch.Tensor):
            inputs[k] = v.to(torch.device("cpu"))

    with torch.no_grad():
        outputs = model(**inputs)
        probs = torch.softmax(outputs.logits, dim=1)
        conf_positive = probs[0][1].item()
        conf_negative = probs[0][0].item()

    if conf_positive > 0.8:
        return {"sentiment": "positive", "confidence": conf_positive}
    elif conf_negative > 0.8:
        return {"sentiment": "negative", "confidence": conf_negative}
    else:
        return {"sentiment": "neutral", "confidence": max(conf_positive, conf_negative)}


async def spark_predict(text: str) -> dict:
    """Spark Lite 预测"""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{SPARK_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {SPARK_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": SPARK_MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": "你是舆情分析师。分析评论的情感极性(positive|negative|neutral)、情绪和态度。只输出JSON。"
                        '格式: {"sentiment":"positive|negative|neutral","emotion":"...","attitude_tendency":"support|oppose|neutral","confidence":0.0-1.0}',
                    },
                    {"role": "user", "content": text[:800]},
                ],
                "temperature": 0.1,
                "max_tokens": 200,
            },
        )
        data = resp.json()
        raw = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        clean = raw.strip()
        if clean.startswith("```"):
            lines = clean.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            clean = "\n".join(lines).strip()
        try:
            parsed = json.loads(clean)
            return {
                "sentiment": parsed.get("sentiment", "unknown"),
                "confidence": parsed.get("confidence", 0.0),
            }
        except:
            return {"sentiment": "parse_error", "confidence": 0.0}


async def judge(sample: dict, bert_s: str, spark_s: str) -> dict:
    """用 DeepSeek 评审 BERT vs Spark Lite"""
    prompt = (
        f"## 原始评论\n{sample['content'][:500]}\n\n"
        f"## 标注对比\n"
        f"- A. BERT模型: {bert_s}\n"
        f"- B. Spark Lite: {spark_s}\n\n"
        f"请判断哪个标注更准确，并给出你认为的正确情感。\n"
        f"只输出JSON。格式: {{\"correct_sentiment\":\"positive|negative|neutral\","
        f"\"better\":\"bert\"|\"spark\"|\"both_wrong\",\"reason\":\"一句话理由\"}}"
    )

    async with httpx.AsyncClient(timeout=30) as client:
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
                        {
                            "role": "system",
                            "content": "你是情感分析质检员，评审两条标注并判断哪条更准。只输出JSON。",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 200,
                },
            )
            data = resp.json()
            raw = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            clean = raw.strip()
            if clean.startswith("```"):
                lines = clean.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                clean = "\n".join(lines).strip()
            parsed = json.loads(clean)
            return {
                "correct": parsed.get("correct_sentiment", "unknown"),
                "better": parsed.get("better", "tie"),
                "reason": parsed.get("reason", ""),
            }
        except Exception as e:
            return {"correct": "error", "better": "error", "reason": str(e)[:100]}


async def fetch_samples(n: int) -> list:
    """从 DB 随机抽检"""
    import asyncpg
    conn = await asyncpg.connect(
        host=settings.DB_HOST, port=settings.DB_PORT,
        user=settings.DB_USER, password=settings.DB_PASSWORD,
        database=settings.DB_NAME,
    )
    try:
        rows = []
        for plat, table in [("weibo", "weibo_note_comment")]:
            sql = f"""
                SELECT al.id as label_id, al.source_platform,
                       c.content
                FROM attitude_labels al
                LEFT JOIN {table} c ON al.source_id = c.id
                WHERE al.source_platform = '{plat}'
                  AND c.content IS NOT NULL
                  AND length(c.content) > 5
                ORDER BY random() LIMIT {n}
            """
            plat_rows = await conn.fetch(sql)
            rows = list(rows) + list(plat_rows)
            if len(rows) >= n:
                break
        return [
            {"content": r["content"][:600], "platform": r["source_platform"]}
            for r in rows[:n]
        ]
    finally:
        await conn.close()


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=30)
    args = parser.parse_args()

    print("=" * 70)
    print("🔬 BERT vs Spark Lite 情感标注对比抽检")
    print(f"   评审模型: {JUDGE_MODEL}")
    print(f"   抽检数量: {args.sample}")
    print("=" * 70)

    # Step 1: 取样本
    print("\nStep 1/3: 随机抽检评论...")
    samples = await fetch_samples(args.sample)
    print(f"  ✅ 获取 {len(samples)} 条样\n")

    # Step 2: 分别标注
    print("Step 2/3: BERT + Spark Lite 分别标注...")
    results = []
    for i, s in enumerate(samples):
        # BERT
        bert_r = bert_predict(s["content"])
        # Spark
        spark_r = await spark_predict(s["content"])

        # 评审
        judge_r = await judge(s, bert_r["sentiment"], spark_r["sentiment"])

        results.append({
            "idx": i + 1,
            "content": s["content"][:40],
            "bert": bert_r["sentiment"],
            "bert_conf": round(bert_r["confidence"], 3),
            "spark": spark_r["sentiment"],
            "spark_conf": round(spark_r["confidence"], 3),
            "judge": judge_r["correct"],
            "better": judge_r["better"],
            "reason": judge_r["reason"][:40],
        })

        # 逐条打印
        text_preview = s["content"][:35].replace("\n", " ")
        verdict = "✅" if judge_r["better"] != "error" else "⚠️"
        print(
            f"  [{i+1:2d}] {verdict} B:{bert_r['sentiment']:<8} "
            f"| S:{spark_r['sentiment']:<10} "
            f"| 正确:{judge_r['correct']:<8} | 更好:{judge_r['better']:<10}"
        )

    # Step 3: 统计
    print("\n" + "=" * 70)
    print("📊 对比统计")
    print("=" * 70)

    valid = [r for r in results if r["better"] != "error"]
    total = len(valid)

    bert_wins = sum(1 for r in valid if r["better"] == "bert")
    spark_wins = sum(1 for r in valid if r["better"] == "spark")
    both_wrong = sum(1 for r in valid if r["better"] == "both_wrong")

    print(f"\n  有效评审: {total}/{len(results)}")
    print(f"\n  ✅ BERT 胜出: {bert_wins} ({bert_wins*100//total}%)")
    print(f"  ✅ Spark Lite 胜出: {spark_wins} ({spark_wins*100//total}%)")
    print(f"  ❌ 两者都错: {both_wrong} ({both_wrong*100//total}%)")

    # 分情感统计 BERT 的分布
    bert_dist = {}
    spark_dist = {}
    judge_dist = {}
    for r in results:
        bert_dist[r["bert"]] = bert_dist.get(r["bert"], 0) + 1
        spark_dist[r["spark"]] = spark_dist.get(r["spark"], 0) + 1
        judge_dist[r["judge"]] = judge_dist.get(r["judge"], 0) + 1

    print(f"\n  📈 BERT 情感分布: {dict(sorted(bert_dist.items()))}")
    print(f"  📈 Spark 情感分布: {dict(sorted(spark_dist.items()))}")
    print(f"  📈 DeepSeek 判定分布: {dict(sorted(judge_dist.items()))}")

    # 输出报告
    output_path = f"{settings.OUTPUT_DIR}/compare_bert_vs_spark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    report = {
        "timestamp": datetime.now().isoformat(),
        "judge_model": JUDGE_MODEL,
        "total": total,
        "bert_wins": bert_wins,
        "spark_wins": spark_wins,
        "both_wrong": both_wrong,
        "bert_accuracy_pct": round(bert_wins / total * 100, 1) if total else 0,
        "spark_accuracy_pct": round(spark_wins / total * 100, 1) if total else 0,
        "details": results[:20],
    }
    with open(output_path, "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n  📄 报告已保存: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
