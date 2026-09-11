"""ai-radar：AI雷达 Agent——大模型发布动态采集+去重+推送。

职责：自动捕捉 Google/OpenAI/Claude/DeepSeek/Kimi/GLM/Qwen 等最新模型发布动态，
      去重后整理成中文速报，推送到飞书/微信。
输入：mode（preview/push）、关键词（可选过滤）
输出：digest（速报文本）/ push_result（推送状态）
工具：HuggingFace API + RSS + DeepSeek 摘要 + 飞书/PushPlus
"""
import json
import os
import time
import logging
import requests
import feedparser
from urllib3.util.retry import Retry
from abc import abstractmethod

from ..core.agent import AbstractAgent
from ..core.context import AgentContext
from ..core.llm import get_provider

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AIRadar/1.0)"}
TIMEOUT = 8

# 零重试会话：被墙/超时时快速失败，避免批量源卡死
_SESSION = requests.Session()
_SESSION.mount(
    "https://",
    requests.adapters.HTTPAdapter(max_retries=Retry(connect=0, read=0, redirect=0)),
)

KEYWORDS = [
    "gpt", "claude", "gemini", "deepseek", "kimi", "glm", "qwen", "llama",
    "mistral", "grok", "o1", "o3", "o4", "4o", "发布", "推出", "上线",
    "开源", "release", "launch", "model", "模型",
]


def _hits_keywords(text: str) -> bool:
    t = (text or "").lower()
    return any(k.lower() in t for k in KEYWORDS)


class _Item:
    """采集条目。"""
    def __init__(self, source: str, title: str, url: str, published=None, summary: str = ""):
        self.source = source
        self.title = title
        self.url = url
        self.published = published
        self.summary = summary

    def key(self) -> str:
        return f"{self.source}::{self.url or self.title}"

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "title": self.title,
            "url": self.url,
            "published": self.published,
            "summary": self.summary,
        }


class _SeenStore:
    """去重存储（seen.json）。"""
    def __init__(self, path: str = "seen.json"):
        self.path = path
        self.data = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def save(self) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def is_new(self, key: str) -> bool:
        return key not in self.data

    def mark(self, key: str, meta: dict | None = None) -> None:
        self.data[key] = {"seen_at": int(time.time()), "meta": meta or {}}


# ---------- 采集源 ----------

class _HuggingFaceSource:
    def __init__(self, org: str, label: str | None = None, limit: int = 12):
        self.org = org
        self.label = label or org
        self.limit = limit

    def fetch(self) -> list[_Item]:
        url = (
            f"https://huggingface.co/api/models?author={self.org}"
            f"&sort=createdAt&direction=-1&limit={self.limit}&full=false"
        )
        try:
            r = _SESSION.get(url, headers=HEADERS, timeout=TIMEOUT)
            r.raise_for_status()
            arr = r.json()
        except Exception as e:
            logging.getLogger("agent.radar").warning("[hf] %s 抓取失败: %s", self.label, e)
            return []
        items = []
        for m in arr:
            mid = m.get("id") or m.get("modelId")
            if not mid:
                continue
            items.append(_Item(
                self.label, mid,
                f"https://huggingface.co/{mid}",
                published=m.get("createdAt"),
                summary=m.get("pipeline_tag") or "",
            ))
        return items


class _RssSource:
    def __init__(self, url: str, label: str | None = None, limit: int = 15):
        self.url = url
        self.label = label or url
        self.limit = limit

    def fetch(self) -> list[_Item]:
        try:
            d = feedparser.parse(self.url)
        except Exception as e:
            logging.getLogger("agent.radar").warning("[rss] %s 解析失败: %s", self.label, e)
            return []
        items = []
        for e in (d.entries or [])[: self.limit]:
            title = e.get("title", "")
            blob = title + " " + (e.get("summary", "") or "")
            if not _hits_keywords(blob):
                continue
            link = e.get("link", "")
            pub = e.get("published") or e.get("updated")
            items.append(_Item(
                self.label, title, link,
                published=pub,
                summary=(e.get("summary", "") or "")[:200],
            ))
        return items


_SOURCES = [
    _HuggingFaceSource("deepseek-ai", "DeepSeek"),
    _HuggingFaceSource("moonshotai", "Kimi(月之暗面)"),
    _HuggingFaceSource("THUDM", "GLM(智谱)"),
    _HuggingFaceSource("Qwen", "Qwen(阿里)"),
    _HuggingFaceSource("meta-llama", "Llama(Meta)"),
    _HuggingFaceSource("mistralai", "Mistral"),
    _HuggingFaceSource("openai", "OpenAI"),
    _HuggingFaceSource("anthropic", "Claude(Anthropic)"),
    _HuggingFaceSource("google", "Gemini(Google)"),
    _RssSource("https://openai.com/news/rss.xml", "OpenAI Blog"),
    _RssSource("https://blog.google/technology/ai/rss/", "Google AI Blog"),
    _RssSource("https://www.anthropic.com/news/rss.xml", "Anthropic News"),
]


# ---------- 推送 ----------

def _send_feishu(webhook: str, text: str) -> bool:
    if not webhook:
        return False
    card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": "🚨 AI雷达 · 模型速报"},
                "template": "blue",
            },
            "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": text}}],
        },
    }
    try:
        r = requests.post(webhook, json=card, timeout=15)
        r.raise_for_status()
        return r.json().get("code", 1) == 0
    except Exception as e:
        logging.getLogger("agent.radar").warning("[feishu] 发送失败: %s", e)
        return False


def _send_pushplus(token: str, title: str, text: str) -> bool:
    if not token:
        return False
    try:
        r = requests.post(
            "https://www.pushplus.plus/send",
            json={"token": token, "title": title, "content": text, "template": "markdown"},
            timeout=15,
        )
        r.raise_for_status()
        return r.json().get("code") == 200
    except Exception as e:
        logging.getLogger("agent.radar").warning("[pushplus] 发送失败: %s", e)
        return False


# ---------- Agent ----------

class RadarAgent(AbstractAgent):
    name = "radar"

    def __init__(self) -> None:
        super().__init__()
        self.llm = get_provider()

    def _run(self, ctx: AgentContext) -> AgentContext:
        mode = ctx.get("mode", "preview")
        keyword = ctx.get("keyword", "")

        # 1) 采集
        all_items = []
        for s in _SOURCES:
            label = getattr(s, "label", str(s))
            try:
                all_items.extend(s.fetch())
            except Exception as e:
                self.log.warning("[collect] 源 %s 出错: %s", label, e)

        # 2) 关键词过滤（如果用户给了 keyword）
        if keyword:
            all_items = [i for i in all_items if keyword.lower() in (i.title + i.summary).lower()]

        # 3) 去重
        store_path = os.environ.get("RADAR_SEEN_PATH", "seen.json")
        first_run = not os.path.exists(store_path)
        store = _SeenStore(store_path)
        new = [i for i in all_items if store.is_new(i.key())]

        self.log.info("采集 %d 条，新条目 %d 条", len(all_items), len(new))

        # 首次运行：建基线不推送
        if first_run:
            for i in all_items:
                store.mark(i.key(), i.to_dict())
            store.save()
            return ctx.put("result", "首次运行：已建立基线（全部标记为已见），后续新动态才会推送。")
                   .put("count", 0)

        if not new:
            return ctx.put("result", "暂无新动态。").put("count", 0)

        # 标记已见
        for i in new:
            store.mark(i.key(), i.to_dict())
        store.save()

        # 4) 摘要
        digest = self._make_digest(new)
        self.log.info("速报生成完毕，长度 %d 字", len(digest))

        # 5) 推送（仅 mode=push）
        push_result = {}
        if mode == "push":
            feishu = os.environ.get("FEISHU_WEBHOOK")
            pushplus = os.environ.get("PUSHPLUS_TOKEN")
            if feishu and _send_feishu(feishu, digest):
                push_result["feishu"] = "ok"
            else:
                push_result["feishu"] = "skipped"
            if pushplus and _send_pushplus(pushplus, "🚨 AI雷达 · 模型速报", digest):
                push_result["pushplus"] = "ok"
            else:
                push_result["pushplus"] = "skipped"

        return (ctx
                .put("result", digest)
                .put("count", len(new))
                .put("push_result", push_result if push_result else None))

    def _make_digest(self, items: list[_Item]) -> str:
        """有 DeepSeek key 用 LLM 摘要，否则纯列表兜底。"""
        key = os.environ.get("DEEPSEEK_API_KEY")
        if key:
            llm_text = self._llm_digest(items)
            if llm_text:
                return llm_text
        return self._fallback_digest(items)

    def _llm_digest(self, items: list[_Item], max_items: int = 20) -> str | None:
        picked = items[:max_items]
        lines = [f"[{i.source}] {i.title} — {i.url}" for i in picked]
        prompt = (
            "你是 AI 资讯编辑。以下是近期大模型/产品的发布动态，请用简体中文写一段速报"
            "（不超过 280 字）：按厂商分组，点出最值得关注的 1-2 条，并附关键链接。"
            "用 Markdown 列表，链接写成 [标题](url) 形式。\n\n" + "\n".join(lines)
        )
        try:
            result = self.llm.chat(prompt)
            return result
        except Exception as e:
            self.log.warning("[digest] LLM 失败，回退纯文本: %s", e)
            return None

    @staticmethod
    def _fallback_digest(items: list[_Item]) -> str:
        by_src: dict[str, list[_Item]] = {}
        for i in items:
            by_src.setdefault(i.source, []).append(i)
        lines = ["# 🚨 AI雷达 · 模型速报"]
        for src, its in by_src.items():
            lines.append(f"\n## {src}")
            for i in its:
                line = f"- [{i.title}]({i.url})"
                if i.published:
                    line += f"  ({i.published})"
                lines.append(line)
        return "\n".join(lines)
