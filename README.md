# AI超市 · ai_supermarket

> 多 Agent 矩阵——像超市货架，客户按需选用。

## Agent 货架（8 个）

| # | Agent | 说明 | handler |
|---|-------|------|---------|
| 1 | **topic** · 爆款选题 | LLM + 热点源 + 向量去重 | llm |
| 2 | **script** · 口播脚本 | 选题 → 口播稿/分镜 | llm |
| 3 | **video** · 口播视频 | 口播稿 → 配音+字幕竖版成片（9:16） | video |
| 4 | **publish** · 抖音发布 | 抖音开放平台 OAuth + 上传 + 发布 | publish |
| 5 | **service** · 私域承接客服 | 意图分类 + 线索 + 话术 + 路由 | llm |
| 6 | **delivery** · 交付调度 | 订单拆成可执行 SOP（交付物/步骤/角色/工期/验收） | llm |
| 7 | **analytics** · 数据复盘 | 播放/转化/互动数据复盘，反哺下期选题脚本权重 | llm |
| 8 | **radar** · AI雷达 | 大模型发布动态采集（HF+RSS）→ 去重 → 中文速报 → 飞书/微信推送 | llm |

## 目录

```
ai_supermarket/
├── README.md
├── .env.example
├── .gitignore
└── ai_supermarket/
    ├── core/                 # Agent 内核（抽象/上下文/LLM）
    │   ├── agent.py
    │   ├── context.py
    │   └── llm.py
    └── agents/               # 8 个 Agent（可扩展）
        ├── topic.py
        ├── script.py
        ├── video.py
        ├── publish.py
        ├── service.py
        ├── delivery.py
        ├── analytics.py
        └── radar.py
```

## GitHub

`https://github.com/input-output-x/ai-supermarket`
