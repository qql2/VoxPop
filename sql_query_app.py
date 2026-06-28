#!/usr/bin/env python3
"""
VoxPop 控制台 — SQL 查询 + 运行状态 + 一键爬取/标注
"""
import json, os, subprocess, uuid, time, threading
from flask import Flask, request, jsonify, render_template_string, Response
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


HTML = r"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"><title>VoxPop 控制台</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font:14px/1.6 -apple-system,sans-serif;background:#f5f5f5;color:#333;padding:20px}
.container{max-width:1200px;margin:0 auto}
h1{margin-bottom:12px;font-size:20px}
.tabs{margin-bottom:16px;display:flex;gap:0;border-bottom:2px solid #e5e5e5}
.tabs button{padding:8px 20px;border:none;background:none;cursor:pointer;font-size:14px;color:#666;border-bottom:2px solid transparent;margin-bottom:-2px}
.tabs button.active{color:#4f46e5;border-bottom-color:#4f46e5;font-weight:600}
.tab-content{display:none}.tab-content.active{display:block}
.presets{margin-bottom:12px;display:flex;flex-wrap:wrap;gap:6px}
.presets button{padding:6px 14px;border:1px solid #ccc;border-radius:4px;background:#fff;cursor:pointer;font-size:13px}
.presets button:hover{background:#e8e8e8}
textarea{width:100%;height:100px;font:13px/1.5 Menlo,monospace;padding:8px;border:1px solid #ccc;border-radius:4px;resize:vertical;margin-bottom:8px}
.toolbar{display:flex;gap:8px;align-items:center;margin-bottom:12px}
.toolbar button{padding:8px 24px;border:none;border-radius:4px;cursor:pointer;font-size:14px}
.btn-primary{background:#4f46e5;color:#fff}.btn-primary:hover{background:#4338ca}
.btn-danger{background:#dc2626;color:#fff}.btn-danger:hover{background:#b91c1c}
.btn-success{background:#16a34a;color:#fff}.btn-success:hover{background:#15803d}
.btn-ghost{background:#6b7280;color:#fff}.btn-ghost:hover{background:#4b5563}
.info{color:#666;font-size:13px}
.error{color:#dc2626;background:#fee2e2;padding:10px;border-radius:4px;margin-bottom:12px;white-space:pre-wrap}
table{width:100%;border-collapse:collapse;background:#fff;border-radius:4px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1)}
th{background:#f0f0f0;text-align:left;padding:8px 10px;font-weight:600;white-space:nowrap;cursor:pointer;font-size:13px}
th:hover{background:#e5e5e5}
td{padding:6px 10px;border-top:1px solid #eee;font-size:13px}
tr:hover td{background:#fafafa}
.stats{margin-bottom:8px;color:#666;font-size:13px}
.loading{color:#666;font-style:italic}
th.sorted-asc::after{content:' ▲';font-size:11px}
th.sorted-desc::after{content:' ▼';font-size:11px}
.badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:12px;font-weight:600}
.badge-ok{background:#dcfce7;color:#166534}
.badge-warn{background:#fef3c7;color:#92400e}
.badge-err{background:#fee2e2;color:#991b1b}
.badge-info{background:#dbeafe;color:#1e40af}
.status-card{background:#fff;border-radius:8px;padding:16px;margin-bottom:12px;box-shadow:0 1px 3px rgba(0,0,0,0.1)}
.status-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px;margin-bottom:16px}
.metric{text-align:center;padding:12px;background:#fafafa;border-radius:6px}
.metric .value{font-size:24px;font-weight:700}
.metric .label{font-size:12px;color:#666;margin-top:4px}
.history-table td{padding:8px 6px}
/* 控制台终端样式 */
.console{background:#1e1e1e;color:#d4d4d4;font:13px/1.5 Menlo,Consolas,monospace;padding:12px;border-radius:6px;height:500px;overflow-y:auto;white-space:pre-wrap;word-break:break-all;margin-top:8px}
.console .ts{color:#6a9955}
.console .err{color:#f48771}
.console .info{color:#569cd6}
.console .ok{color:#4ec9b0}
.console .warn{color:#ce9178}
.console .dim{color:#808080}
.ctrl-bar{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px}
.ctrl-bar button{padding:8px 20px;border:none;border-radius:4px;cursor:pointer;font-size:13px}
.ctrl-bar .running{opacity:0.6;pointer-events:none}
.platform-chips{display:flex;gap:4px;flex-wrap:wrap;margin:8px 0}
.platform-chips label{padding:4px 10px;border:1px solid #ccc;border-radius:12px;cursor:pointer;font-size:12px;background:#fff}
.platform-chips label.active{background:#4f46e5;color:#fff;border-color:#4f46e5}
</style>
</head>
<body>
<div class="container">
<h1>🔍 VoxPop 控制台</h1>
<div class="tabs">
  <button onclick="switchTab('sql')">📊 查询</button>
  <button onclick="switchTab('status')">📋 运行状态</button>
  <button class="active" onclick="switchTab('console')">🖥️ 控制台</button>
</div>

<!-- SQL 查询 -->
<div id="tab-sql" class="tab-content">
  <div class="presets" id="presets"></div>
  <textarea id="sql" placeholder="输入 SQL 查询语句…"></textarea>
  <div class="toolbar">
    <button class="btn-primary" onclick="runQuery()">▶ 执行</button>
    <span class="info" id="q-status"></span>
  </div>
  <div id="q-error" class="error" style="display:none"></div>
  <div id="q-stats" class="stats"></div>
  <div id="q-table"></div>
</div>

<!-- 运行状态 -->
<div id="tab-status" class="tab-content">
  <div id="status-content"><p class="loading">加载中…</p></div>
</div>

<!-- 控制台 -->
<div id="tab-console" class="tab-content active">
  <div class="ctrl-bar">
    <button class="btn-success" id="btn-crawl" onclick="startCrawl()">🕷️ 爬取</button>
    <button class="btn-primary" id="btn-label" onclick="startLabel()">🏷️ 标注</button>
    <button class="btn-ghost" id="btn-stop" onclick="stopTask()" style="display:none">⏹ 停止</button>
    <button class="btn-ghost" onclick="clearConsole()">🗑️ 清屏</button>
  </div>
  <div class="platform-chips">
    <label class="active"><input type="checkbox" value="wb" checked hidden> 微博</label>
    <label class="active"><input type="checkbox" value="bili" checked hidden> B站</label>
    <label class="active"><input type="checkbox" value="xhs" checked hidden> 小红书</label>
    <label class="active"><input type="checkbox" value="zhihu" checked hidden> 知乎</label>
  </div>
  <div id="console" class="console"></div>
</div>

</div>
<script>
// ====== Tab 切换 ======
function switchTab(name) {
  document.querySelectorAll('.tabs button').forEach(b => b.classList.remove('active'));
  event.target.classList.add('active');
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  if (name === 'status') loadStatus();
}

// ====== SQL 查询 ======
const PRESETS = [
  {label:'🏆 职业积极排行',sql:`SELECT mentioned_profession AS 职业, COUNT(*) AS 讨论量, COUNT(*) FILTER (WHERE sentiment_polarity='positive') AS 积极, COUNT(*) FILTER (WHERE sentiment_polarity='negative') AS 消极, ROUND(COUNT(*) FILTER (WHERE sentiment_polarity='positive')::numeric / NULLIF(COUNT(*),0) * 100, 1) AS 积极率, ROUND(COUNT(*) FILTER (WHERE sentiment_polarity='negative')::numeric / NULLIF(COUNT(*),0) * 100, 1) AS 消极率 FROM attitude_labels WHERE label_method='llm' AND mentioned_profession IS NOT NULL GROUP BY mentioned_profession ORDER BY 讨论量 DESC;`},
  {label:'📈 积极率最高',sql:`SELECT mentioned_profession AS 职业, COUNT(*) AS 讨论量, COUNT(*) FILTER (WHERE sentiment_polarity='positive') AS 积极, ROUND(COUNT(*) FILTER (WHERE sentiment_polarity='positive')::numeric / NULLIF(COUNT(*),0) * 100, 1) AS 积极率 FROM attitude_labels WHERE label_method='llm' AND mentioned_profession IS NOT NULL GROUP BY mentioned_profession ORDER BY 积极率 DESC, 讨论量 DESC;`},
  {label:'📉 消极率最高',sql:`SELECT mentioned_profession AS 职业, COUNT(*) AS 讨论量, COUNT(*) FILTER (WHERE sentiment_polarity='negative') AS 消极, ROUND(COUNT(*) FILTER (WHERE sentiment_polarity='negative')::numeric / NULLIF(COUNT(*),0) * 100, 1) AS 消极率 FROM attitude_labels WHERE label_method='llm' AND mentioned_profession IS NOT NULL GROUP BY mentioned_profession ORDER BY 消极率 DESC, 讨论量 DESC;`},
  {label:'📊 全部排行',sql:`SELECT mentioned_profession AS 职业, COUNT(*) AS 讨论量, COUNT(*) FILTER (WHERE sentiment_polarity='positive') AS 积极, COUNT(*) FILTER (WHERE sentiment_polarity='negative') AS 消极, COUNT(*) FILTER (WHERE sentiment_polarity='neutral') AS 中性, ROUND(COUNT(*) FILTER (WHERE sentiment_polarity='positive')::numeric / NULLIF(COUNT(*),0) * 100, 1) AS 积极率, ROUND(COUNT(*) FILTER (WHERE sentiment_polarity='negative')::numeric / NULLIF(COUNT(*),0) * 100, 1) AS 消极率 FROM attitude_labels WHERE label_method='llm' AND mentioned_profession IS NOT NULL GROUP BY mentioned_profession ORDER BY 讨论量 DESC;`},
  {label:'📋 平台数据',sql:`SELECT source_platform AS 平台, COUNT(*) AS 总计, COUNT(*) FILTER (WHERE label_method='llm') AS LLM, COUNT(*) FILTER (WHERE label_method='model') AS 本地, COUNT(*) FILTER (WHERE label_method='error') AS 错误, COUNT(*) FILTER (WHERE sentiment_polarity='positive') AS 积极, COUNT(*) FILTER (WHERE sentiment_polarity='negative') AS 消极 FROM attitude_labels GROUP BY source_platform ORDER BY 平台;`},
  {label:'🔎 搜索',sql:`SELECT mentioned_profession AS 职业, COUNT(*) AS 讨论量, COUNT(*) FILTER (WHERE sentiment_polarity='positive') AS 积极, COUNT(*) FILTER (WHERE sentiment_polarity='negative') AS 消极, ROUND(COUNT(*) FILTER (WHERE sentiment_polarity='positive')::numeric / NULLIF(COUNT(*),0) * 100, 1) AS 积极率 FROM attitude_labels WHERE label_method='llm' AND mentioned_profession ILIKE '%程序员%' GROUP BY mentioned_profession ORDER BY 讨论量 DESC;`},
  {label:'📅 近7天排行',sql:`SELECT mentioned_profession AS 职业, COUNT(*) AS 讨论量, COUNT(*) FILTER (WHERE sentiment_polarity='positive') AS 积极, COUNT(*) FILTER (WHERE sentiment_polarity='negative') AS 消极, ROUND(COUNT(*) FILTER (WHERE sentiment_polarity='positive')::numeric / NULLIF(COUNT(*),0) * 100, 1) AS 积极率 FROM attitude_labels WHERE label_method='llm' AND mentioned_profession IS NOT NULL AND posted_at > EXTRACT(EPOCH FROM NOW() - INTERVAL '7 days') GROUP BY mentioned_profession ORDER BY 讨论量 DESC;`},
  {label:'📅 近30天排行',sql:`SELECT mentioned_profession AS 职业, COUNT(*) AS 讨论量, COUNT(*) FILTER (WHERE sentiment_polarity='positive') AS 积极, COUNT(*) FILTER (WHERE sentiment_polarity='negative') AS 消极, ROUND(COUNT(*) FILTER (WHERE sentiment_polarity='positive')::numeric / NULLIF(COUNT(*),0) * 100, 1) AS 积极率 FROM attitude_labels WHERE label_method='llm' AND mentioned_profession IS NOT NULL AND posted_at > EXTRACT(EPOCH FROM NOW() - INTERVAL '30 days') GROUP BY mentioned_profession ORDER BY 讨论量 DESC;`},
];
PRESETS.forEach(p => {
  const btn = document.createElement('button');
  btn.textContent = p.label;
  btn.onclick = () => { document.getElementById('sql').value = p.sql; runQuery(); };
  document.getElementById('presets').appendChild(btn);
});
document.getElementById('sql').addEventListener('keydown', e => {
  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) runQuery();
});

async function runQuery() {
  const sql = document.getElementById('sql').value.trim();
  if (!sql) return;
  const el = e => document.getElementById(e);
  el('q-error').style.display = 'none';
  el('q-status').textContent = '执行中…';
  el('q-stats').textContent = '';
  el('q-table').innerHTML = '<p class="loading">⟳ 查询中…</p>';
  try {
    const r = await fetch('/query',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sql})});
    const d = await r.json();
    if (d.error) { el('q-error').textContent = '❌ '+d.error; el('q-error').style.display='block'; el('q-table').innerHTML=''; el('q-status').textContent=''; return; }
    el('q-status').textContent = `耗时 ${d.time_ms}ms · ${d.rows} 行`;
    el('q-stats').textContent = `列: ${d.columns.join(', ')}`;
    renderTable(d.columns, d.data);
  } catch(e) { el('q-error').textContent='❌ 请求失败: '+e.message; el('q-error').style.display='block'; el('q-table').innerHTML=''; el('q-status').textContent=''; }
}

let sortCol=-1,sortAsc=true;
function renderTable(cols,rows){
  const c=document.getElementById('q-table'); sortCol=-1; sortAsc=true;
  let h='<table><thead><tr>'+cols.map((c,i)=>'<th onclick="sortTable('+i+')">'+c+'</th>').join('')+'</tr></thead><tbody>';
  rows.forEach(r=>{h+='<tr>'+r.map(v=>'<td>'+(v===null?'NULL':v)+'</td>').join('')+'</tr>'});
  c.innerHTML=h+'</tbody></table>';
}
function sortTable(col){
  const t=document.querySelector('#q-table table'); if(!t)return;
  const b=t.querySelector('tbody'),rows=Array.from(b.querySelectorAll('tr'));
  if(sortCol===col)sortAsc=!sortAsc;else{sortCol=col;sortAsc=true;}
  rows.sort((a,b)=>{let va=a.cells[col].textContent,vb=b.cells[col].textContent,na=parseFloat(va),nb=parseFloat(vb);if(!isNaN(na)&&!isNaN(nb)){va=na;vb=nb}return va<vb?sortAsc?-1:1:va>vb?sortAsc?1:-1:0});
  rows.forEach(r=>b.appendChild(r));
  t.querySelectorAll('th').forEach((th,i)=>th.className=i===col?(sortAsc?'sorted-asc':'sorted-desc'):'');
}

// ====== 运行状态 ======
async function loadStatus(){
  try{const r=await fetch('/status'),d=await r.json();document.getElementById('status-content').innerHTML=renderStatus(d);}catch(e){document.getElementById('status-content').innerHTML='<div class="error" style="display:block">❌ 加载失败: '+e.message+'</div>';}
}
function renderStatus(d){
  const s=d.status||{},h=d.history||[];
  const sc=s.status==='completed'?'badge-ok':s.status==='failed'||s.status==='error'?'badge-err':s.status==='warning'?'badge-warn':'badge-info';
  let html='<div class="status-card"><div style="margin-bottom:12px"><span class="badge '+sc+'" style="font-size:14px;padding:4px 12px">'+(s.status||'未知')+'</span>';
  if(s._time_str)html+='<span class="info" style="margin-left:12px">'+s._time_str+'</span>';
  html+='</div>';
  if(s.status==='never_run')return html+'<p>还没有运行过标注。</p></div>';
  html+='<div class="status-grid">';
  html+='<div class="metric"><div class="value">'+(s.total_labeled||0)+'</div><div class="label">本次标注</div></div>';
  html+='<div class="metric"><div class="value">'+(s.llm_count||0)+'</div><div class="label">LLM</div></div>';
  html+='<div class="metric"><div class="value">'+(s.errors||0)+'</div><div class="label">错误</div></div>';
  html+='<div class="metric"><div class="value">$'+((s.estimated_cost||0)).toFixed(6)+'</div><div class="label">费用</div></div>';
  html+='<div class="metric"><div class="value">'+(s.prompt_tokens||0).toLocaleString()+'</div><div class="label">输入 Token</div></div>';
  html+='<div class="metric"><div class="value">'+(s.completion_tokens||0).toLocaleString()+'</div><div class="label">输出 Token</div></div>';
  html+='<div class="metric"><div class="value">'+(s.elapsed_s||0)+'</div><div class="label">耗时(秒)</div></div>';
  html+='<div class="metric"><div class="value">'+Math.round((s.error_rate||0)*100)+'%</div><div class="label">错误率</div></div></div>';
  if(s.platforms&&Object.keys(s.platforms).length>0){
    html+='<h3 style="font-size:14px;margin-bottom:8px">📦 各平台</h3><table><thead><tr><th>平台</th><th>总计</th><th>LLM</th><th>本地</th><th>错误</th></tr></thead><tbody>';
    for(const[p,pd]of Object.entries(s.platforms))html+='<tr><td>'+p+'</td><td>'+(pd.total||0)+'</td><td>'+(pd.llm||0)+'</td><td>'+(pd.model||0)+'</td><td>'+(pd.errors||0)+'</td></tr>';
    html+='</tbody></table>';
  }
  if(s.warnings&&s.warnings.length)for(const w of s.warnings)html+='<div class="badge badge-warn" style="margin:2px">⚠️ '+w+'</div>';
  if(s.alerts&&s.alerts.length)for(const a of s.alerts)html+='<div class="badge badge-err" style="margin:2px">🔴 '+a+'</div>';
  html+='</div>';
  if(h.length>0){
    html+='<div class="status-card"><h3 style="font-size:14px;margin-bottom:8px">📜 历史（最近 '+h.length+' 次）</h3><table class="history-table"><thead><tr><th>时间</th><th>状态</th><th>条数</th><th>LLM</th><th>错误</th><th>费用</th><th>耗时</th></tr></thead><tbody>';
    for(const r of[...h].reverse()){
      const rc=r.status==='completed'?'badge-ok':r.status==='failed'||r.status==='error'?'badge-err':'badge-info';
      html+='<tr><td>'+(r._time_str||'')+'</td><td><span class="badge '+rc+'">'+r.status+'</span></td><td>'+(r.total_labeled||0)+'</td><td>'+(r.llm_count||0)+'</td><td>'+(r.errors||0)+'</td><td>$'+((r.estimated_cost||0)).toFixed(6)+'</td><td>'+(r.elapsed_s||0)+'s</td></tr>';
    }
    html+='</tbody></table></div>';
  }
  return html;
}

// ====== 控制台 ======
let currentTaskId = null;
let consoleStream = null;

function logConsole(text, cls='') {
  const el = document.getElementById('console');
  el.innerHTML += '<span class="'+cls+'">'+text.replace(/</g,'&lt;')+'</span>';
  el.scrollTop = el.scrollHeight;
}

function getSelectedPlatforms() {
  return Array.from(document.querySelectorAll('.platform-chips input:checked')).map(cb => cb.value);
}

// 勾选样式
document.querySelectorAll('.platform-chips label').forEach(label => {
  label.addEventListener('click', function(e) {
    if (e.target.tagName !== 'INPUT') {
      const cb = this.querySelector('input');
      cb.checked = !cb.checked;
    }
    const cb = this.querySelector('input');
    this.className = cb.checked ? 'active' : '';
  });
});

function setButtonsRunning(running) {
  document.getElementById('btn-crawl').disabled = running;
  document.getElementById('btn-label').disabled = running;
  document.getElementById('btn-crawl').className = running ? 'btn-success running' : 'btn-success';
  document.getElementById('btn-label').className = running ? 'btn-primary running' : 'btn-primary';
  document.getElementById('btn-stop').style.display = running ? 'inline-block' : 'none';
}

async function startCrawl() {
  const platforms = getSelectedPlatforms();
  if (platforms.length === 0) { logConsole('请至少选择一个平台\n', 'warn'); return; }
  logConsole('🚀 开始爬取: ' + platforms.join(', ') + '\n', 'info');
  setButtonsRunning(true);
  try {
    const r = await fetch('/api/crawl', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({platforms})
    });
    const d = await r.json();
    if (d.error) { logConsole('❌ '+d.error+'\n','err'); setButtonsRunning(false); return; }
    currentTaskId = d.task_id;
    startStream(d.task_id);
  } catch(e) { logConsole('❌ 启动失败: '+e.message+'\n','err'); setButtonsRunning(false); }
}

async function startLabel() {
  logConsole('🏷️ 开始标注...\n', 'info');
  setButtonsRunning(true);
  try {
    const r = await fetch('/api/label', { method:'POST' });
    const d = await r.json();
    if (d.error) { logConsole('❌ '+d.error+'\n','err'); setButtonsRunning(false); return; }
    currentTaskId = d.task_id;
    startStream(d.task_id);
  } catch(e) { logConsole('❌ 启动失败: '+e.message+'\n','err'); setButtonsRunning(false); }
}

function startStream(taskId) {
  if (consoleStream) { consoleStream.close(); }
  const el = document.getElementById('console');

  // 先拉历史缓冲区
  fetch('/api/buffer/'+taskId).then(r=>r.json()).then(d=>{
    if (d.lines) { d.lines.forEach(l => appendLogLine(l)); }
  });

  consoleStream = new EventSource('/api/stream/'+taskId);
  consoleStream.onmessage = function(e) {
    try {
      const data = JSON.parse(e.data);
      if (data.event === 'done') {
        logConsole('\n✅ 完成（返回码 '+data.code+'）\n', data.code===0?'ok':'err');
        setButtonsRunning(false);
        consoleStream.close();
        consoleStream = null;
        currentTaskId = null;
        // 刷新状态
        loadStatus();
      } else if (data.event === 'error') {
        logConsole('❌ '+data.message+'\n', 'err');
        setButtonsRunning(false);
      } else if (data.line) {
        appendLogLine(data.line);
      }
    } catch(e) {
      // 纯文本行
      if (e.data) { appendLogLine(e.data); }
    }
  };
  consoleStream.onerror = function() {
    // SSE 断开时尝试重连（浏览器会自动重连）
  };
}

function appendLogLine(line) {
  const el = document.getElementById('console');
  let cls = '';
  if (line.includes('ERROR') || line.includes('❌') || line.includes('错误') || line.includes('失败')) cls = 'err';
  else if (line.includes('INFO') || line.includes('✅') || line.includes('成功')) cls = 'ok';
  else if (line.includes('WARNING') || line.includes('⚠️')) cls = 'warn';
  el.innerHTML += '<span class="'+cls+'">'+line.replace(/</g,'&lt;')+'\n</span>';
  el.scrollTop = el.scrollHeight;
}

function clearConsole() {
  document.getElementById('console').innerHTML = '';
}

async function stopTask() {
  if (!currentTaskId) return;
  logConsole('⏹ 停止任务...\n', 'warn');
  try {
    await fetch('/api/stop/'+currentTaskId, { method:'POST' });
  } catch(e) {}
}
</script>
</body>
</html>
"""

# ====== 路由 ======
@app.route('/')
def index():
    return render_template_string(HTML)


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
    minsider_dir = os.path.expanduser("~/MindSpider")
    cmd = ['/usr/bin/python3', 'main.py', '--deep-sentiment', '--platforms'] + platforms
    env = os.environ.copy()
    env['PYTHONUNBUFFERED'] = '1'
    threading.Thread(
        target=_run_process, args=(task_id, cmd, minsider_dir),
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


if __name__ == '__main__':
    print("🚀 VoxPop 控制台")
    print(f"   访问 http://127.0.0.1:5000")
    app.run(host='127.0.0.1', port=5000, debug=False, threaded=True)
