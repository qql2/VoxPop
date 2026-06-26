#!/usr/bin/env python3
"""BERT vs Spark Lite 快速对比测试"""
import torch, warnings, json, asyncio, httpx
warnings.filterwarnings("ignore")
from transformers import AutoTokenizer, AutoModelForSequenceClassification

# 加载配置
with open("/Users/Admin1/VoxPop/.env") as f:
    c = f.read()
    SPARK_KEY = c.split("SPARK_API_KEY=")[1].split("\n")[0].strip()
    JUDGE_KEY = c.split("LLM_API_KEY=")[1].split("\n")[0].strip()

# 加载 BERT
print("Loading BERT...")
bert_name = "wsqstar/GISchat-weibo-100k-fine-tuned-bert"
tok = AutoTokenizer.from_pretrained(bert_name)
model = AutoModelForSequenceClassification.from_pretrained(bert_name)
model.eval()
print("BERT loaded!")

TEST_TEXTS = [
    "这个产品真的太垃圾了，完全不想用",
    "太棒了，支持支持！",
    "今天天气不错",
    "日本的军事野心越来越明显了，必须警惕",
    "早上好",
    "QQ音乐也是吃相难看，购买会员之后体验感有待提升",
    "支持国产，加油！",
    "美帝这么搞下去，不是犹太集团彻底掌控美国，就是美国那天受不了彻底起来反犹！",
    "那很快又要打起来了，伊朗永远记吃不记打",
    "早上好今天天气真好心情不错",
    "根据沙特媒体的报道，目前霍尔木兹海峡的状况是：有90%的船只提前通报伊朗波斯湾管理局",
    "里根绝对高了，里根最大的问题是废除小罗斯福限制资本的基本国策，大搞自由经济学",
    "AI一定是泡沫，人类文明因为交易而繁荣，如果AI真的能成，几乎绝大部分交易都会被抑制",
    "就没用过这么难用的软件，逼着硬是换回office",
    "不少人不支持特殊孩子进入普通学校就读，而我认为应当结合孩子的实际情况区别看待",
]


def bert_label(text):
    inputs = tok(text[:512], max_length=512, truncation=True, return_tensors="pt")
    with torch.no_grad():
        out = model(**inputs)
        probs = torch.softmax(out.logits, dim=1)
        pos, neg = probs[0][1].item(), probs[0][0].item()
    # 二分类模型 + 置信度阈值 -> 三分类
    guess = "positive" if pos > neg else "negative"
    conf = max(pos, neg)
    if conf > 0.8:
        return guess, conf
    else:
        return "neutral", conf


async def spark_label(text):
    async with httpx.AsyncClient(timeout=30) as c:
        try:
            r = await c.post(
                "https://spark-api-open.xf-yun.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {SPARK_KEY}", "Content-Type": "application/json"},
                json={
                    "model": "lite",
                    "messages": [{"role": "system", "content": "分析情感。输出JSON: {\"sentiment\":\"positive|negative|neutral\"}"}, {"role": "user", "content": text[:800]}],
                    "temperature": 0.1,
                    "max_tokens": 100,
                },
            )
            raw = r.json()["choices"][0]["message"]["content"]
            if not raw.strip():
                return "?"
            clean = raw.strip()
            if clean.startswith("```"):
                lines = clean.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                clean = "\n".join(lines).strip()
            return json.loads(clean).get("sentiment", "?")
        except Exception as e:
            print(f"      Spark error: {e}")
            return "?"


async def judge_deepseek(text, bert_s, spark_s):
    # 如果两者一致，直接返回 both_correct 不走 API
    if bert_s == spark_s:
        return "both_correct"
    prompt = f"评论: {text[:200]}\nA.BERT: {bert_s}\nB.Spark: {spark_s}\n谁更准？只输出JSON: {{\"better\":\"A\"|\"B\"|\"both_wrong\",\"reason\":\"一句话\"}}"
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(
            "https://www.packyapi.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {JUDGE_KEY}", "Content-Type": "application/json"},
            json={"model": "deepseek-v4-flash", "messages": [{"role": "user", "content": prompt}], "temperature": 0.1, "max_tokens": 100},
        )
        raw = r.json()["choices"][0]["message"]["content"]
        if not raw.strip():
            return "error"
        clean = raw.strip()
        if clean.startswith("```"):
            lines = clean.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            clean = "\n".join(lines).strip()
        return json.loads(clean).get("better", "error")


async def main():
    print("=" * 60)
    print("BERT vs Spark Lite 对比测试")
    print(f"共 {len(TEST_TEXTS)} 条测试评论")
    print("=" * 60)

    bert_wins, spark_wins, both_wrong = 0, 0, 0

    for i, text in enumerate(TEST_TEXTS, 1):
        bert_s, bert_c = bert_label(text)
        spark_s = await spark_label(text)

        if spark_s == "?":
            print(f"[{i:2d}] ❌ Spark 解析失败: {text[:30]}...")
            continue

        j = await judge_deepseek(text, bert_s, spark_s)
        icon = "✅" if j == "A" else ("👍" if j == "B" else "⚠️")

        if j == "A":
            bert_wins += 1
        elif j == "B":
            spark_wins += 1
        elif j == "both_correct":
            both_wrong += 1  # both correct = agreement on same answer
        else:
            both_wrong += 1

        print(f"  [{i:2d}] {icon} B:{bert_s:<8} S:{spark_s:<8} | DS:{j:<14} | {text[:30]}...")

    total = bert_wins + spark_wins + both_wrong
    print(f"\n{'='*60}")
    print(f"📊 对比结果")
    if total:
        print(f"  ✅ BERT wins: {bert_wins}/{total} ({bert_wins*100//total}%)")
        print(f"  ✅ Spark wins: {spark_wins}/{total} ({spark_wins*100//total}%)")
        print(f"  🤝 Agree: {both_wrong - (total - bert_wins - spark_wins)}/{total}")
        print(f"  ❌ Both wrong: {total - bert_wins - spark_wins}/{total}")
        print(f"\n  💡 当两者不同意时 BERT胜出率: {bert_wins/(bert_wins+spark_wins)*100:.0f}%")
        print(f"  💡 当两者不同意时 Spark胜出率: {spark_wins/(bert_wins+spark_wins)*100:.0f}%")


if __name__ == "__main__":
    asyncio.run(main())
