#!/usr/bin/env python3
"""批量测试 Spark Lite 目标提取效果 — 30条真实微博评论"""
import os, httpx, json, asyncio, sys

key = os.environ.get("SPARK_API_KEY", "")
if not key:
    print("❌ 请设置环境变量 SPARK_API_KEY")
    sys.exit(1)

TESTS = [
    "这篇博文介绍了格鲁吉亚北部高加索山区的梅斯蒂亚和卡兹别克两大秘境。梅斯蒂亚被誉为格鲁吉亚小瑞士，四周环绕五千米雪山",
    "虽然wps经常不做人，但什么叫批量清理还需付费？说得好像清理C盘还要付钱似的",
    "熬过这关那国内外收益巨大，国内地位没人能撼动，国外哪哪都能说上话。",
    "作为资本家，这是他的真心话，也是所有西方世界（不包括平民）的真心话，但为什么三番五次他要发表这样的言论呢？因为他们迷茫了",
    "如果美国能在霍尔木兹海峡收取过路费，那世界上任何一个国家也都可以跑过去再拦截一道收保护费吧这样大家都扯平了",
    "确实，将来或许有机会与美国对抗，但，绝不是现在，现在看得越清，将来应付就更从容。",
    "之前去了巴统……他们那边有一些旧公园，跟我小时候90年代的小城市公园一模一样，特别梦核",
    "今年以来，不少用户反映，在会员到期续费时发现，原有会员体系已经变化，只能购买更高等级的会员，价格也涨了几十元。",
    "其实…很多软件都默认组件跟缓存存c盘，这也是为啥要三天两头清盘的原因，因为一旦年把不清，你会发现你c盘最少被吃了一半",
    "#法国露天音乐节浪漫变猎场# 浪漫之都名不虚传#法国露天音乐节2人遇刺多人遭性侵#",
    "没太理解，美伊战争美国输了，为什么股市得崩？这俩互为因果的逻辑是什么？",
    "国产替代的困境是钱。免费就全广告，收费就丢用户。金山c端付费率低，只能靠会员资金回笼，所以臃肿失活。",
    "保姆有彩礼么？保姆能管工资卡么？养孩子能叫你妈么？长大了还想要抚养权吗？",
    "特朗普同志大概体验了什么是心有余而力不足。如果每个人的欲望都能实现，地球早已成了碎片",
    "此微博添加位置能帮更多格鲁吉亚同城小伙伴发现本地新鲜事和宝藏打卡地。",
    "难归难，巴基斯坦自从去年大了胜仗，像开挂一样，一下子进入世界舞台的中央，闪闪发光。",
    "云盘缓存可以改位置的，会员权益也一直没变，只是有一些新功能是pro会员独占",
    "美欧等西方国家人其实都是未开化的野蛮生番，还自诩文明，笑死人！",
    "我一朋友，他们很多经济账算不清，如房子……就还在一个屋檐下过，完全aa制。反而不吵架客客气气了。",
    "17卖的越来越好，18系列会下降很大一部分的。因为买了17系列的用户有四分之一都不会买18系列了",
    "从下个月起，美国所有飞机过往别国或美本国的航线，我都要收临时管理费了",
    "评论显示大家被西格纳季小镇的悠闲氛围深深吸引，约40%的网友赞叹其古朴优美的景色和浪漫的中世纪气息",
    "这里面真正应该跌的是百度，结果它反而跌的最少。百度以后除了百度地图还有部分人用，其他方面都会被人遗忘",
    "保姆有彩礼吗？我先不理你彩礼给谁的 是不是都是男出的 彩礼 订婚 各种这样那样 彩礼给你了 你把彩礼给谁是你们家庭问题",
    "只要双方自愿、白纸黑字约定好薪资和权责，不牵扯感情捆绑，对大人和孩子来说都是损失最小的选择。",
    "等一下……也就是说我现在卡是因为wps在线服务开机默认启动吗？",
    "买wps联合会员呀，又便宜又好用，微软的office也不会让你免费用的，想啥呢，一年的会员费够wps用好几年了",
    "其实这反映的是品牌忠诚度溢价。当产品具备不可替代性时，价格弹性确实会降低。",
    "美联储压根就不会加息，都是华尔街在演戏，目前原油已经掉下来了，ai算力最近不断降价",
    "造成的潜在损失呢？比如说如果有违规用人，或者违规决策造成了不良后果",
]


async def test():
    stats = {"total": 0, "has_target": 0, "no_target": 0, "parse_errors": 0}
    target_types = {}

    async with httpx.AsyncClient(timeout=30) as client:
        for i, text in enumerate(TESTS, 1):
            stats["total"] += 1
            try:
                resp = await client.post(
                    "https://spark-api-open.xf-yun.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={
                        "model": "lite",
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "你是舆情分析师。分析评论的情感极性，并识别评论中讨论的主要对象。"
                                    "只输出JSON。"
                                    '格式: {"sentiment":"positive|negative|neutral",'
                                    '"target":"评论讨论的对象名称，无明确对象填null",'
                                    '"target_type":"profession|company|country|person|product|issue|none",'
                                    '"confidence":0.0-1.0}'
                                ),
                            },
                            {"role": "user", "content": text[:800]},
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
                target = p.get("target") or None
                ttype = p.get("target_type") or "none"
                sent = p.get("sentiment") or "?"

                if target:
                    stats["has_target"] += 1
                else:
                    stats["no_target"] += 1

                target_types[ttype] = target_types.get(ttype, 0) + 1

                icon = "✅" if target else "⚠️"
                target_str = f"{target or '-'}".ljust(16)
                ttype_str = f"{ttype}".ljust(12)
                print(f"  [{i:2d}] {icon} {sent:<8} 目标:{target_str} 类型:{ttype_str} | {text[:25]}...")

            except Exception as e:
                stats["parse_errors"] += 1
                print(f"  [{i:2d}] ❌ 失败: {str(e)[:50]} | {text[:25]}...")

    print(f"\n{'='*50}")
    print(f"📊 统计: 共{stats['total']}条 "
          f"有目标{stats['has_target']}({stats['has_target']*100//stats['total']}%) "
          f"无目标{stats['no_target']}({stats['no_target']*100//stats['total']}%) "
          f"失败{stats['parse_errors']}")
    print(f"   目标类型分布: {dict(sorted(target_types.items(), key=lambda x:-x[1]))}")


asyncio.run(test())
