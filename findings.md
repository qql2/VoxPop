# Findings — 爬虫调度策略（唯一不重复的内容）

其他技术决策（DeepInfra response_format、前端架构、旧踩坑记录）见 `CLAUDE.md` 和 `.claude/projects/*/memory/`。

## 自适应调度的核心决策

| 决策 | 原因 | 代码位置 |
|------|------|---------|
| 用 COUNT(*) 对比替代 returncode | MindSpider 全崩也返 0，不可靠 | `run_crawl.py` Step 2 & 6 |
| interval_days 边界 [1, 14] | 最短每天爬，最长两周一次 | `db.py:adjust_schedule_interval` |
| 失败只拉长间隔不动 last_crawled_at | 保持下次到期重试 | `run_crawl.py` Step 6 无数据分支 |
| 增加 run_crawl_history.json | 补全爬取可观测性，原系统缺少爬取日志 | `run_crawl.py:_append_crawl_history` |
