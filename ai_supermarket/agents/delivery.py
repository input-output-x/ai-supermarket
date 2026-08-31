"""ai-delivery：交付调度 Agent（交付层关键）—— 真实逻辑已落地。

职责：把一条订单/需求（数字人视频 / AI 获客代运营 / 写真 / Agent 搭建 …）拆解成
可执行的「交付 SOP」：交付物清单、执行步骤、各环节角色、建议工期、验收标准。

输入：order（订单/需求描述）
输出：deliverables / steps(含角色与工期) / acceptance / status

真实能力接入点：
  - 工单系统：把 SOP 推到飞书/企微/工单 API 替换 _push_sop
  - 角色→人：owner 映射到真实团队/外部供应商
  demo 阶段用 LLM 直接产出 SOP，离线时走关键词模板兜底。
"""
import re
import json

from ..core.agent import AbstractAgent
from ..core.context import AgentContext
from ..core.llm import get_provider, extract_json

# 需求类型 → 模板 SOP（离线兜底用）
TEMPLATES = {
    "数字人": {
        "deliverables": ["口播脚本 ×N", "数字人成片 ×N（9:16）", "字幕/封面", "发布包"],
        "steps": [
            {"step": "需求确认 & 人设定稿", "owner": "策划", "days": 1},
            {"step": "脚本撰写 & 分镜", "owner": "文案", "days": 2},
            {"step": "数字人生成 & 配音", "owner": "视频", "days": 2},
            {"step": "剪辑 & 字幕 & 封面", "owner": "视频", "days": 1},
            {"step": "客户验收 & 发布", "owner": "运营", "days": 1},
        ],
        "acceptance": ["口播同步唇形自然", "9:16 竖版无拉伸", "字幕无误", "客户签字验收"],
    },
    "代运营": {
        "deliverables": ["月度内容日历", "选题库", "成片 ×月产量", "数据周报", "线索承接 SOP"],
        "steps": [
            {"step": "账号诊断 & 定位", "owner": "运营", "days": 2},
            {"step": "选题规划 & 脚本", "owner": "文案", "days": 3},
            {"step": "拍摄/生成 & 剪辑", "owner": "视频", "days": 5},
            {"step": "发布 & 互动承接", "owner": "客服", "days": 1},
            {"step": "周度复盘 & 优化", "owner": "运营", "days": 1},
        ],
        "acceptance": ["按日历准时交付", "播放/线索达标线", "客户周报齐全"],
    },
    "写真": {
        "deliverables": ["精修写真 ×张数", "风格分镜", "可商用授权说明"],
        "steps": [
            {"step": "风格确认 & 参考", "owner": "策划", "days": 1},
            {"step": "生成 & 初修", "owner": "设计", "days": 2},
            {"step": "精修 & 交付", "owner": "设计", "days": 2},
        ],
        "acceptance": ["风格一致", "无瑕疵/无水印", "交付格式 OK"],
    },
    "Agent": {
        "deliverables": ["需求文档 PRD", "Agent 原型", "对接说明", "使用手册"],
        "steps": [
            {"step": "需求梳理 & PRD", "owner": "产品", "days": 2},
            {"step": "Agent 搭建 & 联调", "owner": "研发", "days": 5},
            {"step": "验收 & 培训", "owner": "产品", "days": 2},
        ],
        "acceptance": ["核心链路跑通", "文档齐全", "客户可独立使用"],
    },
}


class DeliveryAgent(AbstractAgent):
    name = "delivery"

    def __init__(self) -> None:
        super().__init__()
        self.llm = get_provider()

    def _detect_type(self, text: str) -> str:
        for k in ("数字人", "代运营", "写真", "Agent", "搭建", "小程序", "系统"):
            if k in text:
                if k in ("搭建", "系统", "小程序"):
                    return "Agent"
                return k
        return "代运营"

    def _heuristic(self, order: str) -> dict:
        t = self._detect_type(order)
        tpl = TEMPLATES.get(t, TEMPLATES["代运营"])
        total = sum(s["days"] for s in tpl["steps"])
        return {
            "type": t,
            "deliverables": tpl["deliverables"],
            "steps": tpl["steps"],
            "acceptance": tpl["acceptance"],
            "total_days": total,
        }

    def _run(self, ctx: AgentContext) -> AgentContext:
        order = (ctx.get("order") or "").strip()
        if not order:
            return ctx.put("status", "empty").put("result", "（空订单）")

        try:
            raw = self.llm.chat(
                "你是 AI 获客代运营的交付调度专家。根据用户的订单/需求，输出一份可执行交付 SOP。"
                "只返回 JSON：{type, deliverables:[], steps:[{step,owner,days}], acceptance:[], total_days}",
                f"订单/需求：{order}",
            )
            data = json.loads(extract_json(raw))
            if not data.get("steps"):
                raise ValueError("空 steps")
        except Exception:
            data = self._heuristic(order)

        return (ctx.put("type", data.get("type"))
                   .put("deliverables", data.get("deliverables", []))
                   .put("steps", data.get("steps", []))
                   .put("acceptance", data.get("acceptance", []))
                   .put("total_days", data.get("total_days"))
                   .put("result", data)
                   .put("status", "done"))
