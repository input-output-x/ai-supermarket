"""实测横评：同一提示词，发给多个大模型，拿真实输出对比。

支持：
  DeepSeek  -> DEEPSEEK_API_KEY      (已有)
  GPT       -> OPENAI_API_KEY        (需用户提供)
  Claude    -> ANTHROPIC_API_KEY     (需用户提供)
  Kimi      -> MOONSHOT_API_KEY      (需用户提供)

原则：**有 key 才真调，没 key 明确标「未配置」并跳过，绝不编造结果。**

用法：
  python -m agents.bench "你的提示词"
  # 或在代码里：
  from agents.bench import bench_models
  results = bench_models("用一句话解释大模型蒸馏")
"""
import os
import json
import sys
import urllib.request

# 各厂商接入配置（base/model 用公开默认值，可用环境变量覆盖）
PROVIDERS = {
    "DeepSeek": {
        "env_key": "DEEPSEEK_API_KEY",
        "base": os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
        "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
        "kind": "openai",
    },
    "GPT": {
        "env_key": "OPENAI_API_KEY",
        "base": os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        "kind": "openai",
    },
    "Claude": {
        "env_key": "ANTHROPIC_API_KEY",
        "base": os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1"),
        "model": os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022"),
        "kind": "anthropic",
    },
    "Kimi": {
        "env_key": "MOONSHOT_API_KEY",
        "base": os.environ.get("MOONSHOT_BASE_URL", "https://api.moonshot.cn/v1"),
        "model": os.environ.get("MOONSHOT_MODEL", "moonshot-v1-8k"),
        "kind": "openai",
    },
}


def _call_openai(base: str, key: str, model: str, system: str, user: str) -> str:
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.7,
    }).encode("utf-8")
    req = urllib.request.Request(
        base + "/chat/completions", data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))["choices"][0]["message"]["content"]


def _call_anthropic(base: str, key: str, model: str, system: str, user: str) -> str:
    body = json.dumps({
        "model": model,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "max_tokens": 800,
    }).encode("utf-8")
    req = urllib.request.Request(
        base + "/messages", data=body,
        headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        d = json.loads(resp.read().decode("utf-8"))
        return d["content"][0]["text"]


def bench_models(prompt: str, system: str = "你是一个有帮助的AI助手，用中文简洁回答。") -> dict:
    """对同一个 prompt 跑所有已配置 key 的模型，返回 {模型名: {ok, output/model/reason}}。"""
    results = {}
    for name, cfg in PROVIDERS.items():
        key = os.environ.get(cfg["env_key"])
        if not key:
            results[name] = {"ok": False, "reason": f"未配置 {cfg['env_key']}，跳过（不编造）"}
            continue
        try:
            if cfg["kind"] == "openai":
                out = _call_openai(cfg["base"], key, cfg["model"], system, prompt)
            else:
                out = _call_anthropic(cfg["base"], key, cfg["model"], system, prompt)
            results[name] = {"ok": True, "model": cfg["model"], "output": out}
        except Exception as e:
            results[name] = {"ok": False, "reason": f"调用失败: {e}"}
    return results


def summarize(results: dict) -> str:
    lines = []
    for name, r in results.items():
        if r.get("ok"):
            out = r["output"].strip().replace("\n", " ")
            lines.append(f"【{name} · {r['model']}】✅\n{out}\n")
        else:
            lines.append(f"【{name}】⚠️ {r.get('reason')}\n")
    return "\n".join(lines)


if __name__ == "__main__":
    prompt = sys.argv[1] if len(sys.argv) > 1 else "用一句话解释什么是大模型蒸馏，并举一个普通人能懂的生活例子。"
    print(f"===== 实测横评 =====\n提示词：{prompt}\n")
    res = bench_models(prompt)
    print(summarize(res))
    measured = [n for n, r in res.items() if r.get("ok")]
    print(f"\n实测完成：{len(measured)}/{len(PROVIDERS)} 个模型已真跑（{measured or '无'}）")
    pending = [n for n, r in res.items() if not r.get("ok")]
    if pending:
        print(f"未实测（缺 key）：{pending} —— 提供对应 API key 后可补全真实结果。")
