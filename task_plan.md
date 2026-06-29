# Task Plan: VoxPop — 全岗位态度盘点

## Goal
基于 MindSpider 爬虫（qql2/MindSpider），对网友评论进行**关键词预过滤 → LLM 全任务标注 → 职业排行盘点**。

## Current Phase
Phase 10 — 爬虫调度系统（设计中）

## Phases 1-9 ✅
- 累计 41,000+ 条标注
- 三合一控制台（Alpine.js + SSE）
- 自动标注 crontab + 护拦
- posted_at 时间字段 + 时间筛选
- 关键词当日去重
- `json_object` 模式标注（99%+ 成功率）

## Phase 10: 爬虫调度系统 ✅

### 问题
当前: `daily_topics` 表只有 `extract_date`，MindSpider 只查当天的。跨天没写 `--apply` 就没关键词爬。
不合理: 热门关键词每天都有新数据，冷门关键词可能隔很久才有。应该不同关键词不同间隔。

### 方案

```
crawl_schedule 表:
  keyword         VARCHAR   -- 关键词
  platform        VARCHAR   -- 平台 (wb/bili/xhs/zhihu)
  interval_days   INT       -- 爬取间隔（天）
  last_crawled_at BIGINT    -- 上次爬取时间戳
  created_at      BIGINT    -- 创建时间
  CONSTRAINT unique (keyword, platform)

run_crawl.py 流程:
  ① 读 crawl_schedule，查出到期关键词
     WHERE last_crawled_at + interval_days * 86400 <= now()
  ② 写入 daily_topics（extract_date=今天）
  ③ 调 MindSpider 爬取
  ④ 更新 crawl_schedule.last_crawled_at

feedback_keywords.py 调整:
  --apply 时不再直接写 daily_topics
  改为写入 crawl_schedule（新关键词 interval_days=1）
```

### 间隔策略
| 关键词来源 | 初始 interval_days | 说明 |
|-----------|-------------------|------|
| feedback_keywords 新发现 | 1 | 先密集爬，快速补样本 |
| 热门职业 (>50 LLM 样本) | 7 | 已充足，每周跟进 |
| 手动添加 | 用户指定 | 灵活 |

### 文件改动清单
- [ ] schema.sql — 加 `crawl_schedule` 表
- [ ] db.py — 加 `get_due_keywords()` / `upsert_schedule()` / `mark_crawled()`
- [ ] run_crawl.py — 重构：读 schedule → 写 daily_topics → 爬 → 标记
- [ ] feedback_keywords.py — --apply 改为写 schedule 而非每日 topic
- [ ] tests/_test_schedule.py — 验证逻辑
- [ ] 文档 — CLAUDE.md + findings.md 更新

## 完整工作流

```
http://127.0.0.1:5000
  ├── 🖥️ 控制台 — 爬取/标注/实时日志
  ├── 📊 查询 — 排行 + 时间筛选 + 下钻
  └── 📋 运行状态 — 指标/历史/告警

爬虫调度:
  feedback_keywords → crawl_schedule → run_crawl.py → MindSpider → DB
                                           ↑ 按间隔过滤到期关键词
```

## 永久规则
- 爬虫手动（控制台 / run_crawl.py）
- 标注自动（crontab 4AM）
- 错误率 > 50% 跳过平台
- 不同关键词不同爬取间隔
