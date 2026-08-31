# AI 口播视频工坊

Vue3 + FastAPI + MySQL 的全栈网站：上传任意图片 + 口播稿，生成 9:16 竖版口播短视频。

## 功能

- 上传图片（人物/动物/任何形象）
- 输入口播稿、选择音色
- 后端生成配音 + 字幕 + 嘴部动画，输出 1080×1920 MP4
- 历史记录列表与播放

## 技术栈

- 前端：Vue 3 + Vite + vue-router + axios
- 后端：FastAPI + SQLAlchemy + mysql-connector-python
- 视频：edge-tts（配音）+ PIL（字幕）+ ffmpeg（合成）
- 数据库：MySQL（或本地 SQLite 测试）

## 启动

### 1. 数据库

MySQL：
```sql
CREATE DATABASE ai_supermarket_web DEFAULT CHARSET utf8mb4;
```

或直接用 SQLite（无需额外操作）。

### 2. 后端

```bash
cd ai_supermarket/web/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# SQLite（默认）
export DATABASE_URL="sqlite:///$(pwd)/web_backend.db"

# 或 MySQL
# export DATABASE_URL="mysql+mysqlconnector://user:password@localhost/ai_supermarket_web"

# 唇形同步 Provider：local（默认）/ bailian（阿里百炼）/ heygen
export LIPSYNC_PROVIDER=local
# 真实逼真数字人（阿里云百炼 wan2.2-s2v 万相数字人，需要 key）
# export LIPSYNC_PROVIDER=bailian
# export DASHSCOPE_API_KEY=sk-xxx
# export HEYGEN_API_KEY=sk-xxx   # 如需 HeyGen 真实数字人

uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

接口：
- `GET /api/health`
- `POST /api/videos`：创建生成任务（multipart：image, script, voice, provider, title）
- `GET /api/videos/{id}`：查询任务状态
- `GET /api/videos`：历史列表
- `GET /api/videos/{id}/download?type=video|audio|cover`

## Agent 货架（客户任选 Agent + 套餐权限壳）

Web 工坊不仅是视频工具，也是 **AI 超市的货架**：客户登录后按套餐看到不同的 Agent，自由选用。

- `GET /api/agents`：返回当前客户套餐下的 Agent 货架，每个 Agent 标注 `locked`（是否该套餐不可用）与 `required_plan`。
  - 请求头带 `X-API-Key` 区分客户；不带则按 `free` 套餐（匿名体验）。
- `POST /api/agents/{id}/run`：运行指定 Agent。
  - `video` 类走 multipart（image + script + voice + provider），返回视频任务号。
  - 纯文本类（`topic`/`script`/`service`/`finance`/`delivery`/`analytics`）走 JSON，走真实大模型（Deepseek）输出（无 key 时走启发式兜底，仍返回结构化结果）。
  - `publish` 类（`抖音发布`）走 JSON（video_path + title）：未配置抖音凭证时返回授权链接，已授权则上传并发布成片。
- `GET /api/agents/publish/auth`：返回抖音开放平台 OAuth 授权链接（需先配置 `DOUYIN_CLIENT_KEY`）。
- `POST /api/agents/publish/exchange`：用 OAuth `code` 换取 `access_token` / `open_id`（写入环境变量后重启即可发布）。

套餐（权限壳核心，定义在 `backend/agents_registry.py`）：

| 套餐 | 可用 Agent |
| --- | --- |
| `free` | 口播视频、爆款选题 |
| `pro` | + 口播脚本、抖音发布、私域承接客服、财税专家 |
| `enterprise` | + 交付调度、数据复盘 |

演示客户（首次启动自动播种）：`sk-free-demo-2026` / `sk-pro-demo-2026` / `sk-ent-demo-2026`。

新增一个上架 Agent：在 `backend/agents_registry.py` 的 `AGENTS` 列表加一条（id / 名称 / 图标 / 分类 / 描述 / 套餐层级 / handler / 输入字段 schema），并在 `PLANS` 里把它加入对应套餐即可，前端货架自动渲染。

> 前端「Agent 货架」页（`/shelf`）提供套餐切换体验：切换 free/pro/enterprise 可直观看到哪些 Agent 被锁定。

### 3. 前端

```bash
cd ai_supermarket/web/frontend
npm install
npm run dev
```

浏览器打开 `http://localhost:5173`。

## 关于「真实唇形同步」

`local` Provider 使用 **edge-tts 配音 + 简单嘴部动画**（本地模拟，非真实口型），用于无 key 快速出片。

要做成抖音上那种逼真的数字人对口型，已内置 **`bailian` Provider（阿里云百炼 / DashScope 万相数字人 `wan2.2-s2v`）**：

- 输入：一张清晰正脸人物图 + 一段人声音频
- 输出：人物说话、口型 / 表情 / 肢体动作与音频同步的逼真视频
- 流程：edge-tts 生成配音 → 上传图/音频到百炼临时存储 → 调用 `wan2.2-s2v`（异步）→ 轮询 → 下载 → 适配 9:16 + 字幕
- 约束：单段音频须 < 20s（视频时长 = 音频时长），长口播稿会自动切片逐段生成再拼接

配置方式：

```bash
export LIPSYNC_PROVIDER=bailian
export DASHSCOPE_API_KEY=sk-xxx        # 阿里云百炼 / DashScope API Key
# 分辨率：默认 480P（0.5元/秒，抖音竖屏够用）；要更清晰设 720P（0.9元/秒）
export BAILIAN_RESOLUTION=480P
```

> 计费提示：百炼 `wan2.2-s2v` 按成功生成的视频秒数计费（失败不收费，会自动降级为本地 fallback）。
> 480P ≈ 0.5 元/秒，720P ≈ 0.9 元/秒。**默认 480P**，竖屏口播完全够用，能省约 44% 成本。

`HeyGenProvider` 也已预留为可插拔 Provider（配置 `HEYGEN_API_KEY` 即可切换）。

后端 Provider 通过 `video_engine.py` 中的 `LipSyncProvider` 抽象统一调度，新增数字人厂商只需实现该抽象并注册到 `_PROVIDERS`。
