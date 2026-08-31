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


class Customer(Base):
    """超市客户（套餐/权限壳的基础）。每个客户有套餐，决定能用的 Agent 集合。"""

    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    plan = Column(String(32), default="free")  # free / pro / enterprise
    api_key = Column(String(128), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
