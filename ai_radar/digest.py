"""摘要层：有 DEEPSEEK_API_KEY 就生成中文速报；否则用纯列表兜底。"""
import os
import requests

DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"


def llm_digest(items, max_items: int = 20):
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        return None
    picked = items[:max_items]
    lines = [f"[{i.source}] {i.title} — {i.url}" for i in picked]
    prompt = (
        "你是 AI 资讯编辑。以下是近期大模型/产品的发布动态，请用简体中文写一段速报"
        "（不超过 280 字）：按厂商分组，点出最值得关注的 1-2 条，并附关键链接。"
        "用 Markdown 列表，链接写成 [标题](url) 形式。\n\n" + "\n".join(lines)
    )
    try:
        r = requests.post(
            DEEPSEEK_URL,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 400,
            },
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[digest] LLM 失败，回退纯文本: {e}")
        return None


def fallback_digest(items):
    by_src = {}
    for i in items:
        by_src.setdefault(i.source, []).append(i)
    lines = ["# 🚨 AI雷达 · 模型速报"]
    for src, its in by_src.items():
        lines.append(f"\n## {src}")
        for i in its:
            line = f"- [{i.title}]({i.url})"
            if i.published:
                line += f"  ({i.published})"
            lines.append(line)
    return "\n".join(lines)
