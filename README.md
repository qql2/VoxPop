# VoxPop — 全岗位态度盘点

> **前置依赖：** 本工具需要 [MindSpider](https://github.com/qql2/MindSpider) 爬取微博/B站评论写入 PostgreSQL 后才能运行。两者是独立的仓库，需先运行 MindSpider 采集数据。

基于 [MindSpider](https://github.com/qql2/MindSpider) 爬取的微博/B站评论，对网友态度进行**情感标注 → 话题聚合 → 乐观/悲观排行**的离线批处理工具。

## 架构

```
[MindSpider] 爬评论  →      PostgreSQL           →     跑 run.py
(qql2/MindSpider)         weibo_note_comment           读取未标注评论
                          bili_video_comment           级联标注 → attitude_labels
                          attitude_labels (新)        聚合排行 → attitude_rankings
                          attitude_rankings (新)      输出排行报告 (JSON/MD)
```

## 快速开始

```bash
cd AttitudeEngine

# 1. 复制配置
cp .env.example .env
# 编辑 .env，填数据库和 API 密钥

# 2. 安装依赖
pip install asyncpg openai pydantic-settings

# 3. 跑一遍（只建表）
python run.py --sql-only

# 4. 手动标注 + 排行（昨天数据）
python run.py

# 5. 小规模测试（只标 200 条）
python run.py --limit 200

# 6. 指定日期
python run.py --date 2026-06-23
```

## 输出

```
outputs/
└── 2026-06-23/
    ├── ranking.json    # 结构化排行数据
    └── ranking.md      # 可读排行报告（乐观 TOP10 + 悲观 TOP10 + 热度 TOP10）
```

## 标注逻辑

1. **本地模型基线**（极简规则/可选小模型） → 高置信度直接输出
2. **LLM 兜底**（DeepSeek API） → 低置信度/需要细粒度情绪时调用
3. **职业匹配** → 关键词词典优先 + LLM 兜底

## 自定义

- `professions.py` — 修改职业关键词词典
- `labeler.py` 中 `_simple_polarity()` — 替换为你的本地模型
- `config.py` — 调整置信度阈值、API 配置
