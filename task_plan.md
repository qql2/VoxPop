# Task Plan: VoxPop — 全岗位态度盘点

## Goal
基于 BettaFish/MindSpider 爬虫，对网友评论进行**关键词预过滤 → LLM 全任务标注 → 职业排行盘点**。

## Current Phase
Phase 6 完成 — 闭环已建立，准备第二轮

## Phases
### 1-3: 调研+骨架+流水线 ✅
### 4: 全量运行（wb/bili/xhs 2,691）✅
### 5: 扩展数据源（zhihu 5,350）✅
### 6: 迭代优化 ✅
- [x] 修复 Auth header + 错误处理（error 标记不退回中性）
- [x] API 切换至 DeepInfra Llama 3.1 8B
- [x] Prompt 标准化（前端 9 变体→1，教师/老师归一等）
- [x] SQL 查询 Web 工具（http://127.0.0.1:5000）
- [x] 反馈闭环脚本 feedback_keywords.py

### 7: 第二轮爬取 ⏳ pending
- [ ] `python3 feedback_keywords.py --apply` 写入 low-sample 关键词
- [ ] `cd ~/BettaFish/MindSpider && python3 main.py --deep-sentiment --platforms zhihu`
- [ ] VoxPop 标注新数据
- [ ] 合并完整排行报告

## 永久规则
- 爬数据只走 MindSpider CLI
- 代码改动及时 commit
- 标注重试失败标记 error
- 低样本职业 → 反馈为爬虫关键词 → 闭环

## 完整动作流

```
① MindSpider CLI                ──→  PostgreSQL（评论表）
         ↓
② VoxPop labeler_fast.py        ──→  attitude_labels
   关键词预过滤 → DeepInfra LLM
         ↓
③ 排行产出 + Web 查询（:5000）
         ↓
④ feedback_keywords.py --apply  ──→  daily_topics → 回到 ①
```

去重：爬虫按 content_id，标注按 (platform, type, id) 幂等。

## Git Log（汇总）
```
1982566 feat: 反馈闭环 — 低样本职业→爬虫关键词
9627475 feat: 可交互 SQL 查询 Web 工具
d5c600d fix: prompt 标准化职业名称
b549993 docs: DeepInfra 切换 + 错误处理修复
7ba0196 feat: zhihu 标注支持
734ab93 feat: 全量标注 + 话题修复
```
