#!/usr/bin/env python3
"""
Spark Lite Prompt 优化对比测试 v3
对比 v1(简单) / v2(详细+Few-shot) / v3(精简+规则) 三种 Prompt 的效果
"""
import os, sys, json, asyncio, httpx

SPARK_API_KEY = os.environ.get("SPARK_API_KEY", "")
SPARK_BASE_URL = "https://spark-api-open.xf-yun.com/v1"

# ===== 三种 System Prompt =====
PROMPT_V1 = (
    "你是态度分析师，分析社交媒体评论并输出JSON。不要输出其他内容，只输出JSON。\n"
    "格式: {\"sentiment\": \"positive|negative|neutral\", "
    "\"emotion\": \"optimism|anxiety|anger|sarcasm|support|doubt|disappointment|indifference\", "
    "\"attitude_tendency\": \"support|oppose|neutral\", "
    "\"confidence\": 0.0-1.0, "
    "\"brief_reason\": \"一句话理由\"}"
)

PROMPT_V2 = """## 角色
你是一名专业的社会舆情分析师，擅长从社交媒体评论中准确识别情感倾向和态度立场。

## 任务
分析每条用户评论，生成结构化 JSON 输出。

## 输出格式（严格遵循 JSON Schema）
{"sentiment": "positive | negative | neutral", "emotion": "optimism | anxiety | anger | sarcasm | support | doubt | disappointment | indifference", "attitude_tendency": "support | oppose | neutral", "confidence": 0.0-1.0}

## 分类规则
- neutral: 客观事实陈述、新闻报道、学术分析、纯叙事
- positive: 表达满意、赞赏、支持、乐观
- negative: 表达不满、批评、反对、悲观

## 边界规则
1. 【事实陈述】新闻报道、历史考据、纯分析 → neutral
2. 【个人叙事】讲故事无褒贬 → neutral
3. 【混合态度】有肯定也有批评 → 取整体倾向

## 示例
输入: 这个产品真的太垃圾了
输出: {"sentiment": "negative", "emotion": "anger", "attitude_tendency": "oppose", "confidence": 0.9}

输入: 今天天气不错
输出: {"sentiment": "positive", "emotion": "optimism", "attitude_tendency": "support", "confidence": 0.8}

输入: 据沙特媒体报道，霍尔木兹海峡有90%的船只提前通报
输出: {"sentiment": "neutral", "emotion": "indifference", "attitude_tendency": "neutral", "confidence": 0.9}

## 约束
只输出JSON，不加任何额外文字，不要用markdown代码块包裹。"""

PROMPT_V3 = """分析评论的情感。只输出JSON。

规则：
- 新闻/事实/考据/叙事 → neutral
- 批评/吐槽/愤怒 → negative
- 赞赏/支持/喜欢 → positive
- 禁止输出 "sadness"，如有悲伤情绪用 "disappointment"

JSON格式：
{"sentiment": "positive|negative|neutral", "emotion": "optimism|anger|doubt|disappointment|indifference|anxiety|sarcasm|support", "attitude_tendency": "support|oppose|neutral", "confidence": 0.0-1.0}"""

# ===== 测试用例（18条相同）=====
TEST_COMMENTS = [
    "这个观点有意思！现在很多人觉得美股永远涨、A股永远3000，其实都是线性外推的错觉。投资最怕的是把短期趋势当成永恒规律。美股从2009年到现在的长牛已经持续了16年，估值处于历史高位，A股虽然一直在3000点徘徊但优质公司的ROE并不差。万物皆周期，关键是找到自己看得懂的周期位置。",
    "QQ音乐也是吃相难看，购买会员之后，很多歌曲只能是在手机端播放，孩子的电话手表端无法播放，电视下载了app还需要单独开会员。真的体验感有待提升",
    "根据沙特媒体的报道，目前霍尔木兹海峡的状况是：在伊朗革命卫队海军宣布关闭之前，有90%的船只都是提前通报伊朗波斯湾管理局报备相关信息，最终走革命卫队规定的格拉姆-拉腊克通过海峡的。",
    "里根绝对高了，里根最大的问题是废除小罗斯福限制资本的基本国策，大搞自由经济学，这个操作看似解决了冷战带来的内部通胀压力，激发了产业资本的生产积极性，但同时释放出了金融资本这个恶魔。",
    "美联储压根就不会加息，都是华尔街在演戏，目前原油已经掉下来了，ai算力最近不断降价，爆款的现象级应用迟迟不能推出，投资和收益形不成闭环，通胀在走低，后面随着ai泡沫频临破灭，经济减速风险非常大。",
    "AI一定是泡沫，人类文明因为交易而繁荣。而如果AI真的能成，几乎绝大部分交易都会被抑制，因为在AI的协助下，人类基本不再需要无效交易，一切都可以理性化处理，导致的结果必然是交易量的塌方。",
    "今天看电影《南京照相馆》，我全程气氛都很悲伤，坐在我后面的两个小孩全程嘻嘻哈哈一直在讲话，另一个踢我凳子不下7次。看南京大屠杀你们嘻嘻哈哈的父母不管，观影素质极低！有作为中国人的觉悟吗？",
    "我觉得国内这些卖车的卖手机的这些厂商都可以学一学苹果和米哈游，苹果在自己国家卖多少美元在中国就直接按汇率换算过来卖，要知道在美国别人是赚美元花美元，但是在我们中国是挣的人民币却以美元的价格在买苹果。",
    "这些ETF中韩港美等都换庄了，之前都是游资模式利用情绪拉高甚至拉板溢价上去了，情绪低迷直接暴跌杀溢价来控制平衡，溢价一直杀不下来就是换庄了现在是量化资金模式。",
    "不少人不支持特殊孩子进入普通学校就读，而我认为应当结合孩子的实际情况区别看待。我以前也是一名融合班老师，对此深有体会：轻度特殊儿童在普通集体环境中进步显著。这段经历也让我了解到了融合教育的意义",
    "就没用过这么难用的软件，逼着硬是换回office，现在是365订阅。卡，弹窗，硬改我默认照片查看器，你好用也行，打开个照片要花10秒。",
    "难归难，巴基斯坦自从去年大了胜仗，像开挂一样，一下子进入世界舞台的中央，闪闪发光。军事外交的重大胜利，是巴基斯坦命运的根本转折。",
    "拜登被低估了，可能是当众拉裤子的形象太深入人心了，事实上，老拜登通过俄乌战争支援乌克兰，硬生生遏制住了俄罗斯！",
    "我从小听我外公说他的父母在他很小的时候把他藏在两个房梁中间架的板上，木板外层放很多农具，他被放在最里面一个框子里。前几年外公去世了，去世前躺床上还在念叨：妈你们哪去了，我到好找啊！找不着了！",
    "在我看来奥巴马是最拉的，不用很多项目，10万亿美债增长到20万亿，这就是美国如今加息也不敢加的终极原因，通胀压不住的罪魁祸首。",
    "还有一个，因为科学届认为llm走不到agi，但是黄教主已经绑架了市场资金，绑架了国运。现在英伟达产品线就像给llm定制的。如果llm只是文本处理，coding和视频。那么就是个工具，一切崩塌。",
    "我姥姥的爸爸是南京夫子庙人，我不太了解当年的事儿。他们从南京到了重庆。他还有个哥哥，其他的兄弟姐妹无一幸免。一场洪水冲走了所有的书信，他们就失去了联系。",
    "我仔细的看然后查了一下，我感觉可能是伪满洲国时期关于地方病和传染病的内部医疗手稿或笔记。至少是1935年后的，因为原文中提到的克山病是1935年11月首次在东北的克山县发现的。",
]

# 预期结果（人工判断）
EXPECTED = [
    {"sentiment": "neutral", "emotion": "doubt|indifference", "attitude": "neutral"},     # 1 市场分析
    {"sentiment": "negative", "emotion": "anger|disappointment", "attitude": "oppose"},    # 2 QQ吐槽
    {"sentiment": "neutral", "emotion": "indifference", "attitude": "neutral"},            # 3 新闻
    {"sentiment": "negative", "emotion": "anger|disappointment", "attitude": "oppose"},    # 4 批判里根
    {"sentiment": "negative", "emotion": "doubt|anxiety", "attitude": "oppose"},           # 5 悲观预判
    {"sentiment": "negative", "emotion": "doubt|anxiety", "attitude": "oppose"},           # 6 AI泡沫论
    {"sentiment": "negative", "emotion": "anger", "attitude": "oppose"},                   # 7 观影愤怒
    {"sentiment": "negative", "emotion": "disappointment|anger", "attitude": "oppose"},    # 8 定价批评
    {"sentiment": "negative", "emotion": "doubt|disappointment", "attitude": "oppose"},    # 9 ETF
    {"sentiment": "positive", "emotion": "support|optimism", "attitude": "support"},       # 10 融合教育
    {"sentiment": "negative", "emotion": "anger|disappointment", "attitude": "oppose"},    # 11 WPS
    {"sentiment": "positive", "emotion": "optimism|support", "attitude": "support"},       # 12 巴基斯坦
    {"sentiment": "positive", "emotion": "support|optimism", "attitude": "support"},       # 13 拜登评价
    {"sentiment": "neutral", "emotion": "indifference|disappointment", "attitude": "neutral"}, # 14 外公
    {"sentiment": "negative", "emotion": "anger|disappointment", "attitude": "oppose"},    # 15 奥巴马
    {"sentiment": "negative", "emotion": "doubt|anxiety", "attitude": "oppose"},           # 16 NVIDIA
    {"sentiment": "neutral", "emotion": "indifference|disappointment", "attitude": "neutral"}, # 17 家族史
    {"sentiment": "neutral", "emotion": "indifference", "attitude": "neutral"},            # 18 考据
]


async def call_and_parse(prompt: str, text: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        t0 = asyncio.get_event_loop().time()
        resp = await client.post(
            f"{SPARK_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {SPARK_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "lite",
                "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": text[:800]}],
                "temperature": 0.1,
                "max_tokens": 200,
            },
        )
        elapsed = asyncio.get_event_loop().time() - t0
        data = resp.json()
        raw = data.get("choices", [{}])[0].get("message", {}).get("content", "")

        # 清洗
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
            return {"sentiment": parsed.get("sentiment"), "emotion": parsed.get("emotion"), "attitude": parsed.get("attitude_tendency"), "confidence": parsed.get("confidence"), "ok": True, "elapsed": elapsed}
        except:
            return {"ok": False, "elapsed": elapsed, "raw": raw[:200], "sentiment": None, "emotion": None, "attitude": None, "confidence": None}


def score(actual: dict, expected: dict) -> dict:
    s_ok = actual.get("sentiment") in expected["sentiment"].split("|") if actual.get("sentiment") else False
    e_ok = actual.get("emotion") in expected["emotion"].split("|") if actual.get("emotion") else False
    a_ok = actual.get("attitude") in expected["attitude"].split("|") if actual.get("attitude") else False
    return {"sentiment": s_ok, "emotion": e_ok, "attitude": a_ok}


async def test_prompt(name: str, prompt: str) -> dict:
    print(f"\n{'='*60}")
    print(f"📝 Prompt: {name}")
    print(f"{'='*60}")

    s_scores, e_scores, a_scores, times = [], [], [], []
    sentiment_dist = {}
    emotion_dist = {}
    enum_violations = {"sadness": 0}
    parse_errors = 0
    valid_emotions = {"optimism","anxiety","anger","sarcasm","support","doubt","disappointment","indifference"}

    for i, (text, exp) in enumerate(zip(TEST_COMMENTS, EXPECTED), 1):
        r = await call_and_parse(prompt, text)
        times.append(r["elapsed"])
        
        if not r["ok"]:
            parse_errors += 1
            print(f"  [{i:2d}] ❌ PARSE FAILED ({r['elapsed']:.1f}s)")
            s_scores.append(False)
            e_scores.append(False)
            a_scores.append(False)
            continue

        sc = score(r, exp)
        s_scores.append(sc["sentiment"])
        e_scores.append(sc["emotion"])
        a_scores.append(sc["attitude"])

        # 统计情感分布
        if r["sentiment"]:
            sentiment_dist[r["sentiment"]] = sentiment_dist.get(r["sentiment"], 0) + 1
        if r["emotion"]:
            emotion_dist[r["emotion"]] = emotion_dist.get(r["emotion"], 0) + 1
            if r["emotion"] not in valid_emotions:
                enum_violations[r["emotion"]] = enum_violations.get(r["emotion"], 0) + 1

        marks = []
        if sc["sentiment"]: marks.append("S✅")
        else: marks.append(f"S❌(期望{exp['sentiment']})")
        if sc["attitude"]: marks.append("A✅")
        else: marks.append("A❌")
        if sc["emotion"]: marks.append("E✅")
        else: marks.append(f"E❌")
        
        print(f"  [{i:2d}] {r['sentiment']}/{r['emotion']} conf:{r.get('confidence','?')} [{r['elapsed']:.1f}s] {' '.join(marks)}")

    n_total = len(TEST_COMMENTS)
    n_valid = n_total - parse_errors
    return {
        "name": name,
        "sentiment_acc": (sum(s_scores) / max(n_valid, 1)) * 100,
        "attitude_acc": (sum(a_scores) / max(n_valid, 1)) * 100,
        "emotion_acc": (sum(e_scores) / max(n_valid, 1)) * 100,
        "parse_success_rate": (n_valid / n_total) * 100,
        "avg_time": sum(times) / len(times),
        "sentiment_dist": sentiment_dist,
        "emotion_dist": emotion_dist,
        "enum_violations": enum_violations,
        "total": n_total,
        "valid": n_valid,
    }


async def main():
    print("=" * 70)
    print("Spark Lite Prompt 对比测试")
    print(f"共 {len(TEST_COMMENTS)} 条评论，3种 Prompt 版本分别测试")
    print("=" * 70)

    results = []
    results.append(await test_prompt("v1 (原始简单版)", PROMPT_V1))
    results.append(await test_prompt("v2 (详细Few-shot版)", PROMPT_V2))
    results.append(await test_prompt("v3 (精简规则版)", PROMPT_V3))

    # 对比汇总
    print("\n" + "=" * 70)
    print("📊 三版对比汇总")
    print("=" * 70)
    print(f"{'版本':<20} {'解析率':>8} {'情感':>7} {'态度':>7} {'情绪':>7} {'耗时':>6} {'分布':<30}")
    print("-" * 85)
    for r in results:
        s_str = f"pos{r['sentiment_dist'].get('positive',0)}/neg{r['sentiment_dist'].get('negative',0)}/neu{r['sentiment_dist'].get('neutral',0)}"
        print(f"{r['name']:<20} {r['parse_success_rate']:>6.0f}% {r['sentiment_acc']:>6.0f}% {r['attitude_acc']:>6.0f}% {r['emotion_acc']:>6.0f}% {r['avg_time']:>4.1f}s {s_str}")

    # 枚举违规分析
    print(f"\n   📋 枚举违规（sadness等不在允许列表的）:")
    for r in results:
        viols = r.get("enum_violations", {})
        if any(v > 0 for v in viols.values()):
            for k, v in viols.items():
                if v > 0:
                    print(f"     {r['name']}: \"{k}\" 出现 {v} 次")
        else:
            print(f"     {r['name']}: 无违规")


if __name__ == "__main__":
    asyncio.run(main())
