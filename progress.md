# Progress Log — VoxPop 全岗位态度盘点

## Phase 1-3: 调研+骨架+流水线 ✅
## Phase 4: 全量运行（wb+bili+xhs 2,691）✅

## Phase 5: 扩展数据源（知乎）✅
### BroadTopicExtraction + DeepSentimentCrawling ✅
- MindSpider CLI `--broad-topic → --deep-sentiment --platforms zhihu`
- BroadTopicExtraction：12 新闻源 → 63 个关键词 + 岗位关键词混入
- 产出：141 条内容 + 5,219 条评论写入 zhihu_content/zhihu_comment

### API 切换与错误修复 ✅
- 发现 labeler_fast.py 缺 Authorization header → 全部 401 fallback
- 修复后首批 866 LLM（被 PackyAPI rate limit）
- 切换至 **DeepInfra Llama 3.1 8B**
- 错误处理改为标记 error，不退回中性
- 清空重标后 1,771 LLM（标准化 prompt）

## Phase 6: 迭代优化 ✅
### Prompt 标准化 ✅
- 新增规则 5：职业名称必须标准化
- 映射：前端/前端开发/前端开发者→前端工程师，码农/程序猿→程序员，老师/教师→教师，保姆/阿姨→保姆，老板/领导/经理→管理岗
- 效果验证：9 个前端变体归一为 1 个"前端工程师"

### SQL 查询 Web 工具 ✅
- Flask + 原生 JS，运行在 http://127.0.0.1:5000
- 6 个预设排行榜 + 自由 SQL 输入 + 表头排序

### 反馈闭环脚本 ✅
- feedback_keywords.py：从标注结果提取低样本职业 → 生成爬虫关键词 → 喂给 MindSpider
- 已发现 296 个职业样本 < 10，262 个 < 3
- `--apply` 参数写入 daily_topics 表

## 最终数据汇总
| 平台 | 总计 | LLM 标注 | 积极 | 消极 |
|------|------|---------|------|------|
| weibo | 1,102 | 164 | 9 | 16 |
| bilibili | 276 | 30 | 3 | 9 |
| xhs | 1,313 | 0 | 0 | 0 |
| zhihu | 5,350 | 1,771 | — | — |
| **合计** | **8,041** | **1,965** | — | — |

## 5-Question Reboot Check
| 问题 | 回答 |
|------|------|
| Where am I? | Phase 6 完成，闭环已建立 |
| Where am I going? | 跑反馈闭环第二轮爬取 |
| What's the goal? | 全岗位态度排行盘点 |
| What have I learned? | See findings.md |
| What have I done? | See progress.md (above) |
