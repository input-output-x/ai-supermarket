from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class VideoCreate(BaseModel):
    script: str
    voice: str = "zh-CN-XiaoxiaoNeural"
    title: Optional[str] = None


class VideoOut(BaseModel):
    id: int
    title: Optional[str]
    script: str
    voice: str
    provider: str
    status: str
    image_path: str
    audio_path: Optional[str]
    video_path: Optional[str]
    cover_path: Optional[str]
    message: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
