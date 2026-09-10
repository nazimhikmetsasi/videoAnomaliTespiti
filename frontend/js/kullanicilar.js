// Kullanicilar ekrani (ASAMA8_PLAN.md SS3.8.3 + 8.5). GET /api/users yalniz
// admin -- 403'te bos tablo degil Turkce yetki mesaji. Ekleme/duzenleme/
// pasiflestirme 8.5'te baglandi. app.js: requireAuth/api/fmtDateTime/
// openFormDialog/ROLE_ADI/FORBIDDEN_MSG.

requireAuth();

// data-icon="person_add" sayfada tek yerde geciyor (grep ile dogrulandi).
const _addBtnIcon = document.querySelector('[data-icon="person_add"]');
const _addBtn = _addBtnIcon ? _addBtnIcon.closest("button") : null;
if (_addBtn) _addBtn.addEventListener("click", () => _openUserForm(null));

const _USER_FIELDS_BASE = [
    { name: "username", label: "Kullanıcı Adı", type: "text", required: true },
    { name: "full_name", label: "Ad Soyad", type: "text", required: true },
    { name: "role", label: "Rol", type: "select", required: true, options: Object.entries(ROLE_ADI) },
    { name: "telegram_chat_id", label: "Telegram Chat ID", type: "text" },
    { name: "is_active", label: "Aktif", type: "checkbox" },
];

// existing=null -> ekleme (POST UserCreate, sifre zorunlu). existing=kullanici
// -> duzenleme (PUT UserUpdate); sifre alani BOS gelir, bos birakilirsa govdeye
// hic konmaz (sunucu hash'e dokunmaz -- api/routers/users.py update_user).
async function _openUserForm(existing) {
    let values = existing
        ? {
            username: existing.username, full_name: existing.full_name, role: existing.role,
            telegram_chat_id: existing.telegram_chat_id || "", is_active: existing.is_active, password: "",
        }
        : { role: "viewer", is_active: true };

    const fields = _USER_FIELDS_BASE.concat([
        { name: "password", label: existing ? "Yeni Şifre (boş bırakılırsa değişmez)" : "Şifre", type: "password", required: !existing },
    ]);

    for (;;) {
        const result = await openFormDialog({
            title: existing ? "Kullanıcı Düzenle" : "Yeni Kullanıcı Ekle",
            fields,
            values,
        });
        if (result === null) return;
        try {
            if (existing) {
                const body = Object.assign({}, result);
                if (!body.password) delete body.password;
                await api("/api/users/" + existing.id, { method: "PUT", body });
            } else {
                await api("/api/users", { method: "POST", body: result });
            }
            load();
            return;
        } catch (e) {
            // Sunucunun 4xx mesaji (ör. son admin korumasi) oldugu gibi gosterilir --
            // istemcide ayni kural tekrar yazilmaz.
            values = Object.assign({}, result, { password: "", error: e.message === FORBIDDEN_MSG ? FORBIDDEN_MSG : e.message });
        }
    }
}

async function _deactivateUser(user) {
    // Toplu bildirim katmani yok -- native confirm/alert (app.js'teki not).
    if (!confirm('"' + user.full_name + '" kullanıcısını pasifleştirmek istediğinize emin misiniz?')) return;
    try {
        await api("/api/users/" + user.id, { method: "DELETE" });
        load();
    } catch (e) {
        alert(e.message === FORBIDDEN_MSG ? "bu işlem için yetkiniz yok" : e.message);
    }
}

function initials(text) {
    return (text || "?").trim().slice(0, 2).toUpperCase();
}

function messageRow(colspan, text) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="${colspan}" class="py-8 px-4 text-center text-on-surface-variant">${text}</td>`;
    return tr;
}

function fillUsers(users) {
    const tbody = document.querySelector("table tbody");
    if (!tbody) return;
    const makeRow = rowTemplate(tbody);

    if (users.length === 0) {
        tbody.appendChild(messageRow(5, "kayıt yok"));
        return;
    }

    for (const user of users) {
        const tr = makeRow(user);
        const tds = tr.querySelectorAll("td");

        // Kullanici Adi: avatar baş harfleri + ad soyad + kullanici adi.
        const identityTd = tds[0];
        identityTd.querySelector(".rounded-full").textContent = initials(user.full_name);
        const nameDivs = identityTd.querySelectorAll("div > div");
        nameDivs[0].textContent = user.full_name;
        nameDivs[1].textContent = "@" + user.username;

        // Rol.
        const roleBadge = tds[1].querySelector("span");
        roleBadge.textContent = ROLE_ADI[user.role] || user.role;
        roleBadge.className =
            user.role === "admin"
                ? "inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-primary-container text-primary border border-primary-fixed-dim"
                : "inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-surface-variant text-on-surface border border-outline-variant";

        // Telegram: yalniz chat_id var/yok bilgisi var, kanal/bot ayrimi API'de yok.
        const tgWrap = tds[2].querySelector("div");
        const connected = !!user.telegram_chat_id;
        tgWrap.className = "flex items-center gap-1.5 " + (connected ? "text-secondary" : "text-on-surface-variant");
        tgWrap.querySelector("span:first-child").className = "w-2 h-2 rounded-full " + (connected ? "bg-secondary" : "bg-outline");
        tgWrap.querySelector("span:last-child").textContent = connected ? "Bağlı" : "Bağlı Değil";

        // Son giris.
        tds[3].textContent = fmtDateTime(user.last_login);

        // Islemler: edit/block ikonlari data-icon ile bulunur (title yok).
        const editIcon = tds[4].querySelector('[data-icon="edit"]');
        const editBtn = editIcon ? editIcon.closest("button") : null;
        if (editBtn) editBtn.addEventListener("click", () => _openUserForm(user));

        const deactivateIcon = tds[4].querySelector('[data-icon="block"]');
        const deactivateBtn = deactivateIcon ? deactivateIcon.closest("button") : null;
        if (deactivateBtn) deactivateBtn.addEventListener("click", () => _deactivateUser(user));

        if (!user.is_active) tr.classList.add("opacity-50");

        tbody.appendChild(tr);
    }
}

async function load() {
    const tbody = document.querySelector("table tbody");
    try {
        const users = await api("/api/users");
        fillUsers(users);
    } catch (err) {
        if (!tbody) return;
        tbody.innerHTML = "";
        const forbidden = err.message === FORBIDDEN_MSG;
        const msg = forbidden ? "bu ekran için yetkiniz yok" : "kullanıcı listesi alınamadı: " + err.message;
        tbody.appendChild(messageRow(5, msg));
        // Liste zaten 403 -- ekleme dugmesi de ayni mantikla gizlenir.
        if (forbidden && _addBtn) _addBtn.hidden = true;
    }
}

document.addEventListener("DOMContentLoaded", load);
