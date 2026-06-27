"""
labeler_fast.py — 异步并行版标注器
用 asyncio httpx 并发调用 DeepSeek API，比串行快 5-10 倍
"""
import json, asyncio, time
import httpx as async_httpx
from typing import List, Dict, Any, Optional
from config import settings
from professions import PROFESSION_KEYWORDS

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
    '    }\n'
    "  ],\n"
    '  "topic": "涉及的社会议题关键词，无则null",\n'
    '  "brief": "一句话总结对该岗位的态度"\n'
    "}\n\n"
)

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
    "prompt_tokens": 0,
    "completion_tokens": 0,
}


def _keyword_match(content: str) -> bool:
    text_lower = content.lower()
    for prof, keywords in PROFESSION_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text_lower:
                return True
    return False


def _parse_response(raw: str) -> Optional[dict]:
    """尝试解析 LLM 返回的 JSON，支持 ```json ``` 包裹"""
    s = raw.strip()
    if s.startswith("```json"):
        s = s[7:]
    elif s.startswith("```"):
        s = s[3:]
    if s.endswith("```"):
        s = s[:-3]
    s = s.strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return None


async def _call_api_async(client: async_httpx.AsyncClient, content: str, sem: asyncio.Semaphore) -> Dict[str, Any]:
    """单条异步 API 调用（带信号量控制并发）"""
    async with sem:
        content = content.strip()[:1000]
        if not content or not _keyword_match(content):
            return dict(_EMPTY_LABEL)
        
        request_body = {
            "model": settings.LLM_MODEL,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            "temperature": 0.1,
            "max_tokens": 400,
        }
        
        for attempt in range(3):
            try:
                resp = await client.post(
                    f"{settings.LLM_BASE_URL}/chat/completions",
                    json=request_body,
                    timeout=15,
                )
                if resp.status_code != 200:
                    if attempt < 2:
                        await asyncio.sleep(0.5)
                        continue
                    return dict(_EMPTY_LABEL)
                
                data = resp.json()
                usage = data.get("usage", {})
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)
                raw = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if not raw:
                    if attempt < 2:
                        await asyncio.sleep(0.5)
                        continue
                    return dict(_EMPTY_LABEL)
                
                parsed = _parse_response(raw)
                if not parsed:
                    if attempt < 2:
                        await asyncio.sleep(0.5)
                        continue
                    return dict(_EMPTY_LABEL)
                
                has_prof = parsed.get("has_profession", False)
                professions = parsed.get("professions", [])
                
                if has_prof and professions:
                    first = professions[0]
                    mentioned_prof = first["name"]
                    sentiment = first["sentiment"]
                    emotion = first.get("emotion", "indifference")
                    confs = [p.get("confidence", 0.5) for p in professions]
                    avg_conf = min(confs)
                else:
                    mentioned_prof = None
                    sentiment = "neutral"
                    emotion = "indifference"
                    avg_conf = 0.5
                
                return {
                    "has_profession": has_prof,
                    "professions": json.dumps(professions, ensure_ascii=False),
                    "sentiment_polarity": sentiment,
                    "emotion_finegrained": emotion,
                    "attitude_tendency": "support" if sentiment == "positive" else ("oppose" if sentiment == "negative" else "neutral"),
                    topic = parsed.get("topic") or None
                    "mentioned_profession": mentioned_prof,
                    "opinion_target": mentioned_prof,
                    "topic_id": topic,
                    "target_type": "profession" if mentioned_prof else None,
                    "confidence_score": avg_conf,
                    "label_method": "llm",
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "raw_response": raw[:1000],
                    "raw_request": json.dumps(request_body, ensure_ascii=False)[:500],
                }
            except (json.JSONDecodeError, async_httpx.TimeoutException, async_httpx.RequestError):
                if attempt < 2:
                    await asyncio.sleep(0.5)
                    continue
                return dict(_EMPTY_LABEL)
        
        return dict(_EMPTY_LABEL)


async def batch_label_async(items: List[Dict[str, Any]], batch_id: str, concurrency: int = 5) -> List[Dict[str, Any]]:
    """异步批量标注，并发控制"""
    sem = asyncio.Semaphore(concurrency)
    async with async_httpx.AsyncClient(timeout=15) as client:
        tasks = [_call_api_async(client, item["content"], sem) for item in items]
        labels = await asyncio.gather(*tasks)
    
    errors = 0
    total_prompt = 0
    total_completion = 0
    
    for i, (item, label) in enumerate(zip(items, labels)):
        is_error = label.get("label_method") == "llm" and label.get("confidence_score", 1) == 0
        if is_error:
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
    
    return labels, errors, total_prompt, total_completion


def generate_batch_id() -> str:
    import uuid
    return f"batch_{uuid.uuid4().hex[:12]}"
