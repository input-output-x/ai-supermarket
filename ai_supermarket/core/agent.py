"""Agent 抽象（类比 Spring 的 @Service 模板方法）。"""
from abc import ABC, abstractmethod
import logging

from .context import AgentContext


class Agent(ABC):
    """所有 Agent 的统一契约。name 为唯一调度名，execute 为执行入口。"""
    name: str

    @abstractmethod
    def execute(self, ctx: AgentContext) -> AgentContext:
        ...


class AbstractAgent(Agent):
    """模板方法：统一日志埋点，子类只实现 _run。"""

    def __init__(self) -> None:
        self.log = logging.getLogger(f"agent.{self.name}")

    def execute(self, ctx: AgentContext) -> AgentContext:
        self.log.info("start | input=%s", ctx.summary())
        out = self._run(ctx)
        self.log.info("done  | output=%s", out.summary())
        return out

    @abstractmethod
    def _run(self, ctx: AgentContext) -> AgentContext:
        ...
