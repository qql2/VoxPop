-- ============================================
-- VoxPop — 态度盘点模块 数据库表结构
-- 与 MindSpider 独立，但共用同一 PostgreSQL 实例
-- 两张表：attitude_labels + attitude_rankings
-- ============================================

-- 1. 态度标注结果表
-- 每条评论一条记录，UNIQUE 保证幂等（可重跑）
CREATE TABLE IF NOT EXISTS attitude_labels (
    id BIGSERIAL PRIMARY KEY,
    source_platform VARCHAR(32) NOT NULL,       -- 'weibo' | 'bilibili'
    source_type VARCHAR(32) NOT NULL,            -- 'comment' | 'note' | 'video'
    source_id BIGINT NOT NULL,                   -- 指向原表（weibo_note_comment.id 等）
    topic_id VARCHAR(64) DEFAULT NULL,           -- 关联 daily_topics.topic_id
    mentioned_profession VARCHAR(64) DEFAULT NULL, -- 涉及的职业，null 表示无明确指向
    opinion_target VARCHAR(128) DEFAULT NULL,          -- 评论对象（如 "QQ音乐"、"日本"、"警察"）
    target_type VARCHAR(32) DEFAULT NULL,              -- 对象类型: profession|company|country|person|product|issue|none

    sentiment_polarity VARCHAR(16) NOT NULL,     -- positive | negative | neutral
    emotion_finegrained VARCHAR(32) DEFAULT NULL,-- optimism | anxiety | anger | sarcasm | support | doubt | disappointment | indifference
    attitude_tendency VARCHAR(16) DEFAULT NULL,  -- support | oppose | neutral | banter

    label_method VARCHAR(16) NOT NULL,           -- 'model' | 'llm'
    confidence_score REAL DEFAULT NULL,          -- 0~1
    raw_response TEXT DEFAULT NULL,              -- LLM 原始返回（debug用）

    labeled_at BIGINT NOT NULL,                  -- unix timestamp
    batch_id VARCHAR(64) DEFAULT NULL,           -- 批处理ID，方便追溯
    posted_at BIGINT DEFAULT NULL,               -- 原始评论发布时间（unix timestamp）

    -- 幂等约束：同一条评论只标一次
    CONSTRAINT uk_attitude_label UNIQUE (source_platform, source_type, source_id)
);

CREATE INDEX IF NOT EXISTS idx_al_topic ON attitude_labels (topic_id);
CREATE INDEX IF NOT EXISTS idx_al_platform ON attitude_labels (source_platform);
CREATE INDEX IF NOT EXISTS idx_al_polarity ON attitude_labels (sentiment_polarity);
CREATE INDEX IF NOT EXISTS idx_al_profession ON attitude_labels (mentioned_profession);
CREATE INDEX IF NOT EXISTS idx_al_labeled_at ON attitude_labels (labeled_at);
CREATE INDEX IF NOT EXISTS idx_al_batch ON attitude_labels (batch_id);


-- 2. 态度排行结果表（缓存用，避免每次都全量聚合）
CREATE TABLE IF NOT EXISTS attitude_rankings (
    id BIGSERIAL PRIMARY KEY,
    ranking_date DATE NOT NULL,
    topic_id VARCHAR(64) NOT NULL,
    topic_name VARCHAR(255) NOT NULL,

    total_labeled INT DEFAULT 0,                 -- 该话题总标注数
    positive_count INT DEFAULT 0,
    negative_count INT DEFAULT 0,
    neutral_count INT DEFAULT 0,

    positive_ratio REAL DEFAULT 0,                -- 积极占比
    negative_ratio REAL DEFAULT 0,
    neutral_ratio REAL DEFAULT 0,

    optimism_index REAL DEFAULT 0,                -- 乐观指数 (positive / total, 0~1)
    pessimism_index REAL DEFAULT 0,               -- 悲观指数 (negative / total, 0~1)
    heat_index REAL DEFAULT 0,                    -- 热度 = total_labeled 归一化后

    emotion_distribution JSONB DEFAULT NULL,       -- 细粒度情绪分布 {"optimism": 12, "anxiety": 3, ...}
    profession_distribution JSONB DEFAULT NULL,    -- 职业分布 {"程序员": 8, "外卖员": 2, ...}

    created_at BIGINT NOT NULL,

    -- 每个话题每天一条
    CONSTRAINT uk_ranking UNIQUE (ranking_date, topic_id)
);

CREATE INDEX IF NOT EXISTS idx_ar_date ON attitude_rankings (ranking_date);
CREATE INDEX IF NOT EXISTS idx_ar_optimism ON attitude_rankings (optimism_index DESC);
CREATE INDEX IF NOT EXISTS idx_ar_pessimism ON attitude_rankings (pessimism_index DESC);
CREATE INDEX IF NOT EXISTS idx_ar_heat ON attitude_rankings (heat_index DESC);


-- 3. 可选：标注进度追踪表（用于断点续标）
CREATE TABLE IF NOT EXISTS attitude_batch_log (
    id BIGSERIAL PRIMARY KEY,
    batch_id VARCHAR(64) NOT NULL UNIQUE,
    platform VARCHAR(32) NOT NULL,
    date_scope VARCHAR(32) NOT NULL,              -- '2026-06-23' 或 '2000-01-01:2026-06-23'
    total_fetched INT DEFAULT 0,
    labeled_count INT DEFAULT 0,
    llm_count INT DEFAULT 0,
    model_count INT DEFAULT 0,
    failed_count INT DEFAULT 0,
    started_at BIGINT NOT NULL,
    finished_at BIGINT DEFAULT NULL,
    status VARCHAR(16) DEFAULT 'running'          -- running | completed | failed
);

-- 4. 爬取关键词去重表：同一关键词当天只爬一次
CREATE TABLE IF NOT EXISTS crawled_keywords (
    id BIGSERIAL PRIMARY KEY,
    keyword VARCHAR(255) NOT NULL,
    platform VARCHAR(32) NOT NULL,                 -- 'wb' | 'bili' | 'xhs' | 'zhihu'
    crawl_date DATE NOT NULL,
    crawled_at BIGINT NOT NULL,
    CONSTRAINT uk_crawled UNIQUE (keyword, platform, crawl_date)
);

-- 5. 爬虫调度表：每个关键词独立爬取间隔
CREATE TABLE IF NOT EXISTS crawl_schedule (
    id BIGSERIAL PRIMARY KEY,
    keyword VARCHAR(255) NOT NULL,
    platform VARCHAR(32) NOT NULL,                 -- 'wb' | 'bili' | 'xhs' | 'zhihu'
    interval_days INT NOT NULL DEFAULT 1,           -- 爬取间隔天数
    last_crawled_at BIGINT DEFAULT NULL,            -- 上次爬取时间戳
    created_at BIGINT NOT NULL,
    CONSTRAINT uk_schedule UNIQUE (keyword, platform)
);
