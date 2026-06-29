# Progress Log — VoxPop 全岗位态度盘点

## Phase 1-8 完成
- 累计 41,050 条态度标注
- 三合一控制台 + crontab 自动标注
- 当日关键词去重 + posted_at 时间字段
- Alpine.js 引入 + 岗位详情下钻

## Phase 9: Bug 修复与性能优化（2026-06-29）

### 错误 1：错误计数坏掉（关键 Bug）
- **现象**：UI 显示 LLM=0、错误=0，用户以为没调 API
- **根因**：`batch_label_async` 统计 error 的逻辑是 `label_method='llm' AND confidence=0`，但 error 标记的项 `label_method='error'`，永远匹配不上
- **修复**：改为 `label.get("label_method") == "error"`
- **影响**：之前所有运行的错误数都被低估了

### 错误 2：LLM 返回非 dict 时崩溃
- **现象**：`'int' object has no attribute 'get'`，标注进程直接停
- **根因**：`json.loads` 返回 int 而非 dict，`parsed.get()` 崩溃
- **修复**：`isinstance(parsed, dict)` 检查，非 dict 走 retry

### 错误 3：error 标签不存现场信息
- **现象**：error 标记的 `raw_response=NULL`，无法排查 API 返回了什么
- **根因**：`_error_label()` 没保留 API 响应
- **修复**：`_error_label(raw_response=...)` 现在会保存：
  - HTTP 错误 → 响应体前 500 字符
  - 解析失败 → LLM 实际返回文本
  - 超时/网络异常 → "exception: TimeoutException: ..."
  - 空响应 → "empty_response"

### 性能：`asyncio.gather` 阻塞全部任务
- **现象**：0 LLM 调用也耗 100s+
- **根因**：gather 等所有任务完成，关键词过滤项的 1ms 救不了 API 项的 15s
- **修复**：预分类——关键词过滤先直出，API 单独 gather
- **效果**：0 LLM 批次 ~100s → ~10ms，混合批次 3.3x 提效

### 重试策略调整
- 恢复解析失败重试（LLM 下次可能输出正确格式）
- 429/503 重试（可恢复）
- 其他 4xx 不重试（改什么都没用）

### Web 展示修正
- "LLM" → "LLM 成功"（消除"以为没调 API"的误导）
- "错误" → "API 失败"（明确表示 API 调用失败数）

### 模型诊断结论：DeepInfra Meta-Llama-3.1-8B 能力不足
- **表现**：HTTP 200，但返回内容完全跑题——写代码、说自己是 AI、要求用户先提供评论
- **根因**：8B 参数模型 hold 不住长中文 system prompt + JSON 格式要求
- **测试数据**：50 并发，HTTP 200 率 100%，但解析成功率 ~10%
- **建议**：换更大模型（如 70B）或换 API 提供商

## Phase 10: 关键词分级调度（2026-06-29）

### 问题
`daily_topics` 按 `extract_date` 匹配，跨天没写 `--apply` 就没关键词爬。热门和冷门关键词没区分。

### 方案
- 新建 `crawl_schedule` 表：`(keyword, platform, interval_days, last_crawled_at)`
- 每关键词独立爬取间隔，默认 1 天
- `run_crawl.py` 重构：读调度 → 写 daily_topics → 爬 → 标记 → 更新时间
- `feedback_keywords.py --apply` 写入 `crawl_schedule`，不再写 `daily_topics`
- `--all` 参数强制爬取（忽略调度间隔）
- 已迁移 30 关键词 × 4 平台 = 120 条

### 文件改动
| 文件 | 改动 |
|------|------|
| schema.sql | 新增 crawl_schedule 表 |
| db.py | 新增 get_due_keywords / upsert_schedule / mark_schedule_crawled |
| run_crawl.py | 重构：调度 → daily_topics → 爬取 → 更新时间 |
| feedback_keywords.py | --apply 改为写 crawl_schedule |

### 关键文件职责（更新）
| 文件 | 作用 |
|------|------|
| run_crawl.py | 爬虫调度入口（按间隔过滤到期关键词） |

### 调试规范（memory）
- 新增持久化 memory：`debug-error-labels.md`
- 规则：调试错误时永远先查 `attitude_labels.raw_response`，不直接调 API
- raw_response 为空时才需要进一步排查

### Git Log
```
f1722f5 perf: 分离关键词过滤与 API 调用
44b042d fix: 运行状态面板更清晰的字段名
d5ddd61 fix: 解析失败恢复重试 + Web 字段名修正
（后续 commit pending: error 标签保留 raw_response）
```

## 文件职责
| 文件 | 作用 |
|------|------|
| sql_query_app.py | 三合一控制台（Alpine.js + 原生 JS）|
| labeler_fast.py | 异步并行标注器（含错误处理 + raw_response 保留）|
| run_label_cron.py | 定时标注（护拦+通知）|
| run_crawl.py | 手动爬取 CLI + 关键词标记 |
| observer.py | 状态记录 + macOS 通知 |
| db.py | 数据库读写 + 排行聚合 |
| reporter.py | 排行报告生成 |
| professions.py | 22 种职业关键词词典 |
| feedback_keywords.py | 低样本职业→爬虫关键词 |
