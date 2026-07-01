# Progress Log — VoxPop 全岗位态度盘点

## Phase 1-10 完成
- 累计 44,566 条态度标注
- crawl_schedule 关键词分级调度
- response_format json_object 解码层约束
- 三合一控制台（Alpine.js + SSE 实时日志）
- crontab 自动标注 + 护拦 + macOS 通知

## Phase 11: 前端重构与工作流可视化（2026-06-30）

### HTML 模板抽离
- 删掉 `HTML = r"""..."""` 巨量内联字符串（占 ~470 行）
- 移到 `templates/index.html`，IDE 语法高亮/格式化可用
- `sql_query_app.py` 从 728 行 → 258 行（-65%）
- 修复内联字符串中 `\'` 转义导致 JS 解析失败的问题

### 工作流可视化 Tab
- 新增 🔄 工作流 Tab
- 展示完整流程图：反馈闭环 → 爬虫调度 → 自动标注 → 查询展示
- 每步有触发按钮 + 上次运行时间
- 新增后端 API：`/api/feedback`、`/api/crawl-all`、`/api/crawl-history`、`/api/workflow/status`

### Web 爬取按钮修复
- 之前 Web 🕷️ 按钮直接调 MindSpider，跳过 `run_crawl.py`
- 改为调 `run_crawl.py --platforms`，走完整调度流程
- 修复后到期关键词会先写入 daily_topics 再爬

### 下钻弹窗时间透传
- 详情弹窗标题显示「近7天」「近30天」
- 时间筛选条件透传到 `/api/comment-detail` API
- 仅显示筛选范围内的评论

## 关键文件职责
| 文件 | 作用 |
|------|------|
| sql_query_app.py | 后端 API + 路由（258 行） |
| templates/index.html | 前端 HTML + CSS + JS（独立文件） |
| labeler_fast.py | 异步并行标注器（TokenBucket + json_object） |
| run_label_cron.py | 定时标注（护拦+通知） |
| run_crawl.py | 爬虫调度入口（按间隔过滤到期关键词） |
| observer.py | 状态记录 + macOS 通知 |
| db.py | 数据库读写 + 排行聚合 + 调度 |
| feedback_keywords.py | 低样本职业→爬虫关键词 |
| reporter.py | 排行报告生成 |
| professions.py | 22 种职业关键词词典 |
| CLAUDE.md | 项目文档 |
