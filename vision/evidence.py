"""Kanit uretimi: aday akisindan epizot kurar, kapaninca +-5 sn mp4 klip +
en iyi kare + `pose_sequences` yazar, `POST /api/evidence` ile bildirir
(ASAMA6_PLAN.md SS5, SS6).

Epizot kavrami Spark'in `session_window`'unun YEREL ikizidir (SS5.1). Esik
mantigi KOPYALANMAZ: kapanista `stream/filters.py`'deki `session_passes()`
aynen cagirilir -- gecmeyen epizot icin kanit uretilmez (diske cop yazilmaz).

Goru dongusu ASLA bloklanmaz: epizot takibi (`on_frame`) hafiftir, I/O
yapmaz. Klip/kare/mongo/HTTP yazimi AYRI bir daemon thread'de kuyruktan
tuketilir. Kuyruk dolarsa en eski is dusurulur, `dropped` sayaci artar --
`vision/source.py`'nin canli kaynak devir teslim deseniyle aynidir.
"""

from __future__ import annotations

import datetime
import os
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import httpx

from stream.filters import session_passes
from vision.rules.engine import Candidate
from vision.source import Frame, VideoSource
from vision.stages.tracker import Track

DEFAULT_MIN_HITS = 2               # stream/filters.py + init.sql spark_min_hits varsayilaniyla ayni
CLIP_PAD_SEC = 5.0
POSE_BUFFER_SEC = 20.0              # 300 karelik halka tampon (~12 sn) + iki yanda 5 sn pay


def default_mongo_url() -> str:
    """api/config.py `_mongo_url()` ile ayni mantik -- vision/ api/ paketine
    bagimli olmadigi icin (ayri dagitilabilir servis) kucuk kopya kabul edilir."""
    if url := os.getenv("MONGO_URL"):
        return url
    user = os.getenv("MONGO_USER", "anomaly")
    password = os.getenv("MONGO_PASSWORD", "")
    port = os.getenv("MONGO_PORT", "27018")
    return f"mongodb://{user}:{password}@localhost:{port}/"


MONGO_DB = os.getenv("MONGO_DB", "anomaly")


def _track_key(track_ids: list[int]) -> str:
    return "-".join(str(t) for t in sorted(track_ids))


@dataclass
class Episode:
    """`start_ts`/`end_ts` (Candidate.ts) SAHNE zamanidir -- dosya kaynaginda
    kare indeksi/FPS'ten gelir, `session_passes()` ve Spark ile ayni saat.
    `wall_start`/`wall_end` DUVAR saatidir (Frame.ts, VideoSource) -- halka
    tamponun kendisi bu saatle tutulur, klip secimi bunlari kullanmali. Dosya
    kaynaginda iki saat AYNI DEGILDIR (sahne zamani 0'dan baslar, duvar saati
    gercek epoch'tur); ikisini karistirmak klip secimini hep bos dondururdu."""

    camera_id: str
    track_key: str
    anomaly_type: str
    candidates: list[Candidate] = field(default_factory=list)
    wall_ts_list: list[float] = field(default_factory=list)   # candidates[i] <-> wall_ts_list[i]
    last_seen: float = 0.0
    wall_start: float = 0.0
    wall_end: float = 0.0

    def add(self, cand: Candidate, wall_ts: float) -> None:
        if not self.candidates:
            self.wall_start = wall_ts
        self.candidates.append(cand)
        self.wall_ts_list.append(wall_ts)
        self.last_seen = cand.ts
        self.wall_end = wall_ts

    @property
    def start_ts(self) -> float:
        return self.candidates[0].ts

    @property
    def end_ts(self) -> float:
        return self.candidates[-1].ts

    @property
    def hits(self) -> int:
        return len(self.candidates)

    @property
    def duration(self) -> float:
        return self.end_ts - self.start_ts

    @property
    def best(self) -> Candidate:
        """En yuksek skorlu aday = en iyi kare varsayimi.
        ponytail: bulaniklik (Laplacian varyansi) veya poz tamlik olcutu
        gerekirse buraya girer."""
        return max(self.candidates, key=lambda c: c.score)

    @property
    def best_wall_ts(self) -> float:
        """`best` adayinin DUVAR saati -- halka tampondan (Frame.ts, ayni
        saat) en iyi kareyi bulmak icin (bkz. Episode docstring)."""
        best_idx = max(range(len(self.candidates)), key=lambda i: self.candidates[i].score)
        return self.wall_ts_list[best_idx]


class EpisodeTracker:
    """SS5.1: adaylar akarken epizot acik kalir; `gap_sec` sessizlikte kapanir.
    Kapanan epizot `session_passes()`'i gecmezse hic dondurulmez."""

    def __init__(self, gap_sec: float = 3.0, min_hits: int = DEFAULT_MIN_HITS,
                 min_sec: dict[str, float] | None = None) -> None:
        self.gap_sec = gap_sec
        self.min_hits = min_hits
        self.min_sec = min_sec
        self._open: dict[tuple[str, str, str], Episode] = {}

    def update(self, camera_id: str, candidates: list[Candidate], now_ts: float,
               wall_ts: float | None = None) -> list[Episode]:
        """`now_ts`/adaylarin `ts`'i SAHNE zamanidir (gap ve `session_passes`
        bunu kullanir). `wall_ts` DUVAR saatidir (halka tampon eslesmesi
        icin, SS5.2); verilmezse `now_ts` ile ayni sayilir (saf birim testleri)."""
        wall_ts = now_ts if wall_ts is None else wall_ts
        for cand in candidates:
            key = (camera_id, _track_key(cand.track_ids), cand.anomaly_type)
            ep = self._open.get(key)
            if ep is None:
                ep = Episode(camera_id, key[1], cand.anomaly_type)
                self._open[key] = ep
            ep.add(cand, wall_ts)

        closed = []
        for key, ep in list(self._open.items()):
            if now_ts - ep.last_seen >= self.gap_sec:
                del self._open[key]
                if session_passes(ep.hits, ep.duration, ep.anomaly_type,
                                   self.min_hits, self.min_sec):
                    closed.append(ep)
        return closed

    def close_all(self, camera_id: str | None = None) -> list[Episode]:
        """Akis bitince (dosya EOF) hala acik epizotlari ZORLA kapatir --
        yoksa `gap_sec`'lik sessizlik hic gelmez ve son epizot hic
        dondurulmez. Kafka tarafinda ayni sorunun cozumu `_EOS` isaretcisiydi
        (ASAMA4_PLAN.md SS5.5); burada dogrudan zorlama yeterli, ayri bir
        mesaj gerekmez -- sunucu icinde tek surec calisiyor."""
        keys = [k for k in self._open if camera_id is None or k[0] == camera_id]
        closed = []
        for key in keys:
            ep = self._open.pop(key)
            if session_passes(ep.hits, ep.duration, ep.anomaly_type,
                               self.min_hits, self.min_sec):
                closed.append(ep)
        return closed


def select_clip_frames(frames: list[Frame], start_ts: float, end_ts: float,
                        pad_sec: float = CLIP_PAD_SEC) -> tuple[list[Frame], bool]:
    """Tampondan `[start_ts-pad, end_ts+pad]` araligina dusen kareleri secer.
    Tampon bu araligi tam kapsamiyorsa (kisa tampon veya uzun epizot) True doner
    -- sessizce kisaltilmaz, `clip_truncated` ile bildirilir (SS5.2#2)."""
    if not frames:
        return [], True
    lo, hi = start_ts - pad_sec, end_ts + pad_sec
    selected = [f for f in frames if lo <= f.ts <= hi]
    truncated = frames[0].ts > lo or frames[-1].ts < hi
    return selected, truncated


def nearest_frame(frames: list[Frame], ts: float) -> Frame | None:
    if not frames:
        return None
    return min(frames, key=lambda f: abs(f.ts - ts))


class _PoseBuffer:
    """Tek izin son `POSE_BUFFER_SEC` saniyelik iskelet ornekleri.
    Epizot kapanmadan once biriktirilir, kapaninca dilimlenir (SS6)."""

    def __init__(self, maxlen_sec: float = POSE_BUFFER_SEC) -> None:
        self.maxlen_sec = maxlen_sec
        self.last_ts = 0.0
        self._samples: deque[dict] = deque()

    def add(self, sample: dict) -> None:
        self._samples.append(sample)
        self.last_ts = sample["ts"]
        while self._samples and sample["ts"] - self._samples[0]["ts"] > self.maxlen_sec:
            self._samples.popleft()

    def slice(self, lo: float, hi: float) -> list[dict]:
        return [s for s in self._samples if lo <= s["ts"] <= hi]


@dataclass
class _Job:
    episode: Episode
    frames: list[Frame]
    truncated: bool
    pose_samples: list[dict]


class EvidenceWriter:
    """Ana goru dongusu `on_frame`'i her karede cagirir. Arka plan thread'i
    kapanan epizotlari klip + kare + mongo + API POST'a cevirir."""

    def __init__(self, source: VideoSource, *, storage_dir: str = "storage",
                 spark_window_sec: float = 3.0, min_hits: int = DEFAULT_MIN_HITS,
                 min_sec: dict[str, float] | None = None,
                 api_base_url: str = "", token: str = "",
                 mongo_url: str = "", queue_max: int = 8,
                 epoch_base: float = 0.0) -> None:
        self.source = source
        self.storage_dir = Path(storage_dir)
        self.tracker = EpisodeTracker(spark_window_sec, min_hits, min_sec)
        self._pose: dict[tuple[str, int], _PoseBuffer] = {}
        # cand.ts SAHNE zamanidir; events.started_at (Spark/consumer) ise
        # epoch_base + cand.ts (vision/publish.py candidate_to_dict ile ayni
        # anlasma). Klip dosya adi ve POST /api/evidence govdesi bu yuzden
        # epoch_base'e gore hesaplanir -- yoksa events tablosuyla ASLA
        # eslesmez (ASAMA6_PLAN.md SS8.2, 3 sn tolerans).
        self.epoch_base = epoch_base
        self._api_base_url = api_base_url.rstrip("/") if api_base_url else ""
        self._headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._mongo_url = mongo_url
        self._mongo = None

        self._queue: queue.Queue[_Job] = queue.Queue(maxsize=queue_max)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

        self.dropped = 0
        self.written_clips = 0
        self.written_frames = 0
        self.posted = 0
        self.post_failed = 0
        self.mongo_failed = 0
        self.last_error = ""

    def start(self) -> None:
        self._thread = threading.Thread(target=self._writer_loop, name="evidence-writer", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            # mp4 kodlama buyuk/4K epizotlarda saniyeler surebilir; kisa bir
            # timeout burada thread'i yari yazilmis (moov atom'suz, bozuk)
            # dosyayla yariya keserdi -- olculen gercek bir hata (bkz.
            # ASAMA6_PLAN.md rapor notu). Halka tampon 300 kareyle sinirli
            # oldugu icin en kotu durum sinirlidir.
            self._thread.join(timeout=30.0)
            if self._thread.is_alive():
                self.last_error = "yazma kuyrugu 30 sn icinde bosalmadi, thread hala calisiyor"

    def on_frame(self, camera_id: str, idx: int, ts: float, wall_ts: float,
                 tracks: list[Track], candidates: list[Candidate]) -> None:
        """Ana goru dongusunden HER karede cagrilir -- I/O yok, hafif.
        `ts` sahne zamani (Candidate.ts ile ayni saat), `wall_ts` duvar
        saatidir (`Frame.ts` ile ayni saat, halka tampon eslesmesi icin)."""
        for track in tracks:
            buf = self._pose.setdefault((camera_id, track.track_id), _PoseBuffer())
            buf.add({
                "idx": idx, "ts": ts,
                "bbox": [float(v) for v in track.bbox],
                "kp": track.keypoints.tolist() if track.keypoints is not None else None,
                "kp_smoothed": track.keypoints_smoothed.tolist()
                if track.keypoints_smoothed is not None else None,
            })

        # Kaybolan izlerin tamponu silinir: _PoseBuffer kendi ornek listesini
        # kirpiyor ama SOZLUK girdisi kaliciydi -- gunlerce donen bir kamerada
        # gorulen her track_id sonsuza kadar birikirdi. POSE_BUFFER_SEC (20 sn)
        # sessizlik epizot bosluğundan (3 sn) uzundur, yani silinen tampon
        # acik bir epizoda lazim olamaz.
        stale = [k for k, buf in self._pose.items() if ts - buf.last_ts > POSE_BUFFER_SEC]
        for key in stale:
            del self._pose[key]

        for ep in self.tracker.update(camera_id, candidates, ts, wall_ts):
            self._close_episode(camera_id, ep)

    def flush(self, camera_id: str) -> None:
        """Akis bitince (dosya EOF) cagrilir -- hala acik epizotlari zorla
        kapatir. Aksi halde `gap_sec`'lik sessizlik hic gelmez ve klibin son
        epizotu (orn. dusme klibin sonuna yakin oluyorsa) hic yazilmaz --
        Kafka/Spark tarafindaki `_EOS` sorununun ayni sekilde `vision/`'da
        yasanan hali (ASAMA4_PLAN.md SS5.5)."""
        for ep in self.tracker.close_all(camera_id):
            self._close_episode(camera_id, ep)

    def _close_episode(self, camera_id: str, ep: Episode) -> None:
        # Halka tampon Frame.ts ile (DUVAR saati) tutulur -- ep.start_ts/
        # end_ts (SAHNE zamani) kullanilirsa dosya kaynaginda hicbir kare
        # eslesmez (bkz. Episode docstring).
        frames, truncated = select_clip_frames(
            self.source.snapshot(), ep.wall_start, ep.wall_end)
        pose_samples = self._collect_pose(camera_id, ep)
        self._enqueue(_Job(ep, frames, truncated, pose_samples))

    def _collect_pose(self, camera_id: str, ep: Episode) -> list[dict]:
        lo, hi = ep.start_ts - CLIP_PAD_SEC, ep.end_ts + CLIP_PAD_SEC
        samples: list[dict] = []
        for track_id_str in ep.track_key.split("-"):
            buf = self._pose.get((camera_id, int(track_id_str)))
            if buf is not None:
                samples.extend(buf.slice(lo, hi))
        samples.sort(key=lambda s: s["ts"])
        return samples

    def _enqueue(self, job: _Job) -> None:
        try:
            self._queue.put_nowait(job)
        except queue.Full:
            try:
                self._queue.get_nowait()
                self.dropped += 1
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(job)
            except queue.Full:
                self.dropped += 1

    def _writer_loop(self) -> None:
        # `stop()` sadece BOS kuyrukta cikisi tetikler -- son karede kapanan
        # bir epizot `stop()` cagrisiyla yarisirsa sessizce kaybolmamali,
        # kuyrukta bekleyen isler tukeninceye kadar islenmeye devam eder.
        while True:
            try:
                job = self._queue.get(timeout=0.2)
            except queue.Empty:
                if self._stop.is_set():
                    return
                continue
            try:
                self._write_job(job)
            except Exception as exc:  # noqa: BLE001
                self.last_error = f"{type(exc).__name__}: {exc}"

    def _write_job(self, job: _Job) -> None:
        ep = job.episode
        # events.started_at ile ayni saat (epoch_base + sahne zamani) --
        # dosya adi ve POST govdesi buna gore, klip/kare secimi DUVAR
        # saatine gore kalir (job.frames zaten wall_start/wall_end ile secildi).
        event_start = self.epoch_base + ep.start_ts
        event_end = self.epoch_base + ep.end_ts
        stem = f"{ep.camera_id}_{ep.anomaly_type}_{int(event_start * 1000)}"

        # YALNIZ gercekten yazilan dosyanin yolu bildirilir. Yazilmayan bir
        # yolu POST etmek veritabanina dolu gorunen ama diskte olmayan bir
        # kayit birakirdi: GET /api/events/{id}/clip 404 doner ve SS12 olcum
        # 5 ("clip_path dolu satir sayisi") oldugundan iyi cikar.
        clip_rel = frame_rel = None
        if job.frames:
            clip_rel = f"clips/{stem}.mp4"
            self._write_clip(self.storage_dir / clip_rel, job.frames)
            self.written_clips += 1

        best_frame = nearest_frame(job.frames, ep.best_wall_ts)
        if best_frame is not None:
            frame_rel = f"frames/{stem}.jpg"
            path = self.storage_dir / frame_rel
            path.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(path), best_frame.image, [cv2.IMWRITE_JPEG_QUALITY, 90])
            self.written_frames += 1

        mongo_ref = self._write_pose_sequence(ep, job.pose_samples)
        self._post_evidence(ep, event_start, event_end, clip_rel, frame_rel,
                            job.truncated, mongo_ref)

    def _write_clip(self, path: Path, frames: list[Frame]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        h, w = frames[0].image.shape[:2]
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"),
                                  self.source.fps, (w, h))
        for f in frames:
            writer.write(f.image)
        writer.release()

    def _write_pose_sequence(self, ep: Episode, samples: list[dict]) -> str | None:
        """Mongo erisilemezse kanit DURMAZ -- mongo_ref None gider, sayac artar."""
        if not self._mongo_url:
            return None
        try:
            if self._mongo is None:
                from pymongo import MongoClient
                self._mongo = MongoClient(self._mongo_url)
            db = self._mongo[MONGO_DB]
            doc = {
                "event_id": None,
                "camera_id": ep.camera_id,
                "track_id": ep.track_key,
                "anomaly_type": ep.anomaly_type,
                "fps": self.source.fps,
                "frames": samples,
                "normalization": {"origin": "mid_hip", "scale": "bbox_height"},
                # BSON Date olmali, float epoch DEGIL: infra/mongo/init.js
                # pose_sequences.created_at uzerine 90 gunluk TTL indeksi
                # koyuyor ve MongoDB TTL'i yalnizca Date alaninda calisir --
                # float yazilirsa belgeler hicbir zaman silinmez.
                "created_at": datetime.datetime.now(datetime.timezone.utc),
            }
            result = db.pose_sequences.insert_one(doc)
            return str(result.inserted_id)
        except Exception as exc:  # noqa: BLE001
            self.mongo_failed += 1
            self.last_error = f"mongo: {exc}"
            return None

    def _post_evidence(self, ep: Episode, start_time: float, end_time: float,
                        clip_rel: str | None, frame_rel: str | None,
                        truncated: bool, mongo_ref: str | None) -> None:
        if not self._api_base_url:
            return
        body = {
            "camera_id": ep.camera_id, "anomaly_type": ep.anomaly_type,
            "track_key": ep.track_key, "start_time": start_time, "end_time": end_time,
            "frame_path": frame_rel, "clip_path": clip_rel,
            "clip_truncated": truncated, "mongo_ref": mongo_ref,
        }
        try:
            resp = httpx.post(f"{self._api_base_url}/api/evidence", json=body,
                               headers=self._headers, timeout=5.0)
            resp.raise_for_status()
            self.posted += 1
        except (httpx.HTTPError, ValueError) as exc:
            self.post_failed += 1
            self.last_error = f"evidence post: {exc}"
