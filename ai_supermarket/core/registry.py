"""进程内 Agent 注册中心（类比 Nacos / Eureka）。"""
from .agent import Agent


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}

    def register(self, agent: Agent) -> None:
        self._agents[agent.name] = agent
        print(f"[registry] registered agent: {agent.name}")

    def get(self, name: str) -> Agent | None:
        return self._agents.get(name)

    def names(self) -> list[str]:
        return list(self._agents)
