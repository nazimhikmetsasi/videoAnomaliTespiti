"""Kanit saklama politikasi: yas kurali, boyut tavani ve budama araligi.

Diske gercek dosya yazar (tmp_path) -- budama mtime ve st_size uzerinden
calisiyor, sahte dosya sistemi bu davranisi olcmez.

    venv\\Scripts\\python.exe -m pytest tests/test_retention.py -q
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vision.retention import Retention, prune  # noqa: E402

MB = 1024 * 1024


def _make(root: Path, sub: str, name: str, *, size: int, age_days: float) -> Path:
    path = root / sub / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\0" * size)
    when = time.time() - age_days * 86400.0
    os.utime(path, (when, when))
    return path


def test_yas_kurali_klip_ve_kareyi_ayri_sureyle_siler(tmp_path: Path) -> None:
    eski_klip = _make(tmp_path, "clips", "a_FALL_1.mp4", size=MB, age_days=10)
    yeni_klip = _make(tmp_path, "clips", "b_FALL_2.mp4", size=MB, age_days=2)
    # Kare klipten UZUN yasar: 10 gunluk kare 90 gun sinirini gecmez
    eski_kare = _make(tmp_path, "frames", "a_FALL_1.jpg", size=1024, age_days=10)
    cok_eski_kare = _make(tmp_path, "frames", "c_FALL_3.jpg", size=1024, age_days=100)

    result = prune(tmp_path, clip_days=7, frame_days=90, max_gb=100)

    assert not eski_klip.exists()
    assert yeni_klip.exists()
    assert eski_kare.exists(), "kare klip omrune degil kendi omrune tabi"
    assert not cok_eski_kare.exists()
    assert result.deleted == 2


def test_yas_sifirsa_kural_kapali(tmp_path: Path) -> None:
    klip = _make(tmp_path, "clips", "a_FALL_1.mp4", size=MB, age_days=365)
    prune(tmp_path, clip_days=0, frame_days=0, max_gb=100)
    assert klip.exists()


def test_boyut_tavani_en_eski_klipten_baslayarak_siler(tmp_path: Path) -> None:
    """Uc klip, her biri 4 MB. Tavan 10 MB -> en eski bir tanesi gitmeli."""
    eski = _make(tmp_path, "clips", "a.mp4", size=4 * MB, age_days=3)
    orta = _make(tmp_path, "clips", "b.mp4", size=4 * MB, age_days=2)
    yeni = _make(tmp_path, "clips", "c.mp4", size=4 * MB, age_days=1)

    result = prune(tmp_path, clip_days=7, frame_days=90, max_gb=10 / 1024)

    assert not eski.exists()
    assert orta.exists() and yeni.exists()
    assert result.total_bytes_after == 8 * MB


def test_tavan_asilsa_bile_kareler_silinmez(tmp_path: Path) -> None:
    """Kareler deponun kucuk bir parcasi; hepsini silmek tavani kurtarmaz
    ama panelin tum gorsel gecmisini goturur."""
    _make(tmp_path, "clips", "a.mp4", size=8 * MB, age_days=1)
    kare = _make(tmp_path, "frames", "a.jpg", size=MB, age_days=1)

    prune(tmp_path, clip_days=7, frame_days=90, max_gb=1 / 1024)

    assert kare.exists()


def test_taninmayan_uzanti_ve_dizine_dokunulmaz(tmp_path: Path) -> None:
    """Depo yolu disaridan (--storage-dir) geliyor; genis silme yetkisi
    kaza riskidir."""
    baska = _make(tmp_path, "clips", "notlar.txt", size=MB, age_days=365)
    disarda = _make(tmp_path, "raporlar", "eski.mp4", size=MB, age_days=365)

    prune(tmp_path, clip_days=1, frame_days=1, max_gb=0)

    assert baska.exists() and disarda.exists()


def test_retention_araliktan_once_tekrar_budamaz(tmp_path: Path) -> None:
    keeper = Retention(tmp_path, clip_days=7, frame_days=90, max_gb=100,
                       min_interval=60.0)
    _make(tmp_path, "clips", "a.mp4", size=MB, age_days=10)

    ilk = keeper.maybe_prune(now=100.0)
    assert ilk is not None and ilk.deleted == 1

    _make(tmp_path, "clips", "b.mp4", size=MB, age_days=10)
    assert keeper.maybe_prune(now=130.0) is None, "aralik dolmadan kosmamali"
    assert (tmp_path / "clips" / "b.mp4").exists()

    ikinci = keeper.maybe_prune(now=161.0)
    assert ikinci is not None and ikinci.deleted == 1
    assert keeper.deleted == 2


def test_ilk_cagri_beklemeden_kosar(tmp_path: Path) -> None:
    """Uzun kosunun basinda devralinan eski dosyalar ilk aralik dolana kadar
    diskte durmamali."""
    keeper = Retention(tmp_path, clip_days=7, frame_days=90, max_gb=100)
    _make(tmp_path, "clips", "a.mp4", size=MB, age_days=10)
    assert keeper.maybe_prune(now=0.0) is not None


def test_eksik_depo_dizini_cokmez(tmp_path: Path) -> None:
    result = prune(tmp_path / "yok", clip_days=7, frame_days=90, max_gb=1)
    assert result.deleted == 0 and result.errors == 0


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
