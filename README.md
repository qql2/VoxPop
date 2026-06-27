# VoxPop — 全岗位态度盘点

> **前置依赖：** 本工具需要 [MindSpider](https://github.com/qql2/MindSpider) 爬取微博/B站/小红书评论写入 PostgreSQL 后才能运行。两者是独立的仓库。

对网友评论进行**关键词预过滤 → DeepSeek 全任务标注（职业提取 + 情感分析 + 态度识别）→ 话题聚合 → 乐观/悲观排行**的离线批处理工具。

## 架构

```
[MindSpider] 爬评论  →      PostgreSQL           →     跑 run.py
(qql2/MindSpider)         weibo_note_comment           读取未标注评论
                          bili_video_comment            级联标注 → attitude_labels
                          xhs_note_comment              聚合排行 → attitude_rankings
                          attitude_labels (新)          输出排行报告 (JSON/MD)
                          attitude_rankings (新)
                          attitude_batch_log (新)
```

## 标注流水线（级联标注）

```
每条评论
    │
    ├─ Step 1: 关键词预过滤
    │   └─ 评论中无职业关键词 → 跳过（返回中性，不调 LLM）
    │
    └─ Step 2: DeepSeek 全任务（仅预过滤命中时调用）
        └─ 一条 prompt 同时完成：
           ├─ 职业提取（多职业支持）
           ├─ 情感极性（positive / negative / neutral）
           ├─ 细粒度情绪（optimism / anxiety / anger / sarcasm / support / doubt / disappointment / indifference）
           ├─ 态度倾向（support / oppose / neutral）
           └─ 话题摘要
```

**为什么用「关键词预过滤」而不是「纯 LLM」？**

> 约 60-70% 的评论不涉及任何职业/岗位（纯生活类）。关键词预过滤直接跳过这些，省掉无意义的 LLM 调用，降低成本和延迟。被过滤掉的评论仍计入"中性/无职业"标注。

## 可观测

每次运行的报告自带观测面板：

| 指标 | 来源 |
|------|------|
| Token 用量（输入/输出/总计） | labeler.py 从 API response 实时采集 |
| 预估成本（USD） | reporter.py 按 Token 量 + 单价计算 |
| 各平台标注量 | db.py 按 source_platform 分组 |
| 标注方法分布（LLM vs 本地关键词） | labeler.py label_method 字段 |
| 情感分布 | attitude_labels sentiment_polarity 聚合 |
| 错误数 | labeler.py 重试失败 + 解析失败 |
| 批次日志 | attitude_batch_log 表 |

## 输出

```
outputs/
└── 2026-06-26/
    ├── ranking.json    # 结构化排行数据（含完整观测面板）
    └── ranking.md      # 可读排行报告（乐观 TOP10 + 悲观 TOP10 + 热度 TOP10）
```

## 职业词典

当前覆盖 **22 种职业**，包含大量网络用语、隐含指代、俚语：

程序员 / 产品经理 / 运营 / 设计师 / 教师 / 学生 / 医生 / 护士 / 警察 / 公务员 / 金融从业者 / 外卖员 / 快递员 / 网约车司机 / 销售 / 自媒体 / 主播 / 保姆·家政 / 保安 / 军人 / 律师 / 农民

词典在 `professions.py` 中管理，可随时扩展。

## 快速开始

```bash
cd VoxPop

# 1. 复制配置
cp .env.example .env
# 编辑 .env，填数据库和 API 密钥

# 2. 安装依赖
pip install asyncpg openai httpx pydantic-settings

# 3. 初始化数据库（只建表）
python run.py --sql-only

# 4. 全量标注（默认跑昨天数据）
python run.py

# 5. 指定日期
python run.py --date 2026-06-23

# 6. 小规模测试（只标 200 条）
python run.py --limit 200

# 7. 单独跑小红书
python run_xhs.py
```

## 自定义

- `professions.py` — 修改/扩充职业关键词词典
- `labeler.py` 中 `_SYSTEM_PROMPT` — 调整 LLM prompt 格式
- `config.py` — 调整数据库、API、输出路径

## 项目状态

- ✅ Phase 1（方案调研）— 完成
- ✅ Phase 2（项目骨架）— 完成，代码已推 GitHub
- ✅ Phase 3（流水线实现）— 完成
- ⏳ Phase 4（全量运行）— 待触发
- ⏳ Phase 5（定制与迭代）— 待开始

## 仓库

https://github.com/qql2/VoxPop
