"""ai-publish：发布 Agent（必备，流量引擎第 4 环）。

职责：生成标题备选与话题标签，按策略多平台发布。
输入：videoPath / cover / topicTitle
输出：titleCandidates / hashtags / publishResult
工具：抖音/视频号开放平台 API + 定时调度（此处标接入点，demo 产出占位结果）
"""
from ..core.agent import AbstractAgent
from ..core.context import AgentContext


class PublishAgent(AbstractAgent):
    name = "publish"

    def _run(self, ctx: AgentContext) -> AgentContext:
        title = ctx.get("topicTitle", "")
        # TODO(接入真实能力): 调各平台开放平台API发布并回写链接；接 scheduler 做定时
        return (ctx.put("titleCandidates", f"[{title}] / [别再错过！{title}]")
                   .put("hashtags", "#AI创业 #副业 #AI超市")
                   .put("publishResult", "douyin=queued; channels=抖音,视频号"))
