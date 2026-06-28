# Findings & Decisions — VoxPop 全岗位态度盘点

## 最终数据（2026-06-28）
| 平台 | 总计 | LLM 标注 | 本地模型 | 错误 |
|------|------|---------|---------|------|
| zhihu | 31,371 | 8,636 | 22,413 | 322 |
| weibo | 4,451 | 865 | 3,572 | 14 |
| bilibili | 3,536 | 1,115 | 2,383 | 38 |
| xhs | 1,692 | 26 | 1,663 | 3 |
| **合计** | **41,050** | **10,642** | **30,031** | **377** |

## DeepInfra 压测结果
| 并发 | 200 | 429 | 吞吐/s | p50 |
|------|-----|-----|--------|-----|
| 5 | 60 | 0 | 7.5 | 0.54s |
| 20 | 60 | 0 | 19.2 | 0.53s |
| 50 | 60 | 0 | 28.1 | 1.53s |
| 100 | 60 | 0 | 35.1 | 1.56s |

## 关键问题记录
| 问题 | 原因 | 修复 |
|------|------|------|
| MediaCrawler --type 报错 | 子模块更新 CLI 改变 | platform_crawler.py 改参数名 |
| qql2/MindSpider 连不上 DB | 默认 mysql，加载优先级问题 | 改 postgresql + 修复 .env 优先级 |
| reporter.py KeyError | 未处理 label_method='error' | 初始化 dict 加 'error' |
| xhs LLM 极低 | 小红书评论多为生活类 | 26/1,692 = 1.5%，正常现象 |
| run_crawl.py 输出缓冲 | subprocess.run 缓冲输出 | API 改为直接跑 MindSpider + PYTHONUNBUFFERED |

## 📌 待解决问题：数据时效

### 问题 A：爬取时效 — 旧数据占额度
- **表现**：同一个关键词（如"程序员"）每次爬都是那批热门旧文章，占满 50 条额度
- **根因**：平台搜索 API 默认按相关度/热度排序，新文章排在后面，额度满了就爬不到
- **影响**：每次 ~1h 爬取，大部分额度被旧数据消耗，新数据获取效率低
- **可能解法**：
  - 利用搜索 API 的 `time_interval` / `sort` 参数（如知乎搜索支持按时间排序）
  - 或：对已有样本的关键词，只爬取发布时间 > 最近一次爬取时间的

### 问题 B：分析时效 — 结果不区分新旧
- **b**：attitude_labels 只存了 `labeled_at`（标注时间），没有存 `posted_at`（原始评论发布时间）
  ```sql
  labeled_at BIGINT NOT NULL  -- 我们标注的时间
  -- 缺少: posted_at         -- 评论在平台上发布的时间
  ```
- **影响**：所有 SQL 查询都只能看全量数据，无法看"最近7天""最近一个月"的趋势
- **方案**：
  1. attitude_labels 加 `posted_at` 列
  2. db.py insert_labels 同步写入
  3. 存量数据从原始评论表回填
  4. 网页查询加时间筛选预设

### 原始评论表的时间字段
| 表 | 时间字段 |
|------|----------|
| zhihu_comment | publish_time, add_ts |
| weibo_note_comment | create_time, add_ts |
| bilibili_video_comment | create_time, add_ts |
| xhs_note_comment | create_time, add_ts |

`add_ts` 是 MediaCrawler 入库时间（对我们没意义），`publish_time`/`create_time` 才是原始发布时间。

## 技术决策
| 决策 | 原因 |
|------|------|
| 只用 TokenBucket，移除 Semaphore | 单层控流更简洁 |
| TokenBucket rate=30 | 压测 35 req/s 无 429 |
| 爬虫切换至 qql2/MindSpider | 用户要求 |
| .env 自身目录优先 | 避免误读 |
| 爬虫手动 + 标注定时 | 爬需要扫码 |
| 护拦：错误率 > 50% 停止 | 防无限烧钱 |
| macOS Alert 弹窗 | Banner 会消失 |
| 状态写入 JSON + 网页展示 | 错过弹窗也能查 |
| 当日关键词去重（crawled_keywords 表） | 同一天不重复爬同关键词 |

## 完整工作流

```
http://127.0.0.1:5000
  ├── 🖥️ 控制台 — 一键爬取/标注 + 实时日志
  ├── 📊 查询 — SQL 排行查询
  └── 📋 运行状态 — 指标 + 历史 + 告警
```

去重：MediaCrawler 按 content_id 查重，VoxPop 按 (platform, type, id) 幂等写入。
