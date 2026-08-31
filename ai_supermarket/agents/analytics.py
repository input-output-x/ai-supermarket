"""ai-analytics：数据复盘 Agent（复盘层关键）—— 真实逻辑已落地。

职责：根据一条视频/账号的播放、转化、互动等数据，产出复盘结论：
核心指标解读、亮点、问题、对下一期选题与脚本权重的建议。

输入：metrics（自由文本，含 播放/转化/点赞/评论/主页访问 等）
输出：summary / highlights / issues / next_actions(area, action, weight) / status

真实能力接入点：
  - 数据源：抖音/视频号开放平台数据 API 替换 _fetch_metrics
  - 反哺：把 next_actions 写回选题/脚本权重库
  demo 阶段用 LLM 直接分析，离线时走数字启发式兜底（算转化率给建议）。
"""
import re
import json

from ..core.agent import AbstractAgent
from ..core.context import AgentContext
from ..core.llm import get_provider, extract_json


class AnalyticsAgent(AbstractAgent):
    name = "analytics"

    def __init__(self) -> None:
        super().__init__()
        self.llm = get_provider()

    def _parse_numbers(self, text: str) -> dict:
        out = {}
        # 播放量 / 观看
        m = re.search(r"(?:播放|观看)[：:\s]*?(\d[\d,\.]*)\s*(万|亿|w)?", text)
        if m:
            out["views"] = self._to_num(m.group(1), m.group(2))
        # 转化 / 线索 / 成交
        m = re.search(r"(?:转化|线索|成交|留资)[：:\s]*?(\d[\d,\.]*)\s*(万|亿|w)?", text)
        if m:
            out["conv"] = self._to_num(m.group(1), m.group(2))
        # 点赞
        m = re.search(r"(?:点赞|赞)[：:\s]*?(\d[\d,\.]*)\s*(万|亿|w)?", text)
        if m:
            out["likes"] = self._to_num(m.group(1), m.group(2))
        return out

    @staticmethod
    def _to_num(s: str, unit: str) -> float:
        v = float(s.replace(",", ""))
        if unit in ("万", "w", "W"):
            v *= 1e4
        elif unit == "亿":
            v *= 1e8
        return v

    def _heuristic(self, metrics: str) -> dict:
        n = self._parse_numbers(metrics)
        views = n.get("views", 0)
        conv = n.get("conv", 0)
        rate = (conv / views * 100) if views else 0.0
        highlights, issues, next_actions = [], [], []
        if views >= 1e4:
            highlights.append(f"播放量达 {views/1e4:.1f} 万，基础曝光合格")
        else:
            issues.append("播放量偏低，选题/封面钩子需加强")
        if rate >= 1:
            highlights.append(f"转化率 {rate:.2f}% 优秀（行业基准约 1%）")
            next_actions.append({"area": "选题", "action": "复用本期高转化选题角度，加大同类占比", "weight": "高"})
        else:
            issues.append(f"转化率 {rate:.2f}% 偏低，承接话术/落地页待优化")
            next_actions.append({"area": "承接", "action": "优化评论区引导与私域话术，提升转化", "weight": "高"})
        next_actions.append({"area": "脚本", "action": "前 3 秒钩子 A/B 测试，保留完播更高版本", "weight": "中"})
        return {
            "summary": f"播放 {views:.0f} / 转化 {conv:.0f} / 转化率 {rate:.2f}%",
            "highlights": highlights or ["数据平稳"],
            "issues": issues or ["暂无明显问题"],
            "next_actions": next_actions,
        }

    def _run(self, ctx: AgentContext) -> AgentContext:
        metrics = (ctx.get("metrics") or "").strip()
        if not metrics:
            return ctx.put("status", "empty").put("result", "（空数据）")

        try:
            raw = self.llm.chat(
                "你是短视频数据复盘专家。根据给出的播放/转化/互动数据，输出复盘结论。"
                "只返回 JSON：{summary, highlights:[], issues:[], next_actions:[{area, action, weight}]}",
                f"数据：{metrics}",
            )
            data = json.loads(extract_json(raw))
            if not data.get("next_actions"):
                raise ValueError("空 next_actions")
        except Exception:
            data = self._heuristic(metrics)

        return (ctx.put("summary", data.get("summary"))
                   .put("highlights", data.get("highlights", []))
                   .put("issues", data.get("issues", []))
                   .put("next_actions", data.get("next_actions", []))
                   .put("result", data)
                   .put("status", "done"))
