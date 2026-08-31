"""ai-publish：发布 Agent（必备，流量引擎第 4 环）—— 真实抖音开放平台接入。

职责：
  1) 永远产出标题备选 + 话题标签（离线，无需 key）
  2) 真正把成片推到抖音开放平台（需配置凭证 + OAuth 授权）

抖音开放平台真实流程（video.create 权限）：
  a. 授权：构造 authorize_url → 用户在抖音端同意 → 拿到 code
  b. 换 token：POST /oauth/access_token/ （client_key/secret/code）→ access_token + open_id
  c. 上传：POST /api/douyin/v1/video/upload_video/ （multipart 视频）→ video_id
  d. 发布：POST /api/douyin/v1/video/create_video/ （video_id + 文案）→ 发布成功

凭证（全部走环境变量，绝不入库）：
  DOUYIN_CLIENT_KEY / DOUYIN_CLIENT_SECRET / DOUYIN_REDIRECT_URI
  DOUYIN_ACCESS_TOKEN / DOUYIN_OPEN_ID（OAuth 换得后填入；也可用 /api/agents/publish/auth 回调写入）
未配置时：返回清晰的"未配置 / 未授权"状态 + 授权链接，绝不假装发布成功。
"""
import os
import requests
from typing import Optional
from urllib.parse import quote

from ..core.agent import AbstractAgent
from ..core.context import AgentContext

DOUYIN_BASE = "https://open.douyin.com"


class DouyinClient:
    """抖音开放平台最小客户端（真实接口，凭证缺失时给出明确状态）。"""

    def __init__(self) -> None:
        self.client_key = os.getenv("DOUYIN_CLIENT_KEY")
        self.client_secret = os.getenv("DOUYIN_CLIENT_SECRET")
        self.redirect_uri = os.getenv("DOUYIN_REDIRECT_URI", "")
        self.access_token = os.getenv("DOUYIN_ACCESS_TOKEN")
        self.open_id = os.getenv("DOUYIN_OPEN_ID")

    def is_configured(self) -> bool:
        return bool(self.client_key and self.client_secret)

    def is_authorized(self) -> bool:
        return bool(self.access_token and self.open_id)

    def authorize_url(self, state: str = "ai_supermarket") -> Optional[str]:
        if not self.client_key:
            return None
        scope = "video.create,user.info"
        return (
            f"{DOUYIN_BASE}/platform/oauth/connect/"
            f"?client_key={self.client_key}&response_type=code"
            f"&scope={quote(scope)}&redirect_uri={quote(self.redirect_uri)}&state={state}"
        )

    def exchange_code(self, code: str) -> dict:
        r = requests.post(
            f"{DOUYIN_BASE}/oauth/access_token/",
            json={
                "client_key": self.client_key,
                "client_secret": self.client_secret,
                "code": code,
                "grant_type": "authorization_code",
            },
            timeout=30,
        )
        return r.json()

    def upload(self, video_path: str) -> dict:
        with open(video_path, "rb") as f:
            r = requests.post(
                f"{DOUYIN_BASE}/api/douyin/v1/video/upload_video/",
                files={"video": f},
                headers={"access-token": self.access_token},
                params={"open_id": self.open_id},
                timeout=180,
            )
        return r.json()

    def create_video(self, video_id: str, text: str) -> dict:
        r = requests.post(
            f"{DOUYIN_BASE}/api/douyin/v1/video/create_video/",
            json={"video_id": video_id, "text": text or ""},
            params={"access_token": self.access_token, "open_id": self.open_id},
            timeout=30,
        )
        return r.json()

    def publish(self, video_path: str, text: str) -> dict:
        """上传 + 发布成片，返回抖音结果。"""
        up = self.upload(video_path)
        vid = (up.get("data") or {}).get("video", {}).get("video_id") or (up.get("video") or {}).get("video_id")
        if not vid:
            return {"status": "upload_failed", "raw": up}
        created = self.create_video(vid, text)
        ok = (created.get("data") or {}).get("item_id") or (created.get("item_id"))
        return {
            "status": "published" if ok else "create_failed",
            "video_id": vid,
            "item_id": ok,
            "raw": created,
        }


class PublishAgent(AbstractAgent):
    name = "publish"

    def __init__(self) -> None:
        super().__init__()
        self.client = DouyinClient()

    @staticmethod
    def _titles(base: str) -> list:
        base = base or "AI超市"
        return [base, f"别再错过！{base}", f"{base}｜普通人也能上手", f"我用AI做了{base}"]

    @staticmethod
    def _tags() -> list:
        return ["#AI创业", "#副业", "#AI超市", "#短视频带货"]

    def _run(self, ctx: AgentContext) -> AgentContext:
        title = ctx.get("topicTitle") or ctx.get("title") or ""
        video_path = ctx.get("video_path")

        # 1) 永远产出标题/标签候选（离线能力）
        titles, tags = self._titles(title), self._tags()

        # 2) 真实发布（按配置状态分级返回，绝不假成功）
        if not self.client.is_configured():
            publish_result = {
                "status": "unconfigured",
                "message": "未配置抖音开放平台凭证（DOUYIN_CLIENT_KEY/SECRET），publish 为占位。",
            }
        elif not self.client.is_authorized():
            publish_result = {
                "status": "need_auth",
                "message": "已配置 client_key，但还未 OAuth 授权。请用下方链接在抖音端授权。",
                "authorize_url": self.client.authorize_url() or "（请先设置 DOUYIN_REDIRECT_URI）",
            }
        elif not video_path or not os.path.exists(video_path):
            publish_result = {
                "status": "need_video",
                "message": "已授权，但本次未提供成片路径（video_path），仅返回标题/标签候选。",
            }
        else:
            try:
                publish_result = {"status": "publishing", **self.client.publish(video_path, " ".join(tags))}
            except Exception as e:
                publish_result = {"status": "publish_error", "message": str(e)}

        return (ctx.put("titleCandidates", titles)
                   .put("hashtags", tags)
                   .put("publishResult", publish_result)
                   .put("status", "done"))
