"""ai-clarify：需求澄清官（动手前先把模糊需求问清楚，避免方向跑偏、胡说八道）。

职责：
- 第一轮：接收（可能很模糊的）需求 → 按维度盘点「已明确 / 缺失」→ 生成带选项的澄清问题。
- 第二轮：接收用户对第一轮问题的回答 → 重新评估清晰度 → 收敛出需求画像(profile) →
         标出仍模糊/不可行的点 → 推荐接下来该调哪个业务 Agent。

输入：
  request  原始需求（可很模糊）
  context  可选背景
  answers  可选，用户对其他 Agent 第一轮问题的回答（list 按序 / dict 按 dimension）
  questions 可选，第一轮产出的问题（第二轮时作为上下文回填）
输出（第一轮）：understood / clear / questions / risk_if_skip / next_step / count
输出（第二轮）：understood / clear / still_missing / profile / questions / recommended_agent / next_step / count / round
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

_SYSTEM_PROMPT_V2 = """你是「需求澄清官」，现在进入第二轮。用户已经回答了你上一轮提出的问题。

你的职责：
1. 用一句话复述现在你理解的目标（结合回答更新）。
2. 盘点 now 已明确的点（clear）和仍缺失/仍模糊的点（still_missing）。
   - 特别注意：如果用户回答本身仍然模糊（例如受众说「所有人」、目标明显不现实），要把它列进 still_missing 并继续追问聚焦。
   - 对明显不现实或风险高的目标（例如普通人「真实上太空」「3年赚一个亿」），要诚实指出可行性缺口，追问预算/资源/是否其实是做相关内容而非字面执行。
3. 收敛出需求画像 profile（JSON 对象），字段尽量填：
   { "goal": 目标, "audience": 受众, "channel": 渠道, "format": 交付形态,
     "scope": 范围(从0/优化老号等), "timeline": 时间线, "constraints": 约束,
     "feasibility": 可行性判断(可选) }
4. 如果仍有关键缺口，继续生成 1-3 个带选项的澄清问题（questions，可空数组）。
5. 基于画像推荐接下来该调哪个业务 Agent（recommended_agent），从以下选：
   topic(爆款选题) / script(口播脚本) / video(口播视频) / publish(抖音发布) /
   service(私域客服) / delivery(交付调度) / analytics(数据复盘) / radar(大模型情报) / clarify(仍需继续澄清)
   选依据：渠道是抖音+短视频+从0起号 → 通常先 topic；若目标仍不清晰 → clarify。
6. 给出下一步建议 next_step。

你必须只返回一个 JSON 对象，不要任何解释文字。结构：
{
  "understood": "更新后的复述",
  "clear": ["已明确1", "已明确2"],
  "still_missing": ["仍缺/仍模糊1"],
  "profile": {"goal": "...", "audience": "...", "channel": "...", "format": "...", "scope": "...", "timeline": "...", "constraints": "...", "feasibility": "..."},
  "questions": [{"dimension": "...", "question": "...", "why": "...", "options": ["A","B"]}],
  "recommended_agent": "topic",
  "next_step": "下一步建议"
}"""

# 离线兜底第一轮：按关键词命中，注入一个该类型最该问的问题；其余走通用基线
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

# 业务 Agent 清单（离线路由用）
_AGENT_DESC = {
    "topic": "爆款选题", "script": "口播脚本", "video": "口播视频",
    "publish": "抖音发布", "service": "私域客服", "delivery": "交付调度",
    "analytics": "数据复盘", "radar": "大模型情报", "clarify": "仍需继续澄清",
}


class ClarifyAgent(AbstractAgent):
    name = "clarify"

    def __init__(self) -> None:
        super().__init__()
        self.llm = get_provider()

    def _run(self, ctx: AgentContext) -> AgentContext:
        request = ctx.get("request", "")
        bg = ctx.get("context", "")
        answers = ctx.get("answers")

        # 第二轮：有答案就进入收敛 + 路由
        if answers:
            prev_q = ctx.get("questions") or []
            return self._run_round2(ctx, request, bg, prev_q, answers)

        # 第一轮：原始澄清
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

    # ---------- 第二轮：收敛 + 路由 ----------

    def _run_round2(self, ctx, request, bg, prev_questions, answers) -> AgentContext:
        # 把第一轮问题 + 用户答案整理成可读上下文
        ans_lines = []
        if isinstance(answers, dict):
            for dim, ans in answers.items():
                ans_lines.append(f"- [{dim}] {ans}")
        elif isinstance(answers, (list, tuple)):
            for i, ans in enumerate(answers, 1):
                dim = prev_questions[i - 1]["dimension"] if i - 1 < len(prev_questions) else f"问题{i}"
                qtxt = prev_questions[i - 1]["question"] if i - 1 < len(prev_questions) else ""
                ans_lines.append(f"- [{dim}] {ans}  （原问：{qtxt}）")
        else:
            ans_lines.append(f"- {answers}")

        prompt = f"【原始需求】\n{request}"
        if bg:
            prompt += f"\n\n【背景】\n{bg}"
        if prev_questions:
            prompt += "\n\n【你之前问过的问题】\n"
            for i, q in enumerate(prev_questions, 1):
                prompt += f"{i}. [{q.get('dimension','')}] {q.get('question','')}\n"
        prompt += "\n\n【用户的回答】\n" + "\n".join(ans_lines)

        try:
            raw = self.llm.chat(_SYSTEM_PROMPT_V2, prompt)
            data = json.loads(extract_json(raw))
        except Exception as e:
            self.log.warning("[clarify] 第二轮 LLM 解析失败，走启发式兜底: %s", e)
            data = self._heuristic_v2(request, bg, prev_questions, answers)

        questions = data.get("questions") or []
        return (ctx
                .put("round", 2)
                .put("understood", data.get("understood", request[:60]))
                .put("clear", data.get("clear", []))
                .put("still_missing", data.get("still_missing", []))
                .put("profile", data.get("profile", {}))
                .put("questions", questions)
                .put("recommended_agent", data.get("recommended_agent", "clarify"))
                .put("next_step", data.get("next_step", "回答上述问题后进入执行。"))
                .put("count", len(questions)))

    # ---------- 离线兜底 ----------

    def _heuristic(self, request: str, bg: str) -> dict:
        """第一轮离线兜底：保证一定产出澄清问题，不依赖任何大模型。"""
        req = request
        clear = []
        questions = []

        for pat, dim, q, opts in _TYPE_RULES:
            if re.search(pat, req, re.IGNORECASE):
                questions.append({"dimension": dim, "question": q, "why": "类型不同，产物形态与工作量差很多。", "options": opts})
                break

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

    def _heuristic_v2(self, request, bg, prev_questions, answers) -> dict:
        """第二轮离线兜底：基于答案做简单归类 + 路由，诚实标出不可行/仍模糊点。"""
        # 把答案拉平成一个字符串 + 按序维度列表
        if isinstance(answers, dict):
            pairs = [(d, str(a)) for d, a in answers.items()]
        elif isinstance(answers, (list, tuple)):
            pairs = []
            for i, a in enumerate(answers):
                dim = prev_questions[i]["dimension"] if i < len(prev_questions) else f"q{i+1}"
                pairs.append((dim, str(a)))
        else:
            pairs = [("回答", str(answers))]

        ans_text = " ".join(a for _, a in pairs)
        profile = {}
        clear = []
        still_missing = []

        for dim, a in pairs:
            al = a.strip()
            if dim == "目标" or "上太空" in al or "上天" in al:
                profile["goal"] = al
                # 字面「上太空」对普通人极不现实 → 标可行性缺口
                if re.search(r"上太空|上天|太空", al):
                    profile["feasibility"] = "高风险：普通人字面「上太空」需巨额预算与特殊渠道，3年内基本不可行；建议确认是做太空主题内容还是真要安排太空旅行"
                    still_missing.append("目标可行性：字面「上太空」对普通人几乎不可行，需确认是做航天/太空科普内容，还是真要安排太空旅行（涉及预算/渠道）")
            elif dim == "受众" or "人" in al:
                profile["audience"] = al
                if al in ("所有人", "全人类", "所有"):
                    still_missing.append("受众太宽：抖音算法无法打所有人不分，需聚焦到具体人群（年龄/兴趣/身份）")
            elif "抖音" in al or dim == "交付物" or dim == "范围":
                if "抖音" in al:
                    profile["channel"] = "抖音"
                    profile["format"] = "短视频"
                if "从0" in al or "起号" in al:
                    profile["scope"] = "从0起号"
                elif "优化" in al or "老号" in al:
                    profile["scope"] = "优化老号"
            elif dim == "约束" or "年" in al or "月" in al or "天" in al:
                profile["timeline"] = al

        # 默认渠道/形态兜底
        if "抖音" in request or "抖音" in ans_text:
            profile.setdefault("channel", "抖音")
            profile.setdefault("format", "短视频")
        profile.setdefault("goal", request[:40])

        # 仍缺则补一个问题（聚焦受众 or 可行性）
        questions = []
        if any("受众" in m for m in still_missing):
            questions.append({"dimension": "受众", "question": "「所有人」在抖音上其实无法精准触达，你最想先打哪类具体人群？",
                              "why": "不聚焦就投流浪费、内容也对不上人。",
                              "options": ["航天/科幻爱好者", "科技发烧友", "青少年/学生群体", "其他（请补充）"]})
        if any("可行性" in m for m in still_missing):
            questions.append({"dimension": "目标", "question": "「真实上太空」你是指做太空主题内容引流，还是真要安排人上天（涉及预算/资质）？",
                              "why": "两者资源与可行性天差地别，必须先定。",
                              "options": ["做太空/航天科普内容引流", "真要安排太空旅行(有预算渠道)", "其他（请补充）"]})

        # 路由：渠道抖音+短视频 → topic；若仍缺 → clarify
        recommended = "topic" if (profile.get("channel") == "抖音" and not still_missing) else "clarify"
        if profile.get("channel") == "抖音":
            recommended = "topic"

        return {
            "understood": f"用户想做：{profile.get('goal', request[:30])}（渠道：{profile.get('channel','未定')}）",
            "clear": clear,
            "still_missing": still_missing,
            "profile": profile,
            "questions": questions,
            "recommended_agent": recommended,
            "next_step": "回答上述聚焦问题后，即可进入「topic 爆款选题」Agent 定内容方向。",
        }
