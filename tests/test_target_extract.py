#!/usr/bin/env python3
"""测试 Spark Lite 的目标提取效果"""
import httpx, json, asyncio

with open("/Users/Admin1/VoxPop/.env") as f:
    content = f.read()
    key = content.split("SPARK_API_KEY=")[1].split("\n")[0].strip()

tests = [
    "QQ音乐也是吃相难看，购买会员之后很多歌曲只能手机端播放，电视还需要单独开会员",
    "日本的军事野心越来越明显了必须警惕",
    "警察暴力执法必须严惩",
    "老师辛苦了每天早起晚睡",
    "里根绝对高了废除小罗斯福限制资本的基本国策大搞自由经济学释放了金融资本恶魔",
    "就没用过这么难用的软件逼着硬是换回office卡弹窗硬改默认照片查看器",
    "今天天气不错",
    "早上好",
    "支持国产，加油",
    "美帝这么搞下去，不是犹太集团彻底掌控美国，就是美国那天受不了彻底起来反犹",
    "不少人不支持特殊孩子进入普通学校就读，而我认为应当结合孩子的实际情况区别看待。我以前也是一名融合班老师，对此深有体会：轻度特殊儿童在普通集体环境中进步显著",
    "我从小听我外公说他的父母在他小时候把他藏在房梁中间的板上，前几年外公去世了，去世前还在念叨：妈你们哪去了",
]


async def test():
    async with httpx.AsyncClient(timeout=30) as client:
        for text in tests:
            resp = await client.post(
                "https://spark-api-open.xf-yun.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": "lite",
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "你是舆情分析师。分析评论的情感极性、情绪、并识别评论中讨论的主要对象(名称和类型)。"
                                "只输出JSON。"
                                "格式: {\"sentiment\":\"positive|negative|neutral\",\"emotion\":\"...\","
                                "\"target\":\"对象名称\",\"target_type\":\"profession|company|country|person|product|issue|none\","
                                "\"confidence\":0.0-1.0}"
                            ),
                        },
                        {"role": "user", "content": text},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 150,
                },
            )
            raw = resp.json()["choices"][0]["message"]["content"]
            clean = raw.strip()
            if clean.startswith("```"):
                lines = clean.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                clean = "\n".join(lines).strip()
            p = json.loads(clean)
            target = p.get("target") or "-"
            ttype = p.get("target_type") or "-"
            sent = p.get("sentiment") or "?"
            print(f"  [{sent:<8}] 目标:{target:<12} 类型:{ttype:<10} | {text[:25]}...")


asyncio.run(test())
