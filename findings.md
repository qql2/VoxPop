# Findings & Decisions — VoxPop 全岗位态度盘点

## 最终数据（2026-07-01）
| 平台 | 总计 | LLM 标注 | 本地模型 | 错误 |
|------|------|---------|---------|------|
| zhihu | 31,371 | 8,636 | 22,413 | 322 |
| weibo | 4,451 | 865 | 3,572 | 14 |
| bilibili | 3,536 | 1,115 | 2,383 | 38 |
| xhs | 1,692 | 26 | 1,663 | 3 |
| **合计** | **44,566** | **10,642** | **30,031** | **377** |

## DeepInfra 技术探索

### 结论：用 `response_format: json_object`，不用 function calling

| 方法 | 成功率 | 说明 |
|------|--------|------|
| system prompt 教 JSON | ~50% | 模型常跑题输出对话/代码 |
| function calling (tool_choice=auto) | ~50% | DeepInfra 不支持 required，模型选择不调 |
| function calling (tool_choice=required) | 0% | DeepInfra 不支持 |
| **`response_format: {"type": "json_object"}`** | **99%+** | **解码层约束，token 阶段限制输出** |

`response_format: json_object` 是 DeepInfra 基于 vLLM 的 constrained decoding 实现。非 Turbo 模型（去掉 `-Turbo` 后缀）质量更好。

### 并发性能
- 100 并发短 prompt：100% 成功
- 20 并发长 prompt + json_object：100% 成功
- 20 并发长 prompt + function calling：40-60% 空响应

## 前端架构
| 决策 | 原因 |
|------|------|
| HTML 抽离到 `templates/index.html` | 内联字符串无法语法高亮，转义坑多 |
| Alpine.js（31.7k ★） | 7kB CDN，声明式，无需构建 |
| Tab 切换混合 Alpine + onclick | Alpine $watch 有兼容问题 |
| SSE 实时日志 | 比 WebSocket 简单，Flask 原生支持 |

## 🚧 踩坑记录

### DeepInfra Function Calling
- `tool_choice: "required"` 不支持，`"auto"` 给模型选择权
- 根因：DeepInfra 接受 tools 参数但不把 Llama 的 `<function=name>` 格式转成 OpenAI 的 tool_calls
- 修复：用 `response_format: json_object` 替代

### JS 解析失败
- 内联 HTML `r"""` 中 `\'` 转义导致 JS 报错
- 修复：HTML 抽到独立文件，用 data-* 属性代替内联转义

### 护拦漏数据
- 错误率 >50% 时 return 前没 insert_labels
- 修复：先写库再停止
