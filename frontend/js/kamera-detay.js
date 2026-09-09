// Kamera detay ekrani (ASAMA8_PLAN.md SS3, 8.3 ilk yarisi). ?id= -> kamera
// basligi/cozunurluk/durum + sagdaki olay akisi. Canli goruntu, katman
// ac-kapa dugmeleri ve gercek FPS/cikarim suresi kutulari 8.4'un isi --
// onlara dokunulmuyor, yalnizca sahte sayilar "-" ile bosaltiliyor.

requireAuth();

const CAMERA_STATUS_ADI = { online: "Çevrimiçi", offline: "Çevrimdışı", error: "Hata" };
// ponytail: app.js'e tasinmali (kameralar.js'teki CAMERA_STATUS_ADI ile ayni).

// Kimlik dogrulamali binary (jpeg) indirme -- api()'nin JSON/metin varsayimi
// kanit karesi icin uygun degil (Authorization basligi olmadan <img src=...>
// 401 doner). ponytail: app.js'e tasinmali, olaylar.js/olay-detay.js'de de
// aynisi tekrarlaniyor.
async function _fetchAuthedBlobUrl(path) {
    const res = await fetch(path, { headers: { Authorization: "Bearer " + token() } });
    if (!res.ok) throw new Error("kanit alinamadi (" + res.status + ")");
    const blob = await res.blob();
    return URL.createObjectURL(blob);
}

function _showFatalError(msg) {
    const main = document.querySelector("main");
    main.innerHTML =
        '<div class="m-6 p-6 bg-error/10 border border-error/30 rounded-lg text-error font-body-md ' +
        'text-body-md flex items-center gap-3">' +
        '<span class="material-symbols-outlined">error</span><span>' + msg + "</span></div>";
}

function _params() {
    return new URLSearchParams(location.search);
}

function _fillCameraInfo(cam) {
    // Ust bar: "Kamera-04_Ana_Giris" -> kamera adi.
    const headerSpans = document.querySelectorAll("header .flex.items-center.gap-2.text-on-surface-variant span");
    if (headerSpans[1]) headerSpans[1].textContent = cam.name;

    // Video alani ustundeki "Stream Info Badge": ad + cozunurluk.
    const badge = document.querySelector(".backdrop-blur");
    if (badge) {
        const dot = badge.children[0];
        const nameSpan = badge.children[1];
        const resSpan = badge.children[3];
        if (nameSpan) nameSpan.textContent = cam.name + (cam.location ? " (" + cam.location + ")" : "");
        if (resSpan) resSpan.textContent = cam.width + "x" + cam.height;
        if (dot) dot.title = CAMERA_STATUS_ADI[cam.status] || cam.status;
    }

    // Sag panel basligi: "Sadece Kamera-04".
    const asideLabel = document.querySelector("aside .font-data-mono.text-\\[10px\\].text-on-surface-variant");
    if (asideLabel) asideLabel.textContent = "Sadece " + cam.name;

    // Gercek FPS / Dusen Kare / Cikarim Suresi -- 8.4 baglanana kadar sahte
    // sayi birakilmaz (ASAMA8_PLAN.md SS "Kamera Detay" maddesi).
    const healthBar = document.querySelector(".h-12.bg-surface-container.border-t");
    if (healthBar) {
        const fps = healthBar.querySelector(".text-secondary");
        const dropped = healthBar.querySelector(".text-on-surface");
        const infer = healthBar.querySelector(".text-primary");
        if (fps) fps.textContent = "—";
        if (dropped) dropped.textContent = "—";
        if (infer) infer.textContent = "—";
    }
}

const SEVERITY_DOT = {
    critical: "bg-error", high: "bg-error",
    medium: "bg-yellow-500", low: "bg-outline-variant",
};

function _fillEventCard(card, ev, cam) {
    // Ikon glifi ve rengi sablon tasarimina ait (madde 5: ikon degismez),
    // dokunulmuyor -- yalnizca metin (gercek) ve sol serit rengi (gercek
    // onem seviyesi, yanlis "kritik" izlenimi vermemesi icin) degisiyor.
    const typeSpan = card.querySelector(".flex.items-center.gap-2 span:last-child");
    const timeSpan = card.querySelector("span.font-data-mono.text-\\[11px\\]");
    const stripDiv = card.querySelector(".absolute.left-0.top-0.bottom-0");
    const descP = card.querySelector("p");
    const thumbDiv = card.querySelector(".w-16.h-12");
    const linkBtn = card.querySelector("button");

    if (typeSpan) typeSpan.textContent = TIP_ADI[ev.anomaly_type] || ev.anomaly_type;
    if (timeSpan) timeSpan.textContent = fmtTime(ev.started_at);
    if (descP) descP.textContent = (cam ? cam.name : "Kamera") + " üzerinde " + (TIP_ADI[ev.anomaly_type] || ev.anomaly_type) + " tespit edildi.";
    const dotClass = SEVERITY_DOT[ev.severity] || "bg-outline-variant";
    if (stripDiv) stripDiv.className = "absolute left-0 top-0 bottom-0 w-1 " + dotClass;
    if (linkBtn) {
        linkBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            location.href = "olay-detay.html?id=" + ev.id;
        });
    }
    card.style.cursor = "pointer";
    card.addEventListener("click", () => { location.href = "olay-detay.html?id=" + ev.id; });

    if (thumbDiv && ev.frame_path) {
        _fetchAuthedBlobUrl("/api/events/" + ev.id + "/frame")
            .then((url) => { thumbDiv.style.backgroundImage = "url('" + url + "')"; thumbDiv.style.backgroundSize = "cover"; thumbDiv.style.backgroundPosition = "center"; })
            .catch(() => { /* kanit yoksa bos kalir */ });
    } else if (thumbDiv) {
        thumbDiv.remove();
    }
}

async function _loadEvents(camId, cam) {
    const streamList = document.querySelector("aside .flex-1.overflow-y-auto.p-2.flex.flex-col.gap-2");
    if (!streamList) return;
    const fillCard = rowTemplate(streamList);
    let events;
    try {
        const result = await api("/api/events?camera_id=" + camId + "&limit=20");
        events = result.items;
    } catch (e) {
        const err = document.createElement("p");
        err.className = "text-error font-body-sm text-body-sm p-2";
        err.textContent = "Olaylar yüklenemedi: " + e.message;
        streamList.appendChild(err);
        return;
    }
    if (events.length === 0) {
        const empty = document.createElement("p");
        empty.className = "text-on-surface-variant font-body-sm text-body-sm p-2 text-center";
        empty.textContent = "Bu kamera için olay yok";
        streamList.appendChild(empty);
        return;
    }
    for (const ev of events) {
        const card = fillCard(ev);
        _fillEventCard(card, ev, cam);
        streamList.appendChild(card);
    }
}

async function _load() {
    const id = _params().get("id");
    if (!id) {
        _showFatalError("Kamera kimliği belirtilmedi (?id= eksik).");
        return;
    }
    let cam;
    try {
        cam = await api("/api/cameras/" + id);
    } catch (e) {
        _showFatalError("Kamera bulunamadı: " + e.message);
        return;
    }
    _fillCameraInfo(cam);
    await _loadEvents(id, cam);
}

_load();
