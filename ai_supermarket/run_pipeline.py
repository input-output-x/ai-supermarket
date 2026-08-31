"""入口：默认跑一次每日主链路（离线 Mock）；带参数切换模式。

用法：
  python -m ai_supermarket.run_pipeline "AI创业"            # 跑一次每日主链路
  python -m ai_supermarket.run_pipeline --serve             # 起网关 HTTP（POST /pipeline, GET /health）
  python -m ai_supermarket.run_pipeline --service "多少钱"  # 演示客服 Agent 意图分流
"""
import sys
import os
import json
import logging

from .gateway import AiSupermarketGateway
from .agents.service import ServiceAgent


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    gw = AiSupermarketGateway()

    if "--serve" in sys.argv:
        port = int(os.environ.get("PORT", "8080"))
        gw.serve(port=port)
        return

    if "--service" in sys.argv:
        i = sys.argv.index("--service")
        msg = sys.argv[i + 1] if i + 1 < len(sys.argv) else "你好"
        from .core.context import AgentContext
        out = ServiceAgent().execute(AgentContext({"message": msg}))
        print("\n=== 客服 Agent 演示 ===")
        print(json.dumps(out.raw(), ensure_ascii=False, indent=2))
        return

    kw = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "AI创业"
    res = gw.run(kw)
    print("\n=== 每日主链路结果 ===")
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
