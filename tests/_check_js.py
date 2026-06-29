#!/usr/bin/env python3
"""检查 JavaScript 语法错误"""
import re, subprocess, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sql_query_app import app

with app.test_client() as c:
    html = c.get('/').data.decode('utf-8')

m = re.search(r'<script>(.*?)</script>', html, re.DOTALL)
js = m.group(1)

with open('/tmp/voxpop_script.js', 'w') as f:
    f.write(js)

import subprocess
result = subprocess.run(
    ['node', '-e', '''
const fs = require("fs");
const code = fs.readFileSync("/tmp/voxpop_script.js", "utf8");
try {
    new Function(code);
    console.log("OK");
} catch(e) {
    console.log("ERROR: " + e.message);
    const mm = e.stack.match(/:(\\d+):(\\d+)/);
    if (mm) {
        console.log("Line: " + mm[1] + ", Col: " + mm[2]);
        const lines = code.split("\\n");
        for (let i = Math.max(0, parseInt(mm[1])-3); i < Math.min(lines.length, parseInt(mm[1])+2); i++) {
            console.log((i+1) + ": " + lines[i].substring(0, 120));
        }
    }
}
'''],
    capture_output=True, text=True, timeout=10
)
print("STDOUT:", result.stdout)
if result.stderr:
    print("STDERR:", result.stderr[:300])
