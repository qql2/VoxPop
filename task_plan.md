# Task Plan: VoxPop

Phases 1-11 ✅ → CLAUDE.md 有完整记录

## Phase 12: 爬虫自适应调度策略 ✅
- [x] 确认记忆缺失原因（6月29日遗漏记录持久记忆文件）
- [x] 修复无条件更新调度表的 bug
- [x] 实现自适应间隔（爬前爬后对比 DB 行数）
- [x] 增加爬前预检（清理 Chrome 锁文件）
- [x] 增加 run_crawl_history.json 可观测性
- [x] 踩坑记录写入 findings.md

## 永久规则
- 调度策略：自适应间隔（有数据缩短 `interval_days-1`、无数据拉长 `interval_days+1`），边界 [1, 14]
- 判断依据：爬前爬后 COUNT(*) 对比（不依赖 MindSpider 返回码）
- Chrome 崩溃后自动拉长间隔降频
- 错误率 > 50% 跳过平台
- 调试错误先查 `raw_response`，不调 API
