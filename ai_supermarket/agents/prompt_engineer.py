"""ai-prompt：提示词工程师 Agent（通用 + ai-supermarket 专用）。

职责：
- 生成：把模糊目标/想法，写成结构化、可直接复制粘贴给大模型的高质量提示词
        （<角色>/<背景>/<任务>/<约束>/<输出格式>/<示例>）。
- 优化：接收已有提示词，指出核心问题并给出改进版。
- ai-supermarket 专用：当传入 target_spec（某 Agent 的 name/description/input_fields/system_prompt）时，
        产出的提示词会贴合该 Agent 的字段与口吻（如给"选题"Agent 出抖音选题提示词）。

纯文本 Agent，复用 core.llm 真实大模型（Deepseek）；离线时走结构化模板兜底，仍返回可用结果。
设计原则：core 包不反向依赖 web 的 agents_registry，target_spec 由调用方（web handler）注入。
"""
from ..core.agent import AbstractAgent
from ..core.context import AgentContext
from ..core.llm import get_provider

# 提示词工程师自身的人设系统提示词
META_SYSTEM = """你是一位世界级的提示词（Prompt）工程师，精通把模糊需求转化为结构清晰、约束明确、可直接复制粘贴给大模型的高质量提示词。
你的产出永远是一份"给他人/模型用的提示词"，而不是直接替用户回答业务问题。
请遵循：
1. 用 <角色> 锚定身份与专业背景；
2. 用 <背景/上下文> 给模型必要信息；
3. 用 <任务> 明确要做什么；
4. 用 <约束> 列出格式、语气、长度、禁忌；
5. 用 <输出格式> 规定返回结构（如 JSON / 分点 / 表格）；
6. 必要时给 <示例> 让模型对齐期望。
语言精炼、可执行，避免空话。若用户提供"目标 Agent 规格"，务必让提示词契合该 Agent 的字段与口吻。"""


class PromptEngineerAgent(AbstractAgent):
    name = "prompt"

    def __init__(self) -> None:
        super().__init__()
        self.llm = get_provider()

    # ---------- 离线兜底：结构化模板 ----------
    def _heuristic(self, goal, target_spec, mode, existing_prompt, audience, constraints, output_format) -> str:
        if mode == "optimize" and existing_prompt:
            return (
                "# 提示词优化（离线模板）\n\n"
                "## 原提示词\n" + existing_prompt + "\n\n"
                "## 主要问题（自查清单）\n"
                "- 角色是否明确？未明确则补 <角色>。\n"
                "- 任务是否可被模型无歧义执行？拆成步骤。\n"
                "- 是否有 <输出格式>？没有则模型会自由发挥。\n"
                "- 是否有约束（语气/长度/禁忌）？\n\n"
                "## 改进版\n请基于以上要点重写，并套用结构：角色 / 背景 / 任务 / 约束 / 输出格式 / 示例。\n"
            )
        target_line = ""
        if target_spec:
            tname = target_spec.get("name", "")
            tdesc = target_spec.get("description", "")
            fields = "、".join([f"{f.get('label')}({f.get('key')})" for f in target_spec.get("input_schema", [])]) or "（无）"
            target_line = (
                f"\n- 目标 Agent：{tname}（{tdesc}）\n"
                f"- 该 Agent 需要的输入字段：{fields}\n"
                f"- 请让提示词产出的内容，正好能填进这些字段、符合该 Agent 定位。"
            )
        aud = f"\n- 目标受众：{audience}" if audience else ""
        cons = f"\n- 约束：{constraints}" if constraints else ""
        ofmt = f"\n- 期望输出格式：{output_format}" if output_format else ""
        return (
            "# 提示词（离线模板）\n\n请按以下结构补全并润色：\n\n"
            "<角色>：（你想让模型扮演的专家）\n"
            "<背景/上下文>：（相关背景）\n"
            f"<任务>：{goal or '（请描述你的目标）'}\n"
            "<约束>：（语气/长度/禁忌）\n"
            "<输出格式>：（如 JSON / 分点 / 表格）\n"
            "<示例>：（可选，给 1 个样例）\n"
            + target_line + aud + cons + ofmt +
            "\n\n> 提示：配置 DEEPSEEK_API_KEY 联网后，将由大模型为你生成更贴合的成品提示词。"
        )

    def _run(self, ctx: AgentContext) -> AgentContext:
        mode = (ctx.get("mode") or "generate").strip().lower()
        goal = (ctx.get("goal") or "").strip()
        existing_prompt = (ctx.get("existing_prompt") or "").strip()
        target_spec = ctx.get("target_spec") or None
        audience = (ctx.get("audience") or "").strip()
        constraints = (ctx.get("constraints") or "").strip()
        output_format = (ctx.get("output_format") or "").strip()

        if mode == "optimize" and not existing_prompt:
            return ctx.put("status", "empty").put("result", "（优化模式需要传入 existing_prompt）")
        if mode != "optimize" and not goal:
            return ctx.put("status", "empty").put("result", "（生成模式需要传入 goal）")

        # 组装"目标 Agent 规格"文本（让产出贴合该 Agent 的字段与口吻）
        target_block = ""
        if target_spec:
            tname = target_spec.get("name", "")
            tdesc = target_spec.get("description", "")
            fields = "、".join([f"{f.get('label')}({f.get('key')})" for f in target_spec.get("input_schema", [])]) or "（无）"
            tsp = target_spec.get("system_prompt", "")
            target_block = (
                f"\n\n[目标 Agent 规格]\n名称：{tname}\n定位：{tdesc}\n"
                f"该 Agent 需要的输入字段：{fields}\n"
                f"该 Agent 自身系统提示词（请让产出的提示词契合其口吻与产出结构）：\n{tsp}\n"
                "要求：产出的提示词，应让使用者能直接产出正好填进上述字段、符合该 Agent 定位的内容。"
            )

        if mode == "optimize":
            user = (
                "【任务】优化下面这份提示词，使其更清晰、约束更明确、产出更可控。\n"
                f"【原提示词】\n{existing_prompt}\n"
                "【优化要点】先指出 2-4 个核心问题，再给出一版改进后、可直接使用的完整提示词。"
                f"{target_block}"
                f"{('【目标受众】' + audience) if audience else ''}"
                f"{('【约束】' + constraints) if constraints else ''}"
                f"{('【期望输出格式】' + output_format) if output_format else ''}"
            )
        else:
            user = (
                "【任务】为以下目标写一份高质量、可直接复制粘贴给大模型使用的提示词。\n"
                f"【目标/想法】{goal}\n"
                "【请产出】<角色>/<背景>/<任务>/<约束>/<输出格式>/<示例(可选)> 结构化的提示词。"
                f"{target_block}"
                f"{('【目标受众】' + audience) if audience else ''}"
                f"{('【约束】' + constraints) if constraints else ''}"
                f"{('【期望输出格式】' + output_format) if output_format else ''}"
            )

        try:
            result = self.llm.chat(META_SYSTEM, user)
            if not result or len(result.strip()) < 10:
                raise ValueError("空回复")
        except Exception:
            result = self._heuristic(goal, target_spec, mode, existing_prompt, audience, constraints, output_format)

        return ctx.put("result", result).put("mode", mode).put("status", "done")
