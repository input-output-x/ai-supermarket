import os
import sys
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, UploadFile, Depends, HTTPException, BackgroundTasks, Header, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from database import engine, Base, get_db, SessionLocal
from models import VideoJob, Customer, UsageRecord, PlanOrder
from schemas import VideoOut
from video_engine import get_provider
from agents_registry import AGENTS, PLANS, get_agent, get_shelf, get_quota
from billing import list_plans, PLAN_PRICES, get_provider as get_pay_provider

# 让 web 后端能复用核心包的 LLM 能力（Deepseek 等真实大模型）
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from ai_supermarket.core.llm import get_provider as get_llm_provider  # noqa: E402
from ai_supermarket.core.context import AgentContext  # noqa: E402
from ai_supermarket.agents.publish import PublishAgent, DouyinClient  # noqa: E402
# AGENTS/PLANS/get_agent/get_shelf/get_quota 已在上文 line 17 导入，无需重复

Base.metadata.create_all(bind=engine)


def _seed_customers():
    """首次启动播种演示客户（不同套餐），便于体验权限壳。"""
    db = SessionLocal()
    try:
        if db.query(Customer).count() == 0:
            demos = [
                Customer(name="免费体验客户", plan="free", api_key="sk-free-demo-2026"),
                Customer(name="专业版客户", plan="pro", api_key="sk-pro-demo-2026"),
                Customer(name="企业版客户", plan="enterprise", api_key="sk-ent-demo-2026"),
            ]
            db.add_all(demos)
            db.commit()
            print("[seed] 已创建演示客户：free / pro / enterprise")
    finally:
        db.close()


_seed_customers()

app = FastAPI(title="AI 超市 · 口播视频工坊", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ROOT = Path(__file__).parent
STORAGE = ROOT / "storage"
UPLOADS = STORAGE / "uploads"
VIDEOS = STORAGE / "videos"

UPLOADS.mkdir(parents=True, exist_ok=True)
VIDEOS.mkdir(parents=True, exist_ok=True)


def _process_job(job_id: int, image_path: str, script: str, voice: str, provider_name: str):
    from sqlalchemy.orm import Session as Sess
    from database import SessionLocal
    db = SessionLocal()
    try:
        job = db.query(VideoJob).get(job_id)
        if not job:
            return
        job.status = "doing"
        db.commit()
        try:
            provider = get_provider(provider_name)
            result = provider.generate(str(job_id), image_path, script, voice, VIDEOS)
            job.video_path = result.get("video_path")
            job.audio_path = result.get("audio_path")
            job.cover_path = result.get("cover_path")
            job.message = result.get("message")
            job.status = "done" if result.get("video_path") else "failed"
        except Exception as e:
            job.status = "failed"
            job.message = str(e)
        db.commit()
    finally:
        db.close()


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    return {"ok": True}


@app.get("/api/videos", response_model=list[VideoOut])
def list_videos(skip: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    return db.query(VideoJob).order_by(VideoJob.id.desc()).offset(skip).limit(limit).all()


@app.get("/api/videos/{job_id}", response_model=VideoOut)
def get_video(job_id: int, db: Session = Depends(get_db)):
    job = db.query(VideoJob).get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job


def _make_video_job(db: Session, image_bytes: bytes, filename: str, script: str, voice: str, provider: str, title: Optional[str] = None):
    """创建视频生成任务（口播工坊与货架共用）。返回 (job, image_path)。"""
    if not script.strip():
        raise HTTPException(status_code=400, detail="script is empty")
    ext = Path(filename or "upload.jpg").suffix.lower() or ".jpg"
    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
        raise HTTPException(status_code=400, detail="unsupported image format")
    safe_name = f"{int(time.time() * 1000)}{ext}"
    image_path = UPLOADS / safe_name
    image_path.write_bytes(image_bytes)
    job = VideoJob(
        title=title or script[:30],
        script=script,
        voice=voice,
        provider=provider or "local",
        status="pending",
        image_path=str(image_path),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job, str(image_path)


@app.post("/api/videos", response_model=VideoOut)
def create_video(
    background_tasks: BackgroundTasks,
    script: str = Form(...),
    voice: str = Form("zh-CN-XiaoxiaoNeural"),
    title: Optional[str] = Form(None),
    provider: Optional[str] = Form("local"),
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    job, image_path = _make_video_job(db, image.file.read(), image.filename or "upload.jpg", script, voice, provider or "local", title)
    background_tasks.add_task(_process_job, job.id, image_path, script, voice, provider or "local")
    return job


@app.get("/api/videos/{job_id}/download")
def download_video(job_id: int, type: str = "video", db: Session = Depends(get_db)):
    job = db.query(VideoJob).get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    field = {"video": job.video_path, "audio": job.audio_path, "cover": job.cover_path}.get(type)
    if not field or not Path(field).exists():
        raise HTTPException(status_code=404, detail="file not ready")
    from fastapi.responses import FileResponse
    return FileResponse(field, filename=f"{job_id}_{type}{Path(field).suffix}")


# ---------- AI 超市 · 货架 / 套餐权限壳 ----------

def get_customer(api_key: Optional[str] = Header(None, alias="X-API-Key"), db: Session = Depends(get_db)) -> Customer:
    """解析当前客户（按 X-API-Key）。未带/找不到 → 默认免费套餐（匿名体验）。"""
    if api_key:
        c = db.query(Customer).filter(Customer.api_key == api_key).first()
        if c:
            return c
    return Customer(name="匿名", plan="free", api_key="")


def _count_usage(db: Session, customer: Customer) -> int:
    return db.query(UsageRecord).filter(UsageRecord.customer_id == customer.id).count()


def _record_usage(db: Session, customer: Customer, agent_id: str) -> None:
    db.add(UsageRecord(customer_id=customer.id, agent_id=agent_id))
    db.commit()


@app.get("/api/agents")
def list_agents(customer: Customer = Depends(get_customer), db: Session = Depends(get_db)):
    """货架：按当前客户套餐返回 Agent 列表，标注 locked / required_plan 与额度。"""
    limit = get_quota(customer.plan)
    used = _count_usage(db, customer)
    return {
        "plan": customer.plan,
        "customer": customer.name,
        "quota": {
            "limit": limit,
            "used": used,
            "remaining": None if limit is None else max(limit - used, 0),
        },
        "agents": get_shelf(customer.plan),
    }


@app.get("/api/usage")
def usage(customer: Customer = Depends(get_customer), db: Session = Depends(get_db)):
    """当前客户的使用计量：总额度/已用/剩余 + 按 Agent 分布。"""
    limit = get_quota(customer.plan)
    rows = db.query(UsageRecord).filter(UsageRecord.customer_id == customer.id).all()
    by_agent = {}
    for r in rows:
        by_agent[r.agent_id] = by_agent.get(r.agent_id, 0) + 1
    used = len(rows)
    return {
        "plan": customer.plan,
        "limit": limit,
        "used": used,
        "remaining": None if limit is None else max(limit - used, 0),
        "by_agent": by_agent,
    }


# ---------- AI 超市 · 计费 / 支付 ----------

@app.get("/api/billing/plans")
def billing_plans():
    """套餐与价格列表（前端升级页用）。"""
    return {"plans": list_plans(), "currency": "cny"}


@app.post("/api/billing/checkout")
async def billing_checkout(request: Request, customer: Customer = Depends(get_customer), db: Session = Depends(get_db)):
    """创建升级结账会话。Stripe 返回托管结账页 URL；未配置凭证则返回清晰提示。"""
    data = await request.json()
    plan = data.get("plan")
    provider = data.get("provider", "stripe")
    if plan not in PLANS:  # 仅允许已知套餐
        raise HTTPException(status_code=400, detail="未知套餐")
    if plan == customer.plan:
        raise HTTPException(status_code=400, detail=f"当前已是 {plan} 套餐")
    pay = get_pay_provider(provider)
    if not pay.is_configured():
        return {"status": "unconfigured", "provider": provider,
                "message": f"未配置 {provider} 支付凭证（参考 .env.example）"}
    base = os.getenv("PUBLIC_BASE_URL", str(request.base_url).rstrip("/"))
    success_url = f"{base}/#/billing?result=success"
    cancel_url = f"{base}/#/billing?result=cancel"
    res = pay.create_checkout(customer.api_key, plan, success_url, cancel_url)
    if res.get("status") == "ok":
        db.add(PlanOrder(customer_id=customer.id, plan=plan, provider=provider,
                         amount_cents=PLAN_PRICES.get(plan, 0), status="pending",
                         session_id=res.get("session_id")))
        db.commit()
        return {"status": "ok", "provider": provider, "url": res["url"]}
    return {"status": res.get("status", "error"), "provider": provider, "message": res.get("message")}


@app.post("/api/billing/webhook/stripe")
async def billing_webhook_stripe(request: Request, db: Session = Depends(get_db)):
    """Stripe 支付成功回调：校验签名 → 升级客户套餐 + 重置额度。"""
    payload = await request.body()
    sig = request.headers.get("Stripe-Signature", "")
    pay = get_pay_provider("stripe")
    event = pay.verify_webhook(payload, sig)
    if event is None:
        raise HTTPException(status_code=400, detail="签名校验失败")
    plan, api_key = pay.parse_paid_plan(event)
    if not plan or not api_key:
        return {"received": True, "ignored": True}
    cust = db.query(Customer).filter(Customer.api_key == api_key).first()
    if not cust:
        return {"received": True, "unknown_customer": True}
    # 升级套餐 + 重置额度（新计费周期）
    cust.plan = plan
    db.query(UsageRecord).filter(UsageRecord.customer_id == cust.id).delete()
    order = db.query(PlanOrder).filter(
        PlanOrder.customer_id == cust.id, PlanOrder.plan == plan, PlanOrder.status == "pending"
    ).order_by(PlanOrder.id.desc()).first()
    if order:
        order.status = "paid"
        order.paid_at = datetime.datetime.utcnow()
    db.commit()
    return {"received": True, "upgraded": plan, "customer": cust.name}


def _build_llm_prompt(agent: dict, data: dict) -> str:
    parts = []
    for sch in agent.get("input_schema", []):
        val = data.get(sch["key"])
        if val:
            parts.append(f"{sch['label']}：{val}")
    return "\n".join(parts) or "（用户未填写输入）"


@app.post("/api/agents/{agent_id}/run")
async def run_agent(agent_id: str, request: Request, customer: Customer = Depends(get_customer), db: Session = Depends(get_db)):
    agent = get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="agent not found")
    if agent_id not in PLANS.get(customer.plan, set()):
        raise HTTPException(status_code=403, detail=f"当前套餐({customer.plan})不可用该 Agent，需 {agent['tier']} 套餐")

    # 额度计量：超限拦截（enterprise 为 None=不限）
    limit = get_quota(customer.plan)
    used = _count_usage(db, customer)
    if limit is not None and used >= limit:
        raise HTTPException(status_code=403, detail=f"套餐({customer.plan})调用额度已用尽 {used}/{limit}，请升级套餐或联系管理员")

    handler = agent["handler"]
    ctype = request.headers.get("content-type", "")

    # 记录一次使用（所有 handler 统一计量）
    _record_usage(db, customer, agent_id)

    if handler == "video":
        form = await request.form()
        image = form.get("image")
        if not getattr(image, "file", None):
            raise HTTPException(status_code=400, detail="video agent 需要 image 文件")
        script = form.get("script") or ""
        voice = form.get("voice") or "zh-CN-XiaoxiaoNeural"
        provider = form.get("provider") or "local"
        job, image_path = _make_video_job(db, image.file.read(), image.filename or "upload.jpg", script, voice, provider)
        background_tasks = BackgroundTasks()
        background_tasks.add_task(_process_job, job.id, image_path, script, voice, provider)
        return {"agent": agent_id, "kind": "video", "job_id": job.id, "status": "pending",
                "message": "视频生成中，可在『口播视频工坊』或轮询 /api/videos/{id} 查看"}

    if handler == "scaffold":
        return {"agent": agent_id, "kind": "scaffold", "result": "该 Agent 为脚手架，待交付（你说『交付』后实现真实逻辑）"}

    if handler == "llm":
        if "multipart" in ctype:
            form = await request.form()
            data = {k: (form.getlist(k) if isinstance(form.get(k), list) else form.get(k)) for k in form.keys()}
        else:
            data = await request.json()
        user_prompt = _build_llm_prompt(agent, data)
        try:
            result = get_llm_provider().chat(agent["system_prompt"], user_prompt)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"LLM 调用失败：{e}")
        return {"agent": agent_id, "kind": "llm", "result": result}

    if handler == "publish":
        if "multipart" in ctype:
            form = await request.form()
            data = {k: form.get(k) for k in form.keys()}
        else:
            data = await request.json()
        pub = PublishAgent()
        ctx = pub.execute(AgentContext({
            "video_path": data.get("video_path"),
            "title": data.get("title"),
            "topicTitle": data.get("title"),
        }))
        return {
            "agent": agent_id,
            "kind": "publish",
            "result": {
                "titleCandidates": ctx.get("titleCandidates"),
                "hashtags": ctx.get("hashtags"),
                "publishResult": ctx.get("publishResult"),
            },
        }

    raise HTTPException(status_code=500, detail="unknown handler")


# 抖音开放平台 OAuth：授权链接 + 用 code 换 token（publish Agent 真实对接入口）
@app.get("/api/agents/publish/auth")
def publish_auth_url(customer: Customer = Depends(get_customer)):
    cli = DouyinClient()
    if not cli.is_configured():
        raise HTTPException(status_code=400, detail="未配置 DOUYIN_CLIENT_KEY/SECRET")
    return {"authorize_url": cli.authorize_url() or "（请先设置 DOUYIN_REDIRECT_URI）"}


@app.post("/api/agents/publish/exchange")
async def publish_exchange(request: Request, customer: Customer = Depends(get_customer)):
    if "publish" not in PLANS.get(customer.plan, set()):
        raise HTTPException(status_code=403, detail=f"当前套餐({customer.plan})不可用该 Agent")
    data = await request.json()
    code = data.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="缺少 code")
    cli = DouyinClient()
    if not cli.is_configured():
        raise HTTPException(status_code=400, detail="未配置 DOUYIN_CLIENT_KEY/SECRET")
    try:
        resp = cli.exchange_code(code)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"换码失败：{e}")
    d = resp.get("data") or {}
    return {
        "access_token": d.get("access_token"),
        "open_id": d.get("open_id"),
        "expires_in": d.get("expires_in"),
        "hint": "将这两个值分别写入环境变量 DOUYIN_ACCESS_TOKEN / DOUYIN_OPEN_ID 后重启服务即可发布。",
    }


# 静态文件：生成的视频可直接访问
app.mount("/videos", StaticFiles(directory=VIDEOS), name="videos")
app.mount("/uploads", StaticFiles(directory=UPLOADS), name="uploads")
