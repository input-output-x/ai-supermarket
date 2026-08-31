# AI 口播视频工坊

Vue3 + FastAPI + MySQL 的全栈网站：上传任意图片 + 口播稿，生成 9:16 竖版口播短视频。

## 功能

- 保留并播放原 `ai_supermarket` 生成的成片
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

# 唇形同步 Provider：local（默认）/ heygen（需 key）
export LIPSYNC_PROVIDER=local
# export HEYGEN_API_KEY=sk-xxx

uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

接口：
- `GET /api/health`
- `GET /api/legacy-video`：原保留成片信息
- `GET /api/legacy-video/stream`：原保留成片流
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

当前 `local` Provider 使用 **edge-tts 配音 + 简单嘴部动画**（非真实口型）。
要做成抖音上那种逼真的数字人对口型，需要接入外部数字人 API：
- HeyGen API
- D-ID API
- 可灵 / 即梦 / 阿里 EMO 等图像生成视频接口

后端已预留 `LipSyncProvider` 抽象和 `HeyGenProvider` 占位，只要拿到 key 就能切换。
