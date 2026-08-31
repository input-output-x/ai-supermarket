"""编排器：定义标准链路 topic -> script -> video -> publish（流量引擎主链路）。"""
from .context import AgentContext
from .registry import AgentRegistry


class AiSupermarketOrchestrator:
    def __init__(self, registry: AgentRegistry) -> None:
        self.registry = registry

    def run_daily_pipeline(self, keyword: str) -> AgentContext:
        ctx = AgentContext().put("keyword", keyword)
        for step in ["topic", "script", "video", "publish"]:
            agent = self.registry.get(step)
            if agent is None:
                print(f"[orchestrator] agent missing, skip step: {step}")
                continue
            ctx = agent.execute(ctx)
        return ctx
