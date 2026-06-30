#!/usr/bin/env python3
"""
VoxPop 控制台 — SQL 查询 + 运行状态 + 一键爬取/标注
"""
import json, os, subprocess, uuid, time, threading
from flask import Flask, request, jsonify, Response
from pathlib import Path
import asyncpg
import asyncio

app = Flask(__name__)

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DB_CONFIG = {
    "host": "127.0.0.1", "port": 5432,
    "user": "postgres", "password": "***",
    "database": "mindspider",
}

# 正在运行的任务
running_tasks: dict = {}
task_buffers: dict = {}  # task_id -> list of lines (for late-joiners)


def _run_process(task_id: str, cmd: list, cwd: str, env: dict = None):
    """在后台线程中运行进程，输出写入环形缓冲区"""
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=cwd, bufsize=1, env=env,
        )
        running_tasks[task_id] = proc
        task_buffers[task_id] = []
        for line in iter(proc.stdout.readline, ''):
            task_buffers[task_id].append(line)
            if len(task_buffers[task_id]) > 2000:
                task_buffers[task_id] = task_buffers[task_id][-1000:]
        proc.wait()
        task_buffers[task_id].append(f"\n[进程退出, 返回码 {proc.returncode}]\n")
    except Exception as e:
        task_buffers[task_id].append(f"\n[启动失败: {e}]\n")
    finally:
        if task_id in running_tasks:
            del running_tasks[task_id]


HTML = open(Path(__file__).parent / 'templates' / 'index.html', encoding='utf-8').read()

# ====== 路由 ======
@app.route('/')
def index():
    return HTML


@app.route('/query', methods=['POST'])
def query():
    sql = request.json.get('sql', '').strip()
    if not sql:
        return jsonify({"error": "SQL 不能为空"})
    if not sql.upper().lstrip().startswith('SELECT'):
        return jsonify({"error": "只允许 SELECT 查询"})

    t0 = time.time()

    async def run_query():
        conn = await asyncpg.connect(**DB_CONFIG)
        try:
            rows = await conn.fetch(sql)
            if not rows:
                return [], []
            columns = list(rows[0].keys())
            data = [[r[c] for c in columns] for r in rows]
            return columns, data
        finally:
            await conn.close()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        cols, data = loop.run_until_complete(run_query())
    except Exception as e:
        return jsonify({"error": str(e)})
    finally:
        loop.close()

    elapsed = int((time.time() - t0) * 1000)
    return jsonify({"columns": cols, "data": data, "rows": len(data), "time_ms": elapsed})


@app.route('/status')
def run_status():
    from observer import read_status, read_history
    return jsonify({"status": read_status(), "history": read_history()})


# ====== API：爬取（直接跑 MindSpider，保证实时流） ======
@app.route('/api/crawl', methods=['POST'])
def api_crawl():
    platforms = request.json.get('platforms', ['wb', 'bili', 'xhs', 'zhihu'])
    task_id = uuid.uuid4().hex[:12]
    cmd = ['/usr/bin/python3', os.path.join(PROJECT_ROOT, 'run_crawl.py'), '--platforms'] + platforms
    env = os.environ.copy()
    env['PYTHONUNBUFFERED'] = '1'
    threading.Thread(
        target=_run_process, args=(task_id, cmd, PROJECT_ROOT),
        kwargs={'env': env}, daemon=True
    ).start()
    return jsonify({"task_id": task_id, "message": f"爬取已启动: {', '.join(platforms)}"})


# ====== API：标注 ======
@app.route('/api/label', methods=['POST'])
def api_label():
    task_id = uuid.uuid4().hex[:12]
    cmd = ['/usr/bin/python3', 'run_label_cron.py']
    env = os.environ.copy()
    env['PYTHONUNBUFFERED'] = '1'
    threading.Thread(
        target=_run_process, args=(task_id, cmd, PROJECT_ROOT),
        kwargs={'env': env}, daemon=True
    ).start()
    return jsonify({"task_id": task_id, "message": "标注已启动"})


# ====== API：停止 ======
@app.route('/api/stop/<task_id>', methods=['POST'])
def api_stop(task_id):
    proc = running_tasks.get(task_id)
    if proc:
        proc.terminate()
        return jsonify({"status": "terminated"})
    return jsonify({"error": "task not found"})


# ====== API：评论详情下钻 ======
@app.route('/api/comment-detail', methods=['POST'])
def api_comment_detail():
    data = request.json or {}
    profession = data.get("profession", "")
    sentiment = data.get("sentiment", "")
    limit = min(data.get("limit", 99999), 99999)
    days = data.get("days", 0)

    if not profession or not sentiment:
        return jsonify({"error": "profession 和 sentiment 不能为空"})

    import time as _time
    t0 = _time.time()
    where_extra = ""
    if days > 0:
        cutoff = int(_time.time()) - days * 86400
        where_extra = f"AND (al.posted_at IS NULL OR al.posted_at > {cutoff})"

    sql = f"""
        SELECT al.source_platform, al.source_id, al.mentioned_profession,
               al.sentiment_polarity, al.emotion_finegrained, al.posted_at, al.raw_response,
               COALESCE(zh.content, wb.content, bl.content, xh.content) AS comment_content
        FROM attitude_labels al
        LEFT JOIN zhihu_comment zh ON al.source_platform='zhihu' AND al.source_id = zh.id::bigint
        LEFT JOIN weibo_note_comment wb ON al.source_platform='weibo' AND al.source_id = wb.id::bigint
        LEFT JOIN bilibili_video_comment bl ON al.source_platform='bilibili' AND al.source_id = bl.id::bigint
        LEFT JOIN xhs_note_comment xh ON al.source_platform='xhs' AND al.source_id = xh.id::bigint
        WHERE al.mentioned_profession = $1 AND al.sentiment_polarity = $2 AND al.label_method='llm'
          AND COALESCE(zh.content, wb.content, bl.content, xh.content) IS NOT NULL
          {where_extra}
        ORDER BY al.posted_at DESC NULLS LAST
        LIMIT $3
    """

    async def run():
        conn = await asyncpg.connect(**DB_CONFIG)
        try:
            rows = await conn.fetch(sql, profession, sentiment, limit)
            result = []
            for r in rows:
                posted = r["posted_at"]
                result.append({
                    "platform": r["source_platform"],
                    "profession": r["mentioned_profession"],
                    "sentiment": r["sentiment_polarity"],
                    "emotion": r["emotion_finegrained"],
                    "posted_at": posted,
                    "posted_at_str": (_time.strftime("%Y-%m-%d %H:%M", _time.localtime(posted // 1000 if posted > 10000000000 else posted)) if posted else "未知"),
                    "comment": (r["comment_content"] or "")[:500],
                    "summary": _extract_brief(r["raw_response"]),
                })
            return jsonify({
                "comments": result,
                "total": len(result),
                "time_ms": int((_time.time() - t0) * 1000),
            })
        finally:
            await conn.close()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(run())
    except Exception as e:
        return jsonify({"error": str(e)})
    finally:
        loop.close()


@app.route('/api/feedback', methods=['POST'])
def api_feedback():
    task_id = uuid.uuid4().hex[:12]
    cmd = ['/usr/bin/python3', os.path.join(PROJECT_ROOT, 'feedback_keywords.py'), '--apply']
    env = os.environ.copy()
    env['PYTHONUNBUFFERED'] = '1'
    threading.Thread(target=_run_process, args=(task_id, cmd, PROJECT_ROOT), kwargs={'env': env}, daemon=True).start()
    return jsonify({"task_id": task_id, "message": "反馈闭环已启动"})


@app.route('/api/crawl-all', methods=['POST'])
def api_crawl_all():
    task_id = uuid.uuid4().hex[:12]
    minsider_dir = os.path.expanduser("~/MindSpider")
    cmd = ['/usr/bin/python3', os.path.join(PROJECT_ROOT, 'run_crawl.py'), '--all']
    env = os.environ.copy()
    env['PYTHONUNBUFFERED'] = '1'
    threading.Thread(target=_run_process, args=(task_id, cmd, minsider_dir), kwargs={'env': env}, daemon=True).start()
    return jsonify({"task_id": task_id, "message": "强制爬取已启动"})


def _extract_brief(raw_response: str) -> str:
    """从 LLM 返回的 JSON 中提取 brief 字段"""
    if not raw_response:
        return ""
    try:
        # 去除 token 前缀
        s = raw_response.strip()
        if s.startswith("[tokens:"):
            idx = s.find("\n")
            if idx > 0:
                s = s[idx:].strip()
        parsed = json.loads(s)
        return parsed.get("brief", "") or ""
    except (json.JSONDecodeError, Exception):
        return ""


# ====== API：缓冲区（晚加入的客户端也能看到之前的内容） ======
@app.route('/api/buffer/<task_id>')
def api_buffer(task_id):
    lines = task_buffers.get(task_id, [])
    return jsonify({"lines": lines})


# ====== SSE 流 ======
@app.route('/api/stream/<task_id>')
def api_stream(task_id):
    def generate():
        # 先发历史缓冲区
        buf = task_buffers.get(task_id, [])
        for line in buf:
            yield f"data: {json.dumps({'line': line.rstrip()})}\n\n"

        # 实时流
        proc = running_tasks.get(task_id)
        if not proc:
            yield f"data: {json.dumps({'event': 'error', 'message': '任务不存在或已完成'})}\n\n"
            return

        try:
            for line in iter(proc.stdout.readline, ''):
                yield f"data: {json.dumps({'line': line.rstrip()})}\n\n"
            proc.wait()
            yield f"data: {json.dumps({'event': 'done', 'code': proc.returncode})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'event': 'error', 'message': str(e)})}\n\n"

    return Response(generate(), mimetype='text/event-stream')


@app.route('/api/workflow/status')
def workflow_status():
    """返回各流程步骤的上次运行时间"""
    import time as _time
    result = {}

    async def gather():
        conn = await asyncpg.connect(**DB_CONFIG)
        try:
            row = await conn.fetchrow("SELECT MAX(created_at) as t FROM crawl_schedule")
            result["feedback_last_run"] = row["t"] if row and row["t"] else None
            row = await conn.fetchrow("SELECT MAX(last_crawled_at) as t FROM crawl_schedule WHERE last_crawled_at IS NOT NULL")
            result["crawl_last_run"] = row["t"] if row and row["t"] else None
            row = await conn.fetchrow("SELECT MAX(finished_at) as t FROM attitude_batch_log")
            result["label_last_run"] = row["t"] if row and row["t"] else None
            result["schedule_count"] = await conn.fetchval("SELECT COUNT(*) FROM crawl_schedule")
            result["total_labeled"] = await conn.fetchval("SELECT COUNT(*) FROM attitude_labels")
        finally:
            await conn.close()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(gather())
    finally:
        loop.close()

    for k in ["feedback_last_run", "crawl_last_run", "label_last_run"]:
        ts = result.get(k)
        if ts:
            result[k] = _time.strftime("%m-%d %H:%M", _time.localtime(ts))
        else:
            result[k] = "从未运行"

    return jsonify(result)


if __name__ == '__main__':
    print("🚀 VoxPop 控制台")
    print(f"   访问 http://127.0.0.1:5000")
    app.run(host='127.0.0.1', port=5000, debug=False, threaded=True)
