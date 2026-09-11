"""Asama 10.5 oz kontrolu: uzun kosu ozetinin ilk saat / son saat ayrimi.

Kosu gerektirmez -- sentetik CSV ile olculur. Onemli olan ozetin CURUMEYI
dogru yerden okumasi: 8 saatlik kayitta "ilk saat" ve "son saat" farkli
satir kumeleridir, ortalama alinirsa sizinti gorunmez.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.soak_test import FIELDS, report  # noqa: E402


def _csv(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "soak.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _row(dakika: float, **over) -> dict:
    row = {k: 0 for k in FIELDS}
    row.update(ts=f"t{dakika}", gecen_dk=dakika, kamera=4, fps_toplam=24.0,
               fps_min=5.8, infer_ms_ort=19.0, goru_rss_mb=2600.0,
               gpu_mb=2100.0, olay_sayisi=1000, storage_mb=50.0)
    row.update(over)
    return row


def test_ozet_ilk_ve_son_saati_ayirir(tmp_path, capsys) -> None:
    rows = ([_row(m, goru_rss_mb=2600.0) for m in (0, 30, 60)]
            + [_row(m, goru_rss_mb=2600.0) for m in (120, 240)]
            + [_row(m, goru_rss_mb=5200.0) for m in (420, 450, 480)])
    assert report(_csv(tmp_path, rows)) == 0
    out = capsys.readouterr().out
    assert "8.0 saat" in out
    # RSS ikiye katlandi: ozet bunu +%100 olarak GORMELI (ortalama alsaydi
    # sizinti seyrelir ve tabloda kaybolurdu).
    assert "+100.0%" in out


def test_tek_satirli_kayit_ozetlenmez(tmp_path, capsys) -> None:
    assert report(_csv(tmp_path, [_row(0)])) == 1
    assert "en az 2 satir" in capsys.readouterr().out
