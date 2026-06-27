"""
labeler.py — DeepSeek 多岗位态度标注（v2）
一条 prompt 输出：是否涉及岗位 → 涉及哪些岗位 → 各自态度
"""
import json, httpx
from typing import List, Dict, Any
from config import settings

_SYSTEM_PROMPT = (
    "你是社会舆情分析专家，专攻「全岗位态度盘点」。"
    "分析每条评论中涉及的工作岗位（职业/职位），"
    "以及对该岗位表达的态度。\n\n"
    "规则：\n"
    "1. 只关心「工作岗位/职业/职位」(如警察、老师、医生、程序员、公务员、外卖员……)\n"
    "2. 非工作岗位的对象(如公司、国家、个人、产品)不标记\n"
    "3. 隐含职业指代也要识别(如「穿制服的」→警察、「白大褂」→医生)\n"
    "4. 一条评论可能涉及多个职业，需独立标注\n\n"
    "输出严格JSON格式，不加额外文字：\n"
    "{\n"
    '  "has_profession": true/false,\n'
    '  "professions": [\n'
    '    {\n'
    '      "name": "警察",\n'
    '      "sentiment": "positive|negative|neutral",\n'
    '      "emotion": "optimism|anxiety|anger|sarcasm|support|doubt|disappointment|indifference",\n'
    '      "confidence": 0.0-1.0\n'
    "    }\n"
    "  ],\n"
    '  "topic": "涉及的社会议题关键词，无则null",\n'
    '  "brief": "一句话总结对该岗位的态度"\n'
    "}\n\n"
    "例子：\n"
    '输入：「警察暴力执法必须严惩」→ {"has_profession":true,"professions":[{"name":"警察","sentiment":"negative","emotion":"anger","confidence":0.95}],"topic":"执法公正","brief":"批评警察暴力执法"}\n'
    '输入：「老师辛苦了」→ {"has_profession":true,"professions":[{"name":"老师","sentiment":"positive","emotion":"support","confidence":0.9}],"topic":"教育","brief":"感谢老师付出"}\n'
    '输入：「今天天气不错」→ {"has_profession":false,"professions":[],"topic":null,"brief":null}\n'
    '输入：「我对警察很失望，但医生真的伟大」→ {"has_profession":true,"professions":[{"name":"警察","sentiment":"negative","emotion":"disappointment","confidence":0.88},{"name":"医生","sentiment":"positive","emotion":"support","confidence":0.9}],"topic":"社会公平","brief":"对警察失望，肯定医生贡献"}'
)


def _clean_json(raw: str) -> str:
    s = raw.strip()
    if s.startswith("```json"):
        s = s[7:]
    elif s.startswith("```"):
        s = s[3:]
    if s.endswith("```"):
        s = s[:-3]
    return s.strip()


_EMPTY_LABEL = {
    "has_profession": False,
    "professions": json.dumps([], ensure_ascii=False),
    "sentiment_polarity": "neutral",
    "emotion_finegrained": "indifference",
    "attitude_tendency": "neutral",
    "mentioned_profession": None,
    "opinion_target": None,
    "target_type": None,
    "confidence_score": 1.0,
    "label_method": "model",
    "raw_response": None,
    "raw_request": None,
}


def _keyword_match(content: str) -> bool:
    """关键词预过滤：评论中是否出现任何职业关键词"""
    from professions import PROFESSION_KEYWORDS
    text_lower = content.lower()
    for prof, keywords in PROFESSION_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text_lower:
                return True
    return False


def cascade_label(content: str) -> Dict[str, Any]:
    """
    级联标注：
    1. 关键词预过滤 — 无职业关键词 → 跳过，不走 LLM
    2. 有职业关键词 → DeepSeek 多职业态度提取
    """
    content = content.strip()[:1000]
    if not content:
        return dict(_EMPTY_LABEL)

    # Step 1: 关键词预过滤
    if not _keyword_match(content):
        return dict(_EMPTY_LABEL)

    # Step 2: DeepSeek 标注（最多重试2次）
    import time as _time
    max_retries = 3
    last_error = None
    
    for attempt in range(max_retries):
        if attempt > 0:
            _time.sleep(0.5)
        client = httpx.Client(timeout=15)
        try:
            request_body = {
                "model": settings.LLM_MODEL,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": content},
                ],
                "temperature": 0.1,
                "max_tokens": 400,
            }

            resp = client.post(
                f"{settings.LLM_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.LLM_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=request_body,
            )

            if resp.status_code != 200:
                raise RuntimeError(f"API HTTP {resp.status_code}: {resp.text[:200]}")

            data = resp.json()
            usage = data.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            raw = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not raw:
                raise RuntimeError("API returned empty response")

            clean = _clean_json(raw)
            parsed = json.loads(clean)

            has_prof = parsed.get("has_profession", False)
            professions = parsed.get("professions", [])

            if has_prof and professions:
                first = professions[0]
                mentioned_prof = first["name"]
                sentiment = first["sentiment"]
                emotion = first.get("emotion", "indifference")
                conf_list = [p.get("confidence", 0.5) for p in professions]
                avg_conf = min(conf_list)
            else:
                mentioned_prof = None
                sentiment = "neutral"
                emotion = "indifference"
                avg_conf = 0.5

            # 在 raw_response 开头嵌入 token 信息供后续提取
            tok_meta = f"[tokens: prompt={prompt_tokens}, completion={completion_tokens}]\n"
            topic = parsed.get("topic") or None
            result = {
                "has_profession": has_prof,
                "professions": json.dumps(professions, ensure_ascii=False),
                "sentiment_polarity": sentiment,
                "emotion_finegrained": emotion,
                "attitude_tendency": "support" if sentiment == "positive" else ("oppose" if sentiment == "negative" else "neutral"),
                "mentioned_profession": mentioned_prof,
                "opinion_target": mentioned_prof,
                "target_type": "profession" if mentioned_prof else None,
                "topic_id": topic,
                "confidence_score": avg_conf,
                "label_method": "llm",
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "raw_response": tok_meta + raw[:1000],
                "raw_request": json.dumps(request_body, ensure_ascii=False)[:500],
            }
            return result
        except (json.JSONDecodeError, httpx.TimeoutException, httpx.RequestError, RuntimeError) as e:
            last_error = e
        finally:
            client.close()
    # 所有重试都失败 → 标记 error，下轮可重标
    err_msg = f"label_error: {last_error}" if last_error else "label_error: max retries"
    fallback = dict(_EMPTY_LABEL)
    fallback["label_method"] = "error"
    fallback["raw_response"] = err_msg
    fallback["confidence_score"] = 0.0
    return fallback


def generate_batch_id() -> str:
    import uuid
    return f"batch_{uuid.uuid4().hex[:12]}"


def batch_cascade_label(items: List[Dict[str, Any]], batch_id: str) -> List[Dict[str, Any]]:
    results = []
    errors = 0
    total_prompt = 0
    total_completion = 0
    for item in items:
        label = cascade_label(item["content"])
        if label.get("raw_response", "") and "label_error:" in str(label.get("raw_response", "")):
            errors += 1
        total_prompt += label.get("prompt_tokens", 0)
        total_completion += label.get("completion_tokens", 0)
        label.update({
            "source_platform": item["source_platform"],
            "source_type": item["source_type"],
            "source_id": item["source_id"],
            "parent_id": item["parent_id"],
            "add_ts": item["add_ts"],
            "batch_id": batch_id,
            "labeled_at": None,
        })
        results.append(label)
    return results, errors, total_prompt, total_completion
