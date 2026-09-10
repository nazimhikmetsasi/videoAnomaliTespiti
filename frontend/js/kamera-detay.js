// Kamera detay ekrani (ASAMA8_PLAN.md SS3, 8.3+8.4). ?id= -> kamera
// basligi/cozunurluk/durum + sagdaki olay akisi (8.3) + tekli canli goruntu,
// katman ac-kapa ve gercek FPS/dusen kare/cikarim suresi (8.4). Baglanti +
// cizim mantigi js/live.js'te ortak -- burada yalnizca bu sayfaya ozel DOM
// bağlantısı var.

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

    // Gercek FPS / Dusen Kare / Cikarim Suresi: canli akis baglanana kadar
    // "—" -- _startLiveView (asagida) meta/health geldikce doldurur.
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

// ------------------------------------------------------- 8.4: canli goruntu
// Sablonun sahte "Simulated Analytics Overlays" (sabit bolge + tespit kutusu)
// ve tek layer-toggle grubu (Kutu/Iskelet/Bolge/ID dugmeleri) burada gercek
// /ws/live + /ws/meta akisina baglanir. Baglanti/yeniden-baglanma/cizim
// js/live.js'te ortak (index.js ile ayni), kopyalanmiyor.
function _startLiveView(cam) {
    const overlayLayer = document.querySelector(
        ".absolute.inset-0.pointer-events-none.z-10.flex.flex-col.justify-between");
    const videoArea = document.querySelector("main .flex-1.bg-black.relative");
    const healthBar = document.querySelector(".h-12.bg-surface-container.border-t");
    if (!overlayLayer || !videoArea || !healthBar) return;

    // Simulated Analytics Overlays (sahte bolge + tespit kutusu) kaldirilir --
    // gercek katmanlar asagida canvas'a cizilir. Top Controls (children[0])
    // -- rozet + katman dugmeleri -- kalir.
    while (overlayLayer.children.length > 1) overlayLayer.lastChild.remove();

    videoArea.innerHTML = "";
    videoArea.style.backgroundSize = "contain";
    videoArea.style.backgroundPosition = "center";
    videoArea.style.backgroundRepeat = "no-repeat";
    const canvas = document.createElement("canvas");
    canvas.className = "absolute inset-0 w-full h-full pointer-events-none";
    videoArea.appendChild(canvas);

    const fpsSpan = healthBar.querySelector(".text-secondary");
    const droppedSpan = healthBar.querySelector(".text-on-surface");
    const inferSpan = healthBar.querySelector(".text-primary");

    // Katman dugmeleri: sablonda Kutu+Bolge aktif, Iskelet+ID pasif geliyor
    // (kendi orijinal sinif dizileri "aktif"/"pasif" gorunumu -- sabitlenip
    // dorduncu dugmeye de ayni iki durum uygulanir, yeni sinif uydurulmaz).
    const layerButtons = document.querySelectorAll(".flex.gap-2.pointer-events-auto button");
    const ACTIVE_BTN_CLASS = layerButtons[0].className;
    const INACTIVE_BTN_CLASS = layerButtons[1].className;
    const LAYER_KEYS = ["box", "skeleton", "zone", "id"];
    const layers = { box: true, skeleton: false, zone: true, id: false };
    let lastMeta = null;

    async function draw() {
        if (!lastMeta) return;
        let zones = lastMeta.zones;
        if (layers.zone && (!zones || !zones.length)) zones = await zonesFor(cam.id);
        drawOverlay(canvas, lastMeta, zones || [], layers);
    }

    layerButtons.forEach((btn, i) => {
        btn.className = layers[LAYER_KEYS[i]] ? ACTIVE_BTN_CLASS : INACTIVE_BTN_CLASS;
        btn.addEventListener("click", () => {
            layers[LAYER_KEYS[i]] = !layers[LAYER_KEYS[i]];
            btn.className = layers[LAYER_KEYS[i]] ? ACTIVE_BTN_CLASS : INACTIVE_BTN_CLASS;
            draw();
        });
    });

    let liveSock = null, metaSock = null;
    function connect() {
        // Korumasiz cagrilirsa "visibilitychange" sekme HIC gizlenmeden de
        // "gorunur oldu" olayi yollayabilir (orn. bu sekme arka planda
        // acilip sonra one alinirsa) -- ikinci connect() zaten acik soketin
        // USTUNE yeni bir cift acar, ilk cift referanssiz kalip sonsuza
        // kadar yayin almaya devam eder (gercek kare CIFTLENIR). Idempotent
        // yapmak icin zaten bagliysa cik.
        if (liveSock) return;
        liveSock = openReconnectingSocket(() => liveWsUrl("live", cam.name), {
            onMessage(blob) {
                _noteFrame(cam.name);
                setFrameImage(videoArea, blob);
            },
        });
        metaSock = openReconnectingSocket(() => liveWsUrl("meta", cam.name), {
            onMessage(data) {
                lastMeta = JSON.parse(data);
                if (fpsSpan) fpsSpan.textContent = lastMeta.fps;
                if (inferSpan && lastMeta.stage_ms && lastMeta.stage_ms.infer != null) {
                    inferSpan.textContent = lastMeta.stage_ms.infer.toFixed(1) + "ms";
                }
                draw();
            },
        });
    }
    function disconnect() {
        if (liveSock) liveSock.stop();
        if (metaSock) metaSock.stop();
        liveSock = null;
        metaSock = null;
    }
    connect();
    document.addEventListener("visibilitychange", () => {
        if (document.hidden) disconnect(); else connect();
    });

    // Dusen kare: GET /api/health/cameras'ta duruyor, meta govdesinde yok
    // (ASAMA8_PLAN.md SS3, madde 3). 5 sn'de bir tazelenir (vision/run.py
    // varsayilan kalp atisi araligi ile ayni buyukluk).
    async function pollHealth() {
        if (document.hidden || !droppedSpan) return;
        try {
            const rows = await api("/api/health/cameras");
            const row = rows.find((r) => r.camera_id === cam.id);
            droppedSpan.textContent = row && row.dropped != null ? String(row.dropped) : "—";
        } catch (_e) { /* saglik ucu gecici dusebilir, sessiz gec */ }
    }
    pollHealth();
    setInterval(pollHealth, 5000);
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
    _startLiveView(cam);
    await _loadEvents(id, cam);
}

_load();
