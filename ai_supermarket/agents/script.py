"""ai-script：脚本 Agent（必备，流量引擎第 2 环）。

职责：根据选题卡片生成口播脚本（钩子 + 反转 + 分镜表 + 字幕节奏）。
输入：topicTitle / hook / audience
输出：voiceover / shots / captionTiming
工具：LLM + 模板引擎（此处 demo 走 LLM，可换结构化 prompt 模板）
"""
from ..core.agent import AbstractAgent
from ..core.context import AgentContext
from ..core.llm import get_provider, extract_json
import json


class ScriptAgent(AbstractAgent):
    name = "script"

    def __init__(self) -> None:
        super().__init__()
        self.llm = get_provider()

    def _run(self, ctx: AgentContext) -> AgentContext:
        title = ctx.get("topicTitle", "")
        hook = ctx.get("hook", "")
        audience = ctx.get("audience", "")
        raw = self.llm.chat(
            "你是抖音口播脚本专家，基于选题生成脚本。返回 JSON"
            "{voiceover: 口播稿, shots: 分镜表, captionTiming: 字幕节奏}",
            f"选题：{title}；钩子：{hook}；人群：{audience}",
        )
        try:
            s = json.loads(extract_json(raw))
        except Exception:
            s = {
                "voiceover": f"{title}。第一个玩法，用AI写朋友圈文案……",
                "shots": "[0-3s]钩子特写;[3-8s]玩法1;[8-20s]玩法2+3;[20-30s]引导私域",
                "captionTiming": "每句≤12字，关键反转处加停顿",
            }
        return (ctx.put("voiceover", s.get("voiceover", ""))
                   .put("shots", s.get("shots", ""))
                   .put("captionTiming", s.get("captionTiming", "")))
