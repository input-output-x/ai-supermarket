"""聚合/网关服务：注册 4 个必备 Agent，把主链路串起来真跑；并暴露 HTTP 接口。

类比 Spring Cloud Gateway：对外的统一入口，内部按编排器调各 Agent 微服务。
  GET  /health    -> 健康检查 + 已注册 Agent 列表
  POST /pipeline  -> body {"keyword": "AI创业"}，返回整条链路结果 JSON
"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .core.registry import AgentRegistry
from .core.orchestrator import AiSupermarketOrchestrator
from .agents.topic import TopicAgent
from .agents.script import ScriptAgent
from .agents.video import VideoAgent
from .agents.publish import PublishAgent
from .agents.service import ServiceAgent


class AiSupermarketGateway:
    def __init__(self) -> None:
        self.registry = AgentRegistry()
        self.orchestrator = AiSupermarketOrchestrator(self.registry)
        # 主链路（流量引擎）：topic -> script -> video -> publish
        for agent in [TopicAgent(), ScriptAgent(), VideoAgent(), PublishAgent()]:
            self.registry.register(agent)
        # 承接层：客服 Agent 注册进注册中心，供 /health 展示与单独调用
        self.registry.register(ServiceAgent())

    def run(self, keyword: str) -> dict:
        ctx = self.orchestrator.run_daily_pipeline(keyword)
        return ctx.raw()

    def serve(self, host: str = "0.0.0.0", port: int = 8080) -> None:
        gateway = self

        class Handler(BaseHTTPRequestHandler):
            def _send(self, code: int, obj) -> None:
                body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path == "/health":
                    self._send(200, {"status": "ok", "agents": gateway.registry.names()})
                else:
                    self._send(404, {"error": "not found"})

            def do_POST(self):
                if self.path == "/pipeline":
                    length = int(self.headers.get("Content-Length", 0) or 0)
                    payload = json.loads(self.rfile.read(length) or b"{}")
                    self._send(200, gateway.run(payload.get("keyword", "AI")))
                else:
                    self._send(404, {"error": "not found"})

            def log_message(self, *args):
                pass

        print(f"[gateway] listening on http://{host}:{port}  (POST /pipeline, GET /health)")
        ThreadingHTTPServer((host, port), Handler).serve_forever()
