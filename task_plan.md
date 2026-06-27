# Task Plan: VoxPop — 全岗位态度盘点

## Goal
基于 BettaFish/MindSpider 爬虫，对网友评论进行**关键词预过滤 → LLM 全任务标注（职业提取+情感分析）→ 话题聚合/职业排行 → 乐观/悲观排行盘点**。

## Current Phase
Phase 6 — 数据已就绪，等待迭代分析

## Phases
### 1-3: 调研+骨架+流水线 ✅
### 4: 全量运行 ✅（wb/bili/xhs 2,691 条）
### 5: 扩展数据源 ✅（知乎 5,350 条 via MindSpider CLI）

### 6: 迭代分析 ⏳ in_progress
- [x] 修复 labeler_fast.py Auth header bug
- [x] 切换 API 至 DeepInfra Llama 3.1 8B
- [x] 修复错误处理：重试失败 → error 标记，不退回中性
- [x] zhihu 成功产出 1,380 LLM 标注（程序员 489 条、前端 45 条）
- [ ] 合并全平台排行报告
- [ ] 职业词典优化（覆盖更多网络用语）
- **Status:** in_progress

## 永久规则
- 爬数据只走 `MindSpider/main.py --deep-sentiment --platforms <平台>`
- 代码改动及时 commit
- 标注重试失败时标记 error，不退回中性

## Errors
| Error | Resolution |
|-------|------------|
| labeler_fast.py 缺 Auth header | 修复后所有 401 变为正确调用 |
| PackyAPI rate limit | 切换 DeepInfra |
| Fallback 中性掩盖失败 | 改为 error 标记，可重标 |
