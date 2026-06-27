"""
数据库操作封装
读取 MindSpider 的原始评论表，写入 attitude_labels / attitude_rankings
"""

import asyncpg
from typing import List, Dict, Any, Optional
from datetime import date, datetime
from config import settings
from professions import PROFESSION_KEYWORDS


class AttitudeDB:
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            database=settings.DB_NAME,
            min_size=1,
            max_size=5,
        )

    async def close(self):
        if self.pool:
            await self.pool.close()

    # ---- 读取原始评论 ----

    async def fetch_unlabeled_comments(
        self,
        platform: str,
        after_id: int = 0,
        limit: int = 500,
        date_scope: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        查出未标注的评论/帖子
        platform: 'weibo' 或 'bilibili'
        """
        if platform == "weibo":
            table = "weibo_note_comment"
            id_field = "id"
            content_field = "content"
            parent_id_field = "note_id"
        elif platform == "bilibili":
            table = "bilibili_video_comment"
            id_field = "id"
            content_field = "content"
            parent_id_field = "video_id"
        elif platform == "xhs":
            table = "xhs_note_comment"
            id_field = "id"
            content_field = "content"
            parent_id_field = "note_id"
        elif platform == "zhihu":
            table = "zhihu_comment"
            id_field = "id"
            content_field = "content"
            parent_id_field = "comment_id"
        else:
            raise ValueError(f"不支持的平台: {platform}")

        # LEFT JOIN attitude_labels 过滤已标注
        sql = f"""
            SELECT c.{id_field} AS source_id, c.{content_field} AS content,
                   c.add_ts, c.{parent_id_field} AS parent_id, '{platform}' AS source_platform,
                   'comment' AS source_type
            FROM {table} c
            LEFT JOIN attitude_labels al
                ON al.source_platform = '{platform}'
                AND al.source_type = 'comment'
                AND al.source_id = c.{id_field}::bigint
            WHERE (al.id IS NULL OR al.label_method = 'error')
              AND c.{id_field} > $1
              AND c.content IS NOT NULL
              AND length(trim(c.content)) > 0
            ORDER BY c.{id_field}
            LIMIT $2
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, after_id, limit)
        return [dict(r) for r in rows]

    # ---- 写入标注结果 ----

    async def insert_labels(self, labels: List[Dict[str, Any]]):
        """批量写入 attitude_labels"""
        if not labels:
            return
        sql = """
            INSERT INTO attitude_labels
                (source_platform, source_type, source_id, topic_id,
                 mentioned_profession, opinion_target, target_type,
                 has_profession, professions,
                 sentiment_polarity, emotion_finegrained,
                 attitude_tendency, label_method, confidence_score,
                 raw_request, raw_response, labeled_at, batch_id)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18)
            ON CONFLICT (source_platform, source_type, source_id)
            DO UPDATE SET
                topic_id = EXCLUDED.topic_id,
                mentioned_profession = EXCLUDED.mentioned_profession,
                opinion_target = EXCLUDED.opinion_target,
                target_type = EXCLUDED.target_type,
                has_profession = EXCLUDED.has_profession,
                professions = EXCLUDED.professions,
                sentiment_polarity = EXCLUDED.sentiment_polarity,
                emotion_finegrained = EXCLUDED.emotion_finegrained,
                attitude_tendency = EXCLUDED.attitude_tendency,
                label_method = EXCLUDED.label_method,
                confidence_score = EXCLUDED.confidence_score,
                raw_request = EXCLUDED.raw_request,
                raw_response = EXCLUDED.raw_response,
                labeled_at = EXCLUDED.labeled_at,
                batch_id = EXCLUDED.batch_id
            WHERE attitude_labels.label_method = 'error'
        """
        now = int(datetime.now().timestamp())
        async with self.pool.acquire() as conn:
            await conn.executemany(
                sql,
                [
                    (
                        l["source_platform"],
                        l["source_type"],
                        l["source_id"],
                        l.get("topic_id"),
                        l.get("mentioned_profession"),
                        l.get("opinion_target"),
                        l.get("target_type"),
                        l.get("has_profession"),
                        l.get("professions"),
                        l["sentiment_polarity"],
                        l.get("emotion_finegrained"),
                        l.get("attitude_tendency"),
                        l["label_method"],
                        l.get("confidence_score"),
                        l.get("raw_request"),
                        l.get("raw_response"),
                        now,
                        l.get("batch_id"),
                    )
                    for l in labels
                ],
            )

    # ---- 批次日志 ----

    async def write_batch_log(
        self, batch_id: str, platform: str, date_scope: str,
        total_fetched: int, labeled_count: int, llm_count: int,
        model_count: int, failed_count: int
    ):
        now = int(datetime.now().timestamp())
        sql = """
            INSERT INTO attitude_batch_log
                (batch_id, platform, date_scope, total_fetched,
                 labeled_count, llm_count, model_count, failed_count,
                 started_at, status)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,'running')
        """
        async with self.pool.acquire() as conn:
            await conn.execute(sql, batch_id, platform, date_scope,
                               total_fetched, labeled_count, llm_count, model_count, failed_count, now)

    async def finish_batch_log(self, batch_id: str):
        now = int(datetime.now().timestamp())
        sql = """
            UPDATE attitude_batch_log
            SET finished_at=$1, status='completed'
            WHERE batch_id=$2
        """
        async with self.pool.acquire() as conn:
            await conn.execute(sql, now, batch_id)

    async def fail_batch_log(self, batch_id: str):
        now = int(datetime.now().timestamp())
        sql = """
            UPDATE attitude_batch_log
            SET finished_at=$1, status='failed'
            WHERE batch_id=$2
        """
        async with self.pool.acquire() as conn:
            await conn.execute(sql, now, batch_id)

    async def get_batch_stats(self, batch_id: str = None) -> list:
        """获取批次统计，用于观察报告"""
        if batch_id:
            sql = "SELECT * FROM attitude_batch_log WHERE batch_id=$1 ORDER BY started_at"
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(sql, batch_id)
        else:
            sql = "SELECT * FROM attitude_batch_log ORDER BY started_at DESC LIMIT 20"
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(sql)
        return [dict(r) for r in rows]

    async def get_label_stats(self, batch_id: str = None) -> dict:
        """获取标注统计：平台分布、方法分布、错误统计
        传递 batch_id 则只查该批次，否则查全部
        """
        if batch_id:
            conditions = "WHERE batch_id = $1"
            params = (batch_id,)
        else:
            conditions = "WHERE 1=1"
            params = ()
        sql = f"""
            SELECT
                source_platform,
                label_method,
                COUNT(*)::int as cnt,
                COUNT(*) FILTER (WHERE raw_response LIKE 'label_error:%')::int as errors
            FROM attitude_labels
            {conditions}
            GROUP BY source_platform, label_method
            ORDER BY source_platform, label_method
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
        return [dict(r) for r in rows]

    # ---- 排行聚合 ----

    async def compute_rankings(self, rank_date: date):
        """按话题聚合情感统计，写入 attitude_rankings"""
        # 从 professions.py 动态生成职业分布 SQL 片段
        prof_filters = []
        for prof in PROFESSION_KEYWORDS:
            prof_filters.append(
                f"'{prof}', COUNT(*) FILTER (WHERE mentioned_profession = '{prof}')::int"
            )
        prof_sql_part = ", ".join(prof_filters)

        sql = f"""
            INSERT INTO attitude_rankings (
                ranking_date, topic_id, topic_name,
                total_labeled, positive_count, negative_count, neutral_count,
                positive_ratio, negative_ratio, neutral_ratio,
                optimism_index, pessimism_index, heat_index,
                emotion_distribution, profession_distribution,
                created_at
            )
            SELECT
                $1::date,
                COALESCE(topic_id, '__untagged__'),
                CASE WHEN topic_id IS NULL THEN '未分类' ELSE topic_id END,
                COUNT(*)::int,
                COUNT(*) FILTER (WHERE sentiment_polarity = 'positive')::int,
                COUNT(*) FILTER (WHERE sentiment_polarity = 'negative')::int,
                COUNT(*) FILTER (WHERE sentiment_polarity = 'neutral')::int,
                ROUND(COUNT(*) FILTER (WHERE sentiment_polarity = 'positive')::numeric / NULLIF(COUNT(*), 0), 4),
                ROUND(COUNT(*) FILTER (WHERE sentiment_polarity = 'negative')::numeric / NULLIF(COUNT(*), 0), 4),
                ROUND(COUNT(*) FILTER (WHERE sentiment_polarity = 'neutral')::numeric  / NULLIF(COUNT(*), 0), 4),
                ROUND(COUNT(*) FILTER (WHERE sentiment_polarity = 'positive')::numeric / NULLIF(COUNT(*), 0), 4),
                ROUND(COUNT(*) FILTER (WHERE sentiment_polarity = 'negative')::numeric / NULLIF(COUNT(*), 0), 4),
                ROUND(COUNT(*)::numeric / NULLIF(MAX(COUNT(*)) OVER (), 0), 4),
                jsonb_build_object(
                    'optimism', COUNT(*) FILTER (WHERE emotion_finegrained = 'optimism')::int,
                    'anxiety', COUNT(*) FILTER (WHERE emotion_finegrained = 'anxiety')::int,
                    'anger', COUNT(*) FILTER (WHERE emotion_finegrained = 'anger')::int,
                    'sarcasm', COUNT(*) FILTER (WHERE emotion_finegrained = 'sarcasm')::int,
                    'support', COUNT(*) FILTER (WHERE emotion_finegrained = 'support')::int,
                    'doubt', COUNT(*) FILTER (WHERE emotion_finegrained = 'doubt')::int,
                    'disappointment', COUNT(*) FILTER (WHERE emotion_finegrained = 'disappointment')::int,
                    'indifference', COUNT(*) FILTER (WHERE emotion_finegrained = 'indifference')::int
                ),
                jsonb_build_object({prof_sql_part}),
                EXTRACT(EPOCH FROM NOW())::bigint
            FROM attitude_labels al
            GROUP BY COALESCE(topic_id, '__untagged__'), CASE WHEN topic_id IS NULL THEN '未分类' ELSE topic_id END
            ON CONFLICT (ranking_date, topic_id)
            DO UPDATE SET
                topic_name = EXCLUDED.topic_name,
                total_labeled = EXCLUDED.total_labeled,
                positive_count = EXCLUDED.positive_count,
                negative_count = EXCLUDED.negative_count,
                neutral_count = EXCLUDED.neutral_count,
                positive_ratio = EXCLUDED.positive_ratio,
                negative_ratio = EXCLUDED.negative_ratio,
                neutral_ratio = EXCLUDED.neutral_ratio,
                optimism_index = EXCLUDED.optimism_index,
                pessimism_index = EXCLUDED.pessimism_index,
                heat_index = EXCLUDED.heat_index,
                emotion_distribution = EXCLUDED.emotion_distribution,
                profession_distribution = EXCLUDED.profession_distribution
        """
        async with self.pool.acquire() as conn:
            await conn.execute(sql, rank_date)
