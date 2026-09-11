"""采集层：可插拔 Source。
- HuggingFaceSource：查某组织最新上传的模型（JSON API，最稳，覆盖 DeepSeek/Kimi/GLM/Qwen/Llama/Mistral/OpenAI/Claude/Google）
- RssSource：解析官方博客 RSS，按关键词过滤模型发布类条目
- HttpSource：兜底，直抓页面提取近期链接（易变，默认不启用）
"""
import requests
import feedparser
from urllib3.util.retry import Retry

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AIRadar/1.0)"}
TIMEOUT = 8

# 零重试会话：被墙/超时时快速失败，避免批量源卡死
_SESSION = requests.Session()
_SESSION.mount(
    "https://",
    requests.adapters.HTTPAdapter(max_retries=Retry(connect=0, read=0, redirect=0)),
)

# 命中这些关键词才视为「模型发布」相关（用于 RSS 过滤）
KEYWORDS = [
    "gpt", "claude", "gemini", "deepseek", "kimi", "glm", "qwen", "llama",
    "mistral", "grok", "o1", "o3", "o4", "4o", "发布", "推出", "上线",
    "开源", "release", "launch", "model", "模型",
]


def hits_keywords(text: str) -> bool:
    t = (text or "").lower()
    return any(k.lower() in t for k in KEYWORDS)


class Item:
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


class HuggingFaceSource:
    def __init__(self, org: str, label: str | None = None, limit: int = 12):
        self.org = org
        self.label = label or org
        self.limit = limit

    def fetch(self):
        url = (
            f"https://huggingface.co/api/models?author={self.org}"
            f"&sort=createdAt&direction=-1&limit={self.limit}&full=false"
        )
        try:
            r = _SESSION.get(url, headers=HEADERS, timeout=TIMEOUT)
            r.raise_for_status()
            arr = r.json()
        except Exception as e:
            print(f"[hf] {self.label} 抓取失败: {e}")
            return []
        items = []
        for m in arr:
            mid = m.get("id") or m.get("modelId")
            if not mid:
                continue
            items.append(
                Item(
                    self.label,
                    mid,
                    f"https://huggingface.co/{mid}",
                    published=m.get("createdAt"),
                    summary=m.get("pipeline_tag") or "",
                )
            )
        return items


class RssSource:
    def __init__(self, url: str, label: str | None = None, limit: int = 15):
        self.url = url
        self.label = label or url
        self.limit = limit

    def fetch(self):
        try:
            d = feedparser.parse(self.url)
        except Exception as e:
            print(f"[rss] {self.label} 解析失败: {e}")
            return []
        items = []
        for e in (d.entries or [])[: self.limit]:
            title = e.get("title", "")
            blob = title + " " + (e.get("summary", "") or "")
            if not hits_keywords(blob):
                continue
            link = e.get("link", "")
            pub = e.get("published") or e.get("updated")
            items.append(
                Item(self.label, title, link, published=pub, summary=(e.get("summary", "") or "")[:200])
            )
        return items


# 默认监控源：国际厂商 + 中国厂商，HuggingFace 为主、RSS 为补
SOURCES = [
    HuggingFaceSource("deepseek-ai", "DeepSeek"),
    HuggingFaceSource("moonshotai", "Kimi(月之暗面)"),
    HuggingFaceSource("THUDM", "GLM(智谱)"),
    HuggingFaceSource("Qwen", "Qwen(阿里)"),
    HuggingFaceSource("meta-llama", "Llama(Meta)"),
    HuggingFaceSource("mistralai", "Mistral"),
    HuggingFaceSource("openai", "OpenAI"),
    HuggingFaceSource("anthropic", "Claude(Anthropic)"),
    HuggingFaceSource("google", "Gemini(Google)"),
    RssSource("https://openai.com/news/rss.xml", "OpenAI Blog"),
    RssSource("https://blog.google/technology/ai/rss/", "Google AI Blog"),
    RssSource("https://www.anthropic.com/news/rss.xml", "Anthropic News"),
]
