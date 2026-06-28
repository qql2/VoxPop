# Task Plan: VoxPop — 全岗位态度盘点

## Goal
基于 MindSpider 爬虫（qql2/MindSpider），对网友评论进行**关键词预过滤 → LLM 全任务标注 → 职业排行盘点**。

## Current Phase
Phase 8 ✅ | Phase 9 ⏳ 待启动

## Phases
### 1-3: 调研+骨架+流水线 ✅
### 4: 全量运行（wb/bili/xhs 2,691）✅
### 5: 扩展数据源（zhihu 5,350）✅
### 6: 迭代优化 ✅
### 7: 第二轮反馈闭环 ✅
- 累计 41,050 条标注
### 8: 控制台与可观测体系 ✅
- sql_query_app.py 三合一控制台
- observer.py + run_label_cron.py + crontab
- 当日关键词去重（crawled_keywords 表）

### 9: 数据时效 ⏳ 待启动
- [ ] attitude_labels 加 `posted_at` 列
- [ ] insert_labels 同步写入原始发布时间
- [ ] 回填存量数据
- [x] attitude_labels 增加 posted_at 列（原始评论发布时间）
- [x] 回填存量 41,050 条，覆盖率 100%
- [x] 网页 SQL 查询新增「近7天」「近30天」时间筛选预设
- [x] 爬虫搜索结果按时间排序（知乎/B站/小红书）
  - 知乎: sort=CREATE_TIME, search_time=ONE_WEEK
  - B站: order=LAST_PUBLISH
  - 小红书: SORT_TYPE=time_descending
  - Git commit: 41ca270 (qql2/MindSpider)

## 完整工作流

```
http://127.0.0.1:5000
  ├── 🖥️ 控制台
  ├── 📊 查询  
  └── 📋 运行状态
```

## 永久规则
- 爬虫手动（控制台 / run_crawl.py）
- 标注自动（crontab 凌晨 4 点 / 控制台）
- 错误率 > 50% 立即停止 + Alert
- 当日关键词不重复爬
