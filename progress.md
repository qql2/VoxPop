# Progress — 爬虫自适应调度

## Phase 12（2026-07-02）

### 修复 Bug
- 🐛 调度更新无条件执行 → `mark_schedule_crawled` 只在 `had_new_data=True` 时跑
- 🐛 硬编码 `port=5432` → 统一用 `AttitudeDB` config 源连接

### 新增功能
- 🔄 自适应间隔调度：爬到新数据缩短、没爬到拉长
- 🔍 爬前预检：杀残留 Chrome 进程 + 清理锁文件
- 📊 爬前爬后 COUNT(*) 对比判断数据获取情况
- 📝 `run_crawl_history.json` 爬取结果可观测性

### 踩坑记录
- 🕳️ MindSpider 返回码 0 但 Chrome 全崩（SIGABRT）
- 🕳️ Chrome 锁文件残留导致下次启动自杀
- 🕳️ DB 端口 5444 vs 5432 不一致
- 🕳️ 6月29日遗漏调度策略的记忆记录

### 新增/修改文件
- `run_crawl.py` — 重写（预检→前后计数→自适应调度→crawl_history）
- `db.py` — 新增 `count_platform_rows()`、`adjust_schedule_interval()`
- `run_crawl_history.json` — 新增可观测性日志
- `.claude/projects/*/memory/crawl-scheduling-strategy.md` — 持久记忆
