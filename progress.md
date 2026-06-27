# Progress Log — VoxPop 全岗位态度盘点

## 2026-06-23 骨架搭建 ✅
## 2026-06-24~26 流水线完善 ✅

## 2026-06-27 全量标注 + 修复 + 知乎爬取 + DeepInfra

### 全量标注（wb/bili/xhs）✅
- weibo 1,102 · bilibili 276 · xhs 1,313 → 2,691

### 知乎爬取（MindSpider CLI）✅
- BroadTopicExtraction → 12 新闻源 → 63 个关键词 + 岗位关键词混入
- `--deep-sentiment --platforms zhihu` → 141 内容 + 5,219 评论
- 数据写入 PostgreSQL zhihu_content/zhihu_comment

### 切换 API & 错误处理修复 ✅
- 发现 labeler_fast.py 缺少 Authorization header → 所有 5000+ 条 401 后 fallback 中性
- 修复 auth header 后首批跑到 866 LLM（被 PackyAPI rate limit）
- 切换至 **DeepInfra Llama 3.1 8B**（`meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo`）
- 修复错误处理：重试全失败 → 标记 `label_method=error`，不退回中性

### zhihu 标注结果（DeepInfra）✅
| 维度 | 值 |
|------|-----|
| 有效 LLM 标注 | 1,380 条 |
| 标注错误 | 10 条 |
| 关键词过滤跳过 | 3,960 条 |

Top 职业：
- 程序员 489（104正/302负/83中）
- 前端类合计 45（20正/25负）
- 老师 21 · 保姆 19 · 公务员 14 · 医生 13 · 外卖员 12

## 全量数据汇总
| 平台 | 总计 | LLM | 积极 | 消极 | 中性 |
|------|------|-----|------|------|------|
| weibo | 1,102 | 164 | 9 | 16 | 1,077 |
| bilibili | 276 | 30 | 3 | 9 | 264 |
| xhs | 1,313 | 0 | 0 | 0 | 1,313 |
| zhihu | 5,350 | 1,380 | 238 | 589 | 4,523 |
| **合计** | **8,041** | **1,574** | **250** | **614** | **7,177** |

## 5-Question Reboot Check
| 问题 | 回答 |
|------|------|
| Where am I? | Phrase 6 — 数据已就绪，等待迭代分析 |
| Where am I going? | 合并排行 + 职业词典优化 |
| What's the goal? | 全岗位态度排行盘点 |
| What have I learned? | See findings.md |
| What have I done? | See above |
