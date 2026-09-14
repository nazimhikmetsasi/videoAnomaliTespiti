"""Kur/Birak anahtari: Evde modunda bildirim bastirilir, tespit surer.

TEZ_KAPSAM.txt Faz 1: "Kur/Birak: Evde = bildirim yok, Koruma = alarm".
Olculen davranis, bastirmanin LLM cagrisindan ONCE olmasidir -- kimseye
gitmeyecek bir rapor icin kota harcanmamalidir.

Veritabani gerektirmez: `_is_armed` ve Notification yazimi sahte oturumla
olculur.

    venv\\Scripts\\python.exe -m pytest tests/test_armed.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class _FakeResult:
    def __init__(self, value=None, rows=None, mapping=None) -> None:
        self._value, self._rows, self._mapping = value, rows or [], mapping

    def scalar(self):
        return self._value

    def mappings(self):
        return self

    def first(self):
        return self._mapping

    def all(self):
        return self._rows


class _FakeSession:
    """execute() cagrilarini SQL metnine gore yonlendirir; added listesi
    hangi Notification satirlarinin yazildigini gosterir."""

    def __init__(self, armed: bool, event_row: dict | None) -> None:
        self.armed, self.event_row = armed, event_row
        self.added: list = []
        self.commits = 0
        self.sql_log: list[str] = []

    def execute(self, clause, params=None):
        sql = str(clause)
        self.sql_log.append(sql)
        if "FROM events e" in sql:
            return _FakeResult(mapping=self.event_row)
        if "armed" in sql:
            return _FakeResult(value=self.armed)
        if "telegram_chat_id" in sql:
            return _FakeResult(rows=[])
        return _FakeResult()

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commits += 1

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


EVENT_ROW = {
    "camera_id": 3, "anomaly_type": "FALL", "confidence": 0.9, "duration_ms": 1200,
    "started_at": None, "track_ids": [7], "severity": "critical",
    "frame_path": None, "camera_name": "kamera_01", "zone_name": None,
}


@pytest.fixture()
def notify(monkeypatch):
    """api.notify'i veritabani ve LLM olmadan yukler."""
    import api.notify as mod
    for key in mod._counters:
        mod._counters[key] = 0
    return mod


def test_evde_modunda_llm_cagrilmaz_ve_skipped_yazilir(notify, monkeypatch) -> None:
    session = _FakeSession(armed=False, event_row=dict(EVENT_ROW))
    monkeypatch.setattr(notify, "SessionLocal", lambda: session)

    def patlayan_llm(ctx):
        raise AssertionError("Evde modunda LLM cagrilmamali -- kota harcanir")

    monkeypatch.setattr(notify, "generate_report", patlayan_llm)

    notify._process_event(42)

    assert notify._counters["skipped"] == 1
    assert notify._counters["sent"] == 0
    assert len(session.added) == 1
    kayit = session.added[0]
    assert kayit.status == "skipped" and kayit.event_id == 42
    # Denetlenebilirlik: neden gonderilmedigi kayitta yazili
    assert "evde" in (kayit.error or "").lower()


def test_koruma_modunda_akis_devam_eder(notify, monkeypatch) -> None:
    session = _FakeSession(armed=True, event_row=dict(EVENT_ROW))
    monkeypatch.setattr(notify, "SessionLocal", lambda: session)
    monkeypatch.setattr(notify, "generate_report", lambda ctx: ("rapor", "template"))
    monkeypatch.setattr(notify, "TELEGRAM_CHAT_ID", "")

    notify._process_event(42)

    assert notify._counters["skipped"] == 0
    assert notify._counters["template"] == 1
    # Alici yok -> gonderim yok, ama rapor YAZILDI (SS4.6 sirasi korunuyor)
    assert any("llm_report_tr" in sql for sql in session.sql_log)


def test_armed_sorgusu_kamera_satirini_globalden_once_sorar(notify) -> None:
    session = _FakeSession(armed=True, event_row=None)
    notify._is_armed(session, 3)
    sql = session.sql_log[-1]
    assert sql.index("camera_id = :cam") < sql.index("camera_id IS NULL")


def test_sorgu_bos_donerse_kurulu_sayilir(notify) -> None:
    """Ariza durumunda sistem SESSIZLESMEMELI: guvenli taraf gurultulu olan.
    `bool(None)` False verir; bu test o tuzagin geri gelmesini engeller."""
    session = _FakeSession(armed=None, event_row=None)
    assert notify._is_armed(session, 3) is True


def test_olay_bulunamazsa_sessiz_cikar(notify, monkeypatch) -> None:
    session = _FakeSession(armed=False, event_row=None)
    monkeypatch.setattr(notify, "SessionLocal", lambda: session)
    notify._process_event(999)
    assert session.added == [] and notify._counters["skipped"] == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
