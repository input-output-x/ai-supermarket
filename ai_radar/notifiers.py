"""推送层：飞书群机器人 + 微信个人(PushPlus)。配置驱动，填了才启用。"""
import os
import requests


def send_feishu(webhook: str, text: str) -> bool:
    if not webhook:
        return False
    card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": "🚨 AI雷达 · 模型速报"},
                "template": "blue",
            },
            "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": text}}],
        },
    }
    try:
        r = requests.post(webhook, json=card, timeout=15)
        r.raise_for_status()
        return r.json().get("code", 1) == 0
    except Exception as e:
        print(f"[feishu] 发送失败: {e}")
        return False


def send_pushplus(token: str, title: str, text: str) -> bool:
    if not token:
        return False
    try:
        r = requests.post(
            "https://www.pushplus.plus/send",
            json={"token": token, "title": title, "content": text, "template": "markdown"},
            timeout=15,
        )
        r.raise_for_status()
        return r.json().get("code") == 200
    except Exception as e:
        print(f"[pushplus] 发送失败: {e}")
        return False
