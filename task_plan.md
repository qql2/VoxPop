# Task Plan: VoxPop — 全岗位态度盘点

## Goal
基于 BettaFish/MindSpider 已有的 B站/微博/小红书爬虫能力，开发独立项目 VoxPop，对网友评论进行**关键词预过滤 → DeepSeek 全任务标注（职业提取 + 情感分析 + 态度识别）→ 话题聚合/职业排行 → 乐观/悲观排行盘点**。

## Current Phase
Phase 5 — 扩展数据源

## Phases

### Phase 1: 方案调研 ✅ complete
- [x] 市场方案调研
- [x] BettaFish 现有能力盘点
- [x] 确定技术路线：离线批处理 + 级联标注
- **Status:** complete

### Phase 2: 项目骨架 ✅ complete
- [x] 目录结构、数据库方案、标注方案、职业维度、输出方式
- [x] 全部代码文件创建 + GitHub 仓库
- [x] 可观测实现（Token/平台/错误/成本）
- **Status:** complete

### Phase 3: 流水线实现 ✅ complete
- [x] 关键词预过滤 + DeepSeek 全任务（职业+情感+情绪+话题）
- [x] 幂等写入、排行聚合、报告输出
- [x] 职业词典 22 种 + 网络用语
- [x] 异步并行版标注器（labeler_fast.py，5 并发）
- **Status:** complete

### Phase 4: 全量运行 ✅ complete
- [x] 建表 ✓
- [x] 修复 DeepSeek API 返回空/JSON 解析问题
- [x] 全量标注 2,691 条（weibo 1,102 + bilibili 276 + xhs 1,313）
- [x] 修复 topic_id 提取 bug（topic 未从 raw_response 写入 DB）
- [x] 产出话题排行 + **职业排行（28 个维度）**
- **Status:** complete

### Phase 5: 扩展数据源 ⏳ in_progress
- [x] 使用 MindSpider 爬知乎（`--platforms zhihu --test`），仅走 MindSpider CLI
- [x] 结果：18 条内容 + 189 条评论（程序员相关）
- [ ] 跑完剩余关键词（前段/AI/996/后端）
- [ ] 对知乎新数据跑全量标注
- [ ] 合并输出完整排行
- **Status:** in_progress

### 永久规则
- 爬数据只走 `MindSpider/main.py --deep-sentiment --platforms <平台>`
- 不能直接运行 MediaCrawler/main.py
- 不能自写爬虫脚本

### Phase 6: 定制与迭代 ⏳ pending
- [ ] 根据产出调整职业词典（移除过宽关键词如"上线"）
- [ ] 根据标注质量调 LLM prompt
- [ ] 评估本地模型替换关键词预过滤
- [ ] 考虑自动调度

## Key Questions
1. ❌ ~~标注方案？~~ → 已定方案 C
2. ❌ ~~词典范围？~~ → 22 种职业
3. ❓ 更多数据源怎么加？→ 评估中
4. ❓ 过宽关键词（"上线"匹配"霸道保姆上线"）是否移除？

## Decisions Made

| 决策 | 选定 | 原因 |
|------|------|------|
| 数据存储 | 独立表 | 不依赖 MindSpider 结构 |
| 标注方案 | 方案 C（级联） | 关键词预过滤省 60-70% LLM 调用 |
| 职业提取 | 词典+LLM兜底 | 先过滤再调用 |
| 输出方式 | JSON + MD 文件 | 最简单起点 |
| 多职业评论 | 全部标注 | 单条 prompt 多职业输出 |
| 并行标注 | asyncio httpx 5 并发 | 比串行快 5-10 倍 |
| topic 提取 | 直接从 LLM 响应提取 | 不依赖 daily_topics 表 |

## Errors Encountered

| Error | Attempt | Resolution |
|-------|---------|------------|
| DeepSeek API 空响应 | 1 | 3 次重试 + fallback |
| 50 条全中性 | 1 | JSON parse 失败触发 fallback |
| topic 全"未分类" | 1 | topic 未从 raw_response 提取到 topic_id |
| topic_name 不更新 | 2 | ON CONFLICT 缺 topic_name |

---

*Template: planning-with-files/templates/task_plan.md*
