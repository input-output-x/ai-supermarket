import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime
from database import Base


class VideoJob(Base):
    __tablename__ = "video_jobs"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=True)
    script = Column(Text, nullable=False)
    voice = Column(String(64), default="zh-CN-XiaoxiaoNeural")
    provider = Column(String(32), default="local")
    status = Column(String(16), default="pending")  # pending / doing / done / failed
    image_path = Column(String(512), nullable=False)
    audio_path = Column(String(512), nullable=True)
    video_path = Column(String(512), nullable=True)
    cover_path = Column(String(512), nullable=True)
    message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
