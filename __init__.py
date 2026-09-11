"""AI超市：多 Agent 微服务矩阵（Python 实现）。

架构类比（与 Java 示例一致）：
  ai_supermarket(包)        ≈ Spring Cloud release train（父工程）
  ai_supermarket.core       ≈ Spring Cloud 公共能力（Agent/注册/总线/编排/LLM）
  ai_supermarket.agents.*   ≈ 独立微服务（ai-topic / ai-script / ...）
  ai_supermarket.gateway    ≈ 网关/聚合服务（把 Agents 串成主链路）
"""
__version__ = "0.0.1"
