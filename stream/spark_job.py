"""Spark Structured Streaming: anomaly-candidates -> oturum -> anomaly-events.

Plandan sapma (ASAMA4_PLAN.md SS5.1): PLAN.md kayan pencere (3 sn, 1 sn kayma)
istiyordu. Kesintisiz N saniyelik bir olay kayan pencerede N/kayma ayri satir
yazar -- Asama 5 tuketicisi ayni olayi onlarca kez isler (DB satiri, LLM
cagrisi, Telegram mesaji). session_window (Spark 3.2+) kesintisiz episodu TEK
satirda toplar; hits ve sure bedava gelir, tek kare gurultusu hits=1 oturumu
olarak zaten elenir.

Cift olcut + tipe gore sure esigi icin SS5.3: FALL bir darbedir (2 aday, sahte
RUN 11 aday uretiyor -- tek esik ikisini ayiramaz), RUN/ZONE/LOITERING bir
durumdur. Esik mantiginin referans kopyasi stream/filters.py'dedir; burada
sutun ifadesiyle (create_map/element_at) ayni sey uygulanir -- streaming
DAG'inde UDF yerine native ifade tercih edildi (Python GIL'e gecis yok).

_EOS toplamadan once ELENMEZ (SS5.5): filtre groupBy'dan SONRA uygulanir,
yoksa damga (watermark) hic ilerlemez ve _EOS'un tek islevi yok olur.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from pyspark.sql import SparkSession
from pyspark.sql.functions import coalesce, col, concat_ws, count, create_map
from pyspark.sql.functions import element_at, from_json, lit
from pyspark.sql.functions import max as spark_max
from pyspark.sql.functions import max_by
from pyspark.sql.functions import min as spark_min
from pyspark.sql.functions import session_window, struct, to_json
from pyspark.sql.types import (ArrayType, DoubleType, IntegerType, MapType,
                                StringType, StructField, StructType)

# docker-compose "./stream:/app:ro" ile bu klasoru DUZLESTIRIR (spark_job.py
# ve filters.py /app icinde yan yanadir, stream/ paketi container'da yok).
# spark-submit script'in kendi dizinini sys.path'e ekler, o yuzden burada
# paket-nitelikli degil duz import: yerelde `stream.filters`, konteynerde
# `filters`. sys.path fallback ikisini de calistirir.
import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parent))
try:
    from stream.filters import MIN_SEC_DEFAULT_MAP
except ModuleNotFoundError:
    from filters import MIN_SEC_DEFAULT_MAP

BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:29092")
GAP_SEC = int(os.getenv("SPARK_GAP_SEC", "3"))
WATERMARK_SEC = int(os.getenv("SPARK_WATERMARK_SEC", "2"))
MIN_HITS = int(os.getenv("SPARK_MIN_HITS", "2"))
MIN_SEC_DEFAULT = float(os.getenv("SPARK_MIN_SEC_DEFAULT", "1.0"))
MIN_SEC = json.loads(os.getenv("SPARK_MIN_SEC", json.dumps(MIN_SEC_DEFAULT_MAP)))
CHECKPOINT_DIR = os.getenv("CHECKPOINT_DIR", "/checkpoints")
SCHEMA_VERSION = 1

# ASAMA6_PLAN.md SS9: spark_min_sec/spark_min_hits/spark_window_sec panelden
# degistirilebilir ama akan sorguya GOMULU -- ancak Spark yeniden baslayinca
# gecerli olur (checkpoint uyumsuzlugu yuzunden sicak yukleme YOK, bilinclidir).
# API_URL bos ise ozellik kapali sayilir (docker-compose SETTINGS_API_URL
# saglamadikca), yukaridaki ortam degiskeni varsayilanlari aynen kalir.
SETTINGS_API_URL = os.getenv("SETTINGS_API_URL", "")
SETTINGS_API_TOKEN = os.getenv("SETTINGS_API_TOKEN", "")


def fetch_settings_from_api() -> tuple[int, int, dict[str, float]] | None:
    """GET /api/settings (global) -> (window_sec, min_hits, min_sec).
    `urllib.request`: Spark imajina yeni paket girmiyor. Ulasilamazsa (ag
    hatasi, 401, bozuk JSON) None doner -- cagiran ortam degiskeni
    varsayilanlarina duser ve tek satir uyari basar."""
    if not SETTINGS_API_URL:
        return None
    req = urllib.request.Request(f"{SETTINGS_API_URL.rstrip('/')}/api/settings")
    if SETTINGS_API_TOKEN:
        req.add_header("Authorization", f"Bearer {SETTINGS_API_TOKEN}")
    try:
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return (int(data["spark_window_sec"]), int(data["spark_min_hits"]),
                dict(data["spark_min_sec"]))
    except (urllib.error.URLError, ValueError, KeyError, TypeError) as exc:
        print(f"  [spark_job] esik API'sinden okunamadi, ortam varsayilanlari "
              f"kullaniliyor: {exc}")
        return None

CANDIDATE_SCHEMA = StructType([
    StructField("schema", IntegerType()),
    StructField("camera_id", StringType()),
    StructField("anomaly_type", StringType()),
    StructField("track_key", StringType()),
    StructField("track_ids", ArrayType(IntegerType())),
    StructField("score", DoubleType()),
    StructField("idx", IntegerType()),
    StructField("ts", DoubleType()),
    StructField("event_time", DoubleType()),
    StructField("zone_name", StringType()),
    StructField("metrics", MapType(StringType(), DoubleType())),
    StructField("thresholds_used", MapType(StringType(), DoubleType())),
])


def build_min_sec_map():
    """Python sozlugunden Spark create_map ifadesi kurar (SS5.3)."""
    items: list = []
    for k, v in MIN_SEC.items():
        items += [lit(k), lit(float(v))]
    return create_map(*items)


def main() -> None:
    global GAP_SEC, MIN_HITS, MIN_SEC
    fetched = fetch_settings_from_api()
    if fetched is not None:
        GAP_SEC, MIN_HITS, MIN_SEC = fetched
        print(f"  [spark_job] esikler API'den alindi: window={GAP_SEC}s "
              f"min_hits={MIN_HITS} min_sec={MIN_SEC}")

    spark = SparkSession.builder.appName("anomaly-spark").getOrCreate()
    spark.sparkContext.setLogLevel("WARN")

    raw = (spark.readStream.format("kafka")
           .option("kafka.bootstrap.servers", BOOTSTRAP)
           .option("subscribe", "anomaly-candidates")
           .option("startingOffsets", "latest")
           # Kafka log'u KALICI DEGIL (docker-compose.yml karari) ama checkpoint
           # volume'u kalici: broker yeniden kurulunca topic offset'i 0'a doner,
           # checkpoint hala 12'yi bekler ve sorgu "offset was changed from 12
           # to 0" ile duser. Kalici olmayan bir log'da veri kaybi zaten kabul
           # edilmis bir maliyettir; olaylar PostgreSQL'de yasar. Kafka log'u
           # kalici yapilirsa bu satir kaldirilabilir.
           .option("failOnDataLoss", "false")
           .load())

    cand = (raw.select(from_json(col("value").cast("string"), CANDIDATE_SCHEMA).alias("c"))
            .select("c.*")
            .withColumn("event_time", col("event_time").cast("timestamp"))
            .withWatermark("event_time", f"{WATERMARK_SEC} seconds"))

    sessions = (cand.groupBy(
                    session_window(col("event_time"), f"{GAP_SEC} seconds"),
                    col("camera_id"), col("track_key"), col("anomaly_type"))
                .agg(count(lit(1)).alias("hits"),
                     spark_min("ts").alias("start_ts"),
                     spark_max("ts").alias("end_ts"),
                     spark_min("event_time").alias("start_time"),
                     spark_max("event_time").alias("end_time"),
                     spark_max("score").alias("score"),
                     max_by(col("track_ids"), col("score")).alias("track_ids"),
                     max_by(col("zone_name"), col("score")).alias("zone_name"),
                     max_by(col("metrics"), col("score")).alias("metrics"),
                     max_by(col("thresholds_used"), col("score")).alias("thresholds_used")))

    min_sec_map = build_min_sec_map()
    confirmed = sessions.where(
        (col("hits") >= MIN_HITS) &
        ((col("end_ts") - col("start_ts")) >=
         coalesce(element_at(min_sec_map, col("anomaly_type")), lit(MIN_SEC_DEFAULT))))

    out = confirmed.select(
        concat_ws(":", "camera_id", "track_key", "anomaly_type",
                  col("start_time").cast("string")).alias("key"),
        to_json(struct(
            lit(SCHEMA_VERSION).alias("schema"),
            col("camera_id"), col("anomaly_type"), col("track_key"), col("track_ids"),
            col("hits"),
            col("start_ts"), col("end_ts"),
            (col("end_ts") - col("start_ts")).alias("duration_sec"),
            col("start_time").cast("double").alias("start_time"),
            col("end_time").cast("double").alias("end_time"),
            col("score"), col("zone_name"), col("metrics"), col("thresholds_used"),
        )).alias("value"))

    (out.writeStream.format("kafka")
     .option("kafka.bootstrap.servers", BOOTSTRAP)
     .option("topic", "anomaly-events")
     .option("checkpointLocation", CHECKPOINT_DIR)
     .outputMode("append")
     .start().awaitTermination())


if __name__ == "__main__":
    main()
