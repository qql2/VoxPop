# Progress Log — VoxPop 全岗位态度盘点

## Phase 1-3: 调研+骨架+流水线 ✅
## Phase 4: 全量运行（wb+bili+xhs 2,691）✅
## Phase 5: 扩展数据源（知乎）✅
- BroadTopicExtraction 产出 141 条内容 + 5,219 条评论
- API 切换至 DeepInfra Llama 3.1 8B
- 错误处理改为标记 error

## Phase 6: 迭代优化 ✅
- Prompt 标准化：职业名称归一化
- Flask SQL 查询 Web 工具
- feedback_keywords.py 反馈闭环脚本

## Phase 7: 第二轮反馈闭环（2026-06-28）
### TokenBucket 控流简化 + 压测
- 移除 Semaphore 双层控流，接入 report() 自动调速
- 压测：100 并发零 429，吞吐 35 req/s
- TokenBucket 默认参数：rate=30, capacity=60, max_rate=60
- 新文件: tests/stress_test_deepinfra.py
- Git commit: `b35c2c6`

### 爬虫切换：BettaFish → qql2/MindSpider
- 修复 MediaCrawler 子模块（指针失效、CLI 参数不兼容）
- 修复 config.py 默认 mysql → postgresql、.env 加载优先级

### 全平台爬取
| 平台 | 耗时 | 产出 |
|------|------|------|
| zhihu | ~1h | +5,527 条 |
| weibo | ~1h | +799 条 |
| bilibili | ~1h | +3,260 条 |
| xhs | ~30min | +389 条 |

### 全平台标注（两轮）
- 第一轮：zhihu 10,500 条（LLM 2,509）
- 第二轮：weibo 1,685 + bilibili 3,260 + xhs 379 = 5,324 条（LLM 1,471）
- Token: 输入 1,552,343 / 输出 310,398
- reporter.py bug fix

## Phase 8: 控制台与可观测体系（2026-06-28）

### observer.py
- `write_status()` → run_status.json + run_history.json
- `notify_normal()` → macOS Banner
- `notify_warning()` / `notify_error()` → macOS Alert（不点不消失）

### run_label_cron.py
- `--dry-run` 预览待标注量
- 护拦：0 条 → 退出 / 错误率 > 50% → 停止 + Alert / 错误率 > 10% → 警告
- 自动写 batch_log + run_status + 排行 + 成本计算

### sql_query_app.py 重写为三合一控制台
- 新增 **🖥️ 控制台** Tab（默认页）
  - 平台勾选（微博/B站/小红书/知乎）
  - 🕷️ 爬取按钮 → 直接跑 MindSpider → 实时 SSE 日志
  - 🏷️ 标注按钮 → 直接跑 run_label_cron → 实时 SSE 日志
  - ⏹ 停止按钮 → terminate 子进程
  - 🗑️ 清屏按钮
  - 自动颜色标记（绿色=成功、红色=错误、黄色=警告）
  - 2000 行环形缓冲区，刷新不丢历史
- 保留 **📊 查询** Tab（预设排行 + 自由 SQL）
- 保留 **📋 运行状态** Tab（指标 + 历史 + 告警）

### crontab
- `0 4 * * * python3 run_label_cron.py >> logs/cron.log`

## 最终数据汇总（2026-06-28）
| 平台 | 总计 | LLM 标注 | 本地模型 | 错误 |
|------|------|---------|---------|------|
| zhihu | 31,371 | 8,636 | 22,413 | 322 |
| weibo | 4,451 | 865 | 3,572 | 14 |
| bilibili | 3,536 | 1,115 | 2,383 | 38 |
| xhs | 1,692 | 26 | 1,663 | 3 |
| **合计** | **41,050** | **10,642** | **30,031** | **377** |

## 5-Question Reboot Check
| 问题 | 回答 |
|------|------|
| Where am I? | Phase 8 完成 |
| Where am I going? | 等凌晨 4 点自动标注，或从控制台手动爬取 |
| What's the goal? | 全岗位态度排行盘点 |
| What have I learned? | See findings.md |
| What have I done? | See progress.md (above) |

## 文件职责
| 文件 | 作用 |
|------|------|
| sql_query_app.py | 三合一控制台（爬取/标注/查询/状态） |
| labeler_fast.py | 异步并行标注器（TokenBucket 30/s） |
| run_label_cron.py | 定时标注（护拦+通知） |
| run_crawl.py | 手动爬取 CLI |
| observer.py | 状态记录 + macOS 通知 |
| db.py | 数据库读写 + 排行聚合 |
| reporter.py | 排行报告生成 |
| professions.py | 22 种职业关键词词典 |
| feedback_keywords.py | 低样本职业→爬虫关键词 |

## 去重机制
| 层级 | 方式 |
|------|------|
| MediaCrawler 入库 | SELECT 查 content_id → 更新/插入 |
| VoxPop 标注 | INSERT ON CONFLICT DO UPDATE (platform, type, id) |
