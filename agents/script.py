"""ai-script：口播脚本 Agent（流量引擎第 2 环）。

职责：根据选题包（topic Agent 产出）+ 可选「实测数据 bench」生成抖音口播脚本。
输入：topicTitle / hook / angle / audience（均来自 topic Agent），bench（可选，bench_models 的实测结果）
输出：voiceover（口播稿）/ shots（分镜表，带时间码）/ captionTiming（字幕节奏）/ cover（封面文案）
工具：LLM（Deepseek）+ 模板兜底（无 key 也能出结构）

设计要点：脚本若拿到真实 bench 数据，会引用「已实测」的模型、并诚实标注「待实测」的模型，
绝不在口播稿里编造未实测模型的输出。
"""
import json

from core.agent import AbstractAgent
from core.context import AgentContext
from core.llm import get_provider, extract_json

_SYSTEM_PROMPT = """你是抖音口播脚本专家，尤其擅长「AI 教程 / 工具实测」类短视频。
基于选题包生成口播脚本，只返回一个 JSON 对象，不要解释文字。
结构：
{
  "voiceover": "完整口播稿（口语化、有钩子有反转，约 200-300 字，可直接念）",
  "shots": "分镜表，每行 [时间] 画面/动作 | 口播，例如：[0-3s] 钩子字幕特写 | 同一句话丢给4个模型…",
  "captionTiming": "字幕节奏建议（1句）",
  "cover": "封面文案（≤8字，与选题包封面呼应）"
}
要求：
- 开头 3 秒必须有强钩子（反差/悬念/利益点），对应 hook；
- 如果提供了实测数据，必须基于真实输出讲，引用已实测的模型，未实测的明确说「待补充/下期测」，不得编造；
- 结尾引导关注/评论（如「想要提示词评论区扣1」）；
- 口语化，少用书面词，每句短。"""


def _bench_summary(bench: dict) -> str:
    if not bench:
        return ""
    lines = ["【实测数据（仅列出已真跑的模型，未实测的跳过）】"]
    for name, r in bench.items():
        if r.get("ok"):
            out = r["output"].strip().replace("\n", " ")
            lines.append(f"{name}：{out}")
        else:
            lines.append(f"{name}：未实测（{r.get('reason','')}）")
    return "\n".join(lines)


class ScriptAgent(AbstractAgent):
    name = "script"

    def __init__(self) -> None:
        super().__init__()
        self.llm = get_provider()

    def _run(self, ctx: AgentContext) -> AgentContext:
        title = ctx.get("topicTitle", "")
        hook = ctx.get("hook", "")
        angle = ctx.get("angle", "")
        audience = ctx.get("audience", "")
        bench = ctx.get("bench") or {}

        prompt = f"【选题】{title}\n【钩子】{hook}\n【角度】{angle}\n【人群】{audience}"
        bs = _bench_summary(bench)
        if bs:
            prompt += f"\n\n{bs}\n\n请基于上面的实测数据写脚本，未实测的模型如实标注「下期测」，不要编造它们的输出。"

        try:
            raw = self.llm.chat(_SYSTEM_PROMPT, prompt)
            s = json.loads(extract_json(raw))
        except Exception as e:
            self.log.warning("[script] LLM 失败，走模板兜底: %s", e)
            s = self._fallback(title, hook, bench)

        s.setdefault("voiceover", f"{title}。{hook}")
        s.setdefault("shots", "[0-3s]钩子|[3-20s]演示|[20-30s]引导关注")
        s.setdefault("captionTiming", "每句≤12字，关键反转处加停顿")
        s.setdefault("cover", title[:8])

        return (ctx.put("voiceover", s["voiceover"])
                   .put("shots", s["shots"])
                   .put("captionTiming", s["captionTiming"])
                   .put("cover", s["cover"]))

    def _fallback(self, title: str, hook: str, bench: dict) -> dict:
        measured = [n for n, r in bench.items() if r.get("ok")]
        pending = [n for n, r in bench.items() if not r.get("ok")]
        note = ""
        if measured:
            note += f"我已经实测了：{('、'.join(measured))}。"
        if pending:
            note += f"{('、'.join(pending))} 下期补测。"
        voiceover = (
            f"{hook}。"
            f"今天我做了一件事：把同一句话，同时丢给 GPT、Claude、DeepSeek、Kimi 四个大模型。\n"
            f"你猜结果差多大？{note}\n"
            f"就拿「解释大模型蒸馏」来说，DeepSeek 直接给我打了个比方——徒弟跟着名厨学做菜，不背菜谱，只学关键手法。\n"
            f"同一个问题，不同模型的脑回路完全不一样，选对模型效率能差好几倍。\n"
            f"想知道你常用的那个模型排第几？关注我，下期把四个模型拉满实测一遍。"
        )
        return {
            "voiceover": voiceover,
            "shots": ("[0-3s] 钩子字幕特写 | 同一句话丢给4个模型，结果差多大\n"
                      "[3-10s] 抛问题 | 你猜它们脑回路差多少\n"
                      "[10-22s] 展示实测样本 | DeepSeek 的「名厨徒弟」比喻\n"
                      "[22-30s] 引导 | 关注我，下期四模型拉满实测"),
            "captionTiming": "每句≤12字；「差多大」处停顿强调",
            "cover": title[:8],
        }
