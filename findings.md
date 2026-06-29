# Findings & Decisions — VoxPop 全岗位态度盘点

## 最终数据（2026-06-29）
| 平台 | 总计 | LLM 标注 | 本地模型 | 错误 |
|------|------|---------|---------|------|
| zhihu | 31,371 | 8,636 | 22,413 | 322 |
| weibo | 4,451 | 865 | 3,572 | 14 |
| bilibili | 3,536 | 1,115 | 2,383 | 38 |
| xhs | 1,692 | 26 | 1,663 | 3 |
| **合计** | **41,050** | **10,642** | **30,031** | **377** |

## 🚧 踩坑记录：DeepInfra Function Calling 不可用

**问题：** 尝试用 DeepInfra 的 function calling（OpenAI 兼容的 `tools` 参数）来约束 Llama 3.1 8B 的输出格式。结果不可靠。

### 现象
| 尝试 | tool_choice | 结果 |
|------|------------|------|
| `tool_choice: "auto"` | 字符串 | 一半 tool_calls 为空，模型选择不调 |
| `tool_choice: "required"` | 字符串 | 全部空，不支持 |
| `tool_choice: {"type": "function", ...}` | dict | 全部空，不支持 |
| 并发 50 + 3 次重试 | auto | 仅 26% 成功 |
| 串行 + 3 次重试 | auto | 100%（但太慢） |

### 根因
1. **DeepInfra 不支持 `tool_choice: "required"`**——OpenAI 有的它没有
2. **`auto` 给了模型选择权**——Llama 3.1 8B 约一半概率不调 function
3. **并发下 DeepInfra 丢请求**——HTTP 200 但 content+tool_calls 全空，甚至断连
4. **`response_format: {"type": "json_object"}` 才是正解**——解码层约束，token 阶段就限制了

### 教训
- DeepInfra function calling 只适合串行低并发
- 强制约束输出格式用 `response_format: json_object`，不是 function calling
- 官方博客：https://deepinfra.com/blog/deepinfra-json-only-responses

## 技术决策
| 决策 | 原因 |
|------|------|
| `response_format: json_object` 替代 function calling | 解码层约束，50 并发 100% 成功 |
| 简化 system prompt | json_object 模式不需复杂格式说明 |
| 删除 `_legacy_parse_json` | json_object 保证输出始终是合法 JSON |
