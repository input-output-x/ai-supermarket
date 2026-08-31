"""AI 超市 · 计费/支付层（让额度计量真正可收费）。

可插拔 Provider：
  - StripeProvider  ：真实 Stripe Checkout（Hosted 页面，免前端 PCI），env 驱动
  - WeChatProvider  ：微信支付占位（Native/JSAPI 需商户号+APIv3 密钥+证书，待接）

流程：
  1) 客户点"升级套餐" → POST /api/billing/checkout {plan, provider}
     → Stripe 返回托管结账页 URL（或微信返回 code_url）
  2) 客户在 Stripe 完成付款 → Stripe 回调 POST /api/billing/webhook/stripe
     → 校验签名 → 把该 customer 的 plan 升级 + 重置额度（新的计费周期）
  3) 客户立即获得更高套餐的 Agent 与额度

凭证（绝不入库，仅环境变量）：
  STRIPE_SECRET_KEY        Stripe 后台 API Key（sk_live_/sk_test_）
  STRIPE_WEBHOOK_SECRET    Stripe Webhook Signing Secret（whsec_...）
  WECHAT_MCH_ID / WECHAT_APIV3_KEY / WECHAT_APP_ID / WECHAT_SERIAL / WECHAT_PRIVATE_KEY  （微信支付，待接）
未配置时：返回清晰的"未配置"状态，绝不假装收款成功。
"""
import os
import hmac
import hashlib
import requests
from abc import ABC, abstractmethod

# 套餐月价（单位：分）。免费档为 0。可按需调整。
PLAN_PRICES = {
    "free": 0,
    "pro": 9900,       # ¥99 / 月
    "enterprise": 29900,  # ¥299 / 月
}
PLAN_LABELS = {"free": "免费版", "pro": "专业版", "enterprise": "企业版"}
STRIPE_BASE = "https://api.stripe.com/v1"


class PaymentProvider(ABC):
    name = "base"

    @abstractmethod
    def is_configured(self) -> bool:
        ...

    @abstractmethod
    def create_checkout(self, customer_api_key: str, plan: str, success_url: str, cancel_url: str) -> dict:
        """返回 {status, url?/message?/raw?}。"""
        ...

    def verify_webhook(self, payload: bytes, sig_header: str) -> dict | None:
        """校验并返回事件 dict；失败返回 None。"""
        return None

    def parse_paid_plan(self, event: dict) -> tuple[str | None, str | None]:
        """从事件取出 (plan, customer_api_key)。"""
        return None, None


class StripeProvider(PaymentProvider):
    name = "stripe"

    def is_configured(self) -> bool:
        return bool(os.getenv("STRIPE_SECRET_KEY"))

    def create_checkout(self, customer_api_key: str, plan: str, success_url: str, cancel_url: str) -> dict:
        secret = os.getenv("STRIPE_SECRET_KEY")
        if not secret:
            return {"status": "unconfigured", "message": "未配置 STRIPE_SECRET_KEY"}
        amount = PLAN_PRICES.get(plan)
        if not amount:
            return {"status": "invalid_plan", "message": f"套餐 {plan} 无价格"}
        data = {
            "mode": "payment",
            "success_url": success_url,
            "cancel_url": cancel_url,
            "client_reference_id": customer_api_key,
            "metadata[customer_api_key]": customer_api_key,
            "metadata[plan]": plan,
            "line_items[0][price_data][currency]": "cny",
            "line_items[0][price_data][unit_amount]": str(amount),
            "line_items[0][price_data][product_data][name]": f"AI超市 {PLAN_LABELS.get(plan, plan)} 套餐",
            "line_items[0][quantity]": "1",
        }
        r = requests.post(f"{STRIPE_BASE}/checkout/sessions", data=data, auth=(secret, ""), timeout=30)
        js = r.json()
        if r.status_code != 200 or not js.get("url"):
            return {"status": "error", "message": js.get("error", {}).get("message", "Stripe 创建会话失败"), "raw": js}
        return {"status": "ok", "url": js["url"], "session_id": js.get("id")}

    def verify_webhook(self, payload: bytes, sig_header: str) -> dict | None:
        secret = os.getenv("STRIPE_WEBHOOK_SECRET")
        if not secret or not sig_header:
            return None
        parts = dict(p.split("=", 1) for p in sig_header.split(",") if "=" in p)
        ts, sig = parts.get("t"), parts.get("v1")
        if not ts or not sig:
            return None
        signed = f"{ts}.".encode() + payload
        expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return None
        import json
        try:
            return json.loads(payload.decode())
        except Exception:
            return None

    def parse_paid_plan(self, event: dict) -> tuple[str | None, str | None]:
        if event.get("type") != "checkout.session.completed":
            return None, None
        obj = event.get("data", {}).get("object", {})
        meta = obj.get("metadata", {})
        return meta.get("plan"), meta.get("customer_api_key")


class WeChatProvider(PaymentProvider):
    """微信支付占位：Native/JSAPI 需商户号 + APIv3 密钥 + 证书，较复杂，待接。"""
    name = "wechat"

    def is_configured(self) -> bool:
        return bool(os.getenv("WECHAT_MCH_ID") and os.getenv("WECHAT_APIV3_KEY"))

    def create_checkout(self, customer_api_key: str, plan: str, success_url: str, cancel_url: str) -> dict:
        if not self.is_configured():
            return {"status": "unconfigured", "message": "未配置微信支付凭证（WECHAT_MCH_ID/WECHAT_APIV3_KEY）"}
        return {
            "status": "not_implemented",
            "message": "微信支付待接入：需商户号 + APIv3 密钥 + 证书，按 Native/JSAPI 流程实现 create_checkout。",
        }


PROVIDERS = {"stripe": StripeProvider, "wechat": WeChatProvider}


def get_provider(name: str = "stripe") -> PaymentProvider:
    return PROVIDERS.get(name, StripeProvider)()


def list_plans() -> list:
    return [
        {"id": p, "label": PLAN_LABELS.get(p, p), "price_cents": PLAN_PRICES.get(p, 0),
         "price_yuan": PLAN_PRICES.get(p, 0) / 100}
        for p in ("free", "pro", "enterprise")
    ]
