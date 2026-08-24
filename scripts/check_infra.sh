#!/usr/bin/env bash
# Asama 1 onay kriteri kontrolu.
# Git Bash konteyner ici yollari Windows yoluna cevirir; bu onu kapatir.
# Kullanim: bash scripts/check_infra.sh   (once: docker compose up -d)
set -uo pipefail
export MSYS_NO_PATHCONV=1

FAIL=0
ok()   { echo "  [OK]   $1"; }
bad()  { echo "  [HATA] $1"; FAIL=1; }
check(){ [ "$2" = "$3" ] && ok "$1 = $3" || bad "$1: beklenen '$3', gelen '$2'"; }

# .env'den kullanici/veritabani adlarini al (yoksa varsayilan)
set -a; [ -f .env ] && . ./.env; set +a
PG_USER="${POSTGRES_USER:-anomaly}"; PG_DB="${POSTGRES_DB:-anomaly}"
MG_USER="${MONGO_USER:-anomaly}"; MG_PASS="${MONGO_PASSWORD:-}"; MG_DB="${MONGO_DB:-anomaly}"

psql_q() { docker exec anomaly-postgres psql -U "$PG_USER" -d "$PG_DB" -tAc "$1" 2>/dev/null | tr -d '\r'; }
mongo_q(){ docker exec anomaly-mongo mongosh --quiet -u "$MG_USER" -p "$MG_PASS" \
             --authenticationDatabase admin "$MG_DB" --eval "$1" 2>/dev/null | tr -d '\r'; }

echo "== PostgreSQL =="
TABLES="audit_log cameras detection_settings events notifications users zones"
check "tablo sayisi" "$(psql_q "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")" "7"
for t in $TABLES; do
    [ "$(psql_q "SELECT to_regclass('public.$t') IS NOT NULL")" = "t" ] && ok "tablo $t" || bad "tablo $t yok"
done
check "events index sayisi" "$(psql_q "SELECT count(*) FROM pg_indexes WHERE tablename='events'")" "6"
check "admin kullanicisi"   "$(psql_q "SELECT count(*) FROM users WHERE username='admin' AND role='admin'")" "1"
check "bcrypt hash"         "$(psql_q "SELECT password_hash LIKE '\$2%' FROM users WHERE username='admin'")" "t"
check "global esik satiri"  "$(psql_q "SELECT count(*) FROM detection_settings WHERE camera_id IS NULL")" "1"
# Kismi index ikinci global satiri engellemeli
psql_q "INSERT INTO detection_settings (camera_id) VALUES (NULL)" >/dev/null 2>&1
check "ikinci global satir engellendi" "$(psql_q "SELECT count(*) FROM detection_settings WHERE camera_id IS NULL")" "1"

echo "== MongoDB =="
for c in pose_sequences telemetry camera_health; do
    [ "$(mongo_q "db.getCollectionNames().includes('$c')")" = "true" ] && ok "koleksiyon $c" || bad "koleksiyon $c yok"
done
check "TTL index sayisi" \
  "$(mongo_q "['pose_sequences','telemetry','camera_health'].filter(c=>db[c].getIndexes().some(i=>'expireAfterSeconds' in i)).length")" "3"

echo "== Kafka =="
TOPICS=$(docker exec anomaly-kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list 2>/dev/null | tr -d '\r')
for t in anomaly-candidates anomaly-events; do
    echo "$TOPICS" | grep -qx "$t" && ok "topic $t" || bad "topic $t yok"
done

echo
[ "$FAIL" = "0" ] && echo "Asama 1 onay kriteri saglandi." || echo "Asama 1 kontrolu BASARISIZ."
exit "$FAIL"
