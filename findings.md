# Findings & Decisions — VoxPop 全岗位态度盘点

<!-- WHAT: 知识库。存储调研中发现的一切和做出的决策。持久化外部记忆。 -->

## Requirements

- 基于已有爬虫结果（MindSpider 已写入 PostgreSQL）做情感分析
- 可爬取 B站 + 微博（暂不扩展，因其他平台有兼容问题）
- 标注评论的情感极性 + 细粒度情绪 + 态度倾向
- 提取评论涉及的职业/岗位
- 按话题聚合产出乐观/悲观排行
- 独立项目，不耦合 BettaFish 代码
- 配置自己的 LLM API，不依赖 BettaFish 的 API 配置
- 文件输出（JSON + Markdown），不要看板
- 手动调度

## Research Findings

### 市场方案
- 商业舆情平台（新浪舆情通、舆情录、启信API）：付费、封闭、不能做自定义"态度排行"
- 开源项目（nlp-public-opinion-analysis、Weibo_PublicOpinion_AnalysisSystem）：实验级别，无排行逻辑
- 学术方向（BERTopic+ALBERT-TextCNN、BERT-BiLSTM-DPCNN）：停留在论文阶段
- **结论：没有可直接复用方案，需要自建**

### BettaFish 现有能力
- MindSpider BroadTopicExtraction：从13个平台发现热点 + AI提取关键词
- DeepSentimentCrawling：基于 MediaCrawler，wb/bili 可正常爬取
- SentimentAnalysisModel：含 WeiboSentiment_SmallQwen(Qwen3微调)、WeiboMultilingualSentiment(HuggingFace distilbert)、ML基线(SVM/Bayes/LSTM/XGBoost)
- InsightEngine：Deep Search Agent，已集成情感分析+报告生成
- 数据库表：weibo_note_comment、bilibili_video_comment、daily_topics

### 技术验证
- 级联标注效率估算：60-70%评论被关键词基线覆盖，30-40%走 LLM
- 职业提取：关键词词典覆盖大部分，边角走 LLM
- 多职业评论处理：占比极小，取第一匹配，不过度设计

## Technical Decisions

| Decision | Rationale |
|----------|-----------|
| 独立新表 attitude_labels/attitude_rankings | 不入侵原表结构，可重跑，与 MindSpider 解耦 |
| 级联标注（方案 C） | 平衡精度与成本，先近后远 |
| 关键词词典 + LLM 兜底 | 词典覆盖大部分场景，LLM 处理边界情况 |
| 文件输出 JSON + Markdown | 最简单起点，后续可加看板 |
| 手动调度 | 先跑通再考虑自动化 |
| DS_store + .gitignore | 避免 macOS 产物污染仓库 |

## Issues Encountered

| Issue | Resolution |
|-------|------------|
| 暂无（尚未进入执行阶段） | — |

## Resources

- GitHub 仓库：https://github.com/qql2/VoxPop
- MediaCrawler（MindSpider 底层爬虫）：https://github.com/NanmiCoder/MediaCrawler
- BettaFish 主项目：https://github.com/666ghj/BettaFish
- HuggingFace 多语言情感模型：tabularisai/multilingual-sentiment-analysis
- DeepSeek API：https://api.deepseek.com
- asyncpg 文档：https://magicstack.github.io/asyncpg/
- Skill 模板来源：planning-with-files/templates/

## Visual/Browser Findings

<!-- 尚未涉及浏览器/图片类调研 -->
-
