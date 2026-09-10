// Olay detay ekrani (ASAMA8_PLAN.md SS3, 8.3 ilk yarisi + 8.5 durum degistirme).
// ?id= -> GET /api/events/{id}. Kanit: /frame (gorsel), /clip (video, yoksa
// metin). LLM raporu goruntuleme 8.3'te yapildi (_fillReport). 8.5: sag
// panelin uc durum dugmesi (Görüldü/Yanlış Alarm/Kapat) PATCH atar.

requireAuth();

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

// Rozet elemani (header'daki durum etiketi) hem ilk yuklemede hem PATCH
// sonrasinda ayni yerden guncellenir -- renk sabit kaliyor (sablonun tek
// varyanti "bg-error/20" idi, 8.3'ten devralindi), yalniz metin degisiyor.
function _setStatusBadge(status) {
    const statusBadge = document.querySelector("header .rounded.bg-error\\/20.text-error");
    if (!statusBadge) return;
    // toUpperCase() Turkce "i" -> "I" yapar (dogrusu "İ") -- tr-TR yerel kurali kullanilir.
    const label = (DURUM_ADI[status] || status).toLocaleUpperCase("tr-TR");
    statusBadge.childNodes[statusBadge.childNodes.length - 1].textContent = " " + label;
}

// Sag paneldeki "Müdahale Aksiyonları" karti icindeki uc dugme: her biri
// EventStatusIn'in kabul ettigi tek bir hedefe PATCH atar ('new' kasten yok).
// Hedef durum zaten mevcut durumsa dugme devre disi gosterilir.
const _STATUS_BUTTON_ICON = { acknowledged: "visibility", false_positive: "block", resolved: "done_all" };

function _wireStatusButtons(ev) {
    const heading = [...document.querySelectorAll("main h3")].find((h) => h.textContent.includes("Müdahale Aksiyonları"));
    const panel = heading ? heading.parentElement : null;
    if (!panel) return;
    let current = ev.status;

    function refreshDisabled() {
        for (const [target, icon] of Object.entries(_STATUS_BUTTON_ICON)) {
            const iconEl = panel.querySelector('[data-icon="' + icon + '"]');
            const btn = iconEl ? iconEl.closest("button") : null;
            if (btn) btn.disabled = current === target;
        }
    }

    for (const [target, icon] of Object.entries(_STATUS_BUTTON_ICON)) {
        const iconEl = panel.querySelector('[data-icon="' + icon + '"]');
        const btn = iconEl ? iconEl.closest("button") : null;
        if (!btn) continue;
        btn.addEventListener("click", async () => {
            btn.disabled = true;
            try {
                const updated = await api("/api/events/" + ev.id, { method: "PATCH", body: { status: target } });
                current = updated.status;
                _setStatusBadge(current);
                refreshDisabled();
            } catch (e) {
                // Bildirim katmani yok -- native alert() (app.js'teki not).
                alert(e.message === FORBIDDEN_MSG ? FORBIDDEN_MSG : e.message);
                refreshDisabled();
            }
        });
    }
    refreshDisabled();
}

function _fillSummary(ev) {
    document.title = "Olay Detayı #" + ev.id + " - VADAP";
    const idHeading = document.querySelector("header h2.font-title-sm");
    if (idHeading) idHeading.textContent = "Olay Detayı #" + ev.id;

    _setStatusBadge(ev.status);

    const summaryCols = document.querySelectorAll("main .flex.gap-stack-md.flex-wrap.items-center > .flex.flex-col");
    // 0: Olay Tipi, 1: Tarih/Saat, 2: Bolge/Kamera (madde sirasi sablonda sabit)
    if (summaryCols[0]) {
        const span = summaryCols[0].querySelector("span:last-child");
        span.textContent = TIP_ADI[ev.anomaly_type] || ev.anomaly_type;
    }
    if (summaryCols[1]) {
        const span = summaryCols[1].querySelector("span:last-child");
        span.textContent = fmtDateTime(ev.started_at);
    }
    if (summaryCols[2]) {
        const span = summaryCols[2].querySelector("span:last-child");
        const cam = ev.camera_name || ("Kamera #" + ev.camera_id);
        span.textContent = ev.zone_name ? (ev.zone_name + " / " + cam) : cam;
    }

    const conf = Number(ev.confidence);
    const pct = Number.isFinite(conf) ? Math.round(conf * 100) : null;
    const confBar = document.querySelector("main .w-32.h-2 > div");
    const confLabel = document.querySelector("main .w-32.h-2").parentElement.querySelector("span.font-data-mono");
    if (confBar) confBar.style.width = (pct === null ? 0 : pct) + "%";
    if (confLabel) confLabel.textContent = pct === null ? "—" : "%" + pct;

    // Sure/karar-veren/track_ids icin sablonda ayri bir alan yok (tasarima
    // yeni oge eklenemez) -- basliktaki simge tooltip'ine yaziliyor, kaybolmuyor.
    if (idHeading) {
        idHeading.title = "Süre: " + fmtDuration(ev.duration_ms) +
            " | Karar: " + (DECIDED_BY_ADI[ev.decided_by] || ev.decided_by) +
            " | Track ID: " + (ev.track_ids && ev.track_ids.length ? ev.track_ids.join(", ") : "—");
    }
}

// "Olculen Degerler" tablosu: kaynak GET /api/events/{id} yanitindaki
// `telemetry` (MongoDB telemetry belgesi, consumer.py yaziyor). Metrik
// adlari kural tipine gore degisir (norm_speed_max, limb_speed_median, ...)
// -- sabit dort satir yerine belgede NE VARSA o listelenir. Esik
// karsilastirmasi rule_verdict.thresholds_used'dan gelir; eslesen esik
// yoksa durum "—" kalir, uydurulmaz.
const METRIK_ADI = {
    norm_speed: "Normalize Hız",
    norm_speed_median: "Normalize Hız (medyan)",
    norm_speed_max: "Normalize Hız (tepe)",
    limb_speed_median: "Uzuv Hızı (medyan)",
    limb_speed_max: "Uzuv Hızı (tepe)",
    tilt_deg: "Gövde Eğimi (°)",
    norm_vy: "Dikey Hız (normalize)",
    proximity: "Yakınlık (normalize)",
    dwell_sec: "Bekleme Süresi (sn)",
};

function _esikBul(metrik, esikler) {
    if (!esikler) return null;
    const taban = metrik.replace(/_(median|max|min)$/, "");
    for (const [ad, deger] of Object.entries(esikler)) {
        if (ad === metrik || ad.endsWith(taban)) return { ad, deger: Number(deger) };
    }
    return null;
}

function _sayi(x) {
    const n = Number(x);
    return Number.isFinite(n) ? n : null;
}

function _fillMeasured(ev) {
    const baslik = [...document.querySelectorAll("main h3")].find((h) => h.textContent.includes("Ölçülen Değerler"));
    const tbody = baslik ? baslik.parentElement.querySelector("tbody") : null;
    if (!tbody) return;
    const makeRow = rowTemplate(tbody);

    const tel = ev.telemetry;
    const metrikler = tel && tel.metrics ? Object.entries(tel.metrics) : [];
    const esikler = tel && tel.rule_verdict ? tel.rule_verdict.thresholds_used : null;

    function satir(ad, deger, durum, asildi) {
        const tr = makeRow({});
        const tds = tr.querySelectorAll("td");
        tds[0].textContent = ad;
        tds[1].textContent = deger;
        const rozet = tds[2].querySelector("span");
        rozet.textContent = durum;
        if (!asildi) {
            rozet.className = "px-1.5 py-0.5 rounded bg-surface-container-highest text-on-surface-variant text-[10px] font-medium";
        }
        tbody.appendChild(tr);
    }

    if (metrikler.length === 0) {
        satir("Telemetri", "kayıt yok", "—", false);
    }
    for (const [ad, ham] of metrikler) {
        const deger = _sayi(ham);
        const esik = _esikBul(ad, esikler);
        let durum = "—";
        let asildi = false;
        if (esik && deger !== null && Number.isFinite(esik.deger)) {
            asildi = deger > esik.deger;
            durum = asildi ? "EŞİK AŞILDI (>" + esik.deger + ")" : "EŞİK ALTINDA (≤" + esik.deger + ")";
        }
        satir(METRIK_ADI[ad] || ad, deger === null ? String(ham) : deger.toFixed(3), durum, asildi);
    }
    // Sureklilik ve vurus sayisi telemetri belgesinde degil olay satirinda /
    // Spark ozetinde -- ikisi de gercek, tabloya eklenir.
    satir("Süreklilik", fmtDuration(ev.duration_ms), "—", false);
    if (tel && tel.hits != null) satir("Vuruş (Spark)", String(tel.hits), "—", false);
}

// "Hareket Analizi" egrisi kare kare hiz serisi ister; API yalnizca ozet
// metrikleri donduruyor (pose_sequences'teki ham kareler disariya acik
// degil). Sablonun sahte egrisi silinir, yerine tek satirlik aciklama
// konur -- sahte veri birakma kurali (ASAMA8_PLAN.md SS4).
function _clearMotionChart() {
    const baslik = [...document.querySelectorAll("main h3")].find((h) => h.textContent.includes("Hareket Analizi"));
    if (!baslik) return;
    const kart = baslik.closest("div").parentElement;
    const alan = kart.querySelector(".relative");
    if (!alan) return;
    alan.innerHTML = '<div class="h-full w-full flex items-center justify-center text-on-surface-variant ' +
        'font-body-sm text-body-sm text-center px-4">hız/açı eğrisi için kare kare seri verisi API\'de yok</div>';
}

// Video ustundeki kutu + iskelet katmani sablonda sabit konumlu ve sabit
// etiketli ("INSAN %94"): kutu koordinati API'de yok, etiket de uydurma.
// Katman gizlenir; gercek kutu/iskelet 8.4'te canli akista cizilecek.
function _hideFakeOverlay() {
    const etiket = [...document.querySelectorAll("main div")].find(
        (d) => d.children.length === 0 && d.textContent.trim().startsWith("İNSAN %"));
    if (etiket && etiket.parentElement) etiket.parentElement.hidden = true;
}

async function _fillEvidence(ev) {
    const videoArea = document.querySelector("main .aspect-video");
    const frameLayer = videoArea ? videoArea.querySelector(".bg-cover.bg-center") : null;
    const tabs = document.querySelectorAll("main .flex.space-x-1 > button");
    const videoTab = tabs[0];
    const frameTab = tabs[1];

    // Sablonun stok fotografi gercek kare gelene kadar bile gorunmesin
    // (sahte veri birakma kurali) -- veri gelmeden once hemen temizlenir.
    if (frameLayer) frameLayer.style.backgroundImage = "";

    let frameUrl = null;
    if (ev.frame_path) {
        try { frameUrl = await _fetchAuthedBlobUrl("/api/events/" + ev.id + "/frame"); } catch (_e) { /* kare yok */ }
    }
    if (frameLayer) {
        if (frameUrl) {
            frameLayer.style.backgroundImage = "url('" + frameUrl + "')";
        } else {
            frameLayer.style.backgroundImage = "";
        }
    }

    if (!videoArea) return;
    let videoEl = null;
    let noClipMsg = null;

    function showFrameView() {
        if (videoEl) videoEl.hidden = true;
        if (noClipMsg) noClipMsg.hidden = true;
        if (frameLayer) frameLayer.hidden = false;
        frameTab.className = "px-4 py-2 bg-surface-container-highest text-on-surface font-title-sm text-title-sm rounded-t-md border-b-2 border-secondary flex items-center gap-2";
        videoTab.className = "px-4 py-2 text-on-surface-variant hover:bg-surface-container-high font-title-sm text-title-sm rounded-t-md transition-colors flex items-center gap-2";
    }

    async function showVideoView() {
        if (frameLayer) frameLayer.hidden = true;
        videoTab.className = "px-4 py-2 bg-surface-container-highest text-on-surface font-title-sm text-title-sm rounded-t-md border-b-2 border-secondary flex items-center gap-2";
        frameTab.className = "px-4 py-2 text-on-surface-variant hover:bg-surface-container-high font-title-sm text-title-sm rounded-t-md transition-colors flex items-center gap-2";
        if (!ev.clip_path) {
            if (!noClipMsg) {
                noClipMsg = document.createElement("p");
                noClipMsg.className = "relative z-20 text-on-surface-variant font-body-md text-body-md";
                noClipMsg.textContent = "Kanıt klibi yok";
                videoArea.appendChild(noClipMsg);
            }
            noClipMsg.hidden = false;
            return;
        }
        if (!videoEl) {
            try {
                const url = await _fetchAuthedBlobUrl("/api/events/" + ev.id + "/clip");
                videoEl = document.createElement("video");
                videoEl.src = url;
                videoEl.controls = true;
                videoEl.className = "relative z-20 max-w-full max-h-full";
                videoArea.appendChild(videoEl);
            } catch (_e) {
                if (!noClipMsg) {
                    noClipMsg = document.createElement("p");
                    noClipMsg.className = "relative z-20 text-on-surface-variant font-body-md text-body-md";
                    videoArea.appendChild(noClipMsg);
                }
                noClipMsg.textContent = "Kanıt klibi yüklenemedi";
                noClipMsg.hidden = false;
                return;
            }
        }
        videoEl.hidden = false;
    }

    videoTab.addEventListener("click", showVideoView);
    frameTab.addEventListener("click", showFrameView);
    // Sablonda "Video Kaniti" varsayilan aktif sekme -- ayni davranis korunuyor.
    await showVideoView();
}

function _fillReport(ev) {
    const reportP = document.querySelector("main p.font-body-md.text-body-md.text-on-surface-variant.leading-relaxed");
    if (!reportP) return;
    reportP.textContent = ev.llm_report_tr || "Rapor üretilmedi.";
}

async function _load() {
    const id = _params().get("id");
    if (!id) {
        _showFatalError("Olay kimliği belirtilmedi (?id= eksik).");
        return;
    }
    let ev;
    try {
        ev = await api("/api/events/" + id);
    } catch (e) {
        _showFatalError("Olay bulunamadı: " + e.message);
        return;
    }
    _fillSummary(ev);
    _fillReport(ev);
    _fillMeasured(ev);
    _clearMotionChart();
    _hideFakeOverlay();
    _wireStatusButtons(ev);
    await _fillEvidence(ev);
}

_load();
