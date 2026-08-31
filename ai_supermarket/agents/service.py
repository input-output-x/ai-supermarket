"""ai-service：客服 Agent（承接层关键）—— 真实逻辑已落地。

职责：承接评论/私信/咨询消息 → LLM 意图分类 + 线索抽取 + 生成回复话术 + 路由。
输入：message / source(可选)
输出：intent / need / contact / reply / route / lead / status

意图路由：
  购买 -> sales      （导流私域 / 发价目表 / 促单）
  咨询 -> consult    （发案例 / 资料 / 诊断）
  售后 -> support    （交付问题跟进）
  合作 -> partner    （城市合伙人 / 招商）
  闲聊 -> chitchat   （轻量互动，埋钩子）

真实能力接入点：
  - 消息接入：平台评论/私信 API（抖音/视频号/企微）替换 _fetch_messages
  - 私域导流：企微/个微 API 替换 _push_to_private
  demo 阶段用 LLM 直接对单条 message 分析，离线时走关键词启发式兜底。
"""
import re
import json

from ..core.agent import AbstractAgent
from ..core.context import AgentContext
from ..core.llm import get_provider, extract_json

INTENTS = ["咨询", "购买", "售后", "合作", "闲聊"]
ROUTE_MAP = {
    "购买": "sales",
    "咨询": "consult",
    "售后": "support",
    "合作": "partner",
    "闲聊": "chitchat",
}


class ServiceAgent(AbstractAgent):
    name = "service"

    def __init__(self) -> None:
        super().__init__()
        self.llm = get_provider()

    def _heuristic(self, message: str) -> dict:
        m = message
        if re.search(r"代理|合伙|招商|一起干|合作|加盟", m):
            intent = "合作"
        elif re.search(r"退款|售后|没收到|做错了|不满意|投诉", m):
            intent = "售后"
        elif re.search(r"多少钱|怎么买|怎么收费|价格|报名|下单|购买|付费", m):
            intent = "购买"
        elif re.search(r"你好|在吗|哈哈|厉害|关注了", m):
            intent = "闲聊"
        else:
            intent = "咨询"
        contact = None
        for pat in [r"(微信|vx|v信|weixin)[:：]?\s*([\w-]{5,20})",
                    r"(\d{11})",
                    r"@([\w\u4e00-\u9fa5]{2,20})"]:
            mt = re.search(pat, m)
            if mt:
                contact = mt.group(2) if mt.lastindex and mt.lastindex >= 2 else mt.group(1)
                break
        need = m
        replies = {
            "购买": "收到～我发你一份《AI超市服务价目表》和体验卡链接，你先看下哪个套餐合适，不确定我帮你选。",
            "咨询": "可以的，先帮你做个免费诊断：你这边主要是想用AI解决获客、还是做内容/交付？我给你对应案例。",
            "售后": "抱歉给你添麻烦了，把具体情况发我，我马上安排交付同学跟进处理。",
            "合作": "欢迎！我们正在找城市合伙人，我发你一份合伙方案，咱们约个时间细聊。",
            "闲聊": "谢谢关注～想用AI做点啥，随时喊我，先送你一份入门资料。",
        }
        return {"intent": intent, "need": need, "contact": contact, "reply": replies[intent]}

    def _run(self, ctx: AgentContext) -> AgentContext:
        message = (ctx.get("message") or "").strip()
        if not message:
            return ctx.put("status", "empty").put("route", "none").put("reply", "（空消息）")

        try:
            raw = self.llm.chat(
                "你是「AI超市」的客服专家。判断用户意图（咨询/购买/售后/合作/闲聊），"
                "抽取需求与联系方式，并给出一条回复话术。只返回 JSON"
                "{intent, need, contact, reply}",
                f"用户消息：{message}",
            )
            data = json.loads(extract_json(raw))
            intent = data.get("intent", "咨询")
            if intent not in INTENTS:
                intent = "咨询"
            data["intent"] = intent
        except Exception:
            data = self._heuristic(message)

        route = ROUTE_MAP.get(data.get("intent", "咨询"), "consult")
        lead = {
            "source": ctx.get("source", "douyin_dm"),
            "message": message,
            "intent": data.get("intent"),
            "need": data.get("need"),
            "contact": data.get("contact"),
        }
        return (ctx.put("intent", data.get("intent"))
                   .put("need", data.get("need"))
                   .put("contact", data.get("contact"))
                   .put("reply", data.get("reply", ""))
                   .put("route", route)
                   .put("lead", lead)
                   .put("status", "done"))
