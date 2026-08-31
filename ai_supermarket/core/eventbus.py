"""进程内事件总线（类比 Spring Cloud Stream），解耦 Agent 通信。"""


class EventBus:
    def __init__(self) -> None:
        self._topics: dict[str, list] = {}

    def subscribe(self, topic: str, fn) -> None:
        self._topics.setdefault(topic, []).append(fn)

    def publish(self, topic: str, payload) -> None:
        for fn in self._topics.get(topic, []):
            fn(topic, payload)
