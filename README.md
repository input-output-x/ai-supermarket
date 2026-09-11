# AI超市 · ai_supermarket

> 多 Agent 内容/服务矩阵——像超市货架一样，客户按需选用。

## 核心 Agent（货架）

| Agent | 说明 | handler |
|-------|------|---------|
| **topic** · 爆款选题 | LLM + 热点源 + 向量去重 | llm |
| **script** · 口播脚本 | 选题 → 口播稿/分镜 | llm |
| **video** · 口播视频 | 口播稿 → 配音+字幕竖版成片（9:16） | video |
| **publish** · 抖音发布 | 抖音开放平台 OAuth + 上传 + 发布（env 驱动） | publish |
| **service** · 私域承接客服 | 意图分类 + 线索 + 话术 + 路由 | llm |
| **delivery** · 交付调度 | 订单拆成可执行 SOP（交付物/步骤/角色/工期/验收） | llm |
| **analytics** · 数据复盘 | 播放/转化/互动数据复盘，反哺下期选题脚本权重 | llm |

## 目录结构

```
ai_supermarket/
├── pyproject.toml
├── README.md
├── .env.example              # 环境变量模板
├── .gitignore
├── ai_supermarket/           # 核心包
│   ├── core/                 # 平台内核（LLM / Agent 抽象 / 上下文 / 注册中心）
│   ├── agents/               # 7 个 Agent（可扩展）
│   │   ├── topic.py
│   │   ├── script.py
│   │   ├── video.py
│   │   ├── publish.py
│   │   ├── service.py
│   │   ├── delivery.py
│   │   └── analytics.py
│   ├── gateway.py            # 聚合网关
│   └── run_pipeline.py       # CLI 入口
└── web/                      # Web 工坊（Vue3 + FastAPI + MySQL）
    ├── frontend/
    └── backend/
```

## 快速开始

```bash
cd ai_supermarket

# 1) 离线 Mock 跑主链路（无需密钥）
python -m ai_supermarket.run_pipeline "AI创业"

# 2) 接 Deepseek 真实大模型
export DEEPSEEK_API_KEY=sk-xxxx
python -m ai_supermarket.run_pipeline "普通人如何用AI智能体赚钱"

# 3) 启动网关
python -m ai_supermarket.run_pipeline --serve
```

## Web 工坊

```bash
cd web/backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

cd web/frontend
npm install && npm run dev
```

## GitHub

仓库：`https://github.com/input-output-x/ai-supermarket`
