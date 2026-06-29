#!/usr/bin/env python3
"""调试 HTML 模板结构"""
with open('/Users/Admin1/VoxPop/sql_query_app.py') as f:
    content = f.read()

start = content.index('HTML = r"""') + len('HTML = r"""')
end = content.index('"""', start)
html_content = content[start:end]

print(f"HTML 模板长度: {len(html_content)} 字符")
print(f"<script> 标签: {html_content.count('<script>')} 处")
print(f"</script> 标签: {html_content.count('</script>')} 处")
print(f"<div class=\"presets\": {html_content.count('<div class=\"presets\"')} 处")

# 检查 js 部分
js_start = html_content.index('<script>') + len('<script>')
# 找到最后一个 </script>
last_close = html_content.rindex('</script>')
js = html_content[js_start:last_close]
print(f"JavaScript 代码长度: {len(js)} 字符")
print(f"const BASE_PRESETS = : {js.count('const BASE_PRESETS')} 处")
print(f"BASE_PRESETS.forEach: {js.count('BASE_PRESETS.forEach')} 处")
print(f"loadStatus 定义: {'function loadStatus' in js}")

# 尝试编译
try:
    compile(js, '<page>', 'exec')
    print("✅ JavaScript 编译通过")
except SyntaxError as e:
    print(f"❌ JavaScript 语法错误: {e}")
