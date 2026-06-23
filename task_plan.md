# VoxPop — 全岗位态度盘点 任务计划

## 目标

基于 BettaFish/MindSpider 已有的 B站/微博爬虫能力，开发独立子项目 独立项目 VoxPop，对网友评论进行情感标注 → 话题聚合 → 乐观/悲观排行盘点。

## 阶段

### Phase 1: 方案调研 ✅ (2026-06-23)
- [x] 调研市场现有舆情方案（新浪舆情通、舆情录、开源项目）
- [x] 充分了解 BettaFish/MindSpider 现有能力
- [x] 确定技术方案：离线批处理 + 级联标注

### Phase 2: 项目骨架 🚧 (2026-06-23)
- [x] 确定目录结构：独立项目，与 MindSpider 分离但复用同个 PostgreSQL
- [x] 确定数据库方案：不入侵原表，新建 attitude_labels + attitude_rankings
- [x] 确定标注方案：方案 C（关键词基线 + LLM 兜底）
- [x] 确定职业维度：预定义词典匹配 → LLM 补充
- [x] 确定输出方式：JSON + Markdown 文件
- [x] 已创建 10 个文件（config/db/labeler/professions/reporter/run/schema/...）

### Phase 3: 本地模型集成 ⏳
- [ ] 测试 WeiboSentiment_SmallQwen 能否在当前环境跑
- [ ] 或使用 WeiboMultilingualSentiment（huggingface tabularisai 模型）
- [ ] 将本地模型替换 `labeler.py` 中的 `_simple_polarity()` 关键词基线

### Phase 4: 跑通完整链路 ⏳
- [ ] 确认 MindSpider 数据库中有数据
- [ ] 配置 .env 连接数据库 + API
- [ ] 执行 `python run.py --sql-only` 建表
- [ ] 执行 `python run.py --limit 50` 小规模测试
- [ ] 验证输出文件

### Phase 5: 定制与迭代 ⏳
- [ ] 根据需求调整 professions.py 职业词典
- [ ] 根据标注质量调整 LLM prompt
- [ ] 视情况增加更多平台（如后续 MindSpider 修复其他平台）

## 关键决策记录

| 决策 | 选项 | 选定 | 原因 |
|------|------|------|------|
| 数据存储 | 入侵原表 vs 新建独立表 | **独立表** | 不依赖 MindSpider 结构，可重跑 |
| 情感标注 | 纯 LLM vs 纯本地 vs **级联** | **方案 C** | 平衡精度与成本 |
| 职业提取 | LLM 纯提取 vs 词典匹配 | **词典+LLM兜底** | 词典覆盖大部分，LLM 兜边角 |
| 输出方式 | 终端打印 / Streamlit 看板 / **文件输出** | **文件输出** | 最简单的起点 |
| 调度 | 自动定时 vs **手动** | **手动** | 先跑通再考虑自动化 |
| 多职业评论 | 拆句多标 vs 取最主要 | **取第一个匹配** | 占比极小，不过度设计 |
| 记忆范围 | 全局记忆 vs 会话内 | **会话内** | 群聊项目记忆不污染全局 |

## 依赖清单

- asyncpg — PostgreSQL 连接
- openai — LLM API 调用
- pydantic-settings — 配置管理
- （可选）torch + transformers — 本地情感模型

## TODO 待定

- 职业词典最终版（当前预设 17 个通用类）
- 本地模型策略（先跑关键词基线，后续替换）
- 是否接入 InsightEngine 的 WeiboMultilingualSentiment 已有的情感分析能力
