"""Kanit-olay eslesme toleransi (docs/ASAMA6_PLAN.md SS8.2).

Deger `detection_settings.spark_window_sec`ten gelir cunku gerekcesi odur:
ayni epizodun iki ucu (vision'in kanidi, Spark'tan gecen olay) arasindaki en
buyuk fark oturum boslugudur. Panelden pencere 5 sn yapilirsa gomulu 3 sn
sessizce yanlis kalirdi.

ACILISTA BIR KEZ okunur, her mesajda degil. Bu bilincli bir sinirdir ve
SS9'daki Spark davranisiyla ayni: `spark_window_sec` streaming DAG'ine de
acilista gomulur, calisirken degismez. Toleransi Spark'in penceresinden daha
dinamik yapmak anlamsiz olurdu -- pencere degismeden toleransin degismesi
eslesmeyi bozar, duzeltmez.

Veritabani okunamazsa varsayilan 3 sn kalir; tuketici ve API bu yuzden
baslamamazlik etmez.
"""

from __future__ import annotations

import datetime

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from api.db.models import DetectionSettings
from api.db.postgres import SessionLocal

_DEFAULT_SEC = 3
_tolerance = datetime.timedelta(seconds=_DEFAULT_SEC)


def load_tolerance() -> None:
    """Acilista cagrilir (api/main.py lifespan, consumer.run)."""
    global _tolerance
    try:
        with SessionLocal() as db:
            sec = db.scalar(
                select(DetectionSettings.spark_window_sec).where(DetectionSettings.camera_id.is_(None))
            )
    except SQLAlchemyError as exc:
        print(f"  esik satiri okunamadi, kanit toleransi {_DEFAULT_SEC} sn kaldi: {exc}")
        return
    if sec:
        _tolerance = datetime.timedelta(seconds=int(sec))


def tolerance() -> datetime.timedelta:
    return _tolerance
