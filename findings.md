# Findings & Decisions — VoxPop 全岗位态度盘点

## 最终数据（2026-06-28）
| 平台 | 总计 | LLM 标注 | 本地模型 | 错误 |
|------|------|---------|---------|------|
| zhihu | 31,371 | 8,636 | 22,413 | 322 |
| weibo | 4,451 | 865 | 3,572 | 14 |
| bilibili | 3,536 | 1,115 | 2,383 | 38 |
| xhs | 1,692 | 26 | 1,663 | 3 |
| **合计** | **41,050** | **10,642** | **30,031** | **377** |

## 关键问题记录
| 问题 | 原因 | 修复 |
|------|------|------|
| MediaCrawler --type 报错 | 子模块更新 CLI 改变 | platform_crawler.py 改参数名 |
| qql2/MindSpider 连不上 DB | 默认 mysql | 改 postgresql + .env 优先级 |
| reporter.py KeyError | 未处理 label_method='error' | 加 'error' 键 |
| xhs LLM 极低 | 小红书评论多为生活类 | 26/1,692 = 1.5%，正常 |
| 爬取输出缓冲 | subprocess.run 缓冲 | API 直接跑 MindSpider + PYTHONUNBUFFERED |
| xhs 时间戳错乱 | 毫秒级 create_time | posted_at 统一处理：>10^10 则除以 1000 |

## 技术决策
| 决策 | 原因 |
|------|------|
| 前端框架: Alpine.js (31.7k ★) | 7.1 kB CDN，声明式，不构建，和 Flask 模板兼容 |
| 详情下钻用独立 API + 弹窗 | 后端 JOIN 查评论 + 前端模态框展示 |
| posted_at 存储原始发布时间 | 支持 SQL 时间过滤（近7天/近30天） |
| 时间戳归一化（秒级/毫秒级兼容） | xhs create_time 为毫秒级，其他平台为秒级 |
| brief 摘要不额外消耗 Token | 与情感分析同一 LLM 调用返回，max_tokens=400 配额内 |

## 完整工作流

```
http://127.0.0.1:5000
  ├── 🖥️ 控制台 — 爬取/标注 + 实时日志
  ├── 📊 查询 — 排行 + 时间筛选 + 点击下钻
  └── 📋 运行状态 — 指标 + 历史 + 告警
```
