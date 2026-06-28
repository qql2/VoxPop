# Progress Log — VoxPop 全岗位态度盘点

## Phase 1-8 完成
- 累计 41,050 条态度标注
- 三合一控制台 + crontab 自动标注
- 当日关键词去重

## Phase 9: 数据时效 + 详情下钻 + Alpine.js（2026-06-29）

### 爬取时效 ✅
- 知乎搜索改为 `sort=CREATE_TIME, search_time=ONE_WEEK`
- B站搜索改为 `order=LAST_PUBLISH`
- 小红书搜索改为 `SORT_TYPE=time_descending`
- git commit 41ca270（qql2/MindSpider），可 `git revert HEAD` 回滚

### 分析时效 ✅
- `attitude_labels` 增加 `posted_at` 列（BIGINT，Unix 时间戳）
- `fetch_unlabeled_comments` 返回各平台原始发布时间
- `labeler.py` / `labeler_fast.py` 透传 posted_at
- `insert_labels` 写入 posted_at
- 回填存量 41,050 条，覆盖率 100%
- SQL 查询预设新增「近7天排行」「近30天排行」

### 岗位详情下钻 ✅
- 新增 `POST /api/comment-detail` API（按职业+情感查评论）
- LEFT JOIN 原始评论表获取评论原文
- 表格中"积极""消极"数字可点击
- 弹窗展示：平台、发布时间、情感、情绪、AI 摘要、评论原文
- 时间戳兼容处理：xhs 毫秒级 vs 其他平台秒级

### 引入 Alpine.js ✅
- CDN 引入 Alpine.js 3.15（31.7k ★, 7.1 kB gzipped）
- Tab 切换从原生 JS 改为 Alpine x-data/x-show
- 弹窗改为 Alpine x-show + x-on:click.self
- 删除旧 switchTab 函数（节省 ~50 行原生 JS）
- 保持与其他原生 JS 函数兼容

## 文件职责
| 文件 | 作用 |
|------|------|
| sql_query_app.py | 三合一控制台（Alpine.js + 原生 JS 混合）|
| labeler_fast.py | 异步并行标注器（TokenBucket 30/s）|
| run_label_cron.py | 定时标注（护拦+通知）|
| run_crawl.py | 手动爬取 CLI + 关键词标记 |
| observer.py | 状态记录 + macOS 通知 |
| db.py | 数据库读写 + 排行聚合 + posted_at |
| reporter.py | 排行报告生成 |
| professions.py | 22 种职业关键词词典 |
| feedback_keywords.py | 低样本职业→爬虫关键词（当日去重）|
