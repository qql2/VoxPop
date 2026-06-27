# Progress Log — VoxPop 全岗位态度盘点

## Session: 2026-06-23 骨架搭建
## Session: 2026-06-24~26 流水线完善

## Session: 2026-06-27 全量标注 + 修复 + 知乎爬取

### 全量标注 ✅
- weibo: 1,102 条（164 LLM）
- bilibili: 276 条（30 LLM）
- xhs: 1,313 条（0 LLM）
- Token: 输入 93,706 / 输出 27,261 / 成本 $0.03

### 修复 topic_id + 产出排行 ✅
- 修复 topic 未从 raw_response 提取的问题
- 产出话题排行（57 个话题）+ 职业排行（28 个维度）

### 知乎爬取（MindSpider CLI）✅
- 第一层：`--broad-topic` → 12 新闻源 → 63 个关键词 + 岗位关键词混入
- 第二层：`--deep-sentiment --platforms zhihu` → 141 内容 + 5,219 评论
- 已通过 MediaCrawler 写入 PostgreSQL（zhihu_content/zhihu_comment）

### zhihu 标注 ✅
- 5,000 条已写入 attitude_labels（0 LLM，全部被关键词过滤跳过）
- db.py 新增 zhihu 平台支持

### 永久规则确立 ✅
- 只走 MindSpider CLI
- 代码改动及时 commit

## 全量数据汇总
| 平台 | 总计 | LLM | 关键词过滤 | 积极 | 消极 | 中性 |
|------|------|-----|-----------|------|------|------|
| weibo | 1,102 | 164 | 938 | 9 | 16 | 1,077 |
| bilibili | 276 | 30 | 246 | 3 | 9 | 264 |
| xhs | 1,313 | 0 | 1,313 | 0 | 0 | 1,313 |
| zhihu | 5,000 | 0 | 5,000 | 0 | 0 | 5,000 |
| **合计** | **7,691** | **194** | **7,497** | **12** | **25** | **7,654** |

## Error Log
| Timestamp | Error | Resolution |
|-----------|-------|------------|
| 06-23 | 误写入 MEMORY.md | 撤回 |
| 06-25 | DeepSeek API 空响应 | 3 次重试 |
| 06-26 | 50 条全中性 | JSON parse fallback |
| 06-27 | topic 全"未分类" | 提取 topic_id 修复 |
| 06-27 | xhs 串行太慢 | 并行版 5 并发 |
| 06-27 | MediaCrawler PostgreSQL 类型不符 | models.py String→BigInteger |
| 06-27 | zhihu 爬虫 0 LLM 标注 | 词典覆盖不足，待优化 |

## 5-Question Reboot Check
| Question | Answer |
|----------|--------|
| Where am I? | Phase 6 — 定制与迭代 |
| Where am I going? | 合并排行 + 优化职业词典 |
| What's the goal? | 全岗位态度排行盘点 |
| What have I learned? | See findings.md |
| What have I done? | See above |
