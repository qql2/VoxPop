#!/usr/bin/env python3
"""VoxPop SQL 查询工具 — 简单的 Web 界面"""
import json, os
from flask import Flask, request, jsonify, render_template_string
import asyncpg
import asyncio

app = Flask(__name__)

DB_CONFIG = {
    "host": "127.0.0.1", "port": 5432,
    "user": "postgres", "password": "***",
    "database": "mindspider",
}

HTML = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>VoxPop 数据库查询</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font: 14px/1.6 -apple-system, sans-serif; background: #f5f5f5; color: #333; padding: 20px; }
    .container { max-width: 1200px; margin: 0 auto; }
    h1 { margin-bottom: 12px; font-size: 20px; }
    .presets { margin-bottom: 12px; display: flex; flex-wrap: wrap; gap: 6px; }
    .presets button { padding: 6px 14px; border: 1px solid #ccc; border-radius: 4px; background: #fff; cursor: pointer; font-size: 13px; }
    .presets button:hover { background: #e8e8e8; }
    textarea { width: 100%; height: 100px; font: 13px/1.5 Menlo, monospace; padding: 8px; border: 1px solid #ccc; border-radius: 4px; resize: vertical; margin-bottom: 8px; }
    .toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
    .toolbar button { padding: 8px 24px; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; }
    .btn-run { background: #4f46e5; color: #fff; }
    .btn-run:hover { background: #4338ca; }
    .info { color: #666; font-size: 13px; }
    .error { color: #dc2626; background: #fee2e2; padding: 10px; border-radius: 4px; margin-bottom: 12px; white-space: pre-wrap; }
    table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 4px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
    th { background: #f0f0f0; text-align: left; padding: 8px 10px; font-weight: 600; white-space: nowrap; cursor: pointer; font-size: 13px; }
    th:hover { background: #e5e5e5; }
    td { padding: 6px 10px; border-top: 1px solid #eee; font-size: 13px; }
    tr:hover td { background: #fafafa; }
    .stats { margin-bottom: 8px; color: #666; font-size: 13px; }
    .loading { color: #666; font-style: italic; }
    th.sorted-asc::after { content: ' ▲'; font-size: 11px; }
    th.sorted-desc::after { content: ' ▼'; font-size: 11px; }
  </style>
</head>
<body>
<div class="container">
  <h1>🔍 VoxPop 数据库查询</h1>
  
  <div class="presets" id="presets"></div>
  
  <textarea id="sql" placeholder="输入 SQL 查询语句…"></textarea>
  
  <div class="toolbar">
    <button class="btn-run" onclick="run()">▶ 执行</button>
    <span class="info" id="status"></span>
  </div>
  
  <div id="error" class="error" style="display:none"></div>
  <div id="stats" class="stats"></div>
  <div id="table-container"></div>
</div>

<script>
const PRESETS = [
  { label: '🏆 职业积极排行', sql: `SELECT mentioned_profession AS 职业, COUNT(*) AS 讨论量, COUNT(*) FILTER (WHERE sentiment_polarity='positive') AS 积极, COUNT(*) FILTER (WHERE sentiment_polarity='negative') AS 消极, ROUND(COUNT(*) FILTER (WHERE sentiment_polarity='positive')::numeric / NULLIF(COUNT(*),0) * 100, 1) AS 积极率, ROUND(COUNT(*) FILTER (WHERE sentiment_polarity='negative')::numeric / NULLIF(COUNT(*),0) * 100, 1) AS 消极率 FROM attitude_labels WHERE label_method='llm' AND mentioned_profession IS NOT NULL GROUP BY mentioned_profession ORDER BY 讨论量 DESC;` },
  { label: '📈 积极率最高', sql: `SELECT mentioned_profession AS 职业, COUNT(*) AS 讨论量, COUNT(*) FILTER (WHERE sentiment_polarity='positive') AS 积极, ROUND(COUNT(*) FILTER (WHERE sentiment_polarity='positive')::numeric / NULLIF(COUNT(*),0) * 100, 1) AS 积极率 FROM attitude_labels WHERE label_method='llm' AND mentioned_profession IS NOT NULL GROUP BY mentioned_profession ORDER BY 积极率 DESC, 讨论量 DESC;` },
  { label: '📉 消极率最高', sql: `SELECT mentioned_profession AS 职业, COUNT(*) AS 讨论量, COUNT(*) FILTER (WHERE sentiment_polarity='negative') AS 消极, ROUND(COUNT(*) FILTER (WHERE sentiment_polarity='negative')::numeric / NULLIF(COUNT(*),0) * 100, 1) AS 消极率 FROM attitude_labels WHERE label_method='llm' AND mentioned_profession IS NOT NULL GROUP BY mentioned_profession ORDER BY 消极率 DESC, 讨论量 DESC;` },
  { label: '📊 所有职业排行', sql: `SELECT mentioned_profession AS 职业, COUNT(*) AS 讨论量, COUNT(*) FILTER (WHERE sentiment_polarity='positive') AS 积极, COUNT(*) FILTER (WHERE sentiment_polarity='negative') AS 消极, COUNT(*) FILTER (WHERE sentiment_polarity='neutral') AS 中性, ROUND(COUNT(*) FILTER (WHERE sentiment_polarity='positive')::numeric / NULLIF(COUNT(*),0) * 100, 1) AS 积极率, ROUND(COUNT(*) FILTER (WHERE sentiment_polarity='negative')::numeric / NULLIF(COUNT(*),0) * 100, 1) AS 消极率 FROM attitude_labels WHERE label_method='llm' AND mentioned_profession IS NOT NULL GROUP BY mentioned_profession ORDER BY 讨论量 DESC;` },
  { label: '📋 各平台数据量', sql: `SELECT source_platform AS 平台, COUNT(*) AS 总计, COUNT(*) FILTER (WHERE label_method='llm') AS LLM标注, COUNT(*) FILTER (WHERE label_method='model') AS 关键词过滤, COUNT(*) FILTER (WHERE label_method='error') AS 标注错误, COUNT(*) FILTER (WHERE sentiment_polarity='positive') AS 积极, COUNT(*) FILTER (WHERE sentiment_polarity='negative') AS 消极 FROM attitude_labels GROUP BY source_platform ORDER BY 平台;` },
  { label: '🔎 搜索职业', sql: `SELECT mentioned_profession AS 职业, COUNT(*) AS 讨论量, COUNT(*) FILTER (WHERE sentiment_polarity='positive') AS 积极, COUNT(*) FILTER (WHERE sentiment_polarity='negative') AS 消极, ROUND(COUNT(*) FILTER (WHERE sentiment_polarity='positive')::numeric / NULLIF(COUNT(*),0) * 100, 1) AS 积极率 FROM attitude_labels WHERE label_method='llm' AND mentioned_profession ILIKE '%程序员%' GROUP BY mentioned_profession ORDER BY 讨论量 DESC;` },
];

const presetsEl = document.getElementById('presets');
PRESETS.forEach(p => {
  const btn = document.createElement('button');
  btn.textContent = p.label;
  btn.onclick = () => { document.getElementById('sql').value = p.sql; run(); };
  presetsEl.appendChild(btn);
});

document.getElementById('sql').addEventListener('keydown', e => {
  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) run();
});

async function run() {
  const sql = document.getElementById('sql').value.trim();
  if (!sql) return;
  const status = document.getElementById('status');
  const error = document.getElementById('error');
  const stats = document.getElementById('stats');
  const container = document.getElementById('table-container');
  error.style.display = 'none';
  status.textContent = '执行中…';
  stats.textContent = '';
  container.innerHTML = '<p class="loading">⟳ 查询中…</p>';
  
  try {
    const resp = await fetch('/query', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({sql})
    });
    const data = await resp.json();
    if (data.error) {
      error.textContent = '❌ ' + data.error;
      error.style.display = 'block';
      container.innerHTML = '';
      status.textContent = '';
      return;
    }
    status.textContent = `耗时 ${data.time_ms}ms · ${data.rows} 行`;
    stats.textContent = `列: ${data.columns.join(', ')}`;
    renderTable(data.columns, data.data);
  } catch(e) {
    error.textContent = '❌ 请求失败: ' + e.message;
    error.style.display = 'block';
    container.innerHTML = '';
    status.textContent = '';
  }
}

let sortCol = -1, sortAsc = true;
function renderTable(cols, rows) {
  const container = document.getElementById('table-container');
  sortCol = -1; sortAsc = true;
  
  let html = '<table><thead><tr>';
  cols.forEach((c, i) => {
    html += `<th onclick="sortTable(${i})">${c}</th>`;
  });
  html += '</tr></thead><tbody>';
  rows.forEach(r => {
    html += '<tr>' + r.map(v => `<td>${v === null ? 'NULL' : v}</td>`).join('') + '</tr>';
  });
  html += '</tbody></table>';
  container.innerHTML = html;
}

function sortTable(col) {
  const container = document.getElementById('table-container');
  const table = container.querySelector('table');
  if (!table) return;
  const tbody = table.querySelector('tbody');
  const rows = Array.from(tbody.querySelectorAll('tr'));
  
  if (sortCol === col) sortAsc = !sortAsc;
  else { sortCol = col; sortAsc = true; }
  
  rows.sort((a, b) => {
    let va = a.cells[col].textContent, vb = b.cells[col].textContent;
    let na = parseFloat(va), nb = parseFloat(vb);
    if (!isNaN(na) && !isNaN(nb)) { va = na; vb = nb; }
    if (va < vb) return sortAsc ? -1 : 1;
    if (va > vb) return sortAsc ? 1 : -1;
    return 0;
  });
  
  rows.forEach(r => tbody.appendChild(r));
  
  // Update sort indicators
  table.querySelectorAll('th').forEach((th, i) => {
    th.className = i === col ? (sortAsc ? 'sorted-asc' : 'sorted-desc') : '';
  });
}
</script>
</body>
</html>
"""

PRESET_QUERIES = {
    "职业积极排行": "SELECT mentioned_profession AS 职业, COUNT(*) AS 讨论量, COUNT(*) FILTER (WHERE sentiment_polarity='positive') AS 积极, COUNT(*) FILTER (WHERE sentiment_polarity='negative') AS 消极, ROUND(COUNT(*) FILTER (WHERE sentiment_polarity='positive')::numeric / NULLIF(COUNT(*),0) * 100, 1) AS 积极率 FROM attitude_labels WHERE label_method='llm' AND mentioned_profession IS NOT NULL GROUP BY mentioned_profession ORDER BY 讨论量 DESC;",
}

@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/query', methods=['POST'])
def query():
    sql = request.json.get('sql', '').strip()
    if not sql:
        return jsonify({"error": "SQL 不能为空"})
    
    # Basic safety: only allow SELECT
    if not sql.upper().lstrip().startswith('SELECT'):
        return jsonify({"error": "只允许 SELECT 查询"})
    
    import time
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
    return jsonify({
        "columns": cols,
        "data": data,
        "rows": len(data),
        "time_ms": elapsed
    })

if __name__ == '__main__':
    print("🚀 VoxPop SQL 查询工具")
    print(f"   访问 http://127.0.0.1:5000")
    app.run(host='127.0.0.1', port=5000, debug=False)
