"""Acilista kosan, TEKRARLANABILIR sema gocleri.

`infra/postgres/init.sql` yalnizca veritabani birimi BOSKEN calisir. Bu
projenin calisan kurulumunda 1700'den fazla olay var; init.sql'i
degistirmek o kuruluma hicbir sey yapmaz. Dolayisiyla yeni bir sutun iki
yere birden yazilmalidir: init.sql (temiz kurulum) ve buraya (var olan
kurulum).

Buradaki her ifade IDEMPOTENT olmak zorundadir -- her acilista yeniden
kosar. `IF NOT EXISTS` kullanilamayan yerlerde (CHECK kisiti) once
`DROP CONSTRAINT IF EXISTS` yapilir.

Alembic kurulmadi: bu proje tek semali, tek gelistiricili ve gocleri
ileriye dogru. Alembic'in surum grafigi, cakisma cozumu ve ayri komut
satiri burada karsiligi olmayan bir maliyettir. Goc sayisi artarsa
yukseltme yolu odur.
"""

from __future__ import annotations

from sqlalchemy import text

from api.db.postgres import engine

# (ad, SQL) -- ad yalnizca hata mesajinda gecer.
MIGRATIONS: list[tuple[str, str]] = [
    (
        # Asama 12.3: Kur/Birak anahtari (TEZ_KAPSAM.txt Faz 1).
        # Varsayilan TRUE = Koruma: gocten sonra sistem kendiliginden
        # sessizlesmemeli, davranis degismeden kalmali.
        "detection_settings.armed",
        "ALTER TABLE detection_settings "
        "ADD COLUMN IF NOT EXISTS armed BOOLEAN NOT NULL DEFAULT TRUE",
    ),
    (
        # 'skipped': Evde modunda bastirilan bildirim. Kayit BIRAKILIR --
        # bir guvenlik sisteminde "alarm gonderilmedi" bilgisi, gonderildi
        # bilgisi kadar denetlenebilir olmalidir.
        "notifications.status CHECK",
        "ALTER TABLE notifications DROP CONSTRAINT IF EXISTS notifications_status_check",
    ),
    (
        "notifications.status CHECK (yeni)",
        "ALTER TABLE notifications ADD CONSTRAINT notifications_status_check "
        "CHECK (status IN ('sent', 'failed', 'skipped'))",
    ),
]


def run_migrations() -> list[str]:
    """Uygulanan goclerin adlarini doner. Tek bir goc patlarsa digerleri
    denenmeye devam eder ve hata basilir: API'nin acilmasini engellemek,
    tek bir sutun yuzunden tum sistemi durdurmak olurdu."""
    applied: list[str] = []
    for name, sql in MIGRATIONS:
        # HER GOC AYRI ISLEMDE: PostgreSQL'de bir ifade patlayinca islem
        # iptal olur ve ayni islemdeki sonraki ifadeler de "current
        # transaction is aborted" ile duser. Tek begin() bloguna almak,
        # ilk hatanin geri kalan goclerin hepsini sessizce goturmesi
        # demekti.
        try:
            with engine.begin() as conn:
                conn.execute(text(sql))
            applied.append(name)
        except Exception as exc:  # noqa: BLE001
            print(f"  [migrate] {name} uygulanamadi: {exc}")
    return applied
