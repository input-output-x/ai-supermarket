"""ai-clarify：需求澄清官（动手前先把模糊需求问清楚，避免方向跑偏、胡说八道）。

职责：接收一段（可能很模糊的）用户需求 → 按维度盘点「已明确 / 缺失」→
      找出最关键的缺口，生成带建议选项的澄清问题 → 说明不澄清就开干的风险 →
      给出下一步建议（先把问题答了，再进执行）。

输入：request（原始需求，可很模糊）、context（可选背景）
输出：understood / clear / questions / risk_if_skip / next_step / count
工具：LLM（Deepseek，返回结构化 JSON）+ 离线启发式兜底
"""
import json
import re
import os

from core.agent import AbstractAgent
from core.context import AgentContext
from core.llm import get_provider, extract_json

_SYSTEM_PROMPT = """你是「需求澄清官」——在动手做任何事之前，先帮用户把模糊的需求说清楚，避免方向跑偏、胡说八道。

用户会给你一段（可能很模糊的）需求描述。你的职责：
1. 用一句话复述你理解的目标。
2. 按维度盘点已明确 vs 缺失的信息：目标、受众、范围、约束、交付物、风格、时间/预算、技术栈。
3. 找出最关键的 3-5 个缺口，生成澄清问题。每个问题包含：
   - dimension：所属维度（目标/受众/范围/约束/交付物/风格/时间/技术）
   - question：要问的问题（具体、可答）
   - why：为什么必须问（不答会怎样跑偏）
   - options：2-4 个可选答案，帮助用户快速选；拿不准就给「其他（请补充）」
4. 说明如果不在这些点上澄清就开干，会有什么风险。
5. 给出下一步建议（通常是：先回答 N 个问题，再进入执行）。

你必须只返回一个 JSON 对象，不要任何解释文字。结构如下：
{
  "understood": "一句话复述你理解的目标",
  "clear": ["已明确的点1", "已明确的点2"],
  "questions": [
    {"dimension": "目标", "question": "...", "why": "...", "options": ["A", "B", "C"]}
  ],
  "risk_if_skip": "不澄清就开干的风险",
  "next_step": "下一步建议"
}"""

# 离线兜底：按关键词命中，注入一个该类型最该问的问题；其余走通用基线
_TYPE_RULES = [
    ("视频|抖音|剪辑|口播|短片|vlog", "风格", "希望是什么观感？",
     ["强钩子种草向", "专业讲解向", "轻松娱乐向", "其他（请补充）"]),
    ("网站|网页|官网|落地页|app|小程序|前端", "技术", "用什么形态交付？",
     ["静态网页(HTML)", "Vue/React 单页", "小程序", "先不定，听建议"]),
    ("文案|文章|稿|脚本|推文|小红书", "交付物", "成稿用在哪、多长？",
     ["短视频口播稿 30-50s", "公众号长文 1500字", "小红书图文文案", "其他（请补充）"]),
    ("设计|logo|封面|海报|图|视觉", "风格", "视觉风格与用途？",
     ["科技感深色", "清爽明亮", "国潮/中式", "其他（请补充）"]),
    ("agent|智能体|自动化|工作流|机器人", "范围", "这个 Agent 解决哪一步？",
     ["单一任务全自动", "半自动+人工确认", "先做原型验证", "其他（请补充）"]),
]


class ClarifyAgent(AbstractAgent):
    name = "clarify"

    def __init__(self) -> None:
        super().__init__()
        self.llm = get_provider()

    def _run(self, ctx: AgentContext) -> AgentContext:
        request = ctx.get("request", "")
        bg = ctx.get("context", "")
        if not request.strip():
            return (ctx
                    .put("understood", "（用户未提供任何需求）")
                    .put("clear", [])
                    .put("questions", [{
                        "dimension": "目标",
                        "question": "你想做成什么事？用一句话说说。",
                        "why": "没有目标就无法判断方向，容易胡说八道。",
                        "options": ["做个产品/工具", "做内容/素材", "梳理方案/策略", "其他（请补充）"],
                    }])
                    .put("risk_if_skip", "无需求即动手 = 必然跑偏，浪费时间。")
                    .put("next_step", "先告诉我你想做成什么，我再拆澄清问题。")
                    .put("count", 1))

        prompt = f"【用户需求】\n{request}"
        if bg:
            prompt += f"\n\n【背景补充】\n{bg}"

        try:
            raw = self.llm.chat(_SYSTEM_PROMPT, prompt)
            data = json.loads(extract_json(raw))
        except Exception as e:
            self.log.warning("[clarify] LLM 解析失败，走启发式兜底: %s", e)
            data = self._heuristic(request, bg)

        questions = data.get("questions") or []
        return (ctx
                .put("understood", data.get("understood", request[:60]))
                .put("clear", data.get("clear", []))
                .put("questions", questions)
                .put("risk_if_skip", data.get("risk_if_skip", ""))
                .put("next_step", data.get("next_step", "回答上述问题后，再进入执行。"))
                .put("count", len(questions)))

    def _heuristic(self, request: str, bg: str) -> dict:
        """离线兜底：保证一定产出澄清问题，不依赖任何大模型。"""
        req = request
        clear = []
        questions = []

        # 类型特有问题
        for pat, dim, q, opts in _TYPE_RULES:
            if re.search(pat, req, re.IGNORECASE):
                questions.append({"dimension": dim, "question": q, "why": "类型不同，产物形态与工作量差很多。", "options": opts})
                break

        # 通用基线（永远该问）
        questions.append({"dimension": "目标", "question": "这件事做成后，最想看到的结果是什么？",
                          "why": "目标不清，所有后续选择都会摇摆。",
                          "options": ["涨粉/引流", "直接变现", "品牌/口碑", "提效/省事"]})
        questions.append({"dimension": "受众", "question": "主要给谁看/谁用？",
                          "why": "受众决定语气、渠道与交付形态。",
                          "options": ["C端普通用户", "B端客户/老板", "同行/开发者", "我自己用"]})
        questions.append({"dimension": "范围", "question": "第一步先做多小？",
                          "why": "范围失控容易做一半烂尾。",
                          "options": ["最小可跑原型", "完整一版", "先给方案再定", "听你建议"]})
        questions.append({"dimension": "时间", "question": "什么时候要？",
                          "why": "排期决定取舍与精度。",
                          "options": ["今天就要", "本周", "不急，求稳", "其他（请补充）"]})

        # 去重（同一 dimension 只留第一条）
        seen = set()
        deduped = []
        for q in questions:
            if q["dimension"] in seen:
                continue
            seen.add(q["dimension"])
            deduped.append(q)

        return {
            "understood": req[:80],
            "clear": clear,
            "questions": deduped[:5],
            "risk_if_skip": "方向、受众、范围都没定就动手，极易做出不对的东西，白干。",
            "next_step": "先回答上述关键问题，我再帮你把需求锁死、进入执行。",
        }
