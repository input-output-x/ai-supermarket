# AI超市 · ai_supermarket

> 多 Agent 矩阵——像超市货架，客户按需选用。

## 前置 Agent（动手前先过这一关）

| # | Agent | 说明 |
|---|-------|------|
| 0 | **clarify** · 需求澄清官 | 动手前把模糊需求问清楚：第一轮按维度盘点缺口→带选项问题→风险；第二轮接收答案收敛需求画像+标出不可行点+路由到业务 Agent，避免方向跑偏、胡说八道 |

## 业务 Agent 货架（8 个）

| # | Agent | 说明 |
|---|-------|------|
| 1 | **topic** · 爆款选题 | LLM + 热点源 + 向量去重 |
| 2 | **script** · 口播脚本 | 选题 → 口播稿/分镜（支持 `shooting_mode`：默认「录屏」= 一人一台电脑屏幕录屏+画外音，分镜只写屏幕操作；也支持「真人」「混合」） |
| 3 | **video** · 口播视频 | 口播稿 → 配音+字幕竖版成片（9:16） |
| 4 | **publish** · 抖音发布 | 抖音开放平台 OAuth + 上传 + 发布 |
| 5 | **service** · 私域承接客服 | 意图分类 + 线索 + 话术 + 路由 |
| 6 | **delivery** · 交付调度 | 订单拆成可执行 SOP |
| 7 | **analytics** · 数据复盘 | 数据复盘，反哺下期选题脚本权重 |
| 8 | **radar** · AI雷达 | 大模型发布动态采集→去重→速报→飞书/微信推送 |

## 目录

```
├── README.md
├── .env.example
├── .gitignore
├── core/              # Agent 内核
│   ├── agent.py       #   AbstractAgent 基类
│   ├── context.py     #   AgentContext 上下文
│   └── llm.py         #   LLM 客户端（Deepseek）
└── agents/            # 9 个 Agent（可扩展）
    ├── clarify.py      #   需求澄清官（前置）
    ├── topic.py
    ├── script.py
    ├── video.py
    ├── publish.py
    ├── service.py
    ├── delivery.py
    ├── analytics.py
    ├── radar.py
    └── bench.py        #   实测横评工具：同一提示词发 GPT/Claude/DeepSeek/Kimi，有 key 才真跑（不编造）
```

## GitHub

`https://github.com/input-output-x/ai-supermarket`
