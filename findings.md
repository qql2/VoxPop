# Findings & Decisions — VoxPop 全岗位态度盘点

## Requirements
- 基于已有爬虫结果做情感分析
- B站 + 微博 + 小红书
- 标注情感极性 + 细粒度情绪 + 态度倾向 + 职业提取
- 出话题排行 + 职业排行
- 独立项目，文件输出，手动调度，可观测

## Research Findings

### 市场方案
- 商业舆情平台：付费、封闭、不能做自定义
- 开源项目：实验级别
- 学术方向：停留在论文
- **结论：自建**

### BettaFish 现有能力
- MindSpider：wb/bili/xhs 可爬取
- SentimentAnalysisModel：含本地模型
- InsightEngine：Deep Search Agent

### 数据库现状（2026-06-27 全量标注后）
| 平台 | 总评论 | 已标 | LLM 标注 | 关键词过滤 |
|------|--------|------|---------|-----------|
| weibo | 1,176 | 1,102 | 164 | 938 |
| bilibili | 276 | 276 | 30 | 246 |
| xhs | 1,349 | 1,313 | 0 | 1,313 |
| **合计** | **2,801** | **2,691** | **194** | **2,497** |

剩余未标（空内容，无实际有效数据）：74 weibo + 36 xhs

### 数据限制 ⚠️
- **没有 IT/编程类评论**："前端""程序员""后端""代码"等关键词在三个平台全部命中为 0 或极低
- 内容以**生活类、时政类、娱乐类**为主
- "程序员"类职业在数据集中没有代表性
- 一些宽泛关键词（"上线"匹配"霸道保姆上线"）可能产生误触发

### 职业排行结果（有效维度 28 个）
热度 Top：保姆(16) > 总统(3) > 老师(3) > 博主(2) > 舰长(2) > 剪辑师(2)
全积极：程序员、军人、海军、安检人员、剪辑师
全消极：律师、工人、金融从业者、海盗、小编、UP主、偶像

### 可扩数据源
需要"程序员"等 IT 类职业评论可以加爬：
1. **V2EX** — 程序员社区，评论丰富
2. **掘金** — 中文技术社区
3. **GitHub Discussions** — 英文，但覆盖面广
4. **知乎** — 各职业讨论都有
5. **即刻** — 年轻用户多，各职业
6. **酷安** — 数码/科技社区

### API 确认
- PackyAPI (DeepSeek V4 Flash) 工作正常
- 每次调用 ~3-5s，约 $0.0001/次
- topic 提取正确率良好（59/194 LLM 标注含有效话题）

## Technical Decisions

| Decision | Rationale |
|----------|-----------|
| 独立表 | 不入侵原表 |
| 级联标注 | 省 60-70% LLM 调用 |
| 幂等写入 | 可安全重跑 |
| topic_id 从 LLM 提取 | 不依赖 daily_topics |
| 并行标注 5 并发 | 速度提升 5-10x |
| labeler_fast.py 独立文件 | 不改原有串行版 |

## 爬取策略（永久）
- **只走 MindSpider CLI**：`cd BettaFish/MindSpider && python main.py --deep-sentiment --platforms <平台>`
- 不能直接跑 MediaCrawler/main.py
- 不能自写爬虫脚本

## Issues Encountered

| Issue | Resolution |
|-------|------------|
| DeepSeek API 空响应 | 3 次重试 + fallback |
| 全中性标注 | JSON parse 失败触发 fallback，待继续观察 |
| topic 全"未分类" | 没从 raw_response 提取 topic_id |
| topic_name 不更新 | ON CONFLICT DO UPDATE 缺 topic_name |
| xhs 串行标注太慢 | 改用 asyncio httpx 并发版，5 并发 |
| 无编程类评论 | 用 MindSpider 爬知乎（已执行，18内容+189评论）|
| MediaCrawler 直接调用 | 纠正：只能用 MindSpider CLI |

## Resources

- GitHub：https://github.com/qql2/VoxPop
- BettaFish：https://github.com/666ghj/BettaFish
- MediaCrawler：https://github.com/NanmiCoder/MediaCrawler
- DeepSeek API：https://api.deepseek.com
- PackyAPI：https://www.packyapi.com
- Planning with Files 模板：~/.openclaw/workspace/skills/planning-with-files/
- 项目目录：~/VoxPop/
- 产出目录：~/VoxPop/outputs/

## Visual/Browser Findings
-
