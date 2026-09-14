"""Dosya kaynagini gercek zamanli akitma (--realtime).

Neden var: `started_at` = epoch_base + idx/fps, yani SAHNE zamanidir. Dosya
diskin hizinda okunursa sahne zamani duvar saatinden kayar ve bu kayma
dogrudan "uctan uca gecikme"ye eklenir -- olculdu, dosya kaynagindan alinan
gecikmeler on binlerce saniyeye ciktiginda hattin hizini degil BIRIKMIS
isleme gecikmesini olcuyorlardi.

    venv\\Scripts\\python.exe -m pytest tests/test_realtime_source.py -q
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vision.source import VideoSource  # noqa: E402

FPS = 20.0
KARE = 12


@pytest.fixture()
def klip(tmp_path: Path) -> Path:
    """Kucuk bir mp4 -- gercek dosya lazim, VideoSource cv2 ile aciyor."""
    path = tmp_path / "test.mp4"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"),
                             FPS, (64, 48))
    assert writer.isOpened(), "mp4 yazici acilamadi"
    for i in range(KARE):
        frame = np.full((48, 64, 3), i * 10 % 255, dtype=np.uint8)
        writer.write(frame)
    writer.release()
    assert path.is_file() and path.stat().st_size > 0
    return path


def _hepsini_oku(src: VideoSource) -> int:
    sayi = 0
    while (frame := src.read(timeout=3.0)) is not None:
        sayi += 1
        if sayi >= KARE:
            break
    return sayi


def test_realtime_kapaliyken_kaynak_hizi_sinirlanmaz(klip: Path) -> None:
    with VideoSource(str(klip)) as src:
        basla = time.monotonic()
        okunan = _hepsini_oku(src)
        gecen = time.monotonic() - basla
    assert okunan == KARE
    # 12 kare / 20 FPS = 0.6 sn; sinirlama yokken bunun cok altinda biter.
    assert gecen < 0.30, f"beklenenden yavas: {gecen:.2f} sn"


def test_realtime_acikken_kaynak_kendi_fpsinde_akar(klip: Path) -> None:
    with VideoSource(str(klip), realtime=True) as src:
        basla = time.monotonic()
        okunan = _hepsini_oku(src)
        gecen = time.monotonic() - basla
    assert okunan == KARE
    beklenen = (KARE - 1) / FPS          # ilk kare beklemez
    assert gecen >= beklenen * 0.8, f"cok hizli: {gecen:.2f} < {beklenen:.2f}"
    assert gecen < beklenen + 0.6, f"cok yavas: {gecen:.2f} sn"


def test_canli_kaynakta_realtime_yok_sayilir() -> None:
    """Canli kaynak zaten kendi hizinda gelir; yavaslatmak kare dusurur.

    Kamera ACILMAZ: yalnizca kurucunun bayragi nasil cozdugu olculuyor ve
    gercek webcam bu sirada baska bir surec tarafindan kullaniliyor olabilir.
    `start()` cagrilmadigi surece okuma is parcacigi baslamaz."""
    src = VideoSource(0, realtime=True)
    assert src.is_live is True
    assert src.realtime is False


def test_realtime_varsayilan_kapali(klip: Path) -> None:
    """eval/ kosulari dosyayi olabildigince hizli islemeli."""
    assert VideoSource(str(klip)).realtime is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
