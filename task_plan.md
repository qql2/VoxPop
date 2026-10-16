# Plan: Langfuse 接入

## 目标
在现有的 DeepInfra LLM 标注调用中插入 Langfuse trace，
追踪每次 API 调用的 token 用量、耗时、成功/失败。

## 可回滚策略（两重保障）

```
① Git 分支: feat/langfuse — 独立分支，不影响 main
② 特性开关: LANGFUSE_ENABLED=false — 关掉就和现在一样

回滚最快路径:
  git checkout main              # 切回主干
  OR
  .env 里 LANGFUSE_ENABLED=false # 不加载即可
```

## 改动清单

### 1. `config.py` — 新增 Langfuse 配置（4 行）
```python
LANGFUSE_ENABLED: bool = False          # 特性开关，默认关
LANGFUSE_HOST: str = "https://cloud.langfuse.com"
LANGFUSE_PUBLIC_KEY: str = ""
LANGFUSE_SECRET_KEY: str = ""
```

### 2. `.env.example` — 注释文档
```
# --- Langfuse（LLM 可观测性） ---
LANGFUSE_ENABLED=false
LANGFUSE_HOST=https://cloud.langfuse.com
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
```

### 3. `labeler_fast.py` — 核心改动（~20 行，3 处）
- **模块顶部**：`from langfuse import Langfuse`（条件导入，若未安装或禁用则跳过）
- **`batch_label_async()` 函数内**：在调用 `asyncio.gather` 前初始化 Langfuse 单例
- **`_call_api_async()` 函数内**：在 `client.post()` 前后用 `@observe()` / `langfuse.trace()` 包装

   具体埋点位置：
   ```python
   # 现有代码:
   resp = await client.post(...)         ← 替换为 langfuse.trace() 包裹
   # 之后拿到:
   usage = data.get("usage", {})         ← Langfuse 自动收集
   ```

   跟踪维度：
   | 维度 | 来源 |
   |------|------|
   | prompt_tokens | usage.prompt_tokens |
   | completion_tokens | usage.completion_tokens |
   | model | request_body["model"] |
   | latency | 自动 |
   | success/error | 根据 resp.status_code |
   
### 4. `requirements.txt` — 加一行
```
langfuse>=2.0.0
```

### 5. 不改的文件
- `run_label_cron.py` — 不改
- `observer.py` — 不改（Langfuse 是补充，不替代现有统计）
- `db.py` — 不改
- `sql_query_app.py` — 不改

## 分支操作流程

```bash
git checkout -b feat/langfuse       # 新建特性分支
# ... coding ...
git add ...
git commit -m "feat: 接入 Langfuse LLM 可观测性"
git checkout main                   # 切回 main
# 测试稳定后合并:
git merge feat/langfuse
git branch -d feat/langfuse         # 删除特性分支
```

## 测试方式
1. `LANGFUSE_ENABLED=false` → 跑一次标注，确认输出和现在完全一致
2. `LANGFUSE_ENABLED=true` + 填入真实 key → 跑一次，确认 Langfuse dashboard 出现 trace

## 回滚方式
| 场景 | 操作 | 恢复时间 |
|------|------|---------|
| 代码有问题 | `git checkout main` | 秒级 |
| Langfuse 服务故障 | `.env` 设 `LANGFUSE_ENABLED=false` + 重启 | 秒级 |
| 不需要了 | `git branch -D feat/langfuse` | 永久 |
