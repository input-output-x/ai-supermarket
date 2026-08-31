"""ai-topic：选题 Agent（必备，流量引擎第 1 环）—— 真实选题逻辑。

职责：从热点源拉候选 -> LLM 评估价值 -> 向量去重 -> 产出选题卡片。
输入：keyword
输出：topicTitle / hook / audience / linkService / heatScore
工具：LLM（chat+embed） + 热点源（本地JSON，可换 WebHotSource） + 向量去重库
"""
import os
import re
import json

from ..core.agent import AbstractAgent
from ..core.context import AgentContext
from ..core.llm import get_provider, cosine, extract_json


def _assets_dir() -> str:
    # ai_supermarket/agents/topic.py -> ai_supermarket/assets
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")


class HotSource:
    """热点源抽象。默认本地种子，可替换为 WebHotSource（接热点榜 API）。"""

    def fetch(self) -> list[dict]:
        raise NotImplementedError


class LocalHotSource(HotSource):
    def __init__(self, path: str) -> None:
        self.path = path

    def fetch(self) -> list[dict]:
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)


class DedupStore:
    """向量去重库：用 embedding 余弦相似度判断选题是否重复。"""

    def __init__(self, path: str, threshold: float = 0.85) -> None:
        self.path = path
        self.threshold = threshold
        self.items: list[dict] = []
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        self.items.append(json.loads(line))

    def is_duplicate(self, vec: list[float]):
        for it in self.items:
            if cosine(vec, it["vec"]) >= self.threshold:
                return True, it["title"]
        return False, None

    def add(self, title: str, vec: list[float]) -> None:
        self.items.append({"title": title, "vec": vec})
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"title": title, "vec": vec}, ensure_ascii=False) + "\n")


class TopicAgent(AbstractAgent):
    name = "topic"

    def __init__(self) -> None:
        super().__init__()
        self.llm = get_provider()
        assets = _assets_dir()
        self.hot = LocalHotSource(os.path.join(assets, "hot_topics.json"))
        self.dedup = DedupStore(os.path.join(assets, "topic_history.jsonl"))

    def _run(self, ctx: AgentContext) -> AgentContext:
        keyword = ctx.get("keyword", "AI")
        candidates = self.hot.fetch()

        best, best_score, best_vec = None, -1.0, None
        for c in candidates:
            title = c.get("title", "")
            vec = self.llm.embed(title)
            dup, old = self.dedup.is_duplicate(vec)
            if dup:
                self.log.info("去重命中，跳过: %s ~ %s", title, old)
                continue
            # LLM 评估选题价值（0-100）
            raw = self.llm.chat(
                "你是短视频选题评估专家，只返回一个 0-100 的数字表示爆款潜力。",
                f"选题：{title}；热度：{c.get('heat')}；关联关键词：{keyword}",
            )
            try:
                llm_score = float(re.findall(r"\d+\.?\d*", raw)[0])
            except Exception:
                llm_score = 50.0
            # 综合：模型评分 60% + 热度 40%
            score = llm_score * 0.6 + float(c.get("heat", 50)) * 0.4
            self.log.info("候选评分 %.1f <- %s", score, title)
            if score > best_score:
                best_score, best, best_vec = score, c, vec

        if best is None:
            return ctx.put("topicTitle", f"{keyword} 今日选题（热点池已去重耗尽）")

        # LLM 生成选题卡片
        card_raw = self.llm.chat(
            "你是抖音口播选题专家，基于候选生成选题卡片，只返回 JSON"
            "{topicTitle, hook, audience, linkService}",
            f"候选：{best['title']}；关键词：{keyword}",
        )
        try:
            card = json.loads(extract_json(card_raw))
        except Exception:
            card = {"topicTitle": best["title"], "hook": "", "audience": "", "linkService": "ai-delivery"}

        self.dedup.add(best["title"], best_vec)
        return (ctx.put("topicTitle", card.get("topicTitle", best["title"]))
                   .put("hook", card.get("hook", ""))
                   .put("audience", card.get("audience", ""))
                   .put("linkService", card.get("linkService", "ai-delivery"))
                   .put("heatScore", round(best_score, 1)))
