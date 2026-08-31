# AI超市 · ai_supermarket

> 多 Agent 内容/服务矩阵（Python 实现）。
> 定位：把每日选题、口播脚本、视频成片、发布、客服、交付、复盘等环节拆成可独立演进、可插拔的 Agent；Agent 数量不限于固定 7 个，按需扩展。

## 已落地能力

- ✅ **真实大模型**：`core/llm.py` 接入 **Deepseek**（`DEEPSEEK_API_KEY`），无 key 时自动回退 Mock 离线跑。
- ✅ **真实选题**：`ai-topic` 用 LLM 评估 + 热点源 + 向量去重选最优题。
- ✅ **真实成片**：`ai-video` 用 **edge-tts 中文配音 + PIL 字幕 + ffmpeg 合成 1080×1920 竖版 mp4 + 封面**，跨平台（不依赖 libass）。
- ✅ **客服 Agent**：`ai-service` 真实意图分类（咨询/购买/售后/合作/闲聊）+ 线索抽取 + 回复话术 + 路由，离线有启发式兜底。
- ✅ **网关**：`gateway.py` 注册当前全部 Agent，`POST /pipeline` 串主链路，`GET /health` 展示 Agent 列表。
- ✅ **AI 口播视频工坊（Web）**：Vue + FastAPI + MySQL，上传图片 + 口播稿即可生成 9:16 竖版口播视频；唇形同步支持可插拔 Provider：**本地 fallback**（edge-tts+字幕+嘴部动画）与 **阿里云百炼 wan2.2-s2v 真实数字人（逼真对口型）**。
- ✅ **Agent 货架 + 套餐权限壳（Web）**：`/api/agents` 按客户套餐（free/pro/enterprise）返回可用/锁定 Agent 列表；客户可自由选用——选题/脚本/客服/财税为**真实大模型输出**，video 为真实成片，delivery/analytics 为脚手架提示。新增 Agent = 在 `web/backend/agents_registry.py` 加一条。

## 目录结构

```
ai_supermarket/
├── pyproject.toml
├── README.md
├── .env.example              # 环境变量模板（复制为 .env 填 key，已被 .gitignore 忽略）
├── .gitignore                # 忽略 .env / output/ / __pycache__ / 去重历史 / web 产物
├── ai_supermarket/           # 核心包
│   ├── core/                 # 平台内核
│   │   ├── agent.py             Agent 抽象
│   │   ├── context.py           AgentContext 流转上下文
│   │   ├── registry.py          AgentRegistry 注册中心
│   │   ├── eventbus.py          EventBus 事件总线
│   │   ├── orchestrator.py      主链路编排
│   │   └── llm.py               LLM 客户端（Deepseek / OpenAI 兼容 + 余弦去重）
│   ├── agents/               # Agent 微服务（数量可扩展）
│   │   ├── topic.py            选题：LLM + 热点源 + 向量去重
│   │   ├── script.py           脚本：选题 -> 口播稿/分镜
│   │   ├── video.py            视频：口播稿 -> 配音+字幕竖版成片
│   │   ├── publish.py          发布：抖音开放平台 OAuth + 上传 + 发布（真实接入，env 驱动）
│   │   ├── service.py          客服：意图分类 + 线索 + 话术 + 路由
│   │   ├── delivery.py         交付（脚手架，待填）
│   │   └── analytics.py        数据复盘（脚手架，待填）
│   ├── assets/               # 热点种子 + 选题去重历史（历史已被 gitignore）
│   ├── gateway.py            # 聚合/网关服务
│   └── run_pipeline.py       # CLI 入口
└── web/                      # AI 口播视频工坊（全栈网站）
    ├── frontend/             # Vue3 + Vite
    └── backend/              # FastAPI + SQLAlchemy + MySQL
```

## 运行核心 Agent 链路

```bash
# 需要 Python >= 3.10（建议用带 edge-tts 的 venv，成片配音需要）
cd ai_supermarket

# 1) 离线 Mock 跑一次每日主链路（无需任何密钥，视频无配音）
python -m ai_supermarket.run_pipeline "AI创业"

# 2) 接 Deepseek 真实大模型跑（需要网络）
export DEEPSEEK_API_KEY=sk-xxxx          # 仅运行时传入，切勿写入代码/提交
export DEEPSEEK_MODEL=deepseek-chat      # 可选
python -m ai_supermarket.run_pipeline "普通人如何用AI智能体赚钱"

# 3) 客服 Agent 演示
python -m ai_supermarket.run_pipeline --service "你们这个AI代运营怎么收费？我想给店里用"

# 4) 启动网关 HTTP 服务
python -m ai_supermarket.run_pipeline --serve
curl -XPOST localhost:8080/pipeline -H 'Content-Type: application/json' -d '{"keyword":"AI创业"}'
```

## AI 口播视频工坊（Web）

详见 `web/README.md`。一句话启动：

```bash
cd ai_supermarket/web
# 1. 起 MySQL（本地或 Docker）并创建库 ai_supermarket_web
# 2. 起后端
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
export DATABASE_URL="mysql+mysqlconnector://user:pass@localhost/ai_supermarket_web"
export LIPSYNC_PROVIDER=local   # 默认本地 fallback；填 bailian 需配置 DASHSCOPE_API_KEY（阿里百炼真实数字人）；填 heygen 需配置 HEYGEN_API_KEY
uvicorn backend.main:app --reload --port 8000

# 3. 起前端
cd frontend
npm install
npm run dev
```

## 接真实大模型说明

设置 `DEEPSEEK_API_KEY` 后，`core/llm.py` 自动从 Mock 切到 Deepseek 真实接口：

- chat：`https://api.deepseek.com/v1`（模型 `deepseek-chat`）。
- embed：**Deepseek 不提供 embedding 接口**，默认用本地「字符 bigram 哈希向量」做近似去重；
  如需真实语义向量，配置 `AI_SUPERMARKET_EMBED_BASE_URL / AI_SUPERMARKET_EMBED_KEY / AI_SUPERMARKET_EMBED_MODEL`。
- 也兼容任意 OpenAI 兼容端点（用 `AI_SUPERMARKET_API_KEY` 替代 `DEEPSEEK_API_KEY` 即可）。

> ⚠️ **密钥安全**：`DEEPSEEK_API_KEY` / `DASHSCOPE_API_KEY` 等只通过环境变量传入运行进程，绝不写入 `.py` / `.env`（已提交的是 `.env.example` 占位）。`.gitignore` 已屏蔽 `.env` 与 `output/`。

## 真实成片（ai-video）实现要点

1. `EdgeTTSEngine` 用 edge-tts 生成中文配音（微软免费语音 `zh-CN-XiaoxiaoNeural`），无网络时降级静音。
2. `PIL` 把每句口播渲染成透明 PNG 字幕（自动居中、半透明底框、中文换行）。
3. ffmpeg 把「纯色背景 + 字幕 PNG」逐句叠加成 1080×1920（9:16）竖版片段，再 concat 拼接。
4. 混音（配音 mp3）→ 最终 mp4；并抽取首帧做封面 jpg。
   - 全程不依赖 libass/subtitles 过滤器，普通 ffmpeg 即可出带字幕的成片。

## GitHub

仓库：`https://github.com/input-output-x/ai-supermarket`
（`.env` / `output/` / 密钥均不入库。）

## 按需取代码（sparse-checkout）

标准 `git clone` 会拉取整个仓库。若你只想取**某个 Agent 的代码**（而不是全部），用 sparse-checkout 只检出指定目录，体积更小、更快：

```bash
# 只取「视频 Agent」+ 它依赖的核心内核（core 提供 LLM/抽象，几乎所有 Agent 都依赖）
git clone --filter=blob:none --sparse https://github.com/input-output-x/ai-supermarket
cd ai_supermarket
git sparse-checkout set ai_supermarket/agents/video.py ai_supermarket/core

# 想再加「选题 Agent」
git sparse-checkout add ai_supermarket/agents/topic.py
```

要点：
- 每个 Agent 是 `ai_supermarket/agents/` 下的独立文件，可单独取。
- **Agent 几乎都依赖 `ai_supermarket/core/`**（LLM 客户端、Agent 抽象、上下文），单独取某个 Agent 时务必连 `core/` 一起取，否则跑不起来。
- 想更彻底地"每个 Agent 一个仓库"，可把 `agents/*` 拆成 git submodule（主仓用 submodule 引用，clone 时 `--recurse-submodules=<只选的>`）；但小项目维护成本高，一般先用 sparse-checkout 即可。
- 注意：**终端客户不使用 git**。客户用的"任选 Agent"发生在部署出去的 Web 工坊（见 `web/`，含 Agent 货架 + 套餐权限壳），与 clone 无关。

## 后续待办

- ✅ `ai-delivery` / `ai-analytics` 已落地（交付 SOP / 数据复盘，真实 LLM + 启发式兜底）。
- ✅ `ai-publish` 已接抖音开放平台真实流程（OAuth 授权 + 上传 + 发布，env 驱动；未配置凭证时返回授权链接，不假成功）。需用户自有 `DOUYIN_CLIENT_KEY/SECRET` 并完成 OAuth 才能实际发片。
- 🔲 `ai-video` 可接云端文生视频替换背景生成。
- 🔲 `ai-service` 接评论/私域 API，把流量真正接住转私域。
- 🔲 Web 工坊接 HeyGen / D-ID / Kling 等更多真实唇形同步 Provider（百炼 wan2.2-s2v 已接入，HeyGen 已预留）。
- 🔲 货架收费基础：给客户套餐做真实使用额度计量（当前 PLANS 仅控制可见性/可用性）。
