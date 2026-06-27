"""
labeler_fast.py — 异步并行版标注器
用 asyncio httpx 并发调用 DeepSeek API，比串行快 5-10 倍
"""
import json, asyncio, time
from asyncio import Lock
import httpx as async_httpx
from typing import List, Dict, Any, Optional
from config import settings
from professions import PROFESSION_KEYWORDS


class TokenBucket:
    """令牌桶 — 控制每秒最大请求数，避免爆发触发 429"""
    def __init__(self, rate: float = 5, capacity: int = 10):
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_refill = time.monotonic()
        self.lock = Lock()
    
    async def acquire(self):
        while True:
            async with self.lock:
                now = time.monotonic()
                elapsed = now - self.last_refill
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
                self.last_refill = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
            await asyncio.sleep(1.0 / max(self.rate, 1))

_SYSTEM_PROMPT = (
    "你是社会舆情分析专家，专攻「全岗位态度盘点」。"
    "分析每条评论中涉及的工作岗位（职业/职位），"
    "以及对该岗位表达的态度。\n\n"
    "规则：\n"
    "1. 只关心「工作岗位/职业/职位」(如警察、老师、医生、程序员、公务员、外卖员……)\n"
    "2. 非工作岗位的对象(如公司、国家、个人、产品)不标记\n"
    "3. 隐含职业指代也要识别(如「穿制服的」→警察、「白大褂」→医生)\n"
    "4. 一条评论可能涉及多个职业，需独立标注\n"
    "5. 重要：职业名称必须标准化，同一岗位的不同叫法统一为最常见的规范名称。例如：前端/前端开发/前端开发者/前端工程师→前端工程师，码农/程序猿/IT民工→程序员，老师/教师/教书匠→教师，医生/大夫/医师→医生，外卖员/骑手/送餐员→外卖员，保姆/阿姨/育儿嫂→保姆，老板/领导/经理/上司→管理岗，公务/事业编/体制内→公务员，护士/护理师→护士，运营/小编/新媒体→运营\n\n"
    "输出严格JSON格式，不加额外文字：\n"
    "{\n"
    '  "has_profession": true/false,\n'
    '  "professions": [\n'
    '    {\n'
    '      "name": "前端工程师",\n'
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


async def _call_api_async(client: async_httpx.AsyncClient, content: str, sem: asyncio.Semaphore, bucket: TokenBucket = None) -> Dict[str, Any]:
    """单条异步 API 调用（带信号量控制并发）"""
    async with sem:
        content = content.strip()[:1000]
        if not content or not _keyword_match(content):
            return dict(_EMPTY_LABEL)
        
        if bucket:
            await bucket.acquire()
        
        request_body = {
            "model": settings.LLM_MODEL,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            "temperature": 0.1,
            "max_tokens": 400,
        }
        
        retry_delays = [0.5, 2, 5]
        for attempt in range(3):
            try:
                resp = await client.post(
                    f"{settings.LLM_BASE_URL}/chat/completions",
                    headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
                    json=request_body,
                    timeout=15,
                )
                if resp.status_code != 200:
                    if attempt < 2:
                        delay = retry_delays[attempt] if resp.status_code != 429 else 5
                        await asyncio.sleep(delay)
                        continue
                    return {"label_method": "error", "confidence_score": 0.0, **{k:v for k,v in dict(_EMPTY_LABEL).items() if k not in ('label_method', 'confidence_score')}}
                
                data = resp.json()
                usage = data.get("usage", {})
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)
                raw = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if not raw:
                    if attempt < 2:
                        delay = retry_delays[attempt]
                        await asyncio.sleep(delay)
                        continue
                    return {"label_method": "error", "confidence_score": 0.0, **{k:v for k,v in dict(_EMPTY_LABEL).items() if k not in ('label_method', 'confidence_score')}}
                
                parsed = _parse_response(raw)
                if not parsed:
                    if attempt < 2:
                        delay = retry_delays[attempt]
                        await asyncio.sleep(delay)
                        continue
                    return {"label_method": "error", "confidence_score": 0.0, **{k:v for k,v in dict(_EMPTY_LABEL).items() if k not in ('label_method', 'confidence_score')}}
                
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
                    "mentioned_profession": mentioned_prof,
                    "opinion_target": mentioned_prof,
                    "topic_id": parsed.get("topic") or None,
                    "target_type": "profession" if mentioned_prof else None,
                    "confidence_score": avg_conf,
                    "label_method": "llm",
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "raw_response": raw[:1000],
                    "raw_request": json.dumps(request_body, ensure_ascii=False)[:500],
                }
            except (json.JSONDecodeError, async_httpx.TimeoutException, async_httpx.RequestError) as e:
                if attempt < 2:
                    delay = retry_delays[attempt] if not isinstance(e, async_httpx.TimeoutException) else 3
                    await asyncio.sleep(delay)
                    continue
                return {"label_method": "error", "confidence_score": 0.0, **{k:v for k,v in dict(_EMPTY_LABEL).items() if k not in ('label_method', 'confidence_score')}}
        
        return {"label_method": "error", "confidence_score": 0.0, **{k:v for k,v in dict(_EMPTY_LABEL).items() if k not in ('label_method', 'confidence_score')}}


async def batch_label_async(items: List[Dict[str, Any]], batch_id: str, concurrency: int = 50) -> List[Dict[str, Any]]:
    """异步批量标注，并发控制"""
    sem = asyncio.Semaphore(concurrency)
    bucket = TokenBucket(rate=7, capacity=14)
    limits = async_httpx.Limits(max_connections=200, max_keepalive_connections=50)
    async with async_httpx.AsyncClient(timeout=15, limits=limits) as client:
        tasks = [_call_api_async(client, item["content"], sem, bucket) for item in items]
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
