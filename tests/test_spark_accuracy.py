#!/usr/bin/env python3
"""
Spark Lite — 复杂评论情感分类效果测试
选数据库中最有观点争议性的评论，逐条标注并记录结果
"""
import os, sys, json, asyncio, httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SPARK_API_KEY = os.environ.get("SPARK_API_KEY", "")
if not SPARK_API_KEY:
    print("❌ 请设置环境变量 SPARK_API_KEY")
    sys.exit(1)

SPARK_BASE_URL = "https://spark-api-open.xf-yun.com/v1"

TEST_COMMENTS = [
    # 1. 美股vsA股 — 有分析有观点，混合情绪
    "这个观点有意思！现在很多人觉得美股永远涨、A股永远3000，其实都是线性外推的错觉。投资最怕的是把短期趋势当成永恒规律。"
    "美股从2009年到现在的长牛已经持续了16年，估值处于历史高位，A股虽然一直在3000点徘徊但优质公司的ROE并不差。万物皆周期，关键是找到自己看得懂的周期位置。",

    # 2. QQ音乐 — 吐槽+具体举例，负面明显
    "QQ音乐也是吃相难看，购买会员之后，很多歌曲只能是在手机端播放，孩子的电话手表端无法播放（孩子经常用电话手表听音乐），"
    "电视下载了app，如果你需要电视上听音乐还需要单独开会员。其实电视端使用的频率很少，那么移动端的会员可以登录电视端的会员就可以了啊。然而并不行，真的体验感有待提升",

    # 3. 伊朗海峡 — 地缘政治分析，偏中立
    "根据沙特媒体的报道，目前霍尔木兹海峡的状况是：在伊朗革命卫队海军宣布关闭之前，有90%的船只都是提前通报伊朗波斯湾管理局报备相关信息，"
    "最终走革命卫队规定的格拉姆-拉腊克通过海峡的。而走其他航道则要缴纳的保费太高。",

    # 4. 美国前总统评价里根 — 长篇历史分析，持批判立场
    "里根绝对高了，里根最大的问题是废除小罗斯福限制资本的基本国策，大搞自由经济学，这个操作看似解决了冷战带来的内部通胀压力，激发了产业资本的生产积极性，"
    "但同时释放出了金融资本这个恶魔，为未来美国资本脱实向虚，产业空心化埋下了祸根。此操作影响深远，让美国大量产业工人下岗，形成五大湖铁锈带，"
    "劫贫济富式的对资本家减税，导致大量中低产阶级美国人破产沦为流浪汉。美国工人的工资从里根的80年代开始就没有增加过，而金融资本快速发展产生的各种经济租却疯狂上涨。",

    # 5. 特斯拉财报 — 有分析有判断，情绪偏负面但理性
    "美联储压根就不会加息，都是华尔街在演戏，目前原油已经掉下来了，ai算力最近不断降价，爆款的现象级应用迟迟不能推出，"
    "投资和收益形不成闭环，资本开支也因此最近减速，通胀在走低，后面随着ai泡沫频临破灭，经济减速风险非常大，降息很快会提到日程上来。",

    # 6. AI泡沫论 — 有观点有深度，情绪偏悲观
    "AI一定是泡沫，人类文明因为交易而繁荣。而如果AI真的能成，几乎绝大部分交易都会被抑制，因为在AI的协助下，人类基本不再需要无效交易，"
    "一切都可以理性化处理，导致的结果必然是交易量的塌方。从而导致文明的坍塌。",

    # 7. 观影体验吐槽 — 生气有立场
    "今天看电影《南京照相馆》，我全程气氛都很悲伤，坐在我后面的两个小孩，一个全程嘻嘻哈哈一直在讲话，另一个踢我凳子不下7次，我多次提醒，她跟没听见一样，"
    "她们的妈妈在旁边也不管。结束之后我再一次跟她们提出此事，她们只是回答没有。在电梯的时候一个小孩就和她妈妈说：我知道啦，不是踢她了，是那个人的按摩椅启动了，她自己没有感觉。"
    "？我请问呢？按摩椅和踢我能感觉不出来吗？看南京大屠杀你们嘻嘻哈哈的父母不管，观影素质极低！有作为中国人的觉悟吗？学校怎么教的？日本来的吗？",

    # 8. 中外定价差异 — 有分析有对比，偏负面
    "我觉得国内这些卖车的卖手机的这些厂商都可以学一学苹果和米哈游，苹果在自己国家卖多少美元在中国就直接按汇率换算过来卖，"
    "要知道在美国别人是赚美元花美元，但是在我们中国是挣的人民币却以美元的价格在买苹果，别人苹果可一点不管我们是花多少人民币买的。"
    "这一点上米哈游其实已经试过了而且颇有成效，徽章在国内卖多少人民币，在国外根本不管汇率，直接换单位，老外照样买单，而且一售而空（比如：国内18元，国外直接18欧）。",

    # 9. ETF量化 — 专业金融分析，偏悲观
    "这些ETF中韩港美等都换庄了，之前都是游资模式利用情绪拉高甚至拉板溢价上去了，情绪低迷直接暴跌杀溢价来控制平衡，"
    "溢价一直杀不下来就是换庄了现在是量化资金模式，前面那个涨停那么艰难指数都涨了10个点以上了，暴跌的时候也没跌那么多甚至还跌不过指数，"
    "现在越来越难玩了，之前好做t现在做T压根做不过量化，可能只能长拿了但是6月的形势也不太适合长拿。",

    # 10. 融合教育 — 有反思有态度转变，混合情绪
    "不少人不支持特殊孩子进入普通学校就读，而我认为应当结合孩子的实际情况区别看待。我以前也是一名融合班老师，对此深有体会："
    "轻度特殊儿童在普通集体环境中进步显著，慢慢就能适应正常学习生活；但症状较重的孩子，还是更适合在专门的特殊学校接受照料与教学。"
    "其实我一开始也很反对融合，真的觉得特别辛苦，直到某届孩子毕业，有个家长给我写了封信，说自己的孩子在毕业表演节目中，会主动留意、照顾特殊幼儿。"
    "孩子们在没有偏见、充满接纳的环境里，学会了包容、体谅，平时相处大家也都能经常给予特殊儿夸奖和帮助，我们都很感动。这段经历也让我了解到了融合教育的意义。",

    # 11. WPS吐槽 — 具体体验差评
    "就没用过这么难用的软件，逼着硬是换回office，现在是365订阅。卡，弹窗，硬改我默认照片查看器，你好用也行，打开个照片要花10秒，"
    "别说我配置低，我i914900k，64g内存，开它都要卡一下。",

    # 12. 巴基斯坦分析 — 偏积极的国际关系分析
    "难归难，巴基斯坦自从去年大了胜仗，像开挂一样，一下子进入世界舞台的中央，闪闪发光。军事外交的重大胜利，是巴基斯坦命运的根本转折："
    "国际地位显著提升，赢得美国、海湾富豪国、伊斯兰世界的信任，并将获得巨大经济回报。",

    # 13. 美国前总统评价拜登 — 有褒有贬的复杂评价
    "拜登被低估了，可能是当众拉裤子的形象太深入人心了，事实上，老拜登通过俄乌战争支援乌克兰，硬生生遏制住了俄罗斯！"
    "其中固然有泽连斯基带着乌克兰军队拼死抵抗的元素，但欧美国家的支持也密不可分",

    # 14. 抗战回忆 — 叙事型，情绪复杂
    "我从小听我外公说他的父母在他很小的时候把他藏在两个房梁中间架的板上，木板外层放很多农具，他被放在最里面一个框子里，"
    "框内铺一层干草，再盖上草木灰混合动物的粪便，外公的爸爸妈妈吩咐他别出来，等到天黑饿的受不了他偷偷出来后就找不见自己父母了，"
    "前几年外公去世了，去世前躺床上还在念叨：妈你们哪去了，我到好找啊！找不着了！外公每次提起父母都会哭，"
    "大年三十我们这边有习俗去给死去的亲人上坟，外公总是偷偷哭，因为我两个老太连个坟都没有",

    # 15. B站UP主评价 — 有立场有风格的表达
    "在我看来奥巴马是最拉的，不用很多项目，10万亿美债增长到20万亿，这就是美国如今加息也不敢加的终极原因，通胀压不住的罪魁祸首，"
    "复利是世界第八大奇迹，奥巴马创造了奇迹。亚太再平衡直接把老美和老中推到对立面，他也不想想当年美国能战胜苏联是因为啥，总结，奥巴马应该是拉稀了",

    # 16. 抖音B站商业模式对比 — 分析型
    "还有一个，因为科学届认为llm走不到agi，但是黄教主已经绑架了市场资金，绑架了国运，甚至天天出来讲绑架文明。"
    "但是，现在这个情况，英伟达产品线就像给llm定制的。如果llm只是文本处理，coding和视频。没有其他。那么就是个工具，一切崩塌。",

    # 17. 抗日回忆 — 叙事+家族史
    "我姥姥的爸爸是南京夫子庙人，我不太了解当年的事儿。他们从南京到了重庆，我不太清楚是这件事儿发生之前他就去重庆工作了，还是之后逃离的。"
    "但是他还有个哥哥，其他的兄弟姐妹无一幸免。哥哥在战争结束之后回到了南京，姥姥的爸爸选择继续在重庆，然后从重庆到了四川，"
    "他们在90年代还有联系，一场洪水冲走了所有的书信，他们就失去了联系，我姥姥一直很想知道她大伯的后代过得好不好，她现在已经80岁了。",

    # 18. 伪满洲国医疗手稿 — 学术考据，中性
    "我仔细的看然后查了一下，我感觉可能是伪满洲国时期关于地方病和传染病的内部医疗手稿或笔记，然后成书或期刊杂志出版的。"
    "至少是1935年后的，因为原文中提到的克山病是1935年11月首次在东北的克山县发现的。图片提到传染病、地方病、患者隔离、健康状况、注射，"
    "也提到了地点如泰安镇、大赉县，可以肯定是伪满洲国时期的东北。可能是医务人员在现场记录，但同时是类似满铁农村调查那类的东西，通过看似学术的走访调查中国民间，为侵华做准备。",
]

_SYSTEM_PROMPT = (
    "你是态度分析师，分析社交媒体评论并输出JSON。不要输出其他内容，只输出JSON。\n"
    "格式: {\"sentiment\": \"positive|negative|neutral\", "
    "\"emotion\": \"optimism|anxiety|anger|sarcasm|support|doubt|disappointment|indifference\", "
    "\"attitude\": \"support|oppose|neutral|banter\", "
    "\"confidence\": 0.0-1.0, "
    "\"brief_reason\": \"一句话理由\"}"
)


async def call_one(text, idx):
    async with httpx.AsyncClient(timeout=30) as client:
        t0 = asyncio.get_event_loop().time()
        resp = await client.post(
            f"{SPARK_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {SPARK_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "lite",
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": text[:800]},
                ],
                "temperature": 0.1,
                "max_tokens": 256,
            },
        )
        elapsed = asyncio.get_event_loop().time() - t0
        data = resp.json()
        raw = data.get("choices", [{}])[0].get("message", {}).get("content", "")

        # 清洗 markdown 包装
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
            parsed = {"error": "parse_failed", "raw": raw[:200]}

        return {
            "idx": idx,
            "elapsed": round(elapsed, 3),
            "prompt_tokens": data.get("usage", {}).get("prompt_tokens", 0),
            "completion_tokens": data.get("usage", {}).get("completion_tokens", 0),
            "total_tokens": data.get("usage", {}).get("total_tokens", 0),
            "raw": raw[:500],
            "parsed": parsed,
        }


async def main():
    print("=" * 70)
    print("Spark Lite 复杂评论情感分类效果测试")
    print(f"共 {len(TEST_COMMENTS)} 条评论，单线程串行调用")
    print("=" * 70)

    results = []
    for i, text in enumerate(TEST_COMMENTS, 1):
        title = text[:60].replace("\n", " ")
        print(f"\n[{i}/{len(TEST_COMMENTS)}] 标注中... {title}...")
        r = await call_one(text, i)
        results.append(r)
        p = r["parsed"]
        print(f"    耗时: {r['elapsed']}s | tokens: {r['total_tokens']}")
        print(f"    → sentiment: {p.get('sentiment','?')}  "
              f"emotion: {p.get('emotion','?')}  "
              f"attitude: {p.get('attitude','?')}")
        print(f"    → confidence: {p.get('confidence','?')}  "
              f"reason: {p.get('brief_reason','')[:60]}")
        if p.get("mentioned_profession"):
            print(f"    → 涉及职业: {p['mentioned_profession']}")

    # 汇总统计
    print("\n" + "=" * 70)
    print("📊 汇总统计")
    print("=" * 70)

    sentiments = {}
    emotions = {}
    attitudes = {}
    total_tokens = 0
    total_time = 0
    errors = 0

    for r in results:
        p = r["parsed"]
        if p.get("sentiment"):
            sentiments[p["sentiment"]] = sentiments.get(p["sentiment"], 0) + 1
        if p.get("emotion"):
            emotions[p["emotion"]] = emotions.get(p["emotion"], 0) + 1
        if p.get("attitude"):
            attitudes[p["attitude"]] = attitudes.get(p["attitude"], 0) + 1
        total_tokens += r.get("total_tokens", 0)
        total_time += r.get("elapsed", 0)
        if "error" in p:
            errors += 1

    total = len(results)
    print(f"  ✅ 成功: {total - errors} / {total}")
    print(f"  ❌ 解析失败: {errors}")
    print(f"  ⏱ 总耗时: {total_time:.1f}s | 平均 {total_time/total:.1f}s/条")
    print(f"  📝 总 tokens: {total_tokens} | 平均 {total_tokens//total}/条")

    print(f"\n  📊 情感分布 (sentiment):")
    for k, v in sorted(sentiments.items(), key=lambda x: -x[1]):
        print(f"     {k}: {v} ({v*100//total}%)")

    print(f"\n  📊 情绪分布 (emotion):")
    for k, v in sorted(emotions.items(), key=lambda x: -x[1]):
        print(f"     {k}: {v}")

    print(f"\n  📊 态度分布 (attitude):")
    for k, v in sorted(attitudes.items(), key=lambda x: -x[1]):
        print(f"     {k}: {v}")


if __name__ == "__main__":
    asyncio.run(main())
