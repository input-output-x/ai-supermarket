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
from models import VideoJob, Customer
from schemas import VideoOut
from video_engine import get_provider

# 让 web 后端能复用核心包的 LLM 能力（Deepseek 等真实大模型）
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from ai_supermarket.core.llm import get_provider as get_llm_provider  # noqa: E402
from agents_registry import AGENTS, PLANS, get_agent, get_shelf  # noqa: E402

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


@app.get("/api/agents")
def list_agents(customer: Customer = Depends(get_customer)):
    """货架：按当前客户套餐返回 Agent 列表，标注 locked / required_plan。"""
    return {
        "plan": customer.plan,
        "customer": customer.name,
        "agents": get_shelf(customer.plan),
    }


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

    handler = agent["handler"]
    ctype = request.headers.get("content-type", "")

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

    raise HTTPException(status_code=500, detail="unknown handler")


# 静态文件：生成的视频可直接访问
app.mount("/videos", StaticFiles(directory=VIDEOS), name="videos")
app.mount("/uploads", StaticFiles(directory=UPLOADS), name="uploads")
