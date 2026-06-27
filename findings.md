# Findings & Decisions — VoxPop 全岗位态度盘点

## 最终数据（2026-06-27）
| 平台 | 总计 | LLM | 积极 | 消极 |
|------|------|-----|------|------|
| weibo | 1,102 | 164 | 9 | 16 |
| bilibili | 276 | 30 | 3 | 9 |
| xhs | 1,313 | 0 | 0 | 0 |
| zhihu | 5,350 | 1,771 | — | — |
| **合计** | **8,041** | **1,965** | — | — |

## Top 职业（LLM 标注，标准化 prompt）
- 程序员 379 · 管理岗 85 · 前端工程师 46 · 保姆 28 · 教师 27

## 关键问题记录
| 问题 | 修复 |
|------|------|
| labeler_fast.py 缺 Auth header | 全部 401，加了 Bearer token |
| PackyAPI rate limit | 切换 DeepInfra Llama 3.1 8B |
| 重试失败退回中性 | 改为 error 标记，不丢失数据 |
| 职业名称碎片化 | Prompt 规则 5 标准化 + 映射表 |
| 低样本职业无后续 | feedback_keywords.py 闭环 |

## 技术决策
| 决策 | 原因 |
|------|------|
| API: DeepInfra Llama 3.1 8B | 比 PackyAPI 稳定，响应 0.7-1.3s |
| 错误标记 error | 可重标，不丢失 |
| Prompt 标准化 | 职业名称归一化 |
| Flask Web 工具 | 即开即用，无构建步骤 |
| 反馈闭环 | 低样本职业→关键词→爬取→标注 |
