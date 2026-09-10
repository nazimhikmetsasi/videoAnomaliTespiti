// Canli izleme ekrani (ASAMA8_PLAN.md SS3, 8.4). Izgara (1/2x2/3x3) + katman
// ac-kapa + /ws/alerts kirmizi alarm. Baglanti/cizim js/live.js'te ortak.
// Sablonun 4 sahte kamera kutusu ve 4 sahte olay karti VERI SABLONUDUR --
// gercek kamera/alarm sayisina gore cogaltilir (ASAMA8_PLAN.md SS2, madde 2).

requireAuth();

const GRID = document.querySelector(".flex-1.grid.grid-cols-2.grid-rows-2.gap-grid-gutter");
const ALARM_TOAST = document.getElementById("alarm-toast");
const EVENT_STREAM = document.querySelector("aside .flex-1.overflow-y-auto.p-2.space-y-2");

// Sablonun toast'i "Depo A - 14:32:05" sahte olayla acilir -- gercek bir
// alarm gelene kadar gizli kalir (rule 3, sahte veri birakilmaz).
if (ALARM_TOAST) ALARM_TOAST.style.display = "none";

const DOT_ONLINE_CLASS = "w-2 h-2 rounded-full bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.6)]";
const DOT_OFFLINE_CLASS = "w-2 h-2 rounded-full bg-outline";
const DOT_ALARM_CLASS = "w-2 h-2 rounded-full bg-error";

// consumer.py SEVERITY (api/workers/consumer.py) ile AYNI harita -- alarm
// govdesinde severity yok (DB'ye yazilirken orada atanir), kart serit rengi
// icin burada da tutulur.
const TYPE_SEVERITY = {
    FALL: "critical", FIGHT: "critical",
    ZONE_VIOLATION: "high", RUN_ZONE: "high",
    RUN: "medium", WRONG_DIRECTION: "medium",
    LOITERING: "low",
};
const SEVERITY_STRIP = {
    critical: "bg-error", high: "bg-error", medium: "bg-yellow-500", low: "bg-outline-variant",
};

// ------------------------------------------------------------- kutu sablonu
// Cam1 (canli/AKTIF gorunumu) ve Cam4'un (Baglanti Yok) merkez blogu kutu
// sablonu olarak sokulur, sahte 4 kutu silinir (rowTemplate ile ayni fikir,
// burada iki AYRI dugum gerektigi icin elle).
let _liveTpl = null, _offlineCenterTpl = null;
(function _captureGridTemplates() {
    _liveTpl = GRID.children[0].cloneNode(true);
    _offlineCenterTpl = GRID.children[3].children[2].cloneNode(true);
    GRID.innerHTML = "";
})();

function _makeLiveBox(cam) {
    const box = _liveTpl.cloneNode(true);
    const header = box.children[0];
    const nameSpan = header.children[0].children[0];
    const statusGroup = header.children[0].children[1];
    const dot = statusGroup.children[0];
    const statusText = statusGroup.children[1];
    const fpsSpan = header.children[1];
    const videoArea = box.children[1];

    videoArea.innerHTML = ""; // sahte bbox overlay'i kaldirilir
    videoArea.style.backgroundSize = "contain";
    videoArea.style.backgroundPosition = "center";
    videoArea.style.backgroundRepeat = "no-repeat";

    const canvas = document.createElement("canvas");
    canvas.className = "absolute inset-0 w-full h-full pointer-events-none";
    videoArea.appendChild(canvas);

    const offline = _offlineCenterTpl.cloneNode(true);
    offline.className += " absolute inset-0 justify-center";
    // "Son Görülme: 14:30" sablonun sahte saatiydi -- gercek deger yoksa
    // uydurulmaz (rule 3), "—" birakilir.
    offline.children[2].textContent = "Son Görülme: " + (cam.last_seen_at ? fmtTime(cam.last_seen_at) : "—");
    offline.style.display = "flex"; // baslangic: baglanti kurulmadi (bkz. asagida display toggling notu)
    videoArea.appendChild(offline);

    nameSpan.textContent = cam.name;
    fpsSpan.textContent = "--";
    statusText.textContent = "BAĞLANTI YOK";
    dot.className = DOT_OFFLINE_CLASS;

    box._vadap = { cam, dot, statusText, fpsSpan, videoArea, canvas, offline, lastMeta: null, alarmTimer: null };
    return box;
}

// ------------------------------------------------------------- izgara boyutu
const BTN_SINGLE = document.querySelector('button[title="Tekli Görünüm"]');
const BTN_2X2 = document.querySelector('button[title="2x2 Izgara"]');
const BTN_3X3 = document.querySelector('button[title="3x3 Izgara"]');
const ACTIVE_TAB_CLASS = BTN_2X2.className;   // sablonda 2x2 varsayilan aktif
const INACTIVE_TAB_CLASS = BTN_SINGLE.className;

let _gridSize = 4;
let _cameras = [];
let _connections = [];

function _applyGridClass(n) {
    const cols = n === 1 ? 1 : n === 4 ? 2 : 3;
    GRID.className = GRID.className
        .replace(/grid-cols-\d+/, "grid-cols-" + cols)
        .replace(/grid-rows-\d+/, "grid-rows-" + cols);
}

function _setGridSize(n) {
    _gridSize = n;
    [BTN_SINGLE, BTN_2X2, BTN_3X3].forEach((b) => { b.className = INACTIVE_TAB_CLASS; });
    (n === 1 ? BTN_SINGLE : n === 4 ? BTN_2X2 : BTN_3X3).className = ACTIVE_TAB_CLASS;
    _applyGridClass(n);
    _renderGrid();
}
BTN_SINGLE.addEventListener("click", () => _setGridSize(1));
BTN_2X2.addEventListener("click", () => _setGridSize(4));
BTN_3X3.addEventListener("click", () => _setGridSize(9));

// ------------------------------------------------------------------ katmanlar
const LAYER_INPUTS = document.querySelectorAll(
    ".flex.items-center.gap-3.border-r.border-outline-variant.pr-4 input[type=\"checkbox\"]");
const LAYER_KEYS = ["box", "skeleton", "zone", "id"];
const _layers = {};
LAYER_INPUTS.forEach((input, i) => {
    _layers[LAYER_KEYS[i]] = input.checked;
    input.addEventListener("change", () => {
        _layers[LAYER_KEYS[i]] = input.checked;
        _redrawAll();
    });
});

function _redrawAll() {
    for (const box of GRID.children) {
        const st = box._vadap;
        if (st && st.lastMeta) _drawForBox(st);
    }
}

async function _drawForBox(st) {
    const meta = st.lastMeta;
    let zones = meta.zones;
    if (_layers.zone && (!zones || !zones.length)) zones = await zonesFor(st.cam.id);
    drawOverlay(st.canvas, meta, zones || [], _layers);
}

// --------------------------------------------------------------- baglantilar
function _connectCamera(cam, box) {
    const st = box._vadap;
    const live = openReconnectingSocket(liveUrlFn("live", cam.name), {
        // DIKKAT: onOpen'da "AKTIF" YAZILMAZ -- ws_server.py el sikismayi
        // yalniz jeton+yol formatina gore kabul eder, o camera_id'ye hic
        // yayin yapan olmasa da baglanti acilir. "Canli" durumu yalnizca
        // GERCEK bir kare gelince (onMessage) dogrudur; aksi halde her kutu
        // yayin yokken de yanlislikla AKTIF gorunurdu (tarayicida yakalanan
        // gercek hata -- test bunu goremezdi).
        onMessage(blob) {
            _noteFrame(cam.name);
            setFrameImage(st.videoArea, blob);
            // hidden ozniteligi DEGIL: bu blok Tailwind'in "flex" sinifini
            // tasiyor, [hidden]{display:none} kural olarak UA sayfasindan
            // gelir ve author kaynakli .flex{display:flex} kuralindan daha
            // dusuk onceliklidir -- bu yuzden `hidden=true` GORSEL OLARAK
            // ISE YARAMAZ (Tailwind kutusu ustte kalir). inline style her
            // zaman kazanir.
            st.offline.style.display = "none";
            // st.alarming iken dot/statusText'e DOKUNULMAZ: her kare (saniyede
            // birkac kez) buraya dusuyor, korumasiz yazarsa _flashBoxAlarm'in
            // "IHLAL" durumunu bir sonraki karede aninda ezerdi -- kirmizi
            // durum goze hic gorunmeden kaybolurdu (gercek tarayici testinde
            // yakalandi).
            if (!st.alarming) {
                st.dot.className = DOT_ONLINE_CLASS;
                st.statusText.textContent = "AKTİF";
            }
        },
        onClose() {
            st.alarming = false;
            st.dot.className = DOT_OFFLINE_CLASS;
            st.statusText.textContent = "BAĞLANTI YOK";
            st.offline.style.display = "flex";
        },
    });
    const meta = openReconnectingSocket(liveUrlFn("meta", cam.name), {
        onMessage(data) {
            st.lastMeta = JSON.parse(data);
            st.fpsSpan.textContent = st.lastMeta.fps + " FPS";
            _drawForBox(st);
        },
    });
    return { live, meta };
}

function _stopAllSockets() {
    for (const c of _connections) { c.live.stop(); c.meta.stop(); }
    _connections = [];
}

function _renderGrid() {
    _stopAllSockets();
    GRID.innerHTML = "";
    for (const cam of _cameras.slice(0, _gridSize)) {
        const box = _makeLiveBox(cam);
        GRID.appendChild(box);
        _connections.push(_connectCamera(cam, box));
    }
}

// Sayfa gizlenince (baska sekme/pencere) tum kutu soketleri kapanir; geri
// donulunce izgara yeniden kurulur (ASAMA8_PLAN.md SS1, madde "yalniz
// gorunen kameralar WS acar").
document.addEventListener("visibilitychange", () => {
    if (document.hidden) _stopAllSockets();
    else _renderGrid();
});

// --------------------------------------------------------------------- alarm
function _boxForAlert(alert) {
    for (const box of GRID.children) {
        const st = box._vadap;
        if (!st) continue;
        if (st.cam.name === alert.camera_name || String(st.cam.id) === String(alert.camera_id)) return box;
    }
    return null;
}

function _flashBoxAlarm(alert) {
    const box = _boxForAlert(alert);
    if (!box) return;
    const st = box._vadap;
    box.classList.remove("border", "border-outline-variant");
    box.classList.add("border-none", "pulse-border");
    st.statusText.textContent = "İHLAL";
    st.dot.className = DOT_ALARM_CLASS;
    st.alarming = true; // canli akisin onMessage'i dot/statusText'i EZMESIN
    clearTimeout(st.alarmTimer);
    st.alarmTimer = setTimeout(() => {
        st.alarming = false;
        box.classList.remove("pulse-border", "border-none");
        box.classList.add("border", "border-outline-variant");
        if (st.offline.style.display === "none") { st.statusText.textContent = "AKTİF"; st.dot.className = DOT_ONLINE_CLASS; }
        else { st.statusText.textContent = "BAĞLANTI YOK"; st.dot.className = DOT_OFFLINE_CLASS; }
    }, 6000);
}

function _showAlarmToast(alert) {
    if (!ALARM_TOAST) return;
    const title = ALARM_TOAST.querySelector("span.font-title-sm");
    const meta = ALARM_TOAST.querySelector("span.font-data-mono");
    if (title) title.textContent = (TIP_ADI[alert.anomaly_type] || alert.anomaly_type) + " Tespit Edildi";
    if (meta) meta.textContent = (alert.camera_name || alert.camera_id) + " - " + _fmtEpoch(alert.start_time);
    ALARM_TOAST.style.display = "";
}

function _fmtEpoch(sec) {
    if (sec == null) return "--";
    return fmtTime(new Date(sec * 1000).toISOString());
}

// ---------------------------------------------------------- canli olay akisi
const _fillEventCard = EVENT_STREAM ? rowTemplate(EVENT_STREAM) : null;

function _fillAlertCard(card, alert) {
    const strip = card.children[0];
    const header = card.children[1];
    const timeGroup = header.children[0];
    const confSpan = header.children[1];
    const body = card.children[2];
    const title = body.children[0];
    const camText = body.children[1];
    const footer = card.children[3];
    const img = footer.children[0];
    const inspectBtn = footer.children[1];

    const sev = TYPE_SEVERITY[alert.anomaly_type] || "medium";
    strip.className = "absolute left-0 top-0 bottom-0 w-1 " + (SEVERITY_STRIP[sev] || "bg-error");
    setTrailingText(timeGroup, _fmtEpoch(alert.start_time));
    confSpan.textContent = "%" + Math.round((alert.score || 0) * 100) + " EMİN";
    title.textContent = TIP_ADI[alert.anomaly_type] || alert.anomaly_type;
    camText.textContent = alert.camera_name || alert.camera_id;

    // Alarm WS'i kanit karesi tasimaz (evidence yazimini beklemez, SS "kirmizi
    // alarm" bolumu) -- sahte gorsel birakilmaz, kucuk resim kaldirilir.
    if (img) img.remove();
    if (inspectBtn) {
        inspectBtn.addEventListener("click", (e) => { e.stopPropagation(); location.href = "olaylar.html"; });
    }
    card.style.cursor = "pointer";
    card.addEventListener("click", () => { location.href = "olaylar.html"; });
}

function _pushAlertCard(alert) {
    if (!_fillEventCard) return;
    const card = _fillEventCard(alert);
    _fillAlertCard(card, alert);
    EVENT_STREAM.prepend(card);
    while (EVENT_STREAM.children.length > 30) EVENT_STREAM.lastChild.remove();
}

function _startAlerts() {
    openReconnectingSocket(alertsWsUrl, {
        onMessage(data) {
            const alert = JSON.parse(data);
            _showAlarmToast(alert);
            _flashBoxAlarm(alert);
            _pushAlertCard(alert);
        },
    });
}

// ------------------------------------------------------------------- yukleme
async function _load() {
    try {
        _cameras = await api("/api/cameras");
    } catch (e) {
        GRID.innerHTML = '<p class="col-span-full p-4 text-error font-body-sm text-body-sm">' +
            "Kameralar yüklenemedi: " + e.message + "</p>";
        return;
    }
    // Yayinda olan kamera ONCE gelir: izgara ilk N kamerayi gosteriyor
    // (_renderGrid), id sirasi kullanildiginda calisan kameralar disarida
    // kalip ekran bastan asagi "Baglanti Yok" olabiliyordu -- 8.6 demosunda
    // tam bunu gosterdi. Sira ICINDE id sirasi korunur (kararli siralama).
    await healthReady();
    _cameras.sort((a, b) => (healthWsPort(b.name) ? 1 : 0) - (healthWsPort(a.name) ? 1 : 0));
    _renderGrid();
    _startAlerts();
}

_load();
