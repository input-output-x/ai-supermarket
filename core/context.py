"""Agent 之间流转的上下文（类比 Message / 工作流变量），灵活 KV。"""


class AgentContext:
    def __init__(self, data: dict | None = None) -> None:
        self._data: dict = dict(data or {})

    def put(self, key: str, value):
        self._data[key] = value
        return self

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def has(self, key: str) -> bool:
        return key in self._data

    def raw(self) -> dict:
        return self._data

    def summary(self) -> str:
        return "; ".join(f"{k}={v}" for k, v in self._data.items())
