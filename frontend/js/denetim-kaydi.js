// Denetim kaydi ekrani (ASAMA8_PLAN.md SS3.8.3). Iki sekme, iki uc:
// "Bildirimler" -> GET /api/notifications (Asama 7'den beri dolan
// notifications tablosu), "Denetim Kaydi" -> GET /api/audit. Ikisi de
// yalniz admin. app.js: requireAuth/api/fmtDateTime.

requireAuth();

function initials(text) {
    return (text || "?").trim().slice(0, 3).toUpperCase();
}

function messageRow(colspan, text) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="${colspan}" class="py-8 px-4 text-center text-on-surface-variant">${text}</td>`;
    return tr;
}

// "Bildirimler" sekmesi: bildirim teslim gunlugu (kanal, hedef, sonuc).
// Basarisiz gonderim satiri hata metnini title'da tasir -- operator neden
// ulasmadigini gormeli.
function fillNotifications(list) {
    const view = document.getElementById("view-notifications");
    if (!view) return;
    const tbody = view.querySelector("table tbody");
    if (!tbody) return;
    const makeRow = rowTemplate(tbody);

    if (list.items.length === 0) {
        tbody.appendChild(messageRow(4, "bildirim kaydı yok"));
        return;
    }

    for (const row of list.items) {
        const tr = makeRow(row);
        const tds = tr.querySelectorAll("td");
        const basarili = row.status === "sent";

        const dot = tds[0].querySelector("div");
        if (dot) dot.className = "w-2 h-2 rounded-full " + (basarili ? "bg-secondary" : "bg-error");
        const olay = tds[0].querySelector("span");
        const tip = TIP_ADI[row.anomaly_type] || row.anomaly_type || "olay";
        olay.textContent = `${tip}${row.camera_name ? " - " + row.camera_name : ""} #${row.event_id}`;
        olay.className = basarili ? "font-medium" : "font-medium text-error";

        tds[1].textContent = `${row.channel} (${row.target})`;

        const rozet = tds[2].querySelector("span");
        const ikon = rozet.querySelector("span");
        ikon.textContent = basarili ? "check_circle" : "error";
        // Rozetin metni ikon span'inin YANINDAKI metin dugumu; tum metin
        // dugumlerini silip tek yeni dugum eklemek en guvenlisi (sablonda
        // ikondan once de bosluk dugumu var).
        [...rozet.childNodes].filter((n) => n.nodeType === 3).forEach((n) => n.remove());
        rozet.appendChild(document.createTextNode(basarili ? "İletildi" : "Başarısız"));
        if (!basarili) {
            rozet.className = "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-error-container text-on-error-container text-xs font-medium border border-error/20";
            if (row.error) rozet.title = row.error;
        }

        tds[3].textContent = fmtDateTime(row.sent_at);
        tbody.appendChild(tr);
    }
}


function fillAuditTable(list) {
    const view = document.getElementById("view-audit");
    if (!view) return;
    const tbody = view.querySelector("table tbody");
    if (!tbody) return;
    const makeRow = rowTemplate(tbody);

    if (list.items.length === 0) {
        tbody.appendChild(messageRow(4, "kayıt yok"));
        return;
    }

    for (const row of list.items) {
        const tr = makeRow(row);
        const tds = tr.querySelectorAll("td");

        const userTd = tds[0];
        const isSystem = row.username == null;
        userTd.querySelector("div").textContent = initials(row.username || "SIL");
        const nameSpan = userTd.querySelector("span");
        nameSpan.textContent = isSystem ? "silinmiş kullanıcı" : row.username;
        nameSpan.className = isSystem ? "font-medium text-secondary" : "font-medium";

        const actionTd = tds[1];
        actionTd.textContent = `${row.action} · ${row.entity}${row.entity_id != null ? " #" + row.entity_id : ""}`;
        if (row.payload) actionTd.title = JSON.stringify(row.payload);

        tds[2].textContent = row.ip || "—";
        tds[3].textContent = fmtDateTime(row.created_at);

        tbody.appendChild(tr);
    }
}

function hataYaz(view, mesaj) {
    const tbody = view ? view.querySelector("table tbody") : null;
    if (!tbody) return;
    tbody.innerHTML = "";
    tbody.appendChild(messageRow(4, mesaj));
}

function hataMetni(err, ekran) {
    return err.message === FORBIDDEN_MSG ? "bu ekran için yetkiniz yok" : ekran + " alınamadı: " + err.message;
}

async function load() {
    try {
        fillNotifications(await api("/api/notifications"));
    } catch (err) {
        hataYaz(document.getElementById("view-notifications"), hataMetni(err, "bildirim kaydı"));
    }
    const view = document.getElementById("view-audit");
    const tbody = view ? view.querySelector("table tbody") : null;
    try {
        const list = await api("/api/audit");
        fillAuditTable(list);
    } catch (err) {
        if (!tbody) return;
        hataYaz(view, hataMetni(err, "denetim kaydı"));
    }
}

document.addEventListener("DOMContentLoaded", load);
