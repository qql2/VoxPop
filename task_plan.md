# Task Plan: VoxPop — 全岗位态度盘点

## Goal
基于 BettaFish/MindSpider 的爬虫能力，对网友评论进行**关键词预过滤 → DeepSeek 全任务标注 → 话题聚合/职业排行 → 乐观/悲观排行盘点**。

## Current Phase
Phase 5 — 扩展数据源完成，等待合并排行

## Phases

### Phase 1: 方案调研 ✅ complete
### Phase 2: 项目骨架 ✅ complete
### Phase 3: 流水线实现 ✅ complete
### Phase 4: 全量运行 ✅ complete
- 2,691 条全量标注（wb/bili/xhs）

### Phase 5: 扩展数据源 ✅ complete
- [x] 使用 **MindSpider CLI** 爬知乎（`--platforms zhihu`），不直接调 MediaCrawler
- [x] 第一层 BroadTopicExtraction：从 12 个新闻源提取 63 个关键词 + 混入岗位关键词
- [x] 第二层 DeepSentimentCrawling：搜索 10 个关键词爬取知乎
- [x] 产出：141 条内容 + 5,219 条评论
- [x] VoxPop 标注 zhihu 数据：5,000 条（0 LLM，全部关键词过滤跳过）
- [x] db.py 添加 zhihu 平台支持

### 永久规则
- **爬数据只走 `MindSpider/main.py --deep-sentiment --platforms <支>`**
- **代码改动及时 commit，便于回滚**

### Phase 6: 定制与迭代 ⏳ pending
- [ ] 合并知乎数据到完整排行
- [ ] 调整职业关键词（zhihu 评论 0 LLM，词典覆盖不足）
- [ ] 评估本地模型

## Decisions Made
| 决策 | 选定 | 原因 |
|------|------|------|
| 数据存储 | 独立表 | 不依赖 MindSpider 结构 |
| 标注方案 | 级联（关键词预过滤+DeepSeek） | 省 60-70% LLM 调用 |
| 并行标注 | asyncio httpx 5 并发 | 比串行快 5-10x |
| 爬取策略 | 只走 MindSpider CLI | 保持架构完整 |
| 代码记录 | 每次改动即 commit | 可回滚 |
