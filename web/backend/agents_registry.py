"""AI 超市 · Agent 注册表（货架的单一事实源）。

所有可上架的 Agent 都在这里声明：元数据 + 输入字段 schema + 套餐层级 + 处理器类型。
- handler="video"  → 复用口播视频工坊流程（真实生成 9:16 视频）
- handler="llm"    → 通用大模型调用（选题/脚本/客服/财税/交付/复盘等纯文本 Agent，真实输出）
- handler="scaffold" → 脚手架 Agent，返回"待交付"提示（仅 publish 抖音开放平台接口待接入）

套餐：free < pro < enterprise，决定客户能用哪些 Agent。
新增 Agent = 在这里加一条 + （如需要）在 main.py 的 _run_llm / _run_video 里接逻辑。
"""

# 套餐 → 可用 Agent 集合（权限壳的核心）
PLANS = {
    "free": {"video", "topic"},
    "pro": {"video", "topic", "script", "publish", "service", "finance"},
    "enterprise": {"video", "topic", "script", "publish", "service", "finance", "delivery", "analytics"},
}

PLAN_ORDER = ["free", "pro", "enterprise"]


# Agent 清单。input_schema 字段：key/label/type(text|textarea|select|file)/options/required
AGENTS = [
    {
        "id": "video",
        "name": "口播视频生成",
        "icon": "🎬",
        "category": "内容生产",
        "description": "上传人物图 + 口播稿，生成 9:16 竖版短视频（本地 fallback / 百炼逼真数字人）",
        "tier": "free",
        "handler": "video",
        "input_schema": [
            {"key": "image", "label": "人物图片", "type": "file", "required": True},
            {"key": "script", "label": "口播稿", "type": "textarea", "required": True},
            {"key": "voice", "label": "音色", "type": "select",
             "options": ["zh-CN-XiaoxiaoNeural", "zh-CN-YunxiNeural", "zh-CN-YunyangNeural"], "required": False},
            {"key": "provider", "label": "生成引擎", "type": "select",
             "options": ["local", "bailian"], "required": False},
        ],
    },
    {
        "id": "topic",
        "name": "爆款选题",
        "icon": "💡",
        "category": "内容生产",
        "description": "根据行业/关键词，产出有钩子、可变现的抖音短视频选题",
        "tier": "free",
        "handler": "llm",
        "system_prompt": "你是抖音爆款选题专家。根据用户给的行业/关键词与目标，产出 5 个有强钩子、可变现的短视频选题，"
                        "每条包含：标题、角度、预期人群、为什么能火。语言口语化、接地气。",
        "input_schema": [
            {"key": "niche", "label": "行业 / 关键词", "type": "text", "required": True},
            {"key": "goal", "label": "目标（涨粉/引流/变现）", "type": "text", "required": False},
        ],
    },
    {
        "id": "script",
        "name": "口播脚本",
        "icon": "📝",
        "category": "内容生产",
        "description": "给选题/要点，写 30-50 秒口播脚本（强钩子开头 + 反转 + 结尾引导）",
        "tier": "pro",
        "handler": "llm",
        "system_prompt": "你是短视频口播脚本专家。根据用户给的选题或要点，写一份 30-50 秒口播脚本，"
                        "结构：0-3 秒强钩子、中间反转/干货、结尾引导关注。台词自然、像真人说话。",
        "input_schema": [
            {"key": "topic", "label": "选题 / 要点", "type": "textarea", "required": True},
        ],
    },
    {
        "id": "publish",
        "name": "抖音发布",
        "icon": "📤",
        "category": "内容生产",
        "description": "将成片发布到抖音开放平台（接口待接入）",
        "tier": "pro",
        "handler": "scaffold",
        "input_schema": [
            {"key": "video_path", "label": "成片路径", "type": "text", "required": True},
            {"key": "title", "label": "发布标题", "type": "text", "required": False},
        ],
    },
    {
        "id": "service",
        "name": "私域承接客服",
        "icon": "🤝",
        "category": "专业服务",
        "description": "根据客户留言/线索，给出承接话术与跟进建议（AI 获客代运营）",
        "tier": "pro",
        "handler": "llm",
        "system_prompt": "你是 AI 获客代运营客服专家。根据用户提供的客户留言或线索，给出：①承接话术 ②跟进节奏建议 "
                        "③转化动作。语气专业、可信、不夸大。",
        "input_schema": [
            {"key": "lead", "label": "客户留言 / 线索", "type": "textarea", "required": True},
        ],
    },
    {
        "id": "finance",
        "name": "财税专家",
        "icon": "🧾",
        "category": "专业服务",
        "description": "中小企业财税顾问：合规、可操作的财税建议（示例专业服务类 Agent）",
        "tier": "pro",
        "handler": "llm",
        "system_prompt": "你是中小企业财税顾问。根据用户的问题与背景数据，给出合规、可操作的财税建议；"
                        "涉及具体金额或税率时，必须提示『以最新政策与主管税务机关为准』，不代替专业会计师意见。",
        "input_schema": [
            {"key": "question", "label": "财税问题", "type": "textarea", "required": True},
            {"key": "context", "label": "补充信息（行业/规模）", "type": "text", "required": False},
        ],
    },
    {
        "id": "delivery",
        "name": "交付调度",
        "icon": "📦",
        "category": "专业服务",
        "description": "把订单/需求拆成可执行交付 SOP：交付物清单、步骤、角色、工期、验收标准",
        "tier": "enterprise",
        "handler": "llm",
        "system_prompt": "你是 AI 获客代运营的交付调度专家。根据用户给的订单/需求（数字人视频/代运营/写真/Agent 搭建等），"
                        "输出一份可执行交付 SOP：交付物清单、执行步骤（含角色与工期）、验收标准。"
                        "只返回 JSON：{type, deliverables:[], steps:[{step,owner,days}], acceptance:[], total_days}",
        "input_schema": [
            {"key": "order", "label": "订单/需求", "type": "textarea", "required": True},
        ],
    },
    {
        "id": "analytics",
        "name": "数据复盘",
        "icon": "📊",
        "category": "专业服务",
        "description": "看播放/转化/互动，产出复盘结论并反哺下一期选题与脚本权重",
        "tier": "enterprise",
        "handler": "llm",
        "system_prompt": "你是短视频数据复盘专家。根据给出的播放/转化/互动等数据，输出复盘结论："
                        "核心指标解读、亮点、问题、对下一期选题与脚本权重的建议。"
                        "只返回 JSON：{summary, highlights:[], issues:[], next_actions:[{area, action, weight}]}",
        "input_schema": [
            {"key": "metrics", "label": "数据（播放/转化等）", "type": "textarea", "required": True},
        ],
    },
]


def get_agent(agent_id: str):
    for a in AGENTS:
        if a["id"] == agent_id:
            return a
    return None


def get_shelf(plan: str) -> list:
    """返回货架：每个 Agent 标注 locked（该套餐不可用）与 required_plan。"""
    shelf = []
    for a in AGENTS:
        allowed = a["id"] in PLANS.get(plan, set())
        shelf.append({
            **a,
            "locked": not allowed,
            "required_plan": a["tier"] if not allowed else None,
        })
    return shelf
