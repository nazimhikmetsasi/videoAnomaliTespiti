"""Asama 8.6 oz kontrolu -- uctan uca demo altyapisi (ASAMA8_PLAN.md 8.6).

Agsiz/Dockersiz calisanlar: saf fonksiyonlar (--loop wrap, .env ayristirma,
port turetme, komut kurma, kamera secimi) + CameraHealthOut/health.py'nin
ws_port alani + settings.py'nin ad/id kimlik cozumu (gercek DB varsa, yoksa
skip -- test_asama8_2.py'deki desenle ayni). Gercek alt surec baslatma,
gercek WS baglantisi ve gercek Mongo yazimi bu testin kapsami disinda; ana
oturum tarayicida/gercek yiginda dogrular.

Calistirma:
    venv\\Scripts\\python.exe -m pytest tests/test_asama8_6.py -q
"""

from __future__ import annotations

import datetime
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.db.models import Camera  # noqa: E402


# ---------------------------------------------------------------- --loop sarimi
def _write_clip(path: Path, frames: int = 8) -> None:
    import cv2
    import numpy as np

    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 25.0, (64, 48))
    assert writer.isOpened(), "test videosu yazilamadi"
    for i in range(frames):
        img = np.full((48, 64, 3), i * 10 % 255, dtype=np.uint8)
        writer.write(img)
    writer.release()


def test_loop_wraps_without_resetting_idx() -> None:
    """--loop acikken dosya kaynagi hic bitmemeli; idx SIFIRLANMAMALI (surekli
    artan sayac) -- yoksa izleyici kimlikleri/kural pencereleri sarimda
    bozulur (docs/DURUM.md gerekcesi)."""
    from vision.source import VideoSource

    with tempfile.TemporaryDirectory() as tmp:
        clip = Path(tmp) / "clip.mp4"
        _write_clip(clip, frames=8)

        with VideoSource(clip, buffer_frames=5, loop=True) as source:
            idxs = []
            for _ in range(20):
                frame = source.read(timeout=5.0)
                assert frame is not None, "loop acikken kaynak asla EOF vermemeli"
                idxs.append(frame.idx)

        assert idxs == list(range(20)), f"idx surekli artmali, sarimda sifirlanmamali: {idxs}"
        assert not source.eof.is_set(), "loop acikken dosya hic bitmis sayilmamali"


def test_loop_off_still_ends_normally() -> None:
    """--loop verilmeden eski davranis (EOF) korunmali -- regresyon."""
    from vision.source import VideoSource

    with tempfile.TemporaryDirectory() as tmp:
        clip = Path(tmp) / "clip.mp4"
        _write_clip(clip, frames=8)

        with VideoSource(clip, buffer_frames=5, loop=False) as source:
            count = 0
            while source.read(timeout=5.0) is not None:
                count += 1
        assert count == 8
        assert source.eof.is_set()


def test_loop_ignored_for_live_source() -> None:
    """Canli kaynakta (rtsp/webcam) loop anlamsiz -- sessizce yok sayilmali,
    reconnect mantigina karismamali."""
    from vision.source import VideoSource

    source = VideoSource("rtsp://ornek/akis", loop=True)
    assert source.loop is False


def test_run_py_parses_loop_flag() -> None:
    from vision.run import parse_args

    assert parse_args(["--source", "x"]).loop is False
    assert parse_args(["--source", "x", "--loop"]).loop is True


# --------------------------------------------------------------- ws_port tasima
def test_camera_health_out_has_ws_port_field() -> None:
    from api.schemas import CameraHealthOut

    assert "ws_port" in CameraHealthOut.model_fields


def test_to_health_out_reads_ws_port_from_doc() -> None:
    from api.routers.health import _to_health_out

    cam = Camera(id=5, name="fall_01")
    now = datetime.datetime.now(datetime.timezone.utc)
    doc = {"ts": now.replace(tzinfo=None), "ws_port": 8006}
    out = _to_health_out(cam, doc, now)
    assert out.ws_port == 8006


def test_to_health_out_missing_ws_port_field_is_none() -> None:
    """StreamServer acilmadan (JWT_SECRET yok) yazilan eski/kismi belge --
    alan hic yoksa panel None gormeli, 0 veya hata degil."""
    from api.routers.health import _to_health_out

    cam = Camera(id=5, name="fall_01")
    now = datetime.datetime.now(datetime.timezone.utc)
    doc = {"ts": now.replace(tzinfo=None)}
    out = _to_health_out(cam, doc, now)
    assert out.ws_port is None


def test_to_health_out_no_doc_ws_port_none() -> None:
    from api.routers.health import _to_health_out

    cam = Camera(id=9, name="run_01")
    now = datetime.datetime.now(datetime.timezone.utc)
    out = _to_health_out(cam, None, now)
    assert out.ws_port is None


def test_health_client_writes_given_ws_port() -> None:
    from vision.health_client import HealthClient
    from vision.source import VideoSource

    captured: dict = {}

    class _FakeCollection:
        def insert_one(self, doc):
            captured.update(doc)

    class _FakeDB:
        camera_health = _FakeCollection()

    class _FakeMongo:
        def __getitem__(self, _name):
            return _FakeDB()

    source = VideoSource("rtsp://ornek/akis")
    client = HealthClient("http://x", "cam1", source, mongo_url="mongodb://x", ws_port=8007)
    client._mongo = _FakeMongo()  # gercek baglanti kurulmadan insert_one yakalanir
    client._write_health()
    assert captured.get("ws_port") == 8007


def test_health_client_ws_port_defaults_to_none() -> None:
    from vision.health_client import HealthClient
    from vision.source import VideoSource

    source = VideoSource("rtsp://ornek/akis")
    client = HealthClient("http://x", "cam1", source)
    assert client._ws_port is None


# ------------------------------------------------------- kamera kimligi (settings)
def _live_session():
    from sqlalchemy import text

    from api.db.postgres import SessionLocal

    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        db.close()
        pytest.skip(f"veritabanina erisilemiyor: {exc}")
    return db


def test_settings_camera_id_accepts_name_against_real_db() -> None:
    """vision/run.py TEK `--camera-id` (kamera adi) kullanir; esik ucu artik
    ad/id ikisini de kabul eder (api/routers/settings.py `_resolve_or_404`,
    api/routers/cameras.py `resolve_camera_id` ile AYNI cozum) -- ayri bir
    --settings-camera-id argumanina gerek kalmadi."""
    from sqlalchemy import select

    from api.routers.settings import get_camera_settings

    db = _live_session()
    try:
        cam = db.scalar(select(Camera).limit(1))
        if cam is None:
            pytest.skip("veritabaninda kamera yok")
        by_name = get_camera_settings(camera_id=cam.name, db=db, _={"role": "admin"})
        by_id = get_camera_settings(camera_id=str(cam.id), db=db, _={"role": "admin"})
        assert by_name.camera_id == by_id.camera_id == cam.id
    finally:
        db.close()


def test_settings_camera_id_unknown_name_returns_404() -> None:
    from fastapi import HTTPException

    from api.routers.settings import get_camera_settings

    db = _live_session()
    try:
        with pytest.raises(HTTPException) as exc_info:
            get_camera_settings(camera_id="__asama8_6_no_such_camera__", db=db, _={"role": "admin"})
        assert exc_info.value.status_code == 404
    finally:
        db.close()


# ----------------------------------------------------- run_pilot_cameras.py saf fonksiyonlar
def test_parse_cameras_arg_default_is_first_three() -> None:
    from scripts.run_pilot_cameras import DEFAULT_CAMERA_COUNT, parse_cameras_arg

    available = ["fall_01", "mixed_01", "normal_01", "police_run", "run_01", "zone_01"]
    assert parse_cameras_arg("", available) == available[:DEFAULT_CAMERA_COUNT]


def test_parse_cameras_arg_explicit_list() -> None:
    from scripts.run_pilot_cameras import parse_cameras_arg

    available = ["fall_01", "run_01", "zone_01"]
    assert parse_cameras_arg("run_01,zone_01", available) == ["run_01", "zone_01"]


def test_parse_cameras_arg_unknown_name_raises() -> None:
    from scripts.run_pilot_cameras import parse_cameras_arg

    with pytest.raises(ValueError):
        parse_cameras_arg("no_such_cam", ["fall_01"])


def test_ws_port_for_derives_from_camera_id() -> None:
    from scripts.run_pilot_cameras import BASE_WS_PORT, ws_port_for

    assert ws_port_for(1) == BASE_WS_PORT + 1
    assert ws_port_for(7) == BASE_WS_PORT + 7


def test_load_env_file_parses_key_value_lines() -> None:
    from scripts.run_pilot_cameras import load_env_file

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / ".env"
        path.write_text("# yorum\nMONGO_PASSWORD=abc123\n\nJWT_SECRET=xyz\n", encoding="utf-8")
        env = load_env_file(path)
    assert env == {"MONGO_PASSWORD": "abc123", "JWT_SECRET": "xyz"}


def test_load_env_file_missing_file_returns_empty() -> None:
    from scripts.run_pilot_cameras import load_env_file

    assert load_env_file(Path("__does_not_exist__.env")) == {}


def test_build_run_command_includes_identity_port_and_loop() -> None:
    from scripts.run_pilot_cameras import build_run_command

    cmd = build_run_command(["fall_01"], ["data/pilot/fall_01.mp4"], 8003,
                             settings_url="http://localhost:8000", settings_token="tok", loop=True)
    assert "--camera-id" in cmd and "fall_01" in cmd
    assert "--ws-port" in cmd and "8003" in cmd
    assert "--loop" in cmd
    assert "--rules" in cmd


def test_build_run_command_no_loop_flag_omitted() -> None:
    from scripts.run_pilot_cameras import build_run_command

    cmd = build_run_command(["fall_01"], ["data/pilot/fall_01.mp4"], 8003,
                             settings_url="http://localhost:8000", settings_token="tok", loop=False)
    assert "--loop" not in cmd


# ------------------------------------------------------- webcam kaynak turu
def test_wants_loop_yalniz_dosyada() -> None:
    """Dongu dosya kaynaginda anlamli, webcam akisi zaten hic bitmez
    (demo kaynaklari: pilot klipler + dizustunun kendi kamerasi)."""
    from scripts.run_pilot_cameras import wants_loop

    assert wants_loop("file", True) is True
    assert wants_loop("webcam", True) is False
    assert wants_loop("file", False) is False


def test_build_run_command_webcamde_loop_vermez() -> None:
    from scripts.run_pilot_cameras import build_run_command, wants_loop

    cmd = build_run_command(["webcam_01"], ["0"], 8010, settings_url="http://x",
                            settings_token="t", loop=wants_loop("webcam", True))
    assert "--loop" not in cmd
    assert cmd[cmd.index("--source") + 1] == "0"
    assert cmd[cmd.index("--camera-id") + 1] == "webcam_01"


# ------------------------------------------- Asama 10.3: tek surec, N kamera
def test_build_run_command_tek_surecte_tum_kameralari_birlestirir() -> None:
    """Kamera basina ayri surec yerine TEK surec: kaynaklar ve adlar ayni
    sirada, virgulle. Her surecin kendi model kopyasini yuklemesi 4 GB
    VRAM'de 3 kamerada tikaniyordu."""
    from scripts.run_pilot_cameras import build_run_command

    cmd = build_run_command(["webcam_01", "fall_01"], ["0", "data/pilot/fall_01.mp4"],
                            8010, settings_url="http://x", settings_token="t", loop=True)
    assert cmd[cmd.index("--source") + 1] == "0,data/pilot/fall_01.mp4"
    assert cmd[cmd.index("--camera-id") + 1] == "webcam_01,fall_01"
    assert cmd.count("--ws-port") == 1


# --------------------------------------- Asama 10.3: canli kaynak olmez
def test_canli_kaynak_sessiz_kalinca_bitmis_sayilmaz() -> None:
    """Webcam acilista gec kalirsa hat onu KALICI olarak olu saymamali.

    Olculen hata: 30 sn sessizlikten sonra kamera bir daha hic okunmadi,
    kuyrugu dolu kaldigi icin dusen kare 955'e cikti ve VideoSource'un
    yeniden baglanma mantigi hic devreye giremedi. Dosya kaynagi gercekten
    biter (eof), canli kaynak bitmez.
    """
    import time as _time
    from vision.camera import CameraPipeline

    pipe = CameraPipeline.__new__(CameraPipeline)   # __init__ kaynak acar
    pipe.finished, pipe.outages, pipe.frames = False, 0, 0
    pipe.idle_since = _time.monotonic() - 999
    pipe.camera_id, pipe.source_arg = "webcam_01", "0"

    class _Source:
        last_error = ""
        def read(self, timeout=2.0): return None
        class _Eof:
            @staticmethod
            def is_set(): return False
        eof = _Eof()
    pipe.source = _Source()

    assert CameraPipeline.read(pipe, timeout=0.0) is None
    assert pipe.finished is False        # OLU SAYILMAZ
    assert pipe.outages == 1
