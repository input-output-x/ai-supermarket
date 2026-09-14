"""ai-barber：AI 理发师 Agent。

职责：根据一个人的特征（性别 / 脸型 / 年龄身份 / 发质发量 / 日常风格 / 改造接受度 / 偏好），
推荐 3 个适合的发型，每个带推荐理由，并额外给出：
- 一句话脸型/气质诊断
- 避雷清单（绝对别剪的 + 为什么）
- 给理发师的沟通话术（用沙龙术语，避免「差不多剪短点」翻车）
- 维持建议（修剪周期 + 日常打理）

输入（均可空，越全推荐越准）：
  gender      性别：男 / 女
  face_shape  脸型：圆 / 方 / 长 / 鹅蛋 / 心形 / 菱形 / 未知
  age_group   年龄段/身份：如 学生 / 职场新人 / 中层管理 / 自由职业 / 中年
  hair_type   发质发量：细软塌 / 粗硬 / 自然卷 / 发量少 / 发量多 / 正常
  style       日常风格：职场干练 / 休闲 / 潮流网红 / 运动 / 文艺
  changeable  改造接受度：只修不染 / 可接受染烫 / 可大改
  preference  偏好/目标：如 显脸小 / 好打理 / 显年轻 / 遮发际线 / 遮瑕疵
输出：faceRead / recommendations(3) / avoid / stylistScript / maintain
工具：LLM（Deepseek）+ 启发式兜底（无 key 也能出结构化结果）
"""
import json

from core.agent import AbstractAgent
from core.context import AgentContext
from core.llm import get_provider, extract_json

_SYSTEM_PROMPT = """你是拥有 15 年经验的资深发型设计师，擅长根据一个人的综合条件推荐发型。
只返回一个 JSON 对象，不要解释文字。结构：
{
  "faceRead": "一句话脸型/气质诊断，点出核心痛点（如：圆脸+细软发，显脸圆且容易塌）",
  "recommendations": [
    {
      "name": "发型名",
      "why": "推荐理由（必须结合用户的脸型/职业/风格/痛点，说清为什么适合他，2-3句）",
      "style": "风格定位（如 通勤利落 / 日系慵懒 / 韩系氛围）",
      "scene": "最适合的场景（如 上班/约会/日常）",
      "difficulty": 2,
      "needsColor": "否",
      "cut": "剪法要点（长度/层次/刘海/鬓角，给理发师看的关键词）",
      "ref": "搜图关键词或参考（如 法式锁骨发 层次 八字刘海）"
    }
  ],
  "avoid": ["不适合的发型1（为什么不适合）", "不适合的发型2（为什么不适合）"],
  "stylistScript": "拿给理发师的原话模板（用沙龙术语，避免「差不多剪短点」，含长度/层次/刘海/厚度具体描述）",
  "maintain": "维持建议（多久修剪一次 + 日常怎么打理，1-2句）"
}
要求：
- recommendations 必须正好 3 个，且彼此有明确差异（如一个保守、一个时髦、一个风格化）；
- difficulty 是整数 1-5（1=洗完就走，5=每天要造型）；
- why 不能空泛（别说「显气质」），必须落到用户的某个具体特征；
- avoid 要戳中用户脸型/发质的真实雷区；
- stylistScript 要具体可执行，让用户照着念就不会翻车。"""

# 启发式兜底：无 key 时按脸型给结构化通用建议，保证能出可用结果
_FALLBACK_BY_FACE = {
    "圆": {
        "faceRead": "圆脸——面部横向留白多，核心是「拉长 + 顶部蓬松 + 两侧收薄」",
        "recs": [
            ("侧分纹理短发 / 锁骨发", "侧分打破对称、顶部吹蓬，视觉拉长脸型；两侧打薄不贴脸", "通勤利落", "上班/日常", 2, "否",
             "顶部保留厚度吹蓬，两侧及后脑勺去量，刘海斜向侧分不过眉", "圆脸 侧分 蓬松顶 收侧"),
            ("高层次长直发", "长发 + 脸颊两侧层次制造纵向线条，弱化圆润感", "文艺慵懒", "约会/日常", 3, "可选",
             "从颧骨下开始打薄层次，避免齐刘海，发尾微内扣", "圆脸 高层次 龙须须 内扣"),
            ("法式八字刘海", "八字刘海露出额头、修饰颧宽，比齐刘海更显脸长", "韩系氛围", "拍照/日常", 2, "否",
             "刘海中分外扩成八字形，长度到颧骨下，两侧留碎发", "圆脸 八字刘海 显脸小"),
        ],
        "avoid": ["齐刘海厚刘海（把脸横向截断更显圆）", "两侧蓬松爆炸头（加宽面部）", "超短圆寸（完全暴露脸型）"],
    },
    "方": {
        "faceRead": "方脸——下颌角明显、轮廓硬，核心是「柔化棱角 + 用曲线缓冲」",
        "recs": [
            ("微卷中长发", "曲线和卷度中和下颌硬朗感，柔化轮廓", "日系温柔", "日常/约会", 3, "可选",
             "下颌处做 C 卷/水波纹，避免直线条，长度过肩", "方脸 微卷 柔化下颌"),
            ("碎发龙须 + 八字刘海", "脸颊两侧碎发遮挡腮帮，弱化方角", "韩系氛围", "日常", 2, "否",
             "颧骨到下颌留碎发，刘海八字外扩", "方脸 龙须 八字刘海"),
            ("渐变undercut（男）", "两侧推短上留长度，干净利落又不强调方颌", "潮男利落", "上班/社交", 2, "否",
             "两侧 3mm 渐变，顶部留 4-6cm 向前梳", "方脸 渐变 undercut"),
        ],
        "avoid": ["齐耳一刀切（水平线强调下颌）", "贴脸直发无层次（暴露轮廓）", "极短寸头（全露方颌）"],
    },
    "长": {
        "faceRead": "长脸——纵向比例长，核心是「缩短视觉 + 增加横向量」",
        "recs": [
            ("空气刘海 / 齐刘海", "用刘海截断过长比例，立刻显脸短", "甜美减龄", "日常/约会", 2, "否",
             "刘海到眉上，蓬松不贴额，两侧留厚度", "长脸 空气刘海 减龄"),
            ("羊毛卷 / 蛋卷头", "整体增加横向体积，平衡长脸", "复古俏皮", "拍照/社交", 4, "可选",
             "小卷从耳下开始，头顶蓬松", "长脸 羊毛卷 显脸短"),
            ("层次锁骨发带鬓角", "鬓角碎发加宽太阳穴，缩短视觉长度", "通勤文艺", "上班/日常", 3, "否",
             "太阳穴到颧骨留鬓角碎发，发尾微卷", "长脸 鬓角 锁骨发"),
        ],
        "avoid": ["大背头无刘海（更显长）", "超长直发无层次（拉长）", "中分贴脸（露出全脸长度）"],
    },
    "鹅蛋": {
        "faceRead": "鹅蛋脸——比例均衡、可塑性最高，几乎不挑发型，按风格选即可",
        "recs": [
            ("锁骨发（万能）", "长度适中、可盐可甜，最容易打理出彩", "通勤百搭", "全场景", 2, "否",
             "发尾微层次，可直可卷", "鹅蛋脸 锁骨发 万能"),
            ("法式刘海 + 微卷", "增加氛围感，显脸小又不挑人", "法式浪漫", "约会/拍照", 3, "可选",
             "刘海轻薄带弧度，发尾大卷", "鹅蛋脸 法式 微卷"),
            ("一刀切直发", "利落高级，鹅蛋脸撑得住直线条", "高级极简", "上班/社交", 2, "否",
             "齐平发尾，发质要好才显质感", "鹅蛋脸 一刀切 直发"),
        ],
        "avoid": ["几乎不挑，但避免完全贴头皮显脸长"],
    },
}
_DEFAULT_FACE = {
    "faceRead": "未提供脸型——按「百搭、好打理、不易翻车」给三个安全选项",
    "recs": [
        ("锁骨发（微层次）", "长度安全、不挑脸型，微层次显发量", "通勤百搭", "全场景", 2, "否",
         "发尾微层次，避免齐平显呆", "安全 锁骨发 微层次"),
        ("侧分纹理短发", "侧分显精神、两侧收薄不显头大", "利落通勤", "上班", 2, "否",
         "顶部吹蓬，两侧去量", "侧分 纹理 短发"),
        ("空气刘海 + 微卷", "减龄且有氛围感，容错率高", "甜美日常", "日常/约会", 3, "否",
         "刘海蓬松不过眉，发尾微卷", "空气刘海 微卷"),
    ],
    "avoid": ["未定脸型前不建议一刀切/超短，容易翻车"],
}


def _build_input_text(ctx: AgentContext) -> str:
    lines = []
    mapping = [
        ("gender", "性别"), ("face_shape", "脸型"), ("age_group", "年龄/身份"),
        ("hair_type", "发质发量"), ("style", "日常风格"), ("changeable", "改造接受度"),
        ("preference", "偏好/目标"),
    ]
    for k, label in mapping:
        v = ctx.get(k)
        if v:
            lines.append(f"{label}：{v}")
    if not lines:
        return "（用户未提供具体特征，请按通用情况推荐安全、好打理、不易翻车的发型）"
    return "\n".join(lines)


class BarberAgent(AbstractAgent):
    name = "barber"

    def __init__(self) -> None:
        super().__init__()
        self.llm = get_provider()

    def _run(self, ctx: AgentContext) -> AgentContext:
        info = _build_input_text(ctx)
        prompt = (
            f"【用户特征】\n{info}\n\n"
            "请为这个人推荐 3 个适合的发型，每个带推荐理由，并给出脸型诊断、避雷清单、"
            "给理发师的沟通话术、维持建议。"
        )
        try:
            raw = self.llm.chat(_SYSTEM_PROMPT, prompt)
            data = json.loads(extract_json(raw))
            recs = data.get("recommendations") or []
        except Exception as e:
            self.log.warning("[barber] LLM 失败，走启发式兜底: %s", e)
            data, recs = self._heuristic(ctx)

        # 兜底字段 + 归一化 recommendations
        recs = [self._norm_rec(r) for r in recs] or [self._norm_rec(r) for r in data.get("recommendations", [])]
        data["recommendations"] = recs[:3] if recs else [self._norm_rec(r) for r in _DEFAULT_FACE["recs"]]

        data.setdefault("faceRead", _DEFAULT_FACE["faceRead"])
        data.setdefault("avoid", data.get("avoid") or _DEFAULT_FACE["avoid"])
        data.setdefault("stylistScript", "建议当面告诉理发师：长度、层次、刘海、厚度四个维度各要什么，避免只说「修一下」")
        data.setdefault("maintain", "一般 4-6 周修剪一次；日常用吹风机+定型产品维持形状")

        return (ctx.put("faceRead", data["faceRead"])
                   .put("recommendations", data["recommendations"])
                   .put("avoid", data["avoid"])
                   .put("stylistScript", data["stylistScript"])
                   .put("maintain", data["maintain"]))

    @staticmethod
    def _norm_rec(r: dict) -> dict:
        r = r or {}
        return {
            "name": r.get("name", "推荐发型"),
            "why": r.get("why", "结合你的特征，整体协调显气质"),
            "style": r.get("style", "百搭"),
            "scene": r.get("scene", "日常"),
            "difficulty": int(r.get("difficulty", 2) or 2),
            "needsColor": r.get("needsColor", "否"),
            "cut": r.get("cut", "按脸型留层次"),
            "ref": r.get("ref", ""),
        }

    def _heuristic(self, ctx: AgentContext):
        face = (ctx.get("face_shape") or "未知")
        block = _FALLBACK_BY_FACE.get(face, _DEFAULT_FACE)
        recs = [
            {
                "name": n, "why": why, "style": st, "scene": sc,
                "difficulty": dif, "needsColor": nc, "cut": cut, "ref": ref,
            }
            for (n, why, st, sc, dif, nc, cut, ref) in block["recs"]
        ]
        return {"faceRead": block["faceRead"], "recommendations": recs, "avoid": block["avoid"]}, recs
