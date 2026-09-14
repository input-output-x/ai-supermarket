"""ai-topic：抖音选题 Agent（流量引擎第 1 环）。

职责：给定一个主题 / 具体选题 + 内容场景，产出可直接拍摄的「选题包」：
  主标题 / 3 个备选标题 / 封面大字号文案 / 黄金 3 秒钩子 / 内容角度 /
  分镜大纲 / 发布建议 / 目标人群 / 爆款潜力分。

输入：
  topic     主题或具体选题（必填；也可用 keyword 兼容旧调用）
  scenario  内容场景，默认「抖音 AI 教程」
  audience  目标人群（可选）
输出：topicTitle / altTitles / cover / hook / angle / outline / postTips / audience / heatScore
工具：LLM（Deepseek，返回结构化 JSON）+ 离线启发式兜底（无 key 也能出结构）
"""
import json
import os

from core.agent import AbstractAgent
from core.context import AgentContext
from core.llm import get_provider, extract_json

_SYSTEM_PROMPT = """你是抖音爆款选题专家，尤其擅长「AI 教程 / AI 工具测评」类内容。
用户会给你一个主题或具体选题。请产出可直接拍摄的选题包，只返回一个 JSON 对象，不要任何解释文字。
结构：
{
  "topicTitle": "主标题（≤14字，有钩子/冲突/数字，像抖音信息流里会点的样子）",
  "altTitles": ["备选标题1", "备选标题2", "备选标题3"],
  "cover": "封面大字号文案（≤8字，冲击力强，可带情绪词）",
  "hook": "黄金3秒口播钩子（1句，制造反差/悬念/利益点）",
  "angle": "内容角度（1句，说明这条视频的独特切入点）",
  "outline": ["分镜1", "分镜2", "分镜3", "分镜4"],
  "postTips": "发布建议（最佳时长/发布时间/引导互动话术，1句）",
  "audience": "目标人群（1句）",
  "heatScore": 85
}
要求：
- 标题不能像广告，避免「一站式/代运营/解决方案/赋能」这类 B 端词；
- 多用具体数字、对比、反常识；封面文案要让人一眼想点；
- heatScore 是你对爆款潜力的判断（0-100 整数）。"""

# 不同场景的选题倾向提示（离线兜底用）
_SCENARIO_HINTS = {
    "AI教程": "工具实测对比、避坑反割韭菜、手把手实操、热点跟进",
    "AI工具测评": "同类型工具横评、结果差多少倍、谁更值",
    "避坑": "别再被XX割韭菜、这N个坑我替你踩了",
}


class TopicAgent(AbstractAgent):
    name = "topic"

    def __init__(self) -> None:
        super().__init__()
        self.llm = get_provider()

    def _run(self, ctx: AgentContext) -> AgentContext:
        topic = (ctx.get("topic") or ctx.get("keyword") or "").strip()
        if not topic:
            return (ctx.put("topicTitle", "（未提供主题）")
                       .put("error", "请传入 topic 或 keyword")
                       .put("heatScore", 0))
        scenario = ctx.get("scenario") or "抖音 AI 教程"
        audience = ctx.get("audience") or ""

        prompt = f"【主题/选题】{topic}\n【内容场景】{scenario}"
        if audience:
            prompt += f"\n【目标人群】{audience}"

        try:
            raw = self.llm.chat(_SYSTEM_PROMPT, prompt)
            data = json.loads(extract_json(raw))
        except Exception as e:
            self.log.warning("[topic] LLM 解析失败，走启发式兜底: %s", e)
            data = self._heuristic(topic, scenario)

        # 字段兜底，保证下游 script Agent 永远拿得到值
        data.setdefault("topicTitle", topic[:14])
        data.setdefault("altTitles", [topic])
        data.setdefault("cover", topic[:8])
        data.setdefault("hook", f"关于{topic}，90%的人都搞错了")
        data.setdefault("angle", "用真实对比说话，不空谈")
        data.setdefault("outline", ["钩子", "演示", "对比", "引导"])
        data.setdefault("postTips", "晚8点发，开头问一个问题引导评论")
        data.setdefault("audience", "想学AI的普通人/职场人")
        data.setdefault("heatScore", 70)

        return (ctx.put("topicTitle", data["topicTitle"])
                   .put("altTitles", data["altTitles"])
                   .put("cover", data["cover"])
                   .put("hook", data["hook"])
                   .put("angle", data["angle"])
                   .put("outline", data["outline"])
                   .put("postTips", data["postTips"])
                   .put("audience", data["audience"])
                   .put("heatScore", data["heatScore"]))

    def _heuristic(self, topic: str, scenario: str) -> dict:
        """离线兜底：基于主题拼一个像样的选题包，保证无 key 也能跑。"""
        t = topic[:14]
        hint = _SCENARIO_HINTS.get(scenario, "用真实案例和对比说话")
        return {
            "topicTitle": t,
            "altTitles": [f"{t}（实测版）", f"别再乱用{t}了", f"{t}到底差多大？"],
            "cover": t[:8],
            "hook": f"同一个需求，我用{t}测了 4 个模型，结果差太大",
            "angle": f"用同一提示词横评主流大模型，拿真实输出对比；{hint}",
            "outline": [
                "抛钩子：同一句话丢给 4 个模型",
                "逐个展示真实输出",
                "点出差异与各自适用场景",
                "引导关注，看后续持续测评",
            ],
            "postTips": "晚 8 点发，评论区留「想要提示词」引导私域",
            "audience": "想用 AI 提效但不懂选模型的普通人",
            "heatScore": 78,
        }
