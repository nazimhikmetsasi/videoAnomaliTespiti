// Video Anomali Tespiti v2 - MongoDB koleksiyonlari, indexler, TTL
// docs/PLAN.md bolum 6.2'nin karsiligi.
// Yalnizca bos bir veri diziniyle ilk acilista calisir.
// Baglam: MONGO_INITDB_DATABASE ile belirtilen veritabani.

// Olay basina ham iskelet zaman serisi. Olay detayinda okunur.
db.createCollection("pose_sequences");
db.pose_sequences.createIndex({ event_id: 1 });
db.pose_sequences.createIndex({ camera_id: 1, created_at: -1 });
db.pose_sequences.createIndex({ created_at: 1 }, { expireAfterSeconds: 7776000 }); // 90 gun

// Reddedilenler dahil tum aday pencereler. Asama 9'daki TCN modelinin
// egitim veri seti buradan uretilir - sistem calistikca kendi verisini biriktirir.
db.createCollection("telemetry");
db.telemetry.createIndex({ camera_id: 1, window_start: -1 });
db.telemetry.createIndex({ arbiter: 1 });
db.telemetry.createIndex({ created_at: 1 }, { expireAfterSeconds: 2592000 }); // 30 gun

// Panelde performans grafiginin kaynagi.
db.createCollection("camera_health");
db.camera_health.createIndex({ camera_id: 1, ts: -1 });
db.camera_health.createIndex({ ts: 1 }, { expireAfterSeconds: 604800 }); // 7 gun

print("mongo init: koleksiyonlar ve indexler hazir -> " + db.getName());
