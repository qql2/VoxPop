# Findings & Decisions — VoxPop 全岗位态度盘点

## Requirements
- 情感标注 + 职业提取 + 排行产出
- 独立项目，可观测

## Research Findings

### 数据库汇总（2026-06-27）
| 平台 | 总评论 | 已标 | LLM |
|------|--------|------|-----|
| weibo | 1,176 | 1,102 | 164 |
| bilibili | 276 | 276 | 30 |
| xhs | 1,349 | 1,313 | 0 |
| zhihu | 5,219 | 5,000 | 0 |
| **合计** | **8,020** | **7,691** | **194** |

### 知乎爬取日志
- MindSpider CLI `--broad-topic → --deep-sentiment --platforms zhihu`
- BroadTopicExtraction：12 新闻源，297 条新闻，63 个关键词
- DeepSentimentCrawling：zhihu 带关键词搜索，5 并发 API
- 数据写入 zhihu_content（141 条）+ zhihu_comment（5,219 条）
- 爬虫目录：`cdp_zhihu_user_data_dir`（首次需扫码，后续自动复用）

### 标注率分析**
- 194 LLM / 7,691 总标注（2.5%）
- zhihu 0 LLM：评论多为泛化讨论（"加油"、"点赞"、"了不起"），不包含职业关键词
- 关键词词典需调整以提升 zhihu 数据的 LLM 命中率

### 技术决策

| 决策 | 原因 |
|------|------|
| 只走 MindSpider CLI | 架构完整性 |
| 爬虫数据直接写入 PostgreSQL（MediaCrawler） | 无需额外 ETL 步骤 |
| models.py String→BigInteger | PostgreSQL 类型严格性要求 |
| 每次改动及时 commit | 可回滚 |
