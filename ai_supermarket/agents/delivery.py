"""ai-delivery：交付 Agent（其他，脚手架）。

职责：实际交付代运营/数字人/写真/Agent搭建，按 SOP 调度（AI超市 第 3 层 交付层）。
输入：order  输出：deliverable / deliveryStatus
工具：各交付子系统API + 工作流引擎
状态：脚手架就位，_run 待实现。
"""
from ..core.agent import AbstractAgent
from ..core.context import AgentContext


class DeliveryAgent(AbstractAgent):
    name = "delivery"

    def _run(self, ctx: AgentContext) -> AgentContext:
        # TODO(后续交付): 接入代运营/数字人/写真/Agent 子系统，按 SOP 产出交付物
        return ctx.put("deliverable", "TODO").put("deliveryStatus", "scaffold")
