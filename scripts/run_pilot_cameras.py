"""Birden fazla pilot kamerayi tek komutla ayaga kaldirir (ASAMA8_PLAN.md 8.6).

IP kamera donanimi yok; demo kaynaklari `data/pilot/` klipleri VE dizustunun
kendi kamerasidir. Kameralar veritabaninda tanimli (`source_type='file'`
pilot klipler icin, `'webcam'` dizustu kamerasi icin -- kaynak degeri webcam
indeksi, ornegin "0"), kaynak yollari `cameras.source`'da dolu. Bu betik
yalniz API'den listeyi okur ve her secili kamera icin bir `vision.run` alt
sureci baslatir; kaynak turune gore tek fark `--loop` (yalniz dosyada).

Kimlik cakismasi (docs/DURUM.md bilinen kisit): vision/run.py'de TEK
`--camera-id` argumani var, WS anahtari (panelin baglandigi) kamera ADI
olmali, esik sicak yukleme ise `/api/settings/{camera_id}` sayisal id
bekliyordu. Cozum burada DEGIL `api/routers/settings.py`de: o uc artik
`api/routers/cameras.py`'deki `resolve_camera_id` ile ad/id ikisini de kabul
ediyor -- vision tarafina ikinci bir kimlik argumani sokmadan tek kimlik
(kamera adi) her yerde calisir.

Kalp atisinin Mongo yazimi host'tan calisirken `.env`'deki MONGO_PASSWORD
ortamda olmadigi icin sessizce basarisiz oluyordu (docs/DURUM.md madde 2) --
bu betik `.env`'i okuyup alt sureclerin ortamina GECIRIR (yeni bagimlilik
yok, python-dotenv degil elle satir ayristirma).

Calistirma:
    venv\\Scripts\\python.exe scripts/run_pilot_cameras.py
    venv\\Scripts\\python.exe scripts/run_pilot_cameras.py --cameras fall_01,run_01
    venv\\Scripts\\python.exe scripts/run_pilot_cameras.py --no-loop

Ctrl+C hepsini duzgun durdurur.
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
LOG_DIR_DEFAULT = "logs"

# 4 GB VRAM'de 6 kamera gercekci degil (model yuklemesi ~25 sn/surec, ana
# oturum olcumu) -- varsayilan yalniz ILK 3 kamera (id sirali).
DEFAULT_CAMERA_COUNT = 3
BASE_WS_PORT = 8001
HEALTH_POLL_SEC = 1.0
READY_TIMEOUT_SEC = 90.0


def load_env_file(path: Path) -> dict[str, str]:
    """.env'i basit `KEY=VALUE` satirlari olarak okur. python-dotenv YOK --
    birkac satirlik ayristirma yeter, yeni bagimlilik eklenmez."""
    env: dict[str, str] = {}
    if not path.is_file():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def parse_cameras_arg(raw: str, available: list[str]) -> list[str]:
    """--cameras bos ise ILK DEFAULT_CAMERA_COUNT kamera (available zaten id
    sirali gelir). Bilinmeyen ad verilirse acik hata -- sessiz atlama yok."""
    if not raw:
        return available[:DEFAULT_CAMERA_COUNT]
    wanted = [name.strip() for name in raw.split(",") if name.strip()]
    unknown = [n for n in wanted if n not in available]
    if unknown:
        raise ValueError(f"bilinmeyen kamera adi: {', '.join(unknown)} (mevcut: {', '.join(available)})")
    return wanted


def ws_port_for(camera_id: int) -> int:
    """Cakismasiz port secimi icindir -- panel portu BUNDAN degil saglik
    kaydindan okur (vision/health_client.py, ASAMA8_PLAN.md 8.6 madde 2)."""
    return BASE_WS_PORT + camera_id


# vision/run.py --kafka'nin kendi varsayilani ile ayni (env, sonra localhost).
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_HOST", "localhost:9092")


def wants_loop(source_type: str, loop_requested: bool) -> bool:
    """Dongu yalnizca dosya kaynaginda anlamlidir; webcam akisi zaten hic
    bitmez. Karar TEK yerde -- cagiran taraflara if merdiveni dagilmasin
    (VideoSource da ayrica sessizce yok sayar, kemer + askidir)."""
    return loop_requested and source_type == "file"


def build_run_command(names: list[str], sources: list[str], port: int, *,
                       settings_url: str, settings_token: str, loop: bool,
                       kafka: str = KAFKA_BOOTSTRAP) -> list[str]:
    """TEK surec, N kamera (Asama 10.3).

    Onceden kamera basina bir surec aciliyordu ve her surec kendi model
    kopyasini VRAM'e yukluyordu; 4 GB'ta bu 3 kamerada tikandi. Tek surecte
    tek model, TEK toplu cikarim cagrisi ve TEK WS portu var.
    """
    cmd = [
        # -u: cikti dosyaya yonlendirildiginde Python blok tamponlar ve
        # logs/vision.log demo boyunca BOS gorunur (8.6 dogrulamasinda
        # "Kafka:" banner satiri bu yuzden gorunmedi). Tamponsuz yaz.
        sys.executable, "-u", "-m", "vision.run",
        "--source", ",".join(sources),
        "--camera-id", ",".join(names),
        "--ws", "--ws-port", str(port),
        "--rules",
        # Aday olaylar Kafka'ya BASILMAZSA Spark'a hicbir sey gitmez: olay
        # yazilmaz, /ws/alerts sessiz kalir, Telegram bildirimi de gitmez --
        # demo zincirinin tamami SESSIZCE olur. 8.6 dogrulamasinda tam bu
        # yasandi: uc kamera 20 dakika calisti, tek olay uretilmedi.
        "--kafka", kafka,
        # Kanit (kare + klip) olmadan olay detayi ekrani bos kalir (Asama 6).
        "--evidence",
        "--settings-url", settings_url,
        "--settings-token", settings_token,
        "--heartbeat-sec", "5",
    ]
    if loop:
        # Yalnizca dosya kaynagini sarar; VideoSource canli kaynakta loop'u
        # zaten yok sayar, karisik listede guvenli.
        cmd.append("--loop")
    return cmd


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Birden fazla pilot kamerayi tek komutla ayaga kaldirir. "
                     f"Varsayilan: ilk {DEFAULT_CAMERA_COUNT} kamera -- 4 GB VRAM'de "
                     "6 kamera ayni anda gercekci degil.")
    parser.add_argument("--cameras", default="",
                        help="virgulle ayrilmis kamera adi listesi, orn. fall_01,run_01 "
                             f"(bos = ilk {DEFAULT_CAMERA_COUNT} kamera)")
    parser.add_argument("--settings-url", default="http://localhost:8000")
    parser.add_argument("--admin-user", default="admin")
    parser.add_argument("--no-loop", action="store_true",
                        help="--loop VERME (varsayilan: dongu acik, klipler kisa)")
    parser.add_argument("--kafka", default=KAFKA_BOOTSTRAP,
                        help=f"aday olay yayini icin bootstrap (varsayilan {KAFKA_BOOTSTRAP})")
    parser.add_argument("--log-dir", default=LOG_DIR_DEFAULT)
    return parser.parse_args(argv)


def login(settings_url: str, username: str, password: str) -> str:
    # OAuth2PasswordRequestForm form-encoded bekler, JSON DEGIL
    # (build_frontend.py'nin login.html'e enjekte ettigi istekle ayni).
    resp = httpx.post(f"{settings_url}/api/auth/login",
                       data={"username": username, "password": password}, timeout=10.0)
    resp.raise_for_status()
    return resp.json()["access_token"]


# Baslatilabilir kaynak turleri: dosya (pilot klipler) ve webcam (dizustunun
# kendi kamerasi). RTSP kamera donanimi yok -- listede gorunse bile bu betik
# baslatmaz, "Baglanti Yok" gosterilir (ASAMA8_PLAN.md SS4: sahte veri yok).
LAUNCHABLE_TYPES = ("file", "webcam")


def fetch_cameras(settings_url: str, token: str) -> list[tuple[int, str, str, str]]:
    """(id, name, source, source_type) dortlusu, id sirali, yalniz
    LAUNCHABLE_TYPES."""
    resp = httpx.get(f"{settings_url}/api/cameras",
                      headers={"Authorization": f"Bearer {token}"}, timeout=10.0)
    resp.raise_for_status()
    rows = sorted(resp.json(), key=lambda c: c["id"])
    return [(c["id"], c["name"], c["source"], c["source_type"])
            for c in rows if c["source_type"] in LAUNCHABLE_TYPES]


def wait_ready(settings_url: str, token: str, names: list[str], timeout: float) -> None:
    """/api/health/cameras'ta secili kameralarin tazece kalp atisi vermesini
    bekler -- alt surec baslatildi != model yuklendi/yayina basladi."""
    deadline = time.monotonic() + timeout
    pending = set(names)
    headers = {"Authorization": f"Bearer {token}"}
    while pending and time.monotonic() < deadline:
        try:
            resp = httpx.get(f"{settings_url}/api/health/cameras", headers=headers, timeout=5.0)
            resp.raise_for_status()
            for row in resp.json():
                if row["name"] in pending and row.get("age_sec") is not None \
                        and row["age_sec"] < HEALTH_POLL_SEC * 10:
                    pending.discard(row["name"])
                    print(f"  hazir: {row['name']}")
        except httpx.HTTPError:
            pass
        if pending:
            time.sleep(HEALTH_POLL_SEC)
    if pending:
        print(f"  UYARI: {timeout:.0f} sn icinde hazir olmayanlar: {', '.join(sorted(pending))} "
              "(surec calisiyor olabilir, model yuklemesi uzun surdu)")


def stop_all(procs: list[subprocess.Popen]) -> None:
    print("\n  durduruluyor...")
    for proc in procs:
        if proc.poll() is not None:
            continue
        try:
            if os.name == "nt":
                # CREATE_NEW_PROCESS_GROUP ile acildilar (asagida) -- ayni
                # konsol grubunda olmadiklari icin duz Ctrl+C onlara ULASMAZ,
                # CTRL_BREAK_EVENT acikca gonderilmeli. Bu, subprocess'in
                # resmi onerdigi Windows deseni (bkz. Popen.send_signal
                # belgesi); GPU/Docker gerektirdigi icin bu ortamda
                # calistirilarak DOGRULANAMADI.
                proc.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                proc.terminate()
        except (OSError, ValueError):
            pass

    deadline = time.monotonic() + 5.0
    for proc in procs:
        remaining = max(0.0, deadline - time.monotonic())
        try:
            proc.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            print(f"  takildi, zorla kapatiliyor: pid={proc.pid}")
            proc.kill()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    env_file = load_env_file(ENV_PATH)
    child_env = {**os.environ, **env_file}

    password = env_file.get("ADMIN_PASSWORD") or os.environ.get("ADMIN_PASSWORD")
    if not password:
        print("  HATA: ADMIN_PASSWORD .env'de yok")
        return 1

    try:
        token = login(args.settings_url, args.admin_user, password)
    except httpx.HTTPError as exc:
        print(f"  HATA: giris basarisiz ({args.settings_url}): {exc}")
        return 1

    try:
        cams = fetch_cameras(args.settings_url, token)
    except httpx.HTTPError as exc:
        print(f"  HATA: kamera listesi alinamadi: {exc}")
        return 1
    if not cams:
        print("  HATA: baslatilabilir kamera yok (dosya ya da webcam) -- "
              "scripts/seed_pilot.py calistirildi mi?")
        return 1

    by_name = {name: (cid, source, stype) for cid, name, source, stype in cams}
    try:
        chosen = parse_cameras_arg(args.cameras, [name for _, name, _, _ in cams])
    except ValueError as exc:
        print(f"  HATA: {exc}")
        return 1

    log_dir = ROOT / args.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    sources = [by_name[name][1] for name in chosen]
    types = [by_name[name][2] for name in chosen]
    port = ws_port_for(by_name[chosen[0]][0])
    cmd = build_run_command(chosen, sources, port, settings_url=args.settings_url,
                             settings_token=token,
                             loop=any(wants_loop(t, not args.no_loop) for t in types),
                             kafka=args.kafka)
    log_path = log_dir / "vision.log"
    log_file = open(log_path, "w", encoding="utf-8")
    log_files = [log_file]
    proc = subprocess.Popen(cmd, cwd=str(ROOT), env=child_env,
                             stdout=log_file, stderr=subprocess.STDOUT,
                             creationflags=creationflags)
    procs = [proc]
    print(f"  baslatildi: tek surec, {len(chosen)} kamera "
          f"({', '.join(chosen)}), port={port}, pid={proc.pid} -> {log_path}")

    print(f"\n  {len(chosen)} kamera tek surecte, "
          f"model yuklemesi ~25 sn surer...")
    wait_ready(args.settings_url, token, chosen, timeout=READY_TIMEOUT_SEC)

    print("\n  Ctrl+C ile hepsini durdur.")
    warned: set[int] = set()
    try:
        while True:
            time.sleep(1.0)
            for proc in procs:
                if proc.poll() is not None and proc.pid not in warned:
                    warned.add(proc.pid)
                    print(f"  UYARI: bir surec kendiliginden kapandi (pid={proc.pid}, kod={proc.returncode})")
    except KeyboardInterrupt:
        pass
    finally:
        stop_all(procs)
        for log_file in log_files:
            log_file.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
