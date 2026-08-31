"""ai-analytics：数据复盘 Agent（其他，脚手架）。

职责：看播放/转化，反哺选题与脚本权重（AI超市 第 4 层 交易层 反馈闭环）。
输入：metrics  输出：report / topicWeight
工具：数据看板API + LLM 分析
状态：脚手架就位，_run 待实现。
"""
from ..core.agent import AbstractAgent
from ..core.context import AgentContext


class AnalyticsAgent(AbstractAgent):
    name = "analytics"

    def _run(self, ctx: AgentContext) -> AgentContext:
        # TODO(后续交付): 接入数据看板API + LLM分析，输出复盘报告与选题权重
        return ctx.put("report", "TODO").put("topicWeight", "TODO").put("status", "scaffold")
