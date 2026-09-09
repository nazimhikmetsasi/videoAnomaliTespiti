"""GET/POST/PUT/DELETE /api/users -- kullanici yonetimi (ASAMA8_PLAN.md SS3.8.2).

Sifre hash'i veritabaninda uretilir (crypt(:password, gen_salt('bf'))) --
Asama 5 karari bozulmuyor, Python tarafinda ikinci bir bcrypt/passlib yolu
yok (api/auth.py'deki authenticate_user ile ayni desen). DELETE gercek silme
degil pasiflestirme: audit_log.user_id ve zones.created_by FK'leri var,
kullanici silinirse "kim yapti" denetim izi kopar.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.audit import write_audit
from api.auth import require_role
from api.db.models import User
from api.db.postgres import get_db
from api.schemas import UserCreate, UserOut, UserUpdate

router = APIRouter()


def _get_or_404(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "kullanici bulunamadi")
    return user


def _active_admin_count(db: Session, exclude_id: int) -> int:
    return db.scalar(
        select(func.count()).select_from(User)
        .where(User.role == "admin", User.is_active.is_(True), User.id != exclude_id)
    ) or 0


def _yetki_kaybi(target: User, data: dict) -> bool:
    """Admin yetkisini kaldiran IKI degisiklik var: pasiflestirme ve rolu
    admin'den dusurme. Yalniz birincisini korumak sistemi admin'siz
    birakabilirdi -- son admin'i 'viewer' yapmak da paneli kilitler."""
    if data.get("is_active") is False:
        return True
    yeni_rol = data.get("role")
    return yeni_rol is not None and yeni_rol != "admin" and target.role == "admin"


def _guard_admin_loss(db: Session, target: User, acting: dict) -> None:
    """Kendi hesabinin yetkisini kaldirma ve son admin'in yetkisini kaldirma
    engellenir. Son-admin kontrolu yalniz halen AKTIF bir admin icin calisir
    -- zaten pasif bir kullaniciyi tekrar pasiflestirmek zararsizdir."""
    if target.id == acting["id"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "kendi hesabinizin yetkisini kaldiramazsiniz")
    if target.role == "admin" and target.is_active and _active_admin_count(db, target.id) == 0:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "son admin pasiflestirilemez veya rolu dusurulemez")


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _: dict = Depends(require_role("admin"))) -> list[User]:
    # Pasifler DAHIL -- ekran gecmis kullanicilari da gostermeli.
    return list(db.scalars(select(User).order_by(User.id)))


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreate, db: Session = Depends(get_db), user: dict = Depends(require_role("admin")),
) -> User:
    try:
        row = db.execute(
            text(
                "INSERT INTO users (username, password_hash, full_name, role, telegram_chat_id, is_active) "
                "VALUES (:username, crypt(:password, gen_salt('bf')), :full_name, :role, :telegram_chat_id, :is_active) "
                "RETURNING id"
            ),
            body.model_dump(),
        ).first()
    except IntegrityError:
        # username UNIQUE -- panelin formu bunu 500 degil 409 gormeli.
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "bu kullanici adi zaten kayitli") from None
    new_id = row[0]
    write_audit(db, user_id=user["id"], action="create", entity="user", entity_id=new_id)
    db.commit()
    return _get_or_404(db, new_id)


@router.put("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int, body: UserUpdate, db: Session = Depends(get_db),
    user: dict = Depends(require_role("admin")),
) -> User:
    target = _get_or_404(db, user_id)
    data = body.model_dump(exclude_unset=True)
    password = data.pop("password", None)
    if _yetki_kaybi(target, data):
        _guard_admin_loss(db, target, user)
    for field, value in data.items():
        setattr(target, field, value)
    if password:
        db.execute(
            text("UPDATE users SET password_hash = crypt(:password, gen_salt('bf')) WHERE id = :id"),
            {"password": password, "id": user_id},
        )
    write_audit(db, user_id=user["id"], action="update", entity="user", entity_id=user_id)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "bu kullanici adi zaten kayitli") from None
    db.refresh(target)
    return target


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int, db: Session = Depends(get_db), user: dict = Depends(require_role("admin")),
) -> None:
    target = _get_or_404(db, user_id)
    _guard_admin_loss(db, target, user)
    target.is_active = False
    write_audit(db, user_id=user["id"], action="delete", entity="user", entity_id=user_id)
    db.commit()
