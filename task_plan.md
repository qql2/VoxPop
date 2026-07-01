# Task Plan: VoxPop — 全岗位态度盘点

## Goal
基于 MindSpider 爬虫（qql2/MindSpider），对网友评论进行**关键词预过滤 → LLM 全任务标注 → 职业排行盘点**。

## Current Phase
Phase 11 ✅

## Phases 1-10 ✅
- 累计 44,566 条标注
- 三合一控制台（Alpine.js + SSE 实时日志）
- 自动标注 crontab + 护拦（错误率 >50% 跳过平台）
- posted_at 时间字段 + 时间/样本量筛选
- crawl_schedule 关键词分级调度系统
- `response_format: json_object` 解码层约束标注
- 岗位详情下钻弹窗

## Phase 11: 前端重构与工作流可视化 ✅
- [x] 内联 HTML 抽离到 `templates/index.html`（728→258 行）
- [x] 新增 🔄 工作流 Tab（流程图 + 触发按钮 + 上次运行时间）
- [x] Web 🕷️ 按钮改为调用 `run_crawl.py`（走调度）
- [x] 爬取历史展示（各平台统计 + 详细记录）
- [x] 新增 `/api/feedback`、`/api/crawl-all`、`/api/crawl-history` API
- [x] 详情下钻弹窗透传时间筛选

## 完整工作流

```
http://127.0.0.1:5000
  ├── 📊 查询 — 排行 + 时间/样本过滤 + 下钻
  ├── 📋 运行状态 — 标注指标 + 历史记录
  ├── 🔄 工作流 — 流程图 + 触发按钮 + 爬取历史
  └── 🖥️ 控制台 — 爬取/标注/实时日志

爬虫调度:
  feedback_keywords → crawl_schedule → run_crawl.py → MindSpider → DB
                                           ↑ 按间隔过滤到期关键词
```

## 永久规则
- 爬虫手动（控制台 / run_crawl.py），需扫码
- 标注自动（crontab 4AM / 控制台）
- 错误率 > 50% 跳过平台
- 不同关键词不同爬取间隔
- 调试错误先查 `raw_response`，不调 API
