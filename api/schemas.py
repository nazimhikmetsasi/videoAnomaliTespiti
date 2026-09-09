"""Istek/yanit govdeleri (pydantic v2). from_attributes=True olanlar
SQLAlchemy ORM nesnesinden dogrudan kurulur (ASAMA5_PLAN.md SS9).
"""

from __future__ import annotations

import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


# --------------------------------------------------------------------- auth
class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str
    role: str
    is_active: bool
    telegram_chat_id: str | None = None
    last_login: datetime.datetime | None = None
    created_at: datetime.datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UserCreate(BaseModel):
    """Sifre hash'i veritabaninda uretilir (crypt()) -- gorunmesi gereken
    tek dogrulanmamis alan `password`, Python tarafinda hic tutulmaz."""

    username: str
    full_name: str
    role: Literal["admin", "operator", "viewer"]
    telegram_chat_id: str | None = None
    is_active: bool = True
    password: str


class UserUpdate(BaseModel):
    """Tum alanlar istege bagli (PATCH semantigi) -- `password` yoksa hash'e
    dokunulmaz (api/routers/users.py)."""

    username: str | None = None
    full_name: str | None = None
    role: Literal["admin", "operator", "viewer"] | None = None
    telegram_chat_id: str | None = None
    is_active: bool | None = None
    password: str | None = None


# -------------------------------------------------------------------- audit
class AuditOut(BaseModel):
    id: int
    user_id: int | None
    username: str | None = None
    action: str
    entity: str
    entity_id: int | None
    payload: dict[str, Any] | None
    ip: str | None
    created_at: datetime.datetime


class AuditListOut(BaseModel):
    total: int
    items: list[AuditOut]


# ------------------------------------------------------------------- health
class CameraHealthOut(BaseModel):
    camera_id: int
    name: str
    fps_actual: float | None = None
    dropped: int | None = None
    infer_ms: float | None = None
    gpu_mem: int | None = None
    queue_depth: int | None = None
    age_sec: float | None = None


# ------------------------------------------------------------------ cameras
class CameraIn(BaseModel):
    name: str
    source: str
    # DB CHECK'ine ikinci kez guvenmek yerine 422 donmek daha okunur (SS9.2)
    source_type: Literal["webcam", "file", "rtsp"]
    location: str | None = None
    width: int = 960
    height: int = 540
    target_fps: int = 25
    is_active: bool = True


class CameraOut(CameraIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    last_seen_at: datetime.datetime | None = None
    created_at: datetime.datetime


class CameraHeartbeatIn(BaseModel):
    status: Literal["online", "offline", "error"]


# -------------------------------------------------------------------- zones
class ZoneIn(BaseModel):
    camera_id: int
    name: str
    zone_type: Literal["forbidden", "restricted_hours", "direction"]
    polygon: list[list[float]]
    direction_vector: list[float] | None = None
    active_from: datetime.time | None = None
    active_to: datetime.time | None = None
    is_active: bool = True

    @field_validator("polygon")
    @classmethod
    def _check_polygon(cls, v: list[list[float]]) -> list[list[float]]:
        # v1'de piksel koordinati gonderilince bolge sessizce kadraj disina
        # dusuyordu (docs/DURUM.md) -- tek dogrulama noktasi burasi (SS9.3)
        if len(v) < 3:
            raise ValueError("poligon en az 3 nokta icermeli")
        for point in v:
            if len(point) != 2:
                raise ValueError("her nokta [x, y] seklinde 2 sayidan olusmali")
            if not (0.0 <= point[0] <= 1.0 and 0.0 <= point[1] <= 1.0):
                raise ValueError("koordinatlar 0.0-1.0 araliginda olmali")
        return v

    @model_validator(mode="after")
    def _check_direction(self) -> "ZoneIn":
        # field_validator("direction_vector", ...) validate_default=False
        # yuzunden alan gonderilmeyip varsayilan None kullanildiginda HIC
        # calismazdi -- model_validator her zaman calisir (SS9.3).
        if self.zone_type == "direction" and self.direction_vector is None:
            raise ValueError("zone_type=direction icin direction_vector zorunlu")
        if self.zone_type != "direction" and self.direction_vector is not None:
            raise ValueError("direction_vector yalnizca zone_type=direction icin gecerli")
        return self


class ZoneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    camera_id: int
    name: str
    zone_type: str
    polygon: list[list[float]]
    direction_vector: list[float] | None = None
    active_from: datetime.time | None = None
    active_to: datetime.time | None = None
    is_active: bool
    created_by: int | None = None
    created_at: datetime.datetime


# ----------------------------------------------------------------- settings
class SettingsIn(BaseModel):
    """vision/rules/engine.py Thresholds + Spark/TCN esikleriyle birebir."""

    pose_conf: float
    track_conf: float
    fall_tilt_deg: float
    fall_norm_vy: float
    run_norm_speed: float
    run_gait_speed: float
    loiter_sec: int
    fight_proximity: float
    window_frames: int
    spark_window_sec: int
    spark_min_hits: int
    spark_min_sec: dict[str, float]
    tcn_min_conf: float


class SettingsPatch(BaseModel):
    """PUT govdesi: TUM alanlar istege baglidir.

    Panel tek bir esigi degistirdiginde (ornegin run_norm_speed) diger 12
    alani geri gondermek zorunda kalmamalidir; gonderilmeyen alan mevcut
    degerinde kalir (model_dump(exclude_unset=True)). Zorunlu tam govde,
    formda dokunulmamis bir alani yanlislikla eski degerine geri yazma
    (lost update) riskini de dogurur.
    """

    pose_conf: float | None = None
    track_conf: float | None = None
    fall_tilt_deg: float | None = None
    fall_norm_vy: float | None = None
    run_norm_speed: float | None = None
    run_gait_speed: float | None = None
    loiter_sec: int | None = None
    fight_proximity: float | None = None
    window_frames: int | None = None
    spark_window_sec: int | None = None
    spark_min_hits: int | None = None
    spark_min_sec: dict[str, float] | None = None
    tcn_min_conf: float | None = None


# settings_client.py bu esikleri pipeline'i yeniden baslatmadan uygular;
# digerleri model/tracker/pencere kurulumunda dondugu icin restart ister (SS7)
RESTART_REQUIRED = ["pose_conf", "track_conf", "window_frames"]


class SettingsOut(SettingsIn):
    camera_id: int | None
    source: Literal["camera", "global"]
    updated_at: datetime.datetime
    restart_required: list[str] = RESTART_REQUIRED


# ------------------------------------------------------------------- events
class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    camera_id: int
    zone_id: int | None
    anomaly_type: str
    track_ids: list[int]
    confidence: float
    severity: str
    decided_by: str
    started_at: datetime.datetime
    ended_at: datetime.datetime | None
    duration_ms: int | None
    frame_path: str | None
    clip_path: str | None
    llm_report_tr: str | None
    mongo_ref: str | None
    status: str
    acked_by: int | None
    acked_at: datetime.datetime | None
    created_at: datetime.datetime


class EventListOut(BaseModel):
    total: int
    items: list[EventOut]


class EventDetailOut(EventOut):
    camera_name: str | None = None
    zone_name: str | None = None
    telemetry: dict[str, Any] | None = None


class EventStatusIn(BaseModel):
    # 'new' kasten yok: bir olay tekrar 'new' yapilamaz (SS9.5)
    status: Literal["acknowledged", "false_positive", "resolved"]


# ------------------------------------------------------------------ evidence
class EvidenceIn(BaseModel):
    """vision/ epizot kapanisinda gonderir (ASAMA6_PLAN.md SS8.1). camera_id
    metin -- Kafka govdesiyle ayni: sayisal id veya kamera adi olabilir."""

    camera_id: str
    anomaly_type: str
    track_key: str
    start_time: float
    end_time: float | None = None
    frame_path: str | None = None
    clip_path: str | None = None
    clip_truncated: bool = False
    mongo_ref: str | None = None


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: int | None
    camera_id: int
    anomaly_type: str
    track_key: str
    started_at: datetime.datetime
    ended_at: datetime.datetime | None
    frame_path: str | None
    clip_path: str | None
    clip_truncated: bool
    mongo_ref: str | None
    created_at: datetime.datetime


class EvidenceMatchOut(BaseModel):
    """POST /api/evidence yaniti: hangi yolun izlendigini bildirir."""

    matched: bool
    event_id: int | None = None
    evidence_id: int | None = None


# ---------------------------------------------------------------- analytics
class AnalyticsSummaryOut(BaseModel):
    total: int
    by_type: list[dict[str, Any]]
    by_severity: list[dict[str, Any]]
    by_status: list[dict[str, Any]]
    by_camera: list[dict[str, Any]]
    by_hour: list[dict[str, Any]]


class AblationRowOut(BaseModel):
    decided_by: str
    anomaly_type: str
    status: str
    count: int


class QualityRowOut(BaseModel):
    """Ground-truth etiketi yok -- recall/f1 hesaplanamaz, her zaman None
    (QualityOut.note aciklar). Gercek sinyal operatorun events.status geri
    bildirimi: confirmed = acknowledged + resolved (ASAMA8_PLAN.md SS3.8.2)."""

    anomaly_type: str
    total: int
    confirmed: int
    false_positive: int
    pending: int
    precision: float | None
    recall: float | None = None
    f1: float | None = None


class QualityOut(BaseModel):
    items: list[QualityRowOut]
    note: str
