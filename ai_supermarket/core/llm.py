"""LLM 客户端抽象：默认 MockProvider（离线可跑），设了 API Key 自动切真实大模型。

现已默认支持 Deepseek：
  DEEPSEEK_API_KEY   有则启用 Deepseek 真实 chat（https://api.deepseek.com/v1，deepseek-chat）
  DEEPSEEK_MODEL     默认 deepseek-chat
  DEEPSEEK_BASE_URL  默认 https://api.deepseek.com/v1

也兼容任意 OpenAI 兼容端点（仅当其存在时）：
  AI_SUPERMARKET_API_KEY / AI_SUPERMARKET_BASE_URL / AI_SUPERMARKET_MODEL

关于 embedding：
  Deepseek 不提供 embedding 接口，因此 embed() 默认走「本地字符 bigram 哈希向量」
  （离线、零依赖，可做近似去重）。如需真实语义向量，配置：
  AI_SUPERMARKET_EMBED_BASE_URL / AI_SUPERMARKET_EMBED_KEY / AI_SUPERMARKET_EMBED_MODEL
"""
import os
import re
import math
import json
import hashlib
import urllib.request


def cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        n = min(len(a), len(b))
        a, b = a[:n], b[:n]
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


class LLMProvider:
    def chat(self, system: str, user: str) -> str:
        raise NotImplementedError

    def embed(self, text: str) -> list[float]:
        raise NotImplementedError


class LocalEmbedder:
    """本地字符 bigram 哈希向量（256 维），离线、零依赖。

    对中文近义标题有较好的「字面近重复」检测能力（同主题 → 重叠 bigram 多 → 余弦高）。
    若要真正的语义去重，请配置 AI_SUPERMARKET_EMBED_* 接入 embedding 服务。
    """

    DIM = 256

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.DIM
        s = re.sub(r"\s+", "", text or "")
        if not s:
            return vec
        grams = list(s)
        if len(s) >= 2:
            grams += [s[i:i + 2] for i in range(len(s) - 1)]
        for g in grams:
            h = int(hashlib.md5(g.encode("utf-8")).hexdigest(), 16)
            vec[h % self.DIM] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class MockProvider(LLMProvider):
    """离线演示用：根据 system 关键词返回结构化占位结果，embedding 用本地哈希向量。"""

    def __init__(self) -> None:
        self.embedder = LocalEmbedder()

    def chat(self, system: str, user: str) -> str:
        if "选题卡片" in system or "topic card" in system.lower():
            return json.dumps({
                "topicTitle": "普通人用AI赚到第一桶金的3个低门槛玩法",
                "hook": "你以为AI离你很远？其实楼下早餐店都在用",
                "audience": "想副业变现的小微店主/个体户",
                "linkService": "ai-delivery",
            }, ensure_ascii=False)
        if "脚本" in system or "script" in system.lower():
            return ("（口播稿）开头用强钩子制造反差，中间给3个可落手玩法，"
                    "结尾引导私域领模板。分镜：0-3s钩子特写；3-20s玩法展开；20-30s引导。")
        if "评估" in system or "打分" in system:
            return "82"
        return "ok"

    def embed(self, text: str) -> list[float]:
        return self.embedder.embed(text)


class OpenAIEmbedder:
    def __init__(self, base: str, key: str, model: str) -> None:
        self.base, self.key, self.model = base, key, model

    def embed(self, text: str) -> list[float]:
        data = json.dumps({"model": self.model, "input": text}).encode("utf-8")
        req = urllib.request.Request(
            self.base + "/embeddings", data=data,
            headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))["data"][0]["embedding"]


class ChatProvider(LLMProvider):
    """统一 chat 走真实大模型（Deepseek 或 OpenAI 兼容），embed 走可配置 embedder。"""

    def __init__(self, base: str, key: str, model: str, embedder: LLMProvider) -> None:
        self.base, self.key, self.model = base, key, model
        self.embedder = embedder

    def _post(self, path: str, body: dict) -> dict:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            self.base + path, data=data,
            headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def chat(self, system: str, user: str) -> str:
        r = self._post("/chat/completions", {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0.7,
        })
        return r["choices"][0]["message"]["content"]

    def embed(self, text: str) -> list[float]:
        return self.embedder.embed(text)


def _make_embedder() -> LLMProvider:
    eb = os.environ.get("AI_SUPERMARKET_EMBED_BASE_URL")
    ek = os.environ.get("AI_SUPERMARKET_EMBED_KEY")
    em = os.environ.get("AI_SUPERMARKET_EMBED_MODEL", "text-embedding-3-small")
    if eb and ek:
        return OpenAIEmbedder(eb, ek, em)
    return LocalEmbedder()


def get_provider() -> LLMProvider:
    # 优先 Deepseek
    dk = os.environ.get("DEEPSEEK_API_KEY")
    if dk:
        base = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
        print(f"[llm] 使用 Deepseek 真实接口 (model={model})")
        return ChatProvider(base, dk, model, _make_embedder())
    # 兼容任意 OpenAI 兼容端点
    ak = os.environ.get("AI_SUPERMARKET_API_KEY")
    if ak:
        base = os.environ.get("AI_SUPERMARKET_BASE_URL", "https://api.openai.com/v1")
        model = os.environ.get("AI_SUPERMARKET_MODEL", "gpt-4o-mini")
        print(f"[llm] 使用 OpenAI 兼容接口 (model={model})")
        return ChatProvider(base, ak, model, _make_embedder())
    # 离线
    print("[llm] 未检测到 DEEPSEEK_API_KEY / AI_SUPERMARKET_API_KEY，使用 MockProvider（离线演示）")
    return MockProvider()


def extract_json(text: str) -> str:
    """从模型可能包裹的自然语言里抠出第一段 JSON。"""
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]
    return text
