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


class UsageRecord(Base):
    """客户使用计量：每次调用某 Agent 记一条（收费/额度基础）。"""

    __tablename__ = "usage_records"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, index=True, nullable=False)
    agent_id = Column(String(64), index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class PlanOrder(Base):
    """套餐订单（计费/支付记录）。支付成功 → 升级客户套餐 + 重置额度。"""

    __tablename__ = "plan_orders"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, index=True, nullable=False)
    plan = Column(String(32), nullable=False)          # 目标套餐
    provider = Column(String(32), default="stripe")    # stripe / wechat
    amount_cents = Column(Integer, default=0)
    status = Column(String(16), default="pending")     # pending / paid / failed
    session_id = Column(String(255), nullable=True)    # 支付方会话 ID
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    paid_at = Column(DateTime, nullable=True)
