# AI雷达（ai_radar）

AI超市生态下的**独立情报产品**：自动捕捉 Google / OpenAI / Claude / DeepSeek / Kimi / GLM / Qwen 等大模型发布动态，去重后整理成中文速报，推送到**飞书群机器人**和**微信个人（PushPlus）**。

纯 Python、可定时跑，不依赖任何云平台账号。

## 能力
- **采集**：HuggingFace 模型 API（最稳，覆盖各厂商官方组织）+ 官方博客 RSS（OpenAI/Google/Anthropic），按关键词过滤「模型发布」类条目。
- **去重**：`seen.json` 记录已见条目，绝不重复推送；首次运行自动建立基线。
- **摘要**：配了 `DEEPSEEK_API_KEY` 则生成中文速报；没配也有纯列表兜底。
- **推送**：飞书（interactive 卡片）+ 微信个人（PushPlus markdown）。

## 快速开始
```bash
pip install -r requirements.txt
cp .env.example .env        # 按需填入 FEISHU_WEBHOOK / PUSHPLUS_TOKEN / DEEPSEEK_API_KEY
python radar.py             # 本地预览（首次会建基线）
python radar.py --push      # 抓取新动态并推送
```

## 配置（.env）
| 变量 | 说明 | 必填 |
|---|---|---|
| `DEEPSEEK_API_KEY` | 中文摘要用，不填则纯列表 | 否 |
| `FEISHU_WEBHOOK` | 飞书群机器人 webhook（`https://open.feishu.cn/open-apis/bot/v2/hook/xxx`） | 推送飞书时必填 |
| `PUSHPLUS_TOKEN` | PushPlus token（https://www.pushplus.plus） | 推送微信时必填 |

### 飞书群机器人
飞书群 → 设置 → 群机器人 → 添加机器人 → 复制 webhook 地址填到 `FEISHU_WEBHOOK`。

### 微信个人推送（PushPlus）
1. 打开 https://www.pushplus.plus ，微信扫码登录。
2. 控制台拿到 `token`，填到 `PUSHPLUS_TOKEN`。
3. 关注「PushPlus 推送加」公众号即可收到。

## 定时运行
- **本机 cron**（需联网 + 已填 .env）：
  ```cron
  0 9 * * * cd /path/to/ai_radar && /usr/bin/python3 radar.py --push >> radar.log 2>&1
  ```
- **服务器**：同上，部署到任意有公网/联网的机器即可。
- **WorkBuddy 自动化**：可设一个每天 09:00 的定时任务跑 `python radar.py --push`（注意运行环境需能联网）。

## 自定义监控源
编辑 `sources.py` 的 `SOURCES` 列表：加 `HuggingFaceSource("组织名", "展示名")` 或 `RssSource("订阅地址", "展示名")`。想监控更多中国厂商，加对应 HuggingFace 组织即可（如 `ZhipuAI`、`Alibaba-NLP` 等）。

## 目录
```
ai_radar/
├── radar.py          # 主流程
├── sources.py        # 采集源（HF + RSS）
├── store.py          # 去重 seen.json
├── digest.py         # 中文摘要 / 兜底
├── notifiers.py      # 飞书 + PushPlus 推送
├── requirements.txt
├── .env.example
└── seen.json         # 运行时生成（已 gitignore）
```
