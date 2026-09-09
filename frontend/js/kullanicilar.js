// Kullanicilar ekrani (ASAMA8_PLAN.md SS3.8.3). GET /api/users yalniz admin
// -- 403'te bos tablo degil Turkce yetki mesaji. Ekleme/duzenleme/pasiflestirme
// 8.5'in isi, dugmeler baglanmaz. app.js: requireAuth/api/fmtDateTime.

requireAuth();

// api/auth.py require_role() tek yerde bu metni dondurur.
const FORBIDDEN_MSG = "bu islem icin yetkiniz yok";

const ROLE_ADI = { admin: "Yönetici", operator: "Operatör", viewer: "Görüntüleyici" };

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

        // Islemler (duzenle/pasiflestir) 8.5'in isi -- dugmeler baglanmadi.

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
        const msg = err.message === FORBIDDEN_MSG ? "bu ekran için yetkiniz yok" : "kullanıcı listesi alınamadı: " + err.message;
        tbody.appendChild(messageRow(5, msg));
    }
}

document.addEventListener("DOMContentLoaded", load);
