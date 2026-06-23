"""
级联标注器
方案 C：简单本地模型做第一关 + LLM 兜底做细粒度标注
"""

import json
import hashlib
from typing import List, Dict, Any, Optional
from datetime import datetime

from openai import OpenAI
from config import settings
from professions import PROFESSION_KEYWORDS


# ---- LLM 客户端 ----
_llm_client: Optional[OpenAI] = None


def _get_llm():
    global _llm_client
    if _llm_client is None:
        _llm_client = OpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
        )
    return _llm_client


# ---- 本地简单模型（规则 + 可选小模型） ----

def _simple_polarity(content: str) -> tuple:
    """
    极简规则基线：关键词匹配 + 简单极性判断
    后续可替换为 WeiboSentiment_SmallQwen 等本地模型
    返回 (polarity, confidence)
    """
    text = content.lower()

    positive_words = ["太棒了", "支持", "喜欢", "好", "赞", "优秀", "期待",
                      "牛逼", "厉害", "不错", "良心", "绝了", "开心", "感动"]
    negative_words = ["垃圾", "恶心", "垃圾", "反感", "讨厌", "失望", "愤怒",
                      "离谱", "傻逼", "无语", "恶心", "烂", "坑", "抵制"]

    pos_score = sum(1 for w in positive_words if w in text)
    neg_score = sum(1 for w in negative_words if w in text)

    if pos_score > neg_score:
        return "positive", 0.5 + (pos_score - neg_score) * 0.1
    elif neg_score > pos_score:
        return "negative", 0.5 + (neg_score - pos_score) * 0.1
    else:
        return "neutral", 0.5


# ---- 职业提取 ----

def _extract_profession(content: str) -> Optional[str]:
    """职业关键词匹配"""
    found = []
    for prof, keywords in PROFESSION_KEYWORDS.items():
        for kw in keywords:
            if kw in content:
                found.append(prof)
                break  # 一个职业只加一次
        if len(found) > 2:
            break  # 找到3个建议停，等 LLM 选
    if len(found) == 1:
        return found[0]
    if len(found) == 0:
        return None
    return None  # 多个或不确定时留给 LLM 判断


# ---- LLM 标注 ----

_SYSTEM_PROMPT = """你是态度分析师，分析社交媒体评论并输出JSON。
请不要输出任何其他内容，只输出JSON。

输出格式：
{
  "sentiment": "positive|negative|neutral",
  "emotion": "optimism|anxiety|anger|sarcasm|support|doubt|disappointment|indifference",
  "attitude": "support|oppose|neutral|banter",
  "mentioned_profession": "职业名称（可选的，没有则为null）",
  "confidence": 0.0-1.0,
  "brief_reason": "一句话理由"
}"""


def _llm_label(content: str) -> Dict[str, Any]:
    """调用 LLM 进行细粒度标注"""
    client = _get_llm()
    resp = client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": content[:800]},
        ],
        temperature=0.1,
        max_tokens=256,
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {}

    return {
        "sentiment_polarity": data.get("sentiment", "neutral"),
        "emotion_finegrained": data.get("emotion"),
        "attitude_tendency": data.get("attitude"),
        "mentioned_profession": data.get("mentioned_profession"),
        "confidence_score": data.get("confidence", 0.5),
        "raw_response": raw,
    }


def _llm_label_with_profession(content: str, hint_professions: List[str]) -> Dict[str, Any]:
    """LLM 标注 + 指定职业范围"""
    client = _get_llm()
    resp = client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"评论内容：{content[:800]}\n\n上下文职业候选：{', '.join(hint_professions)}\n如果评论涉及其中某个职业请填写。否则为null。"},
        ],
        temperature=0.1,
        max_tokens=256,
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {}

    return {
        "sentiment_polarity": data.get("sentiment", "neutral"),
        "emotion_finegrained": data.get("emotion"),
        "attitude_tendency": data.get("attitude"),
        "mentioned_profession": data.get("mentioned_profession"),
        "confidence_score": data.get("confidence", 0.5),
        "raw_response": raw,
    }


# ---- 级联标注主入口 ----

def cascade_label(content: str) -> Dict[str, Any]:
    """
    级联标注一条评论
    1. 本地模型做第一关（极简规则分词 / 可选加载小模型）
    2. 置信度够高 → 直接返回
    3. 置信度低 / 需要细粒度 → LLM 兜底
    """
    content = content.strip()[:1000]
    if not content:
        return {
            "sentiment_polarity": "neutral",
            "emotion_finegrained": None,
            "attitude_tendency": None,
            "mentioned_profession": None,
            "confidence_score": 1.0,
            "label_method": "model",
            "raw_response": None,
        }

    # ---- Step 1: 本地模型 ----
    polarity, confidence = _simple_polarity(content)

    if confidence >= settings.MODEL_CONFIDENCE_THRESHOLD:
        # 本地模型够自信 → 直接出结果
        profession = _extract_profession(content)
        return {
            "sentiment_polarity": polarity,
            "emotion_finegrained": None,
            "attitude_tendency": None,
            "mentioned_profession": profession,
            "confidence_score": confidence,
            "label_method": "model",
            "raw_response": None,
        }

    # ---- Step 2: LLM 兜底 ----
    # 先看本地能不能猜出职业候选
    hint_profs = []
    for prof, keywords in PROFESSION_KEYWORDS.items():
        for kw in keywords:
            if kw in content:
                hint_profs.append(prof)
                break

    if hint_profs:
        llm_result = _llm_label_with_profession(content, hint_profs)
    else:
        llm_result = _llm_label(content)

    llm_result["label_method"] = "llm"
    return llm_result


def batch_cascade_label(items: List[Dict[str, Any]], batch_id: str) -> List[Dict[str, Any]]:
    """批量级联标注"""
    results = []
    for item in items:
        label = cascade_label(item["content"])
        label.update({
            "source_platform": item["source_platform"],
            "source_type": item["source_type"],
            "source_id": item["source_id"],
            "topic_id": item.get("topic_id"),
            "batch_id": batch_id,
        })
        results.append(label)
    return results


def generate_batch_id() -> str:
    return datetime.now().strftime("batch_%Y%m%d_%H%M%S")
