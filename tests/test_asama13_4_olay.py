"""Asama 13.4 Paket A: dusme sonucu -- tuketici, bildirim, goc, panel.

Veritabani gerektirenler Postgres'e erisilemezse skip eder.

    venv\\Scripts\\python.exe -m pytest tests/test_asama13_4_olay.py -q
"""

from __future__ import annotations

import datetime
import queue as queue_mod
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import api.notify as notify  # noqa: E402
from api.workers import consumer  # noqa: E402
from api.workers.consumer import PendingOutcomes, outcome_to_update  # noqa: E402

UTC = datetime.timezone.utc
T0 = 1_700_000_000.0


def _msg(**over) -> dict:
    base = {
        "schema": 1, "camera_id": "cam1", "track_id": 7, "fall_time": T0,
        "fall_ts": 12.4, "outcome": "down", "decided_ts": 37.4, "adopted": [],
        "metrics": {"decided_after_sec": 25.0, "last_seen_ago_sec": 0.2},
    }
    base.update(over)
    return base


# ------------------------------------------------------------ Tuketici (saf)
def test_outcome_to_update_full() -> None:
    upd = outcome_to_update(_msg())
    assert upd is not None
    assert upd["camera_id"] == "cam1" and upd["track_id"] == 7 and upd["outcome"] == "down"
    assert upd["fall_time"] == datetime.datetime.fromtimestamp(T0, tz=UTC)
    assert upd["metrics"]["decided_after_sec"] == 25.0


def test_outcome_to_update_metrics_optional() -> None:
    m = _msg()
    del m["metrics"]
    assert outcome_to_update(m)["metrics"] == {}


@pytest.mark.parametrize("field", ["camera_id", "track_id", "fall_time", "outcome"])
def test_outcome_to_update_missing_field(field: str) -> None:
    m = _msg()
    del m[field]
    assert outcome_to_update(m) is None


@pytest.mark.parametrize("over", [
    {"outcome": "dead"}, {"outcome": None}, {"track_id": "x"}, {"track_id": 1.5},
    {"track_id": True}, {"fall_time": "abc"}, {"fall_time": None}, {"camera_id": ""},
    {"camera_id": None},
])
def test_outcome_to_update_bad_values(over: dict) -> None:
    assert outcome_to_update(_msg(**over)) is None


@pytest.mark.parametrize("o", ["down", "recovered", "unknown"])
def test_outcome_to_update_all_outcomes(o: str) -> None:
    assert outcome_to_update(_msg(outcome=o))["outcome"] == o


# ------------------------------------------------------------ PendingOutcomes
class _Clock:
    def __init__(self) -> None:
        self.t = 100.0

    def __call__(self) -> float:
        return self.t


def test_pending_add_match_remove() -> None:
    p = PendingOutcomes(clock=_Clock())
    a, b = {"id": "a"}, {"id": "b"}
    p.add(1, a)
    p.add(1, b)
    p.add(2, {"id": "c"})
    assert len(p) == 3
    done = p.retry(1, lambda u: (5, "new") if u["id"] == "a" else None)
    assert done == [(a, (5, "new"))]
    assert len(p) == 2                       # a gitti, b ve kamera 2'ninki kaldi
    assert p.retry(1, lambda u: None) == []  # eslesmeyen kalir
    assert len(p) == 2


def test_pending_expires_after_ttl_and_counts() -> None:
    clock = _Clock()
    p = PendingOutcomes(ttl=60.0, clock=clock)
    p.add(1, {"id": "a"})
    clock.t += 30
    p.add(1, {"id": "b"})
    clock.t += 31                  # a: 61 sn, b: 31 sn
    assert p.expire() == 1
    assert len(p) == 1
    clock.t += 30
    assert p.expire() == 1
    assert len(p) == 0 and p.expire() == 0


# ------------------------------------------------------------ Tuketici (DB)
def _live_session():
    from api.db.migrate import run_migrations
    from api.db.postgres import SessionLocal
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        db.close()
        pytest.skip(f"veritabanina erisilemiyor: {exc}")
    run_migrations()   # idempotent; acilista zaten kosar
    return db


@pytest.fixture()
def db():
    session = _live_session()
    try:
        yield session
    finally:
        session.rollback()   # hicbir sey commit edilmez
        session.close()


def _camera(db) -> int:
    return db.execute(text(
        "INSERT INTO cameras (name, source, source_type) VALUES ('t13_4', 'x', 'file') RETURNING id"
    )).scalar()


def _event(db, cam: int, started: datetime.datetime, tids=(7,), sev="critical",
           status="new") -> int:
    return db.execute(text("""
        INSERT INTO events (camera_id, anomaly_type, track_ids, confidence, severity,
                            decided_by, started_at, status)
        VALUES (:c, 'FALL', :t, 0.9, :s, 'rule', :st, :status) RETURNING id
    """), {"c": cam, "t": list(tids), "s": sev, "st": started, "status": status}).scalar()


def _upd(outcome: str, tid: int = 7, t: float = T0) -> dict:
    return outcome_to_update(_msg(outcome=outcome, track_id=tid, fall_time=t))


def _row(db, ev: int):
    return db.execute(text("SELECT severity, fall_outcome FROM events WHERE id = :i"),
                      {"i": ev}).first()


def test_apply_recovered_lowers_critical_to_high(db) -> None:
    cam = _camera(db)
    ev = _event(db, cam, datetime.datetime.fromtimestamp(T0, tz=UTC))
    assert consumer._apply_outcome(db, cam, _upd("recovered")) == (ev, "new")
    assert tuple(_row(db, ev)) == ("high", "recovered")


def test_apply_recovered_keeps_high_and_down_keeps_critical(db) -> None:
    cam = _camera(db)
    ev_high = _event(db, cam, datetime.datetime.fromtimestamp(T0, tz=UTC), sev="high")
    assert consumer._apply_outcome(db, cam, _upd("recovered")) is not None
    assert tuple(_row(db, ev_high)) == ("high", "recovered")
    ev_crit = _event(db, cam, datetime.datetime.fromtimestamp(T0 + 100, tz=UTC))
    assert consumer._apply_outcome(db, cam, _upd("down", t=T0 + 100)) is not None
    assert tuple(_row(db, ev_crit)) == ("critical", "down")
    ev_unk = _event(db, cam, datetime.datetime.fromtimestamp(T0 + 200, tz=UTC))
    assert consumer._apply_outcome(db, cam, _upd("unknown", t=T0 + 200)) is not None
    assert tuple(_row(db, ev_unk)) == ("critical", "unknown")


def test_apply_twice_changes_nothing(db) -> None:
    cam = _camera(db)
    ev = _event(db, cam, datetime.datetime.fromtimestamp(T0, tz=UTC))
    assert consumer._apply_outcome(db, cam, _upd("down")) == (ev, "new")
    assert consumer._apply_outcome(db, cam, _upd("recovered")) is None
    assert tuple(_row(db, ev)) == ("critical", "down")


def test_apply_no_match_outside_tolerance_or_other_track(db) -> None:
    cam = _camera(db)
    tol = consumer.tolerance().total_seconds()
    ev = _event(db, cam, datetime.datetime.fromtimestamp(T0, tz=UTC))
    assert consumer._apply_outcome(db, cam, _upd("down", t=T0 + tol + 5)) is None
    assert consumer._apply_outcome(db, cam, _upd("down", tid=99)) is None
    assert _row(db, ev)[1] is None


def test_apply_picks_nearest_started_at(db) -> None:
    cam = _camera(db)
    far = _event(db, cam, datetime.datetime.fromtimestamp(T0 - 2, tz=UTC), tids=(7, 8))
    near = _event(db, cam, datetime.datetime.fromtimestamp(T0 + 0.5, tz=UTC), tids=(7,))
    assert consumer._apply_outcome(db, cam, _upd("down"))[0] == near
    assert _row(db, far)[1] is None


# ------------------------------------------------------------ Bildirim
def _saat(started: datetime.datetime) -> str:
    return started.astimezone().strftime("%H:%M:%S")


STARTED = datetime.datetime.fromtimestamp(T0, tz=UTC)


def test_text_down_still_on_floor() -> None:
    t = notify.outcome_text("down", "kamera_01", STARTED,
                            {"decided_after_sec": 25.0, "last_seen_ago_sec": 0.4})
    assert t == (f"⚠️ KALKAMADI — kamera_01\n{_saat(STARTED)}'teki düşmeden 25 sn sonra "
                 f"kişi hâlâ yerde.")


def test_text_down_not_seen_for_long() -> None:
    t = notify.outcome_text("down", "kamera_01", STARTED,
                            {"decided_after_sec": 25.0, "last_seen_ago_sec": 24.2})
    assert t == (f"⚠️ KALKAMADI — kamera_01\n{_saat(STARTED)}'teki düşmeden sonra kişinin "
                 f"kalktığı görülmedi. Son 24 sn'dir kamerada görünmüyor; "
                 f"son görüldüğünde yerdeydi.")


def test_text_down_stale_boundary() -> None:
    at = notify.outcome_text("down", "k", STARTED, {"decided_after_sec": 25, "last_seen_ago_sec": 3.6})
    over = notify.outcome_text("down", "k", STARTED, {"decided_after_sec": 25, "last_seen_ago_sec": 3.7})
    assert "hâlâ yerde" in at and "görünmüyor" in over


def test_text_recovered() -> None:
    t = notify.outcome_text("recovered", "kamera_01", STARTED, {"recovered_after_sec": 5.2})
    assert t == (f"✅ KALKTI — kamera_01\n{_saat(STARTED)}'teki düşmeden 5 sn sonra kişi "
                 f"ayağa kalktı. Önem yüksek'e indirildi.")


def test_text_unknown_is_none() -> None:
    assert notify.outcome_text("unknown", "k", STARTED, {}) is None


def test_enqueue_outcome_item_and_drop_oldest() -> None:
    old = notify._queue
    notify._queue = queue_mod.Queue(maxsize=2)
    try:
        notify.enqueue(1)
        notify.enqueue_outcome(2, "down", {"a": 1.0})
        notify.enqueue_outcome(3, "recovered", {})   # dolu: en eski (event 1) dusmeli
        items = [notify._queue.get_nowait(), notify._queue.get_nowait()]
    finally:
        notify._queue = old
    assert items == [("outcome", 2, {"outcome": "down", "metrics": {"a": 1.0}}),
                     ("outcome", 3, {"outcome": "recovered", "metrics": {}})]


def test_worker_dispatches_by_kind() -> None:
    calls: list = []
    old_q, old = notify._queue, (notify._process_event, notify._process_outcome,
                                 notify.NOTIFY_MIN_INTERVAL_SEC, notify._sleep)
    notify._queue = queue_mod.Queue()
    notify.enqueue(5)
    notify.enqueue_outcome(6, "down", {"x": 1})
    notify._queue.put(None)
    notify._process_event = lambda i: calls.append(("event", i))
    notify._process_outcome = lambda i, o, m: calls.append(("outcome", i, o, m))
    notify.NOTIFY_MIN_INTERVAL_SEC = 0.0
    notify._sleep = lambda s: None
    try:
        notify._worker_loop()
    finally:
        notify._queue = old_q
        (notify._process_event, notify._process_outcome,
         notify.NOTIFY_MIN_INTERVAL_SEC, notify._sleep) = old
    assert calls == [("event", 5), ("outcome", 6, "down", {"x": 1})]


class _Res:
    def __init__(self, value=None, rows=None, mapping=None) -> None:
        self._v, self._rows, self._m = value, rows or [], mapping

    def scalar(self): return self._v
    def mappings(self): return self
    def first(self): return self._m
    def all(self): return self._rows


class _Sess:
    def __init__(self, armed: bool) -> None:
        self.armed, self.added, self.sql = armed, [], []

    def execute(self, clause, params=None):
        sql = str(clause)
        self.sql.append(sql)
        if "FROM events e" in sql:
            return _Res(mapping={"camera_id": 3, "started_at": STARTED, "camera_name": "kamera_01"})
        if "armed" in sql:
            return _Res(value=self.armed)
        return _Res()   # alici listesi bos -> TELEGRAM_CHAT_ID yedegi

    def add(self, obj): self.added.append(obj)
    def commit(self): pass
    def __enter__(self): return self
    def __exit__(self, *exc): return False


@pytest.fixture()
def sent(monkeypatch):
    out: list = []
    monkeypatch.setattr(notify, "TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setattr(notify, "TELEGRAM_CHAT_ID", "111")
    monkeypatch.setattr(notify, "_send_with_retry",
                        lambda chat, txt, photo: (out.append((chat, txt, photo)) or ("sent", "")))
    monkeypatch.setattr(notify, "generate_report",
                        lambda ctx: (_ for _ in ()).throw(AssertionError("LLM cagrilmamali")))
    return out


def test_process_outcome_sends_template_and_records(sent, monkeypatch) -> None:
    sess = _Sess(armed=True)
    monkeypatch.setattr(notify, "SessionLocal", lambda: sess)
    notify._process_outcome(42, "down", {"decided_after_sec": 25.0, "last_seen_ago_sec": 0.0})
    assert len(sent) == 1 and sent[0][0] == "111" and sent[0][2] is None
    assert sent[0][1].startswith("⚠️ KALKAMADI — kamera_01")
    assert [(n.event_id, n.target, n.status) for n in sess.added] == [(42, "111", "sent")]


def test_process_outcome_evde_modu_skipped(sent, monkeypatch) -> None:
    sess = _Sess(armed=False)
    monkeypatch.setattr(notify, "SessionLocal", lambda: sess)
    notify._process_outcome(42, "recovered", {"recovered_after_sec": 4})
    assert sent == []
    assert len(sess.added) == 1
    assert sess.added[0].status == "skipped" and "evde" in sess.added[0].error


def test_process_outcome_unknown_sends_nothing(sent, monkeypatch) -> None:
    sess = _Sess(armed=True)
    monkeypatch.setattr(notify, "SessionLocal", lambda: sess)
    notify._process_outcome(42, "unknown", {})
    assert sent == [] and sess.added == []


def test_unknown_never_enqueued_by_consumer(monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(notify, "enqueue_outcome", lambda *a: calls.append(a))
    monkeypatch.setattr(consumer, "get_mongo", lambda: (_ for _ in ()).throw(consumer.PyMongoError("x")))
    counters = {"outcome_applied": 0, "mongo_errors": 0}
    consumer._finish_outcome(1, "new", _upd("unknown"), counters)
    consumer._finish_outcome(2, "false_positive", _upd("down"), counters)
    consumer._finish_outcome(3, "new", _upd("recovered"), counters)
    assert [c[0] for c in calls] == [3]
    assert counters == {"outcome_applied": 3, "mongo_errors": 3}   # Mongo hatasi olumcul degil


# ------------------------------------------------------------ Goc
def test_migrations_list_has_fall_outcome_statements() -> None:
    from api.db.migrate import MIGRATIONS
    sqls = [s for n, s in MIGRATIONS if "fall_outcome" in s]
    assert any("ADD COLUMN IF NOT EXISTS fall_outcome" in s for s in sqls)
    drop = next(i for i, s in enumerate(sqls) if "DROP CONSTRAINT IF EXISTS events_fall_outcome_check" in s)
    add = next(i for i, s in enumerate(sqls) if "ADD CONSTRAINT events_fall_outcome_check" in s)
    assert drop < add


def test_migrations_idempotent_on_live_db(db) -> None:
    from api.db.migrate import MIGRATIONS, run_migrations
    first, second = run_migrations(), run_migrations()
    assert len(second) == len(MIGRATIONS) and len(first) == len(MIGRATIONS)
    db.execute(text("SELECT fall_outcome FROM events LIMIT 1"))


# ------------------------------------------------------------ Panel
def _js(name: str) -> str:
    return (ROOT / "frontend" / "js" / f"{name}.js").read_text(encoding="utf-8")


def test_panel_outcome_labels_in_app_js() -> None:
    src = _js("app")
    assert 'down: "kalkamadı"' in src and 'recovered: "kalktı"' in src \
        and 'unknown: "belirsiz"' in src
    assert src.index("DUSME_SONUCU") > src.index("TIP_ADI")


def test_panel_badge_uses_outcome_via_textcontent() -> None:
    lines = _js("olaylar").splitlines()
    i = next(n for n, ln in enumerate(lines) if "ev.fall_outcome" in ln)
    block = "\n".join(lines[max(0, i - 2): i + 2])
    assert "textContent" in block and "DUSME_SONUCU[ev.fall_outcome]" in block
    assert '" · "' in block and "innerHTML" not in block


def test_event_schema_has_fall_outcome() -> None:
    from api.schemas import EventOut
    from api.db.models import Event
    assert "fall_outcome" in EventOut.model_fields and hasattr(Event, "fall_outcome")
