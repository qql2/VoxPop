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
    """动态令牌桶 — 自动调速，高失败率缩容，成功后扩容"""
    def __init__(self, rate: float = 30, capacity: int = 60, min_rate: float = 1, max_rate: float = 60):
        self.rate = rate
        self.capacity = capacity
        self.min_rate = min_rate
        self.max_rate = max_rate
        self.tokens = capacity
        self.last_refill = time.monotonic()
        self.lock = Lock()
        self.success_since_last_error = 0
    
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
    
    def report(self, status_code: int):
        """报告 API 响应码，触发自动调速"""
        if status_code == 429:
            new_rate = max(self.min_rate, self.rate * 0.7)
            if new_rate != self.rate:
                self.rate = new_rate
                self.capacity = int(self.rate * 2)
            self.success_since_last_error = 0
        elif status_code == 200:
            self.success_since_last_error += 1
            if self.success_since_last_error >= 10:
                new_rate = min(self.max_rate, self.rate + 0.5)
                if new_rate != self.rate:
                    self.rate = new_rate
                    self.capacity = int(self.rate * 2)
                self.success_since_last_error = 0

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
    "你必须调用 analyze_attitude function 输出分析结果，不要输出其他文字。"
)


_ANALYZE_TOOL = {
    "type": "function",
    "function": {
        "name": "analyze_attitude",
        "description": "分析评论中涉及的工作岗位及对该岗位表达的态度",
        "parameters": {
            "type": "object",
            "properties": {
                "has_profession": {"type": "boolean", "description": "评论中是否涉及任何工作岗位"},
                "professions": {
                    "type": "array",
                    "description": "涉及的工作岗位列表",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "标准化后的职业名称"},
                            "sentiment": {"type": "string", "enum": ["positive", "negative", "neutral"]},
                            "emotion": {"type": "string", "enum": ["optimism", "anxiety", "anger", "sarcasm", "support", "doubt", "disappointment", "indifference"]},
                            "confidence": {"type": "number", "description": "置信度 0-1"},
                        },
                        "required": ["name", "sentiment", "emotion", "confidence"],
                    },
                },
                "topic": {"type": "string", "description": "涉及的社会议题，无则null"},
                "brief": {"type": "string", "description": "一句话总结对该岗位的态度"},
            },
            "required": ["has_profession", "professions"],
        },
    },
}

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


def _error_label(raw_response: str = None) -> dict:
    """返回 error 标记的标签（保留现场 raw_response 用于排查）"""
    return {"label_method": "error", "confidence_score": 0.0,
            "raw_response": (raw_response or "")[:500],
            **{k: v for k, v in dict(_EMPTY_LABEL).items()
               if k not in ('label_method', 'confidence_score', 'raw_response')}}


def _keyword_match(content: str) -> bool:
    text_lower = content.lower()
    for prof, keywords in PROFESSION_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text_lower:
                return True
    return False


def _legacy_parse_json(raw: str) -> Optional[dict]:
    """兼容模式：从文本中提取第一个 JSON 对象"""
    s = raw.strip()
    # 去掉 markdown 包裹
    if s.startswith("```json"):
        s = s[7:]
    elif s.startswith("```"):
        s = s[3:]
    if s.endswith("```"):
        s = s[:-3]
    # 找到第一个 { 和最后一个 }
    start = s.find("{")
    end = s.rfind("}")
    if start >= 0 and end > start:
        s = s[start:end + 1]
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            return None
    # 尝试数组格式 [{...}]
    start = s.find("[{")
    end = s.rfind("}]")
    if start >= 0 and end > start:
        try:
            items = json.loads(s[start:end + 2])
            if isinstance(items, list) and len(items) > 0:
                return items[0]
        except json.JSONDecodeError:
            pass
    return None


async def _call_api_async(client: async_httpx.AsyncClient, content: str, bucket: TokenBucket = None) -> Dict[str, Any]:
    """单条异步 API 调用（TokenBucket 限流）"""
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
        "tools": [_ANALYZE_TOOL],
        "tool_choice": "auto",
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
            if bucket:
                bucket.report(resp.status_code)

            # ---------网络/服务端错误：重试---------
            if resp.status_code == 429:
                if attempt < 2:
                    await asyncio.sleep(5)
                    continue
                return _error_label(resp.text[:500])
            elif resp.status_code == 503 or resp.status_code >= 500:
                if attempt < 2:
                    await asyncio.sleep(retry_delays[attempt])
                    continue
                return _error_label(resp.text[:500])
            elif resp.status_code != 200:
                return _error_label(resp.text[:500])

            data = resp.json()
            usage = data.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)

            # ---------解析（优先 tool_calls，fallback 到 content）---------
            msg = data.get("choices", [{}])[0].get("message", {})
            tc = msg.get("tool_calls", [])
            parsed = None
            raw_saved = ""
            if tc and len(tc) > 0:
                raw_saved = tc[0]["function"]["arguments"]
                try:
                    parsed = json.loads(raw_saved)
                except json.JSONDecodeError:
                    parsed = None
            if not parsed:
                content = msg.get("content", "")
                raw_saved = content
                if content:
                    parsed = _legacy_parse_json(content)
            if not parsed:
                if attempt < 2:
                    delay = retry_delays[attempt]
                    await asyncio.sleep(delay)
                    continue
                return _error_label(raw_saved[:500])

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
                "raw_response": raw_saved[:1000],
                "raw_request": json.dumps(request_body, ensure_ascii=False)[:500],
            }
        except (json.JSONDecodeError, async_httpx.TimeoutException, async_httpx.RequestError) as e:
            if attempt < 2:
                delay = retry_delays[attempt] if not isinstance(e, async_httpx.TimeoutException) else 3
                await asyncio.sleep(delay)
                continue
            return _error_label(f"exception: {type(e).__name__}: {str(e)[:200]}")

    return _error_label("max_retries_exhausted")


async def batch_label_async(items: List[Dict[str, Any]], batch_id: str) -> List[Dict[str, Any]]:
    """异步批量标注，TokenBucket 限流
    先处理关键词过滤（不调 API），再处理 LLM 调用，
    避免 0 LLM 时被 gather 阻塞。
    """
    bucket = TokenBucket(rate=30, capacity=60)

    # 预分类：关键词过滤的直出，需调 API 的集中处理
    labels = [None] * len(items)
    api_items: List[int] = []  # (index, item) 只保留需调 API 的
    for i, item in enumerate(items):
        content = item["content"].strip()[:1000]
        if not content or not _keyword_match(content):
            labels[i] = dict(_EMPTY_LABEL)
        else:
            api_items.append(i)

    # API 调用（仅在有必要时）
    if api_items:
        limits = async_httpx.Limits(max_connections=200, max_keepalive_connections=50)
        async with async_httpx.AsyncClient(timeout=15, limits=limits) as client:
            tasks = [_call_api_async(client, items[idx]["content"], bucket) for idx in api_items]
            api_labels = await asyncio.gather(*tasks)
        for pos, idx in enumerate(api_items):
            labels[idx] = api_labels[pos]
    else:
        # 全部关键词过滤，无需创建 HTTP client
        pass

    # 统计+附加上下文
    errors = 0
    total_prompt = 0
    total_completion = 0
    for i, (item, label) in enumerate(zip(items, labels)):
        if label.get("label_method") == "error":
            errors += 1
        total_prompt += label.get("prompt_tokens", 0)
        total_completion += label.get("completion_tokens", 0)
        label.update({
            "source_platform": item["source_platform"],
            "source_type": item["source_type"],
            "source_id": item["source_id"],
            "parent_id": item["parent_id"],
            "add_ts": item["add_ts"],
            "posted_at": item.get("posted_at"),
            "batch_id": batch_id,
            "labeled_at": None,
        })

    return labels, errors, total_prompt, total_completion


def generate_batch_id() -> str:
    import uuid
    return f"batch_{uuid.uuid4().hex[:12]}"
