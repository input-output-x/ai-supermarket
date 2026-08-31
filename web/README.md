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
