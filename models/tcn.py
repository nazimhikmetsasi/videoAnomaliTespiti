"""Asama 9.3: iskelet dizisi siniflandiricisi (TCN) — tanim, egitim, cikarim.

Girdi (Asama 13.3) ZAMAN IZGARASIDIR: bir izin ornekleri `resample` ile
GRID_HZ (25 Hz) izgarasina oturtulur, (50, 53) pencere = son 1.96 sn. Boylece
canli kamera 10 FPS'te de calissa model egitimde gordugu zaman olcegini gorur.
Egitim verisi `eval/extract_sequences.py` ham iz dosyalaridir (data/tracks);
pencereler ve kare dusurme artirimi burada, egitim aninda kurulur. Kanal
duzeni ve gerekcesi docs/ASAMA9_PLAN.md SS2'de.

Mimari: genisletilmis (dilated) nedensel Conv1d, 5 blok, 64 kanal, genisleme
1-2-4-8-16 -> alim alani 63 nokta, yani tum pencere tek gecelisde gorulur.
LSTM/Transformer denenmedi: sabit 50 noktalik pencerede ikisi de daha cok
parametre ve daha yavas cikarim demek.

    venv/Scripts/python.exe -m models.tcn --train
    venv/Scripts/python.exe -m models.tcn --train --epochs 60
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import zlib
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

from vision.stages.features import STALE_SEC

CLASSES = ("NORMAL", "FALL", "RUN", "FIGHT")
WINDOW, CHANNELS = 50, 53
GRID_HZ = 25.0           # model girdisinin zaman izgarasi
WINDOW_SEC = (WINDOW - 1) / GRID_HZ     # 1.96 sn
KP_CONF = 0.5            # bunun altindaki eklem iki kare arasinda ara degerlenmez
# Egitim penceresi kaydirmasi, butun siniflarda ayni (25 FPS'te 10 kare). Eski
# kare tabanli pencere 30 FPS klipte 1.67 sn'ydi; 1.96 sn'lik pencereyle 25
# karelik kaydirma kisa kliplerden (FIGHT ortanca 2.8 sn) pencere sayisini
# yariya indiriyordu (bitint_box_0002: 10 -> 5).
STRIDE_SEC = 0.4
AUGMENT_FPS = (15.0, 10.0, 5.0)         # egitim/dogrulama icin kare dusurme hizlari
MIN_POSE_RATIO = 0.6     # penceredeki pozlu kare orani bunun altindaysa pencere duser
WEIGHTS_PATH = Path(__file__).resolve().parent / "tcn.pt"
META_PATH = Path(__file__).resolve().parent / "tcn_meta.json"
VAL_EVERY = 5            # her 5. KLIP dogrulamaya — bolme klip bazinda (sizinti yok)
EPS = 1e-6               # zaman karsilastirmalarinda kayan nokta payi


class FrameDropper:
    """Kare hizini dusurur: canli kameranin (~10 FPS) islem hizini taklit eder.

    Cagrilar `ts` sirasiyla yapilir; True = kare islenir. `jitter` modunda adim
    U(0.5, 1.5) ile carpilir (degisken isleme suresi), ortalama hiz hedefte kalir.
    """

    def __init__(self, target_fps: float, mode: str = "regular", seed: int = 0) -> None:
        if mode not in ("regular", "jitter"):
            raise ValueError(f"bilinmeyen mod: {mode}")
        self.step = 1.0 / target_fps if target_fps > 0 else 0.0
        self.mode = mode
        self.rng = np.random.default_rng(seed)
        self.next_t: float | None = None

    def _step(self) -> float:
        if self.mode == "jitter":
            return self.step * float(self.rng.uniform(0.5, 1.5))
        return self.step

    def __call__(self, ts: float) -> bool:
        if self.step <= 0:
            return True
        if self.next_t is None:
            self.next_t = ts + self._step()
            return True
        if ts < self.next_t - EPS:
            return False
        self.next_t += self._step()
        if self.next_t < ts:          # kaynakta bosluk: kareler patlama olmasin
            self.next_t = ts + self._step()
        return True


def frame_vector(bbox: np.ndarray, kp: np.ndarray | None,
                 prev_bbox: np.ndarray | None, dt: float) -> np.ndarray:
    """Tek karenin 53 kanali. Poz yoksa iskelet kanallari sifir kalir.

    Egitim (eval/extract_sequences) ve calisma zamani (vision/rules/arbiter)
    AYNI fonksiyonu cagirir; iki kopya olsa biri degistiginde model uretimde
    baska bir uzayda calismaya baslardi ve bu sessizce olurdu.
    """
    vec = np.zeros(CHANNELS, dtype=np.float32)
    x1, y1, x2, y2 = (float(v) for v in bbox)
    width, height = max(x2 - x1, 1e-6), max(y2 - y1, 1e-6)
    if kp is not None:
        norm = (kp[:, :2] - np.array([x1, y1])) / np.array([width, height])
        vec[:34] = norm.reshape(-1)
        vec[34:51] = kp[:, 2]
    if prev_bbox is not None and dt > 0:
        now = np.array([(x1 + x2) / 2, (y1 + y2) / 2])
        before = np.array([(prev_bbox[0] + prev_bbox[2]) / 2,
                           (prev_bbox[1] + prev_bbox[3]) / 2])
        # bbox'a normalizasyon kuresel hareketi siliyor; RUN aksi halde
        # yuruyusten ayirt edilemezdi. Saniyeye bolunur: iz kare atladiginda
        # yer degistirme buyur ama HIZ ayni kalir (FeatureEngine._velocity ile
        # ayni anlasma).
        vec[51:53] = (now - before) / height / dt
    return vec


class Block(nn.Module):
    def __init__(self, channels: int, dilation: int) -> None:
        super().__init__()
        # Nedensel dolgu: sol tarafa (dilation * 2) kadar, sagdan kirpilir --
        # pencerenin sonu gelecege bakmaz.
        self.pad = dilation * 2
        self.conv = nn.Conv1d(channels, channels, 3, dilation=dilation)
        self.norm = nn.BatchNorm1d(channels)
        self.act = nn.ReLU()
        self.drop = nn.Dropout(0.2)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        y = nn.functional.pad(x, (self.pad, 0))
        return x + self.drop(self.act(self.norm(self.conv(y))))


class TCN(nn.Module):
    def __init__(self, channels: int = CHANNELS, hidden: int = 64,
                 classes: int = len(CLASSES)) -> None:
        super().__init__()
        self.stem = nn.Conv1d(channels, hidden, 1)
        self.blocks = nn.Sequential(*[Block(hidden, d) for d in (1, 2, 4, 8, 16)])
        self.head = nn.Linear(hidden, classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (B, 50, 53) -> (B, sinif) ham skor."""
        h = self.blocks(self.stem(x.transpose(1, 2)))
        return self.head(h.mean(dim=2))


def resample(ts: np.ndarray, bbox: np.ndarray, kp: np.ndarray, has_pose: np.ndarray,
             t_end: float | None = None) -> np.ndarray | None:
    """Tek izin ornekleri (ts artan) -> (WINDOW, CHANNELS); kapsam/poz yetersizse None.

    Izgara t_end'den geriye 1/GRID_HZ adimli. Her nokta iki komsu ornekten
    ara degerlenir; satirlar yine `frame_vector`dan gecer (tek kaynak).
    """
    ts = np.asarray(ts, dtype=np.float64)
    if t_end is None:
        t_end = float(ts[-1])
    n = int(np.searchsorted(ts, t_end + EPS, side="right"))
    if n == 0:
        return None
    ts, bbox, kp, has_pose = ts[:n], bbox[:n], kp[:n], has_pose[:n]
    grid = t_end - (WINDOW - 1 - np.arange(WINDOW)) / GRID_HZ
    if ts[0] > grid[0] + EPS:
        return None
    # +EPS: izgara zamanina kayan nokta payiyla oturan ornek 'a' sayilir (w~0);
    # 25 FPS girdi boylece eski kare-kare vektorleri aynen uretir.
    a = np.clip(np.searchsorted(ts, grid + EPS, side="right") - 1, 0, n - 1)
    b = np.minimum(a + 1, n - 1)
    span = ts[b] - ts[a]
    ok = span > 0
    w = np.clip(np.where(ok, (grid - ts[a]) / np.where(ok, span, 1.0), 0.0), 0.0, 1.0)
    bbox_g = bbox[a] + (bbox[b] - bbox[a]) * w[:, None]
    both = has_pose[a] & has_pose[b]
    near = np.where(w <= 0.5, a, b)
    pose_g = both | has_pose[near]
    if pose_g.mean() < MIN_POSE_RATIO:
        return None
    kp_a, kp_b = kp[a], kp[b]
    lerp = kp_a + (kp_b - kp_a) * w[:, None, None]
    # Guveni dusuk eklemde ara deger eklemi uydurur: guveni yuksek komsunun
    # konumu alinir. w ~ 0 / 1 ise nokta zaten bir ornege oturuyor, dokunulmaz.
    low = ((kp_a[..., 2] < KP_CONF) | (kp_b[..., 2] < KP_CONF)) \
        & ((w > EPS) & (w < 1 - EPS))[:, None]
    better = np.where((kp_a[..., 2] >= kp_b[..., 2])[..., None], kp_a[..., :2], kp_b[..., :2])
    lerp[..., :2] = np.where(low[..., None], better, lerp[..., :2])
    kp_g = np.where(both[:, None, None], lerp, kp[near])
    out = np.empty((WINDOW, CHANNELS), dtype=np.float32)
    for k in range(WINDOW):
        out[k] = frame_vector(bbox_g[k], kp_g[k] if pose_g[k] else None,
                              bbox_g[k - 1] if k > 0 else None, 1.0 / GRID_HZ)
    return out


def split_runs(ts: np.ndarray) -> list[np.ndarray]:
    """Iz STALE_SEC'ten uzun kayboluyorsa pencere zinciri kopar (indeks dizileri).

    Uretimde de oyle: FeatureEngine bu kadar gorulmeyen izin durumunu dusurur.
    Daha kisa bosluklar korunur; kesintisiz kare sarti kliplerin cogunu eliyordu.
    """
    cut = np.flatnonzero(np.diff(ts) > STALE_SEC + EPS) + 1
    return np.split(np.arange(len(ts)), cut)


def clip_windows(data: dict, stride_sec: float,
                 keep: np.ndarray | None = None) -> tuple[np.ndarray, int]:
    """Bir klibin iz dosyasi -> (N, WINDOW, CHANNELS) ve DUSURULEN pencere sayisi.

    `keep`: kare indeksi uzerinde bool maske (kare dusurme artirimi); None = hepsi.
    Pencere sonu hep GERCEK bir ornektir (calisma zamaninda da oyle). `event_frames`
    doluysa pencere olay karesini icermiyorsa duser (URFD kare bazli etiketi).
    """
    fps = float(data["fps"])
    frame, track = data["frame"], data["track"]
    sel = np.ones(len(frame), bool) if keep is None else keep[frame]
    events = np.asarray(data["event_frames"], dtype=np.float64) / fps
    kept, dropped = [], 0
    for tid in np.unique(track[sel]):
        idx = np.flatnonzero(sel & (track == tid))
        all_ts = frame[idx] / fps
        for run in split_runs(all_ts):
            r = idx[run]
            ts, bbox, kp, hp = all_ts[run], data["bbox"][r], data["kp"][r], data["has_pose"][r]
            prev_end, j = -1, 0
            while True:
                t = ts[0] + WINDOW_SEC + j * stride_sec
                if t > ts[-1] + EPS:
                    break
                j += 1
                # Hedeften SONRAKI ilk ornek: geriye cekmek (t'den onceki ornek)
                # pencereyi WINDOW_SEC'in altina dusurup resample'a None
                # dondurtuyordu -- 30 FPS'te ilk pencere hic cikmiyordu.
                end = int(np.searchsorted(ts, t - EPS, side="left"))
                if end == prev_end:
                    continue
                prev_end = end
                t_end = ts[end]
                if events.size and not np.any((events >= t_end - WINDOW_SEC - EPS)
                                              & (events <= t_end + EPS)):
                    dropped += 1
                    continue
                window = resample(ts[:end + 1], bbox[:end + 1], kp[:end + 1],
                                  hp[:end + 1], t_end)
                if window is None:
                    dropped += 1
                else:
                    kept.append(window)
    stack = np.stack(kept) if kept else np.empty((0, WINDOW, CHANNELS), np.float32)
    return stack, dropped


def augment_keep(n_frames: int, fps: float, target_fps: float, seed: int) -> np.ndarray:
    """Klip duzeyinde kare dusurme maskesi (bool, kare indeksi uzerinde).

    Seyreltici klibin TUM zaman cizgisinde kosar: yalniz iz gorulen karelerde
    kossaydi izsiz araliklar bosluk sayilirdi.
    """
    if target_fps >= fps:
        return np.ones(n_frames, dtype=bool)
    dropper = FrameDropper(target_fps, "jitter", seed)
    return np.array([dropper(t) for t in np.arange(n_frames) / fps], dtype=bool)


def _rate_key(rate: float | None) -> str:
    return "native" if rate is None else f"{rate:g}"


def build_split(root: Path) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """data/tracks -> {"train", "val@native", "val@15", "val@10", "val@5"}: (x, y).

    Bolme KLIP bazinda (i % VAL_EVERY); ayni klibin butun hiz kopyalari ayni
    tarafta kalir, sizinti yok. Bos iz dosyalari atlanir ama sira numarasini
    korur (bolme eski veriyle ayni kalir).
    """
    rates: list[float | None] = [None, *AUGMENT_FPS]
    xs: dict[str, list] = {}
    ys: dict[str, list] = {}
    counts: dict[tuple[str, str, str], int] = {}
    for label, name in enumerate(CLASSES):
        stride = STRIDE_SEC
        for i, path in enumerate(sorted((root / name).glob("*.npz"))):
            with np.load(path) as npz:
                data = {k: npz[k] for k in npz.files}
            if not len(data["frame"]):
                continue
            val = i % VAL_EVERY == 0
            fps, n_frames = float(data["fps"]), int(data["n_frames"])
            seed = zlib.crc32(path.stem.encode())
            for rate in rates:
                if rate is not None and rate >= fps and not val:
                    continue        # kopya olurdu: egitimde ayni pencereyi ikiletme
                keep = None if rate is None else augment_keep(n_frames, fps, rate, seed)
                stack, _ = clip_windows(data, stride, keep)
                if not stack.shape[0]:
                    continue
                key = f"val@{_rate_key(rate)}" if val else "train"
                xs.setdefault(key, []).append(stack)
                ys.setdefault(key, []).append(np.full(stack.shape[0], label, np.int64))
                cell = (name, "val" if val else "train", _rate_key(rate))
                counts[cell] = counts.get(cell, 0) + stack.shape[0]
    keys = ["train"] + [f"val@{_rate_key(r)}" for r in rates]
    out = {}
    for key in keys:
        if key in xs:
            out[key] = (np.concatenate(xs[key]), np.concatenate(ys[key]))
        else:
            out[key] = (np.empty((0, WINDOW, CHANNELS), np.float32), np.empty(0, np.int64))
    names = [_rate_key(r) for r in rates]
    print(f"  {'sinif':8} {'bolme':6} " + " ".join(f"{n:>8}" for n in names))
    for name in CLASSES:
        for part in ("train", "val"):
            print(f"  {name:8} {part:6} " + " ".join(
                f"{counts.get((name, part, n), 0):8d}" for n in names))
    return out


def val_concat(split: dict[str, tuple[np.ndarray, np.ndarray]]) -> tuple[np.ndarray, np.ndarray]:
    parts = [v for k, v in split.items() if k.startswith("val@") and v[0].shape[0]]
    return np.concatenate([x for x, _ in parts]), np.concatenate([y for _, y in parts])


def load_split(root: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """(x_tr, y_tr, x_va, y_va); dogrulama butun hizlarin birlesimi."""
    split = build_split(root)
    x_tr, y_tr = split["train"]
    if not x_tr.shape[0] or not any(k.startswith("val@") and v[0].shape[0]
                                    for k, v in split.items()):
        raise SystemExit(f"{root} bos veya tek tarafli — once eval.extract_sequences")
    x_va, y_va = val_concat(split)
    return x_tr, y_tr, x_va, y_va


def scores(confusion: np.ndarray) -> list[tuple[str, float, float, float, int]]:
    out = []
    for i, name in enumerate(CLASSES):
        tp = confusion[i, i]
        precision = tp / max(confusion[:, i].sum(), 1)
        recall = tp / max(confusion[i].sum(), 1)
        f1 = 2 * precision * recall / max(precision + recall, 1e-9)
        out.append((name, precision, recall, f1, int(confusion[i].sum())))
    return out


def confusion_of(model: nn.Module, x: torch.Tensor, y: torch.Tensor,
                 batch: int = 512) -> np.ndarray:
    model.eval()
    matrix = np.zeros((len(CLASSES), len(CLASSES)), dtype=np.int64)
    with torch.no_grad():
        for start in range(0, x.shape[0], batch):
            pred = model(x[start:start + batch]).argmax(dim=1)
            for gercek, tahmin in zip(y[start:start + batch].tolist(), pred.tolist()):
                matrix[gercek, tahmin] += 1
    return matrix


def train(root: Path, epochs: int, device: str) -> None:
    torch.manual_seed(0)
    np.random.seed(0)
    split = build_split(root)
    x_tr, y_tr = split["train"]
    if not x_tr.shape[0] or not any(k.startswith("val@") and v[0].shape[0]
                                    for k, v in split.items()):
        raise SystemExit(f"{root} bos veya tek tarafli — once eval.extract_sequences")
    x_va, y_va = val_concat(split)
    mean = x_tr.reshape(-1, CHANNELS).mean(axis=0)
    std = x_tr.reshape(-1, CHANNELS).std(axis=0) + 1e-6
    print(f"  egitim {x_tr.shape[0]} pencere / dogrulama {x_va.shape[0]} pencere")
    print("  sinif dagilimi (egitim): " +
          "  ".join(f"{n}={int((y_tr == i).sum())}" for i, n in enumerate(CLASSES)))

    to = lambda a: torch.tensor((a - mean) / std, dtype=torch.float32, device=device)
    x_tr_t, x_va_t = to(x_tr), to(x_va)
    y_tr_t = torch.tensor(y_tr, device=device)
    y_va_t = torch.tensor(y_va, device=device)

    counts = np.bincount(y_tr, minlength=len(CLASSES)).astype(np.float32)
    weight = torch.tensor(counts.sum() / (len(CLASSES) * np.maximum(counts, 1)),
                          dtype=torch.float32, device=device)
    model = TCN().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.CrossEntropyLoss(weight=weight)

    best_f1, best_state, patience = -1.0, None, 0
    for epoch in range(1, epochs + 1):
        model.train()
        order = torch.randperm(x_tr_t.shape[0], device=device)
        total = 0.0
        for start in range(0, order.shape[0], 128):
            idx = order[start:start + 128]
            optimizer.zero_grad()
            loss = loss_fn(model(x_tr_t[idx]), y_tr_t[idx])
            loss.backward()
            optimizer.step()
            total += float(loss) * idx.shape[0]
        macro_f1 = float(np.mean([f for _, _, _, f, _ in
                                  scores(confusion_of(model, x_va_t, y_va_t))]))
        print(f"  epoch {epoch:3d}  kayip {total / order.shape[0]:.4f}  "
              f"dogrulama makro F1 {macro_f1:.3f}")
        if macro_f1 > best_f1:
            best_f1, patience = macro_f1, 0
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
        else:
            patience += 1
            if patience >= 10:      # erken durdurma
                print(f"  10 epoch iyilesme yok, duruldu")
                break

    model.load_state_dict(best_state)
    matrix = confusion_of(model, x_va_t, y_va_t)
    print(f"\n  karisiklik matrisi (satir = gercek, sutun = tahmin)")
    print("            " + "".join(f"{n:>9}" for n in CLASSES))
    for i, name in enumerate(CLASSES):
        print(f"  {name:9} " + "".join(f"{v:9d}" for v in matrix[i]))
    print(f"\n  {'sinif':9} {'kesinlik':>9} {'duyarlilik':>11} {'F1':>7} {'pencere':>9}")
    for name, precision, recall, f1, support in scores(matrix):
        print(f"  {name:9} {precision:9.3f} {recall:11.3f} {f1:7.3f} {support:9d}")
    print(f"  makro F1 {best_f1:.3f}")
    by_rate: dict[str, float] = {}
    print("\n  dogrulama makro F1, hiz basina:")
    for key, (xv, yv) in split.items():
        if not key.startswith("val@") or not xv.shape[0]:
            continue
        m = confusion_of(model, to(xv), torch.tensor(yv, device=device))
        by_rate[key[4:]] = float(np.mean([f for _, _, _, f, _ in scores(m)]))
        print(f"    {key[4:]:>8} {by_rate[key[4:]]:.3f}  ({xv.shape[0]} pencere)")

    sample = x_va_t[:1]
    for _ in range(10):
        model(sample)
    torch.cuda.synchronize() if device.startswith("cuda") else None
    t0 = time.perf_counter()
    for _ in range(100):
        model(sample)
    torch.cuda.synchronize() if device.startswith("cuda") else None
    print(f"  pencere basina cikarim {(time.perf_counter() - t0) * 10:.2f} ms")

    torch.save(model.state_dict(), WEIGHTS_PATH)
    META_PATH.write_text(json.dumps({
        "classes": list(CLASSES), "window": WINDOW, "channels": CHANNELS,
        "mean": mean.tolist(), "std": std.tolist(),
        "val_macro_f1": best_f1,
        "grid_hz": GRID_HZ, "window_sec": WINDOW_SEC,
        "augment_fps": list(AUGMENT_FPS), "val_macro_f1_by_rate": by_rate,
        "trained_at": time.strftime("%Y-%m-%d %H:%M"),
    }, indent=2), encoding="utf-8")
    print(f"  kaydedildi: {WEIGHTS_PATH.name}, {META_PATH.name}")


class TCNClassifier:
    """Cikarim sarmalayicisi — HybridArbiter bunu kullanir."""

    def __init__(self, device: str = "cuda") -> None:
        meta = json.loads(META_PATH.read_text(encoding="utf-8"))
        if meta.get("grid_hz") != GRID_HZ:
            raise ValueError("tcn_meta.json kare tabanli girdiyle egitilmis model; "
                             "models.tcn --train ile yeniden egit")
        self.classes = tuple(meta["classes"])
        self.mean = np.array(meta["mean"], dtype=np.float32)
        self.std = np.array(meta["std"], dtype=np.float32)
        self.device = device
        self.model = TCN(classes=len(self.classes)).to(device)
        self.model.load_state_dict(torch.load(WEIGHTS_PATH, map_location=device))
        self.model.eval()

    def __call__(self, windows: np.ndarray) -> np.ndarray:
        """(N, 50, 53) izgara penceresi -> (N, sinif) olasilik."""
        x = torch.tensor((windows - self.mean) / self.std,
                         dtype=torch.float32, device=self.device)
        with torch.no_grad():
            return torch.softmax(self.model(x), dim=1).cpu().numpy()


def main() -> int:
    parser = argparse.ArgumentParser(description="TCN egitimi")
    parser.add_argument("--train", action="store_true")
    parser.add_argument("--tracks", default="data/tracks")
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = parser.parse_args()
    if not args.train:
        parser.print_help()
        return 2
    train(Path(args.tracks), args.epochs, args.device)
    return 0


if __name__ == "__main__":
    sys.exit(main())
