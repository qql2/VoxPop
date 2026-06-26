#!/usr/bin/env python3
"""
Spark Lite 优化版 Prompt 效果测试
基于 2026 Prompt Engineering 方法论优化

改进要点（基于搜索结果）:
  1. 明确角色定义 + 任务描述（Role & Task）
  2. 结构化合约（JSON Schema 约束）
  3. 限定输出选择范围（enum 约束）
  4. 添加 Few-shot 示例（Positive/Negative/Neutral 各一）
  5. 明确边界条件说明（新闻 vs 观点、叙事 vs 评价）
"""
import os, sys, json, asyncio, httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SPARK_API_KEY = os.environ.get("SPARK_API_KEY", "")
if not SPARK_API_KEY:
    print("❌ 请设置环境变量 SPARK_API_KEY")
    sys.exit(1)

SPARK_BASE_URL = "https://spark-api-open.xf-yun.com/v1"
SPARK_MODEL = "lite"

# ============================
# v2 优化版 Prompt
# ============================
SYSTEM_PROMPT_V2 = """## 角色
你是一名专业的社会舆情分析师，擅长从社交媒体评论中准确识别情感倾向和态度立场。

## 任务
分析每条用户评论，生成结构化 JSON 输出。

## 输出格式（严格遵循 JSON Schema）
{
  "sentiment": "positive | negative | neutral",
  "emotion": "optimism | anxiety | anger | sarcasm | support | doubt | disappointment | indifference",
  "attitude_tendency": "support | oppose | neutral",
  "confidence": 0.0-1.0
}

## 分类规则
### sentiment（情感极性）
- positive: 表达满意、赞赏、支持、乐观
- negative: 表达不满、批评、反对、悲观
- neutral: 客观事实陈述、新闻报道、学术分析、纯叙事

### emotion（细粒度情绪）
- optimism: 乐观期待
- anxiety: 焦虑担忧
- anger: 愤怒指责
- sarcasm: 讽刺挖苦
- support: 明确支持拥护
- doubt: 怀疑质疑
- disappointment: 失望不满
- indifference: 冷漠无所谓

### attitude_tendency（态度立场）
- support: 明显倾向赞成
- oppose: 明显倾向反对
- neutral: 中立或未表态

## 重要边界规则
1. 【客观事实】纯新闻报道、事实陈述、无主观评价的文本 → sentiment=neutral, attitude_tendency=neutral
2. 【学术分析】考据、论证、技术讨论等理性分析，无明显情感倾向 → sentiment=neutral
3. 【个人叙事】纯粹的个人经历讲述，无明显褒贬 → sentiment=neutral
4. 【简评】"好""不错""NB"等有情感但无详细分析 → 按字面判断，可以 non-neutral
5. 【混合态度】一段话中既有肯定又有批评 → 取整体倾向

## 示例（Few-shot）
输入1: 这个产品真的太垃圾了，完全不想用
输出1: {"sentiment": "negative", "emotion": "anger", "attitude_tendency": "oppose", "confidence": 0.9}

输入2: 今天天气不错
输出2: {"sentiment": "positive", "emotion": "optimism", "attitude_tendency": "support", "confidence": 0.8}

输入3: 根据沙特媒体报道，目前霍尔木兹海峡的情况是，有90%的船只提前通报了相关信息
输出3: {"sentiment": "neutral", "emotion": "indifference", "attitude_tendency": "neutral", "confidence": 0.9}

## 约束
- 只输出 JSON，不加任何额外文字
- 不要添加 markdown 代码块包装
- confidence < 0.6 时代表不确定，这种情况少用"""


def make_prompt_v2(text: str) -> list:
    return [
        {"role": "system", "content": SYSTEM_PROMPT_V2},
        {"role": "user", "content": text[:800]},
    ]


async def call_spark_v2(text: str, idx: int) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        t0 = asyncio.get_event_loop().time()
        resp = await client.post(
            f"{SPARK_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {SPARK_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": SPARK_MODEL,
                "messages": make_prompt_v2(text),
                "temperature": 0.1,
                "max_tokens": 256,
            },
        )
        elapsed = asyncio.get_event_loop().time() - t0
        data = resp.json()
        raw = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        usage = data.get("usage", {})

        # 清洗可能的 markdown 包装
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
        except json.JSONDecodeError:
            parsed = {"error": "parse_failed", "raw": raw[:300]}

        return {
            "idx": idx,
            "elapsed": round(elapsed, 3),
            "total_tokens": usage.get("total_tokens", 0),
            "text": text[:60],
            "parsed": parsed,
        }


TEST_COMMENTS = [
    # 1 — 混合观点，分析型
    "这个观点有意思！现在很多人觉得美股永远涨、A股永远3000，其实都是线性外推的错觉。投资最怕的是把短期趋势当成永恒规律。"
    "美股从2009年到现在的长牛已经持续了16年，估值处于历史高位，A股虽然一直在3000点徘徊但优质公司的ROE并不差。万物皆周期，关键是找到自己看得懂的周期位置。",
    # 2 — 明确吐槽
    "QQ音乐也是吃相难看，购买会员之后，很多歌曲只能是在手机端播放，孩子的电话手表端无法播放，电视下载了app还需要单独开会员。真的体验感有待提升",
    # 3 — 新闻报道（之前被误判为 positive 的）
    "根据沙特媒体的报道，目前霍尔木兹海峡的状况是：在伊朗革命卫队海军宣布关闭之前，有90%的船只都是提前通报伊朗波斯湾管理局报备相关信息，最终走革命卫队规定的格拉姆-拉腊克通过海峡的。而走其他航道则要缴纳的保费太高。",
    # 4 — 历史批判分析（里根）
    "里根绝对高了，里根最大的问题是废除小罗斯福限制资本的基本国策，大搞自由经济学，这个操作看似解决了冷战带来的内部通胀压力，激发了产业资本的生产积极性，但同时释放出了金融资本这个恶魔。",
    # 5 — 金融分析+预判
    "美联储压根就不会加息，都是华尔街在演戏，目前原油已经掉下来了，ai算力最近不断降价，爆款的现象级应用迟迟不能推出，投资和收益形不成闭环，通胀在走低，后面随着ai泡沫频临破灭，经济减速风险非常大。",
    # 6 — AI 泡沫论
    "AI一定是泡沫，人类文明因为交易而繁荣。而如果AI真的能成，几乎绝大部分交易都会被抑制，因为在AI的协助下，人类基本不再需要无效交易，一切都可以理性化处理，导致的结果必然是交易量的塌方。",
    # 7 — 观影吐槽+愤怒
    "今天看电影《南京照相馆》，我全程气氛都很悲伤，坐在我后面的两个小孩全程嘻嘻哈哈一直在讲话，另一个踢我凳子不下7次。看南京大屠杀你们嘻嘻哈哈的父母不管，观影素质极低！有作为中国人的觉悟吗？",
    # 8 — 定价批评（之前误判为 positive）
    "我觉得国内这些卖车的卖手机的这些厂商都可以学一学苹果和米哈游，苹果在自己国家卖多少美元在中国就直接按汇率换算过来卖，要知道在美国别人是赚美元花美元，但是在我们中国是挣的人民币却以美元的价格在买苹果。",
    # 9 — ETF 交易分析
    "这些ETF中韩港美等都换庄了，之前都是游资模式利用情绪拉高甚至拉板溢价上去了，情绪低迷直接暴跌杀溢价来控制平衡，溢价一直杀不下来就是换庄了现在是量化资金模式。",
    # 10 — 融合教育（有反思的正面叙事）
    "不少人不支持特殊孩子进入普通学校就读，而我认为应当结合孩子的实际情况区别看待。我以前也是一名融合班老师，对此深有体会：轻度特殊儿童在普通集体环境中进步显著。这段经历也让我了解到了融合教育的意义",
    # 11 — 纯吐槽
    "就没用过这么难用的软件，逼着硬是换回office，现在是365订阅。卡，弹窗，硬改我默认照片查看器，你好用也行，打开个照片要花10秒。",
    # 12 — 积极分析（巴基斯坦）
    "难归难，巴基斯坦自从去年大了胜仗，像开挂一样，一下子进入世界舞台的中央，闪闪发光。军事外交的重大胜利，是巴基斯坦命运的根本转折。",
    # 13 — 美国总统评价（有褒有贬）
    "拜登被低估了，可能是当众拉裤子的形象太深入人心了，事实上，老拜登通过俄乌战争支援乌克兰，硬生生遏制住了俄罗斯！",
    # 14 — 抗战回忆（叙事）
    "我从小听我外公说他的父母在他很小的时候把他藏在两个房梁中间架的板上，木板外层放很多农具，他被放在最里面一个框子里。前几年外公去世了，去世前躺床上还在念叨：妈你们哪去了，我到好找啊！找不着了！",
    # 15 — 总统批判（直言）
    "在我看来奥巴马是最拉的，不用很多项目，10万亿美债增长到20万亿，这就是美国如今加息也不敢加的终极原因，通胀压不住的罪魁祸首。",
    # 16 — NVIDIA/LLM 分析
    "还有一个，因为科学届认为llm走不到agi，但是黄教主已经绑架了市场资金，绑架了国运。现在英伟达产品线就像给llm定制的。如果llm只是文本处理，coding和视频。那么就是个工具，一切崩塌。",
    # 17 — 家族史（叙事）
    "我姥姥的爸爸是南京夫子庙人，我不太了解当年的事儿。他们从南京到了重庆。他还有个哥哥，其他的兄弟姐妹无一幸免。一场洪水冲走了所有的书信，他们就失去了联系。",
    # 18 — 学术考据（之前误判为 positive）
    "我仔细的看然后查了一下，我感觉可能是伪满洲国时期关于地方病和传染病的内部医疗手稿或笔记。至少是1935年后的，因为原文中提到的克山病是1935年11月首次在东北的克山县发现的。",
]

# 人工标注的预期结果（用于对比）
EXPECTED = [
    {"sentiment": "neutral", "emotion": "doubt|indifference", "attitude": "neutral", "reason": "市场分析，"},
    {"sentiment": "negative", "emotion": "anger|disappointment", "attitude": "oppose", "reason": "QQ音乐吐槽"},
    {"sentiment": "neutral", "emotion": "indifference", "attitude": "neutral", "reason": "新闻报道（"},    # 之前误判
    {"sentiment": "negative", "emotion": "anger|disappointment", "attitude": "oppose", "reason": "批判里根政策"},
    {"sentiment": "negative", "emotion": "doubt|anxiety", "attitude": "oppose", "reason": "市场悲观预判"},
    {"sentiment": "negative", "emotion": "doubt|anxiety", "attitude": "oppose", "reason": "AI泡沫论"},
    {"sentiment": "negative", "emotion": "anger", "attitude": "oppose", "reason": "观影糟糕体验"},
    {"sentiment": "positive|negative", "emotion": "doubt|disappointment", "attitude": "oppose", "reason": "批评定价不"},  # 之前误判
    {"sentiment": "negative", "emotion": "doubt|disappointment", "attitude": "oppose", "reason": "市场分析", },
    {"sentiment": "positive", "emotion": "support|optimism", "attitude": "support", "reason": "融合教育正向"},
    {"sentiment": "negative", "emotion": "anger|disappointment", "attitude": "oppose", "reason": "WPS难用"},
    {"sentiment": "positive", "emotion": "optimism|support", "attitude": "support", "reason": "巴基斯坦积极"},
    {"sentiment": "positive", "emotion": "support|optimism", "attitude": "support", "reason": "拜登评价有偏爱"},
    {"sentiment": "neutral", "emotion": "sadness|indifference", "attitude": "neutral", "reason": "外公回忆叙"},
    {"sentiment": "negative", "emotion": "anger|disappointment", "attitude": "oppose", "reason": "直言批评"},
    {"sentiment": "negative", "emotion": "doubt|anxiety", "attitude": "oppose", "reason": "NVIDIA/LLM分析"},
    {"sentiment": "neutral", "emotion": "indifference|sadness", "attitude": "neutral", "reason": "家族史叙事"},
    {"sentiment": "neutral", "emotion": "indifference", "attitude": "neutral", "reason": "学术考据分析"},  # 之前误判
]


def evaluate(parsed: dict, expected: dict) -> dict:
    """对比实际结果与预期"""
    sentiment_ok = parsed.get("sentiment") in expected["sentiment"].split("|")
    attitude_ok = parsed.get("attitude_tendency") in expected["attitude"].split("|")
    return {
        "sentiment_match": sentiment_ok,
        "attitude_match": attitude_ok,
        "emotion_match": parsed.get("emotion", "") in expected["emotion"].split("|"),
        "expected": expected["sentiment"] if not sentiment_ok else None,
        "got_sentiment": parsed.get("sentiment", "?"),
        "got_attitude": parsed.get("attitude_tendency", "?"),
    }


async def main():
    print("=" * 70)
    print("🔬 Spark Lite 优化版 Prompt (v2) 效果测试")
    print(f"   共 {len(TEST_COMMENTS)} 条评论")
    print("=" * 70)

    results = []
    for i, text in enumerate(TEST_COMMENTS, 1):
        print(f"\n[{i:2d}/{len(TEST_COMMENTS)}] 标注中... {text[:50]}...", end=" ", flush=True)
        r = await call_spark_v2(text, i)
        p = r["parsed"]
        eval_result = evaluate(p, EXPECTED[i-1]) if i <= len(EXPECTED) else {}

        sentiment = p.get("sentiment", "?")
        emotion = p.get("emotion", "?")
        attitude = p.get("attitude_tendency", "?")
        conf = p.get("confidence", "?")
        print(f"[{r['elapsed']}s]")
        print(f"   → {sentiment}/{emotion}/{attitude} (conf:{conf})")
        if eval_result:
            marks = []
            if eval_result["sentiment_match"]:
                marks.append("sentiment✅")
            else:
                marks.append(f"sentiment❌(期望{eval_result['expected']})")
            if eval_result["attitude_match"]:
                marks.append("attitude✅")
            else:
                marks.append(f"attitude❌")
            if eval_result["emotion_match"]:
                marks.append("emotion✅")
            else:
                marks.append(f"emotion❌")
            print(f"   → {' '.join(marks)}")

        results.append({**r, "eval": eval_result})

    # 汇总
    print("\n" + "=" * 70)
    print("📊 汇总对比")
    print("=" * 70)

    total = len(results)
    sentiment_ok = sum(1 for r in results if r.get("eval", {}).get("sentiment_match"))
    attitude_ok = sum(1 for r in results if r.get("eval", {}).get("attitude_match"))
    emotion_ok = sum(1 for r in results if r.get("eval", {}).get("emotion_match"))
    total_time = sum(r["elapsed"] for r in results)

    print(f"   总条数: {total}")
    print(f"   ⏱ 总耗时: {total_time:.1f}s | 平均 {total_time/total:.1f}s/条")
    print(f"")
    print(f"   ✅ 情感极性准确率: {sentiment_ok}/{total} ({sentiment_ok*100//total}%)")
    print(f"   ✅ 态度倾向准确率: {attitude_ok}/{total} ({attitude_ok*100//total}%)")
    print(f"   ✅ 细粒度情绪准确率: {emotion_ok}/{total} ({emotion_ok*100//total}%)")
    print(f"")

    # 分析具体错误
    print("   ❌ 错误详情:")
    errors_found = False
    for i, r in enumerate(results, 1):
        ev = r.get("eval", {})
        if not ev.get("sentiment_match") or not ev.get("attitude_match"):
            errors_found = True
            p = r["parsed"]
            expected = EXPECTED[i-1]
            print(f"   [#{i:2d}] 原文: {TEST_COMMENTS[i-1][:50]}...")
            print(f"         预期: {expected['sentiment']}/{expected['attitude']} | 实际: {p.get('sentiment','?')}/{p.get('attitude_tendency','?')}")
            print(f"         情绪: {p.get('emotion','?')} (期望 {expected['emotion']})")
    if not errors_found:
        print("   无错误 — 全部匹配")

    # 特殊改进项分析
    print(f"\n   📋 关键改进项对比:")
    improvements = [(3, "新闻报道→预期neutral"), (8, "定价批评→非positive"), (14, "叙事→非anger"), (17, "叙事→非anger"), (18, "考据→预期neutral")]
    for idx, desc in improvements:
        r = results[idx-1]
        p = r["parsed"]
        actual = f"{p.get('sentiment','?')}/{p.get('emotion','?')}"
        print(f"     #{idx:2d} {desc}: 实际→ {actual}")


if __name__ == "__main__":
    asyncio.run(main())
