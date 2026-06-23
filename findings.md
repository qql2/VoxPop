# VoxPop — 调研发现

## 市场方案调研

### 商业舆情平台
| 平台 | 特点 | 不适合原因 |
|------|------|-----------|
| 新浪舆情通 | 微博官方数据、情感分析、报告生成 | 付费，封闭，不能做自定义"态度排行" |
| 舆情录 | 20类信源，免费7天 | 锁定为通用监控，不能本地化 |
| 启信舆情API | 企业级品牌口碑监控 | 不面向个人开发者 |

**结论**：没有直接可用的"全岗位态度盘点"成熟方案。

### 开源项目
- `Yoyo-0125/nlp-public-opinion-analysis`：微博+知乎爬取 + BERT 情感分析。功能浅，无排行逻辑。
- `MacchiatoZhou/Weibo_PublicOpinion_AnalysisSystem`：全栈舆情系统，偏学术方向。
- B站弹幕情感分析（GitHub samklein112）：学术级别的 demo 项目。

**结论**：都是实验级别或通用框架，没有一个做"态度排行盘点"的。

### 学术方向
- BERTopic + ALBERT-TextCNN 做微博多级舆情分析（2025 ACM论文）
- BERT-BiLSTM-DPCNN 在 B站+微博评论分类上达到 96.12% 精度
- 停留在实验阶段，工程化程度低

## BettaFish 现有能力盘点

### 可用模块

| 模块 | 路径 | 价值 |
|------|------|------|
| MindSpider BroadTopicExtraction | `MindSpider/BroadTopicExtraction/` | 从13个平台发现热点 + AI提取关键词 |
| MindSpider DeepSentimentCrawling | `MindSpider/DeepSentimentCrawling/` | 按关键词爬取 B站/微博 评论到数据库 |
| SentimentAnalysisModel | `SentimentAnalysisModel/` | 多个情感模型 |
| └─ WeiboSentiment_SmallQwen | .../WeiboSentiment_SmallQwen/ | Qwen3 0.6B~8B 微调，需 GPU |
| └─ WeiboMultilingualSentiment | .../WeiboMultilingualSentiment/ | HuggingFace distilbert，22语言 |
| └─ WeiboSentiment_MachineLearning | .../WeiboSentiment_MachineLearning/ | SVM/贝叶斯/LSTM/XGBoost基线 |
| InsightEngine | `InsightEngine/` | Deep Search Agent，已集成情感分析+报告生成 |

### 数据表
- `weibo_note` — 微博帖子（有 topic_id 关联）
- `weibo_note_comment` — 微博评论（有 content/ip_location/点赞等）
- `bilibili_video` — B站视频
- `bilibili_video_comment` — B站评论
- `daily_topics` — 话题（AI提取）
- `daily_news` — 每日热点新闻

### 平台兼容性
- ✅ 正常：微博 (wb)、B站 (bili)
- ❌ 不可用：抖音、快手、小红书、知乎、贴吧

## 技术方案推演

### 数据分析映射
```
ODS（原始层）→ weibo_note_comment / bilibili_video_comment
DWD（明细层）→ attitude_labels（新增标注表）
DWS（汇总层）→ attitude_rankings（新增排行缓存表）
ADS（应用层）→ 每日排行报告（JSON/MD）
```

### 级联标注效率估算
- 评论60-70%被关键词基线高置信度覆盖 → 0 额外成本
- 剩余 30-40% 走 LLM
- 如果日均 1000 条评论，约 300-400 条需 LLM，deepseek-chat 价格可忽略

### 职业提取策略
- 预定义词典匹配优先
- 单匹配 → 直接返回
- 多匹配 → 取第一（不引入多标复杂度）
- 无匹配 → LLM 兜底

## 代码结构（已创建）

```
AttitudeEngine/
├── config.py         # DB + LLM API 配置，独立 .env
├── db.py             # 读评论表、写 attitude_labels、聚合排行
├── labeler.py         # 级联标注核心
├── professions.py     # 预置 17 个职业关键词
├── reporter.py        # 排行报告输出
├── run.py             # 手动入口
├── schema.sql         # 3 张新表定义
├── .env.example       # 配置模板
├── requirements.txt   # 仅 3 个依赖
├── README.md          # 使用说明
├── task_plan.md       # 本文件
├── findings.md        # 本文件
└── progress.md        # 进度日志
```
