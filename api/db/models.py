"""SQLAlchemy 2.0 mapped siniflari -- infra/postgres/init.sql'in birebir
karsiligi (docs/PLAN.md SS6.1). create_all() COAGRILMAZ: tablolari init.sql
yaratir, burasi yalnizca var olan semayi tarif eder (ASAMA5_PLAN.md SS2).
Sema kaymasini yakalayan koruma tests/test_schema_sync.py'dedir (bu aşamanin
disinda, ikinci ajan yazacak).
"""

from __future__ import annotations

import datetime

from sqlalchemy import ARRAY, BigInteger, Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, Time, func
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20), default="viewer")
    telegram_chat_id: Mapped[str | None] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    # server_default: ORM unset birakinca DB'nin kendi DEFAULT now()'i uygulanir
    # (server_default olmadan SQLAlchemy acikca NULL gonderir, NOT NULL'i kirar).
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Camera(Base):
    __tablename__ = "cameras"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    source: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(20))
    location: Mapped[str | None] = mapped_column(String(150))
    width: Mapped[int] = mapped_column(Integer, default=960)
    height: Mapped[int] = mapped_column(Integer, default=540)
    target_fps: Mapped[int] = mapped_column(Integer, default=25)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(20), default="offline")
    last_seen_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    # server_default: ORM unset birakinca DB'nin kendi DEFAULT now()'i uygulanir
    # (server_default olmadan SQLAlchemy acikca NULL gonderir, NOT NULL'i kirar).
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Zone(Base):
    __tablename__ = "zones"

    id: Mapped[int] = mapped_column(primary_key=True)
    camera_id: Mapped[int] = mapped_column(ForeignKey("cameras.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    zone_type: Mapped[str] = mapped_column(String(30))
    polygon: Mapped[list] = mapped_column(JSONB)                       # [[x,y], ...] 0-1 normalize
    direction_vector: Mapped[list | None] = mapped_column(JSONB)       # [dx,dy]
    active_from: Mapped[datetime.time | None] = mapped_column(Time)
    active_to: Mapped[datetime.time | None] = mapped_column(Time)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # server_default: ORM unset birakinca DB'nin kendi DEFAULT now()'i uygulanir
    # (server_default olmadan SQLAlchemy acikca NULL gonderir, NOT NULL'i kirar).
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DetectionSettings(Base):
    """vision/rules/engine.py Thresholds ile birebir tutulur (esik alanlari)."""

    __tablename__ = "detection_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    camera_id: Mapped[int | None] = mapped_column(ForeignKey("cameras.id", ondelete="CASCADE"), unique=True)
    pose_conf: Mapped[float] = mapped_column(Numeric(3, 2, asdecimal=False))
    track_conf: Mapped[float] = mapped_column(Numeric(3, 2, asdecimal=False))
    fall_tilt_deg: Mapped[float] = mapped_column(Numeric(5, 2, asdecimal=False))
    fall_norm_vy: Mapped[float] = mapped_column(Numeric(6, 3, asdecimal=False))
    run_norm_speed: Mapped[float] = mapped_column(Numeric(6, 3, asdecimal=False))
    run_gait_speed: Mapped[float] = mapped_column(Numeric(6, 3, asdecimal=False))
    loiter_sec: Mapped[int] = mapped_column(Integer)
    fight_proximity: Mapped[float] = mapped_column(Numeric(4, 2, asdecimal=False))
    window_frames: Mapped[int] = mapped_column(Integer)
    spark_window_sec: Mapped[int] = mapped_column(Integer)
    spark_min_hits: Mapped[int] = mapped_column(Integer)
    spark_min_sec: Mapped[dict] = mapped_column(JSONB)
    tcn_min_conf: Mapped[float] = mapped_column(Numeric(3, 2, asdecimal=False))
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    camera_id: Mapped[int] = mapped_column(ForeignKey("cameras.id", ondelete="CASCADE"))
    zone_id: Mapped[int | None] = mapped_column(ForeignKey("zones.id", ondelete="SET NULL"))
    anomaly_type: Mapped[str] = mapped_column(String(30))
    track_ids: Mapped[list[int]] = mapped_column(ARRAY(Integer))
    confidence: Mapped[float] = mapped_column(Numeric(4, 3, asdecimal=False))
    severity: Mapped[str] = mapped_column(String(10))
    decided_by: Mapped[str] = mapped_column(String(10))                # rule / model / hybrid -- ablation kaynagi
    started_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    frame_path: Mapped[str | None] = mapped_column(Text)
    clip_path: Mapped[str | None] = mapped_column(Text)
    llm_report_tr: Mapped[str | None] = mapped_column(Text)
    mongo_ref: Mapped[str | None] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(20), default="new")
    acked_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    acked_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    # server_default: ORM unset birakinca DB'nin kendi DEFAULT now()'i uygulanir
    # (server_default olmadan SQLAlchemy acikca NULL gonderir, NOT NULL'i kirar).
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Evidence(Base):
    """vision/ epizot kapanisinda POST /api/evidence ile yazar. event_id NULL
    = henuz eslesmemis (ASAMA6_PLAN.md SS8.2)."""

    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    event_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("events.id", ondelete="CASCADE"))
    camera_id: Mapped[int] = mapped_column(ForeignKey("cameras.id", ondelete="CASCADE"))
    anomaly_type: Mapped[str] = mapped_column(String(30))
    track_key: Mapped[str] = mapped_column(String(50))
    started_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    frame_path: Mapped[str | None] = mapped_column(Text)
    clip_path: Mapped[str | None] = mapped_column(Text)
    clip_truncated: Mapped[bool] = mapped_column(Boolean, default=False)
    mongo_ref: Mapped[str | None] = mapped_column(String(24))
    # server_default: ORM unset birakinca DB'nin kendi DEFAULT now()'i uygulanir
    # (server_default olmadan SQLAlchemy acikca NULL gonderir, NOT NULL'i kirar).
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    event_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("events.id", ondelete="CASCADE"))
    channel: Mapped[str] = mapped_column(String(20))
    target: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(10))
    error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(50))
    entity: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[int | None] = mapped_column(BigInteger)
    payload: Mapped[dict | None] = mapped_column(JSONB)
    ip: Mapped[str | None] = mapped_column(INET)
    # server_default: ORM unset birakinca DB'nin kendi DEFAULT now()'i uygulanir
    # (server_default olmadan SQLAlchemy acikca NULL gonderir, NOT NULL'i kirar).
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
