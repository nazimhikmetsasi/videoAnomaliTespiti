#!/usr/bin/env bash
# Kafka topic'lerini olusturur. Tekrar calistirilabilir (--if-not-exists).
# Compose'da kafka-init servisi bunu bir kez calistirir ve cikar.
# Elle: docker compose run --rm kafka-init
set -euo pipefail

BOOTSTRAP="${KAFKA_BOOTSTRAP:-localhost:9092}"
KT=/opt/kafka/bin/kafka-topics.sh

create() {
    "$KT" --bootstrap-server "$BOOTSTRAP" --create --if-not-exists \
          --topic "$1" --partitions "$2" --replication-factor 1 \
          --config retention.ms="$3"
}

# vision/ -> Spark. Ham aday olaylar, hacimli, kisa omurlu (1 saat).
create anomaly-candidates 3 3600000

# Spark -> event worker. Dogrulanmis olaylar, uzun omurlu (24 saat).
create anomaly-events 3 86400000

echo "--- mevcut topic'ler ---"
"$KT" --bootstrap-server "$BOOTSTRAP" --list
