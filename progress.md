# Progress Log — VoxPop 全岗位态度盘点
<!--
  WHAT: 会话日志 — 按时间顺序记录做了什么、何时做、结果如何。
  WHY: 回答 "What have I done?"。帮助中断后恢复上下文。
  WHEN: 每完成一个阶段或遇到错误时更新。
-->

## Session: 2026-06-23 22:46~23:44

### Phase 1: 方案调研 ✅ complete
- **Status:** complete
- **Started:** 2026-06-23 22:46
- Actions taken: 市场调研、BettaFish 能力盘点、确定技术路线
- Files: `findings.md`

### Phase 2: 项目骨架 ✅ complete
- **Status:** complete
- **Started:** 2026-06-23 23:21
- Actions taken: 创建全部项目文件、初始化 Git、推 GitHub
- Files: config.py, db.py, labeler.py, professions.py, reporter.py, run.py, schema.sql, README.md

## Session: 2026-06-24 ~ 06-26（迭代完善）

### Phase 3: 流水线完善 ✅ complete
- **Status:** complete
- Actions taken:
  - labeler.py v2: 单条 prompt 多职业输出（一次 DeepSeek 调用完成全部任务）
  - 职业词典 17→22 种，加入网络用语
  - 实现可观测（Token 追踪、平台拆分、错误统计、批次日志、成本估算）
  - 加入 xhs 支持、观察接口
- Files: labeler.py, professions.py, reporter.py, db.py, run_xhs.py

### Phase 4: 试跑（2026-06-25~26）⚠️
- 6/25: DeepSeek API 空响应中断
- 6/26: 50 条全中性（JSON parse 失败触发 fallback）
- Resolution: 加 3 次重试 + fallback

## Session: 2026-06-27 全量标注 + 修复

### 文档对齐 ✅
- 按 planning-with-files 模板重写 task_plan.md、findings.md、progress.md、README.md

### 全量标注 ✅
- weibo: 1,102 条（164 LLM/938 关键词过滤）
- bilibili: 276 条（30 LLM/246 过滤）✅
- xhs: 1,313 条（0 LLM/1,313 过滤）✅
- **总计 2,691 条**
- LLM 情感分布: 12 正面 / 25 负面 / 157 中性
- Token: 输入 93,706 / 输出 27,261 / 成本 $0.03

### 修复 topic_id 提取 ✅
- labeler.py/labeler_fast.py 增加 topic_id 提取
- 回填 59 条已有数据的话题
- 修复排行 SQL: 直接用 topic_id 当话题名，不再依赖 daily_topics 表
- 修复 ON CONFLICT DO UPDATE 缺少 topic_name

### 产出职业排行 ✅
- 新增 `profession_ranking.json` + `profession_ranking.md`
- 28 个职业维度排行

### 创建并行版标注器 ✅
- `labeler_fast.py` — asyncio httpx 并发版，5 并发，比串行快 5-10 倍

### 发现的数据限制 ✅
- 爬取数据以生活类/时政类为主，没有 IT/编程类评论
- "前端程序员"等 IT 相关职业在本数据集中自然产出为零
- 部分 keyword 过于宽泛（"上线"匹配到"霸道保姆上线"）

## Test Results

| Test | Input | Expected | Actual | Status |
|------|-------|----------|--------|--------|
| --sql-only 建表 | `python run.py --sql-only` | 三张表创建成功 | 成功 | ✅ |
| 小规模 50 条 | 2026-06-26 | 有正/负面 | 全中性 | ❌ |
| 小规模 50 条 | 2026-06-27 | 有正/负面 | 12+25 有效 | ✅ |
| 全量 weibo | 自动 | 全部标注 | 1102 条 | ✅ |
| 全量 bilibili | 自动 | 全部标注 | 276 条 | ✅ |
| 全量 xhs | 自动 | 全部标注 | 1313 条 | ✅ |
| topic 提取 | 修复后 | 话题可显示 | 57 个话题 | ✅ |
| 职业排行 | 首次产出 | 28 个职业维度 | 28 个 | ✅ |

## Error Log

| Timestamp | Error | Attempt | Resolution |
|-----------|-------|---------|------------|
| 2026-06-23 23:26 | 误写入 MEMORY.md | 1 | 撤回编辑 |
| 2026-06-25 | DeepSeek API 空响应 | 1 | 3 次重试 + fallback |
| 2026-06-26 | 50 条全中性 | 1 | 排查为 JSON parse 失败 |
| 2026-06-27 | xhs 并行标注器卡住 | 1 | 改用 asyncio httpx 并发版 |
| 2026-06-27 | topic 全为"未分类" | 1 | topic 未从 raw_response 提取 |
| 2026-06-27 | topic_name 不更新 | 2 | ON CONFLICT 漏了 topic_name |

## 5-Question Reboot Check

| Question | Answer |
|----------|--------|
| Where am I? | Phase 4 — 全量标注完成，等待新数据源 |
| Where am I going? | 扩展数据源（爬更多平台的 IT/编程类评论） |
| What's the goal? | 对网友评论进行情感标注 → 职业提取 → 乐观/悲观排行盘点 |
| What have I learned? | See findings.md |
| What have I done? | See progress.md (above) |

---

*Template: planning-with-files/templates/progress.md*
