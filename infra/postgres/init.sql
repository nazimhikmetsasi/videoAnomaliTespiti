-- Video Anomali Tespiti v2 - PostgreSQL semasi
-- docs/PLAN.md bolum 6.1'in birebir karsiligi.
-- Bu dosya yalnizca bos bir veri diziniyle ilk acilista calisir.

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- bcrypt icin: crypt() + gen_salt('bf')

-- ---------------------------------------------------------------- users
CREATE TABLE users (
    id               SERIAL PRIMARY KEY,
    username         VARCHAR(50)  NOT NULL UNIQUE,
    password_hash    VARCHAR(255) NOT NULL,
    full_name        VARCHAR(100) NOT NULL,
    role             VARCHAR(20)  NOT NULL DEFAULT 'viewer'
                     CHECK (role IN ('admin', 'operator', 'viewer')),
    telegram_chat_id VARCHAR(50),
    is_active        BOOLEAN      NOT NULL DEFAULT TRUE,
    last_login       TIMESTAMPTZ,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- -------------------------------------------------------------- cameras
CREATE TABLE cameras (
    id           SERIAL PRIMARY KEY,
    name         VARCHAR(100) NOT NULL,
    source       TEXT         NOT NULL,          -- '0' | 'data/test.mp4' | 'rtsp://...'
    source_type  VARCHAR(20)  NOT NULL
                 CHECK (source_type IN ('webcam', 'file', 'rtsp')),
    location     VARCHAR(150),
    width        INT          NOT NULL DEFAULT 960,
    height       INT          NOT NULL DEFAULT 540,
    target_fps   INT          NOT NULL DEFAULT 25,
    is_active    BOOLEAN      NOT NULL DEFAULT TRUE,
    status       VARCHAR(20)  NOT NULL DEFAULT 'offline'
                 CHECK (status IN ('online', 'offline', 'error')),
    last_seen_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_cameras_active ON cameras (is_active);

-- ---------------------------------------------------------------- zones
-- polygon 0-1 normalize saklanir; cozunurluk degisince koordinat bozulmaz.
CREATE TABLE zones (
    id               SERIAL PRIMARY KEY,
    camera_id        INT          NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    name             VARCHAR(100) NOT NULL,
    zone_type        VARCHAR(30)  NOT NULL
                     CHECK (zone_type IN ('forbidden', 'restricted_hours', 'direction')),
    polygon          JSONB        NOT NULL,      -- [[x,y], ...] 0-1 normalize
    direction_vector JSONB,                      -- [dx,dy], ters yon tespiti icin
    active_from      TIME,
    active_to        TIME,
    is_active        BOOLEAN      NOT NULL DEFAULT TRUE,
    created_by       INT          REFERENCES users(id) ON DELETE SET NULL,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_zones_camera ON zones (camera_id, is_active);

-- ---------------------------------------------------- detection_settings
-- Tum hiz/mesafe esikleri bbox YUKSEKLIGINE normalize birimdedir.
-- camera_id NULL = global varsayilan (tek satir olmali).
CREATE TABLE detection_settings (
    id               SERIAL PRIMARY KEY,
    camera_id        INT UNIQUE REFERENCES cameras(id) ON DELETE CASCADE,
    pose_conf        NUMERIC(3,2) NOT NULL DEFAULT 0.25,
    track_conf       NUMERIC(3,2) NOT NULL DEFAULT 0.30,
    fall_tilt_deg    NUMERIC(5,2) NOT NULL DEFAULT 45.0,
    fall_norm_vy     NUMERIC(6,3) NOT NULL DEFAULT 1.20,
    run_norm_speed   NUMERIC(6,3) NOT NULL DEFAULT 1.80,
    run_gait_speed   NUMERIC(6,3) NOT NULL DEFAULT 1.20,
    loiter_sec       INT          NOT NULL DEFAULT 30,
    fight_proximity  NUMERIC(4,2) NOT NULL DEFAULT 1.20,
    window_frames    INT          NOT NULL DEFAULT 50,
    -- Kayan pencere degil oturum bosluk suresi: bu kadar saniyelik sessizlikten
    -- sonrasi yeni olaydir (ASAMA4_PLAN.md SS5.1, session_window kullanilir).
    spark_window_sec INT          NOT NULL DEFAULT 3,
    -- 5 -> 2: gercek FALL yalnizca 2 aday uretiyor (docs/DURUM.md), 5 onu elerdi.
    spark_min_hits   INT          NOT NULL DEFAULT 2,
    -- Tip basina minimum oturum suresi (sn). FALL bir darbedir (0.0, hits>=2
    -- tek koruma); RUN/ZONE/LOITERING bir durumdur. Tek sutun yerine JSONB:
    -- yeni bir kural tipi sema gocu gerektirmesin (ASAMA4_PLAN.md SS5.3/SS7).
    spark_min_sec    JSONB        NOT NULL DEFAULT
        '{"FALL":0.0,"RUN":1.0,"ZONE_VIOLATION":1.0,"LOITERING":2.0,"FIGHT":0.5}',
    tcn_min_conf     NUMERIC(3,2) NOT NULL DEFAULT 0.60,
    -- Kur/Birak anahtari (TEZ_KAPSAM.txt Faz 1: "Evde = bildirim yok,
    -- Koruma = alarm"). FALSE iken tespit ve kanit uretimi AYNEN surer,
    -- yalnizca disari bildirim gitmez -- olay gecmisi eksilmez.
    -- Var olan kurulumlar icin ayni sutun api/db/migrate.py'de.
    armed            BOOLEAN      NOT NULL DEFAULT TRUE,
    updated_by       INT          REFERENCES users(id) ON DELETE SET NULL,
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- PostgreSQL'de NULL'lar birbirinden farkli sayilir, bu yuzden UNIQUE sutunu
-- tek basina birden fazla global satiri engellemez. Kismi index engeller.
CREATE UNIQUE INDEX idx_settings_single_global
    ON detection_settings ((camera_id IS NULL)) WHERE camera_id IS NULL;

-- --------------------------------------------------------------- events
CREATE TABLE events (
    id            BIGSERIAL PRIMARY KEY,
    camera_id     INT          NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    zone_id       INT          REFERENCES zones(id) ON DELETE SET NULL,
    anomaly_type  VARCHAR(30)  NOT NULL
                  CHECK (anomaly_type IN ('FALL', 'RUN', 'ZONE_VIOLATION',
                                          'RUN_ZONE', 'FIGHT', 'LOITERING',
                                          'WRONG_DIRECTION')),
    track_ids     INT[]        NOT NULL DEFAULT '{}',
    confidence    NUMERIC(4,3) NOT NULL,
    severity      VARCHAR(10)  NOT NULL
                  CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    -- Tez icin kritik: ablation tablosu bu sutundan uretilir.
    decided_by    VARCHAR(10)  NOT NULL
                  CHECK (decided_by IN ('rule', 'model', 'hybrid')),
    started_at    TIMESTAMPTZ  NOT NULL,
    ended_at      TIMESTAMPTZ,
    duration_ms   INT,
    frame_path    TEXT,
    clip_path     TEXT,
    llm_report_tr TEXT,
    mongo_ref     VARCHAR(24),                   -- pose_sequences ObjectId
    status        VARCHAR(20)  NOT NULL DEFAULT 'new'
                  CHECK (status IN ('new', 'acknowledged', 'false_positive', 'resolved')),
    acked_by      INT          REFERENCES users(id) ON DELETE SET NULL,
    acked_at      TIMESTAMPTZ,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_events_camera_time ON events (camera_id, started_at DESC);
CREATE INDEX idx_events_type        ON events (anomaly_type);
CREATE INDEX idx_events_status      ON events (status);
CREATE INDEX idx_events_decided_by  ON events (decided_by);
CREATE INDEX idx_events_time        ON events (started_at DESC);

-- Tekrar yazma korumasi: Spark oturum penceresi bir episodu tek satir olarak
-- yazar, bu dortlu dogal anahtardir. Tuketici en-az-bir-kez teslimatinda
-- ayni olayi INSERT ... ON CONFLICT DO NOTHING ile atlar (ASAMA5_PLAN.md SS6.4).
CREATE UNIQUE INDEX idx_events_dedup
    ON events (camera_id, anomaly_type, started_at, track_ids);

-- --------------------------------------------------------- notifications
CREATE TABLE notifications (
    id       BIGSERIAL    PRIMARY KEY,
    event_id BIGINT       NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    channel  VARCHAR(20)  NOT NULL CHECK (channel IN ('telegram', 'fcm')),
    target   VARCHAR(120) NOT NULL,
    status   VARCHAR(10)  NOT NULL CHECK (status IN ('sent', 'failed', 'skipped')),
    error    TEXT,
    sent_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_notifications_event ON notifications (event_id);

-- ------------------------------------------------------------ audit_log
CREATE TABLE audit_log (
    id         BIGSERIAL   PRIMARY KEY,
    user_id    INT         REFERENCES users(id) ON DELETE SET NULL,
    action     VARCHAR(50) NOT NULL,
    entity     VARCHAR(50) NOT NULL,
    entity_id  BIGINT,
    payload    JSONB,
    ip         INET,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_user_time ON audit_log (user_id, created_at DESC);

-- -------------------------------------------------------------- evidence
-- vision/ epizot kapanisinda POST /api/evidence ile bildirir. Sira garantisi
-- yoktur (kanit vs. Spark'tan gecen olay); event_id NULL kalabilir --
-- eslesmeyen satir silinmez, GET /api/evidence?unmatched=true ile gorunur
-- (docs/ASAMA6_PLAN.md SS8.2).
CREATE TABLE evidence (
    id             BIGSERIAL PRIMARY KEY,
    event_id       BIGINT REFERENCES events(id) ON DELETE CASCADE,
    camera_id      INT NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    anomaly_type   VARCHAR(30) NOT NULL,
    track_key      VARCHAR(50) NOT NULL,
    started_at     TIMESTAMPTZ NOT NULL,
    ended_at       TIMESTAMPTZ,
    frame_path     TEXT,
    clip_path      TEXT,
    clip_truncated BOOLEAN NOT NULL DEFAULT FALSE,
    mongo_ref      VARCHAR(24),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_evidence_match ON evidence (camera_id, anomaly_type, started_at);
CREATE INDEX idx_evidence_event ON evidence (event_id);

-- --------------------------------------------------------- tohum kayitlar
-- Sifre .env'deki ADMIN_PASSWORD'dan alinir ve burada bcrypt'lenir; depoda
-- acik sifre tutulmaz. Ilk giristen sonra panelden degistirilmelidir.
\getenv admin_password ADMIN_PASSWORD

INSERT INTO users (username, password_hash, full_name, role)
VALUES ('admin', crypt(:'admin_password', gen_salt('bf')), 'Sistem Yoneticisi', 'admin');

-- Global varsayilan esik satiri (camera_id NULL). Bir kameraya ozel satir
-- eklenirse o kamera icin bunun uzerine yazar.
INSERT INTO detection_settings (camera_id) VALUES (NULL);
