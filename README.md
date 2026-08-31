# AI超市 · ai_supermarket (Python)

> 多 Agent 微服务矩阵（Python 实现，架构对齐之前的 Java 示例）。
> 关系类比：`ai_supermarket`(包) ≈ Spring Cloud 父工程；`core` ≈ Spring Cloud 公共能力；`agents.*` ≈ 独立微服务；`gateway` ≈ 网关/聚合服务。

## 目录结构

```
ai_supermarket_python/
├── pyproject.toml
├── README.md
└── ai_supermarket/
    ├── core/            # 平台内核
    │   ├── agent.py        Agent 抽象 / AbstractAgent 模板
    │   ├── context.py      AgentContext 流转上下文
    │   ├── registry.py     AgentRegistry 注册中心（类 Nacos）
    │   ├── eventbus.py     EventBus 事件总线（类 Stream）
    │   ├── orchestrator.py  AiSupermarketOrchestrator 主链路编排
    │   └── llm.py          LLM 客户端（Mock/OpenAI 兼容 + 向量余弦）
    ├── agents/          # 7 个 Agent 微服务
    │   ├── topic.py        【必备·真实逻辑】选题：LLM + 热点源 + 向量去重
    │   ├── script.py       【必备】脚本：选题 -> 口播稿/分镜
    │   ├── video.py        【必备】视频：脚本 -> 成片（接文生视频/ffmpeg 处已标 TODO）
    │   ├── publish.py      【必备】发布：成片 -> 多平台（接开放平台API 处已标 TODO）
    │   ├── service.py      【其他·脚手架】客服（承接层）
    │   ├── delivery.py     【其他·脚手架】交付（交付层）
    │   └── analytics.py    【其他·脚手架】数据复盘（交易层反馈）
    ├── assets/          # 热点种子 + 选题去重历史
    │   ├── hot_topics.json
    │   └── topic_history.jsonl
    ├── gateway.py       # 聚合/网关服务：注册4 Agent，串主链路 + HTTP 接口
    └── run_pipeline.py  # 入口：跑一次链路 / --serve 起 HTTP
```

## 运行

```bash
# 需要 Python >= 3.10（本机用托管的 3.13.12 验证过）
cd ai_supermarket_python

# 1) 跑一次每日主链路（离线 Mock，无需任何密钥）
python -m ai_supermarket.run_pipeline "AI创业"

# 2) 启动网关 HTTP 服务（POST /pipeline, GET /health）
python -m ai_supermarket.run_pipeline --serve
curl -XPOST localhost:8080/pipeline -H 'Content-Type: application/json' -d '{"keyword":"AI创业"}'
```

## 接真实大模型（可选）

设置环境变量后，`core/llm.py` 自动从 MockProvider 切到 OpenAI 兼容接口：

```bash
export AI_SUPERMARKET_API_KEY=sk-xxx
export AI_SUPERMARKET_BASE_URL=https://api.openai.com/v1   # 可换任意兼容端点
export AI_SUPERMARKET_MODEL=gpt-4o-mini
export AI_SUPERMARKET_EMBED_MODEL=text-embedding-3-small
```

## ai-topic 真实选题逻辑（已落地）

1. `LocalHotSource.fetch()` 拉热点候选（可换成 WebHotSource 接热点榜 API）。
2. 每个候选 `llm.embed(title)` 取向量，`DedupStore.is_duplicate` 用余弦相似度（阈值 0.85）去重，避免连发同款。
3. `llm.chat(...)` 对候选打分 0-100，综合「模型分 60% + 热度 40%」选最优。
4. `llm.chat(...)` 生成选题卡片 JSON（topicTitle/hook/audience/linkService），并写回去重历史。

## 本次交付范围

- ✅ Python 重写整套 ai_supermarket；`ai-topic` 接 LLM + 热点源 + 去重，已实跑验证。
- ✅ `gateway.py` 聚合/网关服务把 topic→script→video→publish 串起来真跑，并暴露 HTTP。
- 🔲 `ai-service / ai-delivery / ai-analytics` 脚手架就位，等后续填充。
- 🔜 后续：video/publish 接真实外部 API；把 Mock 换成真实 LLM；service/delivery/analytics 落地，闭环补全。
