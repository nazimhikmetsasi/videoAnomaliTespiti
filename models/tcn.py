"""Asama 9.3: iskelet dizisi siniflandiricisi (TCN) — tanim, egitim, cikarim.

Girdi `eval/extract_sequences.py` ciktisidir: (50, 53) pencere. Kanal duzeni
ve gerekcesi docs/ASAMA9_PLAN.md SS2'de.

Mimari: genisletilmis (dilated) nedensel Conv1d, 5 blok, 64 kanal, genisleme
1-2-4-8-16 -> alim alani 63 kare, yani tum pencere tek gecelisde gorulur.
LSTM/Transformer denenmedi: sabit 50 karelik pencerede ikisi de daha cok
parametre ve daha yavas cikarim demek.

    venv/Scripts/python.exe -m models.tcn --train
    venv/Scripts/python.exe -m models.tcn --train --epochs 60
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

CLASSES = ("NORMAL", "FALL", "RUN", "FIGHT")
WINDOW, CHANNELS = 50, 53
STRIDE = 25              # egitim penceresi kaydirmasi (eval/extract_sequences)
MIN_POSE_RATIO = 0.6     # penceredeki pozlu kare orani bunun altindaysa pencere duser
WEIGHTS_PATH = Path(__file__).resolve().parent / "tcn.pt"
META_PATH = Path(__file__).resolve().parent / "tcn_meta.json"
VAL_EVERY = 5            # her 5. KLIP dogrulamaya — bolme klip bazinda (sizinti yok)


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


def load_split(root: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """npz'leri okur, KLIP bazinda egitim/dogrulama ayirir.

    Ayni klibin pencereleri iki tarafa dusemez: dusseydi dogrulama skoru
    sisrdi ve tez tablosu gecersiz olurdu.
    """
    parts: dict[str, list] = {"train": [], "val": []}
    labels: dict[str, list] = {"train": [], "val": []}
    for label, name in enumerate(CLASSES):
        files = sorted((root / name).glob("*.npz"))
        for i, path in enumerate(files):
            windows = np.load(path)["x"]
            if not windows.shape[0]:
                continue
            key = "val" if i % VAL_EVERY == 0 else "train"
            parts[key].append(windows)
            labels[key].append(np.full(windows.shape[0], label, dtype=np.int64))
    if not parts["train"] or not parts["val"]:
        raise SystemExit(f"{root} bos veya tek tarafli — once eval.extract_sequences")
    return (np.concatenate(parts["train"]), np.concatenate(labels["train"]),
            np.concatenate(parts["val"]), np.concatenate(labels["val"]))


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
    x_tr, y_tr, x_va, y_va = load_split(root)
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
        "trained_at": time.strftime("%Y-%m-%d %H:%M"),
    }, indent=2), encoding="utf-8")
    print(f"  kaydedildi: {WEIGHTS_PATH.name}, {META_PATH.name}")


class TCNClassifier:
    """Cikarim sarmalayicisi — HybridArbiter bunu kullanir."""

    def __init__(self, device: str = "cuda") -> None:
        meta = json.loads(META_PATH.read_text(encoding="utf-8"))
        self.classes = tuple(meta["classes"])
        self.mean = np.array(meta["mean"], dtype=np.float32)
        self.std = np.array(meta["std"], dtype=np.float32)
        self.device = device
        self.model = TCN(classes=len(self.classes)).to(device)
        self.model.load_state_dict(torch.load(WEIGHTS_PATH, map_location=device))
        self.model.eval()

    def __call__(self, windows: np.ndarray) -> np.ndarray:
        """(N, 50, 53) -> (N, sinif) olasilik."""
        x = torch.tensor((windows - self.mean) / self.std,
                         dtype=torch.float32, device=self.device)
        with torch.no_grad():
            return torch.softmax(self.model(x), dim=1).cpu().numpy()


def main() -> int:
    parser = argparse.ArgumentParser(description="TCN egitimi")
    parser.add_argument("--train", action="store_true")
    parser.add_argument("--sequences", default="data/sequences")
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = parser.parse_args()
    if not args.train:
        parser.print_help()
        return 2
    train(Path(args.sequences), args.epochs, args.device)
    return 0


if __name__ == "__main__":
    sys.exit(main())
