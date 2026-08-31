import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, UploadFile, Depends, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from database import engine, Base, get_db
from models import VideoJob
from schemas import VideoOut
from video_engine import get_provider

Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI 口播视频工坊", version="0.1.0")

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
    if not script.strip():
        raise HTTPException(status_code=400, detail="script is empty")
    ext = Path(image.filename or "upload.jpg").suffix.lower() or ".jpg"
    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
        raise HTTPException(status_code=400, detail="unsupported image format")
    safe_name = f"{int(__import__('time').time()*1000)}{ext}"
    image_path = UPLOADS / safe_name
    with open(image_path, "wb") as f:
        f.write(image.file.read())

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

    background_tasks.add_task(_process_job, job.id, str(image_path), script, voice, provider or "local")
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


# 静态文件：生成的视频可直接访问
app.mount("/videos", StaticFiles(directory=VIDEOS), name="videos")
app.mount("/uploads", StaticFiles(directory=UPLOADS), name="uploads")
