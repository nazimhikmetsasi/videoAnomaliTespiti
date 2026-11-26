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

// ---------------------------------------------------------------- alarm sesi
// Web Audio beeps (no sound files). AudioContext stays suspended until a user
// gesture, so the first click/key creates or resumes it.
const BEEP_PLAN = { critical: [880, 3], high: [660, 2] };
const BEEP_MS = 150, BEEP_GAP_MS = 120, BEEP_MIN_INTERVAL_MS = 1000;
let _audioCtx = null, _lastBeepAt = 0;

function _isMuted() {
    try { return localStorage.getItem("alarmMuted") === "1"; } catch (_e) { return false; }
}

function _unlockAudio() {
    try {
        if (!_audioCtx) {
            const AC = window.AudioContext || window.webkitAudioContext;
            if (!AC) return;
            _audioCtx = new AC();
        }
        if (_audioCtx.state === "suspended") _audioCtx.resume();
    } catch (_e) { /* audio is optional */ }
}
document.addEventListener("click", _unlockAudio);
document.addEventListener("keydown", _unlockAudio);

function _audioLocked() {
    return !_audioCtx || _audioCtx.state !== "running";
}

// Returns true when a beep sequence was started.
function _playAlarmSound(sev) {
    const plan = BEEP_PLAN[sev];
    if (!plan || _isMuted() || _audioLocked()) return false;
    const nowMs = Date.now();
    if (nowMs - _lastBeepAt < BEEP_MIN_INTERVAL_MS) return false; // one sound per second
    _lastBeepAt = nowMs;
    const [freq, count] = plan;
    const t0 = _audioCtx.currentTime;
    for (let i = 0; i < count; i++) {
        const start = t0 + i * (BEEP_MS + BEEP_GAP_MS) / 1000;
        const end = start + BEEP_MS / 1000;
        const osc = _audioCtx.createOscillator();
        const gain = _audioCtx.createGain();
        osc.frequency.value = freq;
        // short ramps avoid clicks at start/end
        gain.gain.setValueAtTime(0.0001, start);
        gain.gain.linearRampToValueAtTime(0.25, start + 0.02);
        gain.gain.linearRampToValueAtTime(0.0001, end);
        osc.connect(gain).connect(_audioCtx.destination);
        osc.start(start);
        osc.stop(end + 0.02);
    }
    return true;
}

// Mute button next to the grid-size buttons (same class tokens as them).
const BTN_MUTE = document.createElement("button");
BTN_MUTE.className = INACTIVE_TAB_CLASS;
BTN_MUTE.title = "Alarm sesi";
const _muteIcon = document.createElement("span");
_muteIcon.className = "material-symbols-outlined text-[18px]";
BTN_MUTE.appendChild(_muteIcon);
BTN_SINGLE.parentElement.appendChild(BTN_MUTE);

function _paintMute() {
    _muteIcon.textContent = _isMuted() ? "volume_off" : "volume_up";
}
BTN_MUTE.addEventListener("click", () => {
    try { localStorage.setItem("alarmMuted", _isMuted() ? "0" : "1"); } catch (_e) { /* private mode */ }
    _paintMute();
});
_paintMute();

// ------------------------------------------------------------ toast + onay
// The toast shows only the latest alarm; its buttons act on that alarm's event.
const TOAST_BTN_WRAP = document.createElement("div");
TOAST_BTN_WRAP.className = "flex items-center gap-2";
const TOAST_NOTE = document.createElement("div");
TOAST_NOTE.className = "text-xs opacity-80";
let _toastBtns = null, _toastCtx = null, _toastSeq = 0, _toastHideTimer = null;

(function _setupToast() {
    if (!ALARM_TOAST) return;
    const first = ALARM_TOAST.querySelector("button");
    if (!first) return;
    first.removeAttribute("onclick"); // template's inline "just hide" handler
    first.textContent = "Görüldü";
    const falseBtn = first.cloneNode(false);
    falseBtn.textContent = "Yanlış Alarm";
    const closeBtn = first.cloneNode(false);
    closeBtn.textContent = "Kapat";
    first.parentElement.insertBefore(TOAST_BTN_WRAP, first);
    TOAST_BTN_WRAP.append(first, falseBtn, closeBtn);
    ALARM_TOAST.querySelector("span.font-data-mono").parentElement.appendChild(TOAST_NOTE);
    _toastBtns = { ack: first, fp: falseBtn, close: closeBtn };
    first.addEventListener("click", () => _setEventStatus("acknowledged"));
    falseBtn.addEventListener("click", () => _setEventStatus("false_positive"));
    closeBtn.addEventListener("click", () => { ALARM_TOAST.style.display = "none"; });
})();

function _camIdOf(alert) {
    const cam = _cameras.find((c) => c.name === alert.camera_name || String(c.id) === String(alert.camera_id));
    return cam ? cam.id : alert.camera_id;
}

// Alarm does not wait for the DB write, so the event may not exist yet: retry.
async function _findEventId(ctx, seq) {
    const q = new URLSearchParams({
        camera_id: ctx.cameraId, anomaly_type: ctx.type, limit: "5",
        from: new Date((ctx.t - ctx.win) * 1000).toISOString(),
        to: new Date((ctx.t + ctx.win) * 1000).toISOString(),
    });
    for (let i = 0; i < 3; i++) {
        if (seq !== _toastSeq) return null;
        const res = await api("/api/events?" + q.toString());
        const items = (res && res.items) || [];
        if (items.length) {
            const dist = (e) => Math.abs(new Date(e.started_at).getTime() / 1000 - ctx.t);
            return items.reduce((a, b) => (dist(b) < dist(a) ? b : a)).id;
        }
        if (i < 2) await new Promise((r) => setTimeout(r, 1500));
    }
    return null;
}

async function _setEventStatus(status) {
    const ctx = _toastCtx, seq = _toastSeq;
    if (!ctx || ctx.busy) return;
    ctx.busy = true;
    TOAST_NOTE.textContent = "...";
    try {
        const id = await _findEventId(ctx, seq);
        if (seq !== _toastSeq) return;
        if (id == null) { TOAST_NOTE.textContent = "Olay henüz kaydedilmedi; Olaylar ekranından onaylayın"; return; }
        await api("/api/events/" + id, { method: "PATCH", body: { status } });
        if (seq !== _toastSeq) return;
        _toastBtns.ack.style.display = _toastBtns.fp.style.display = "none";
        TOAST_NOTE.textContent = status === "acknowledged" ? "Görüldü ✓" : "Yanlış alarm olarak işaretlendi";
        clearTimeout(_toastHideTimer);
        _toastHideTimer = setTimeout(() => { if (seq === _toastSeq) ALARM_TOAST.style.display = "none"; }, 2000);
    } catch (e) {
        if (seq !== _toastSeq) return;
        TOAST_NOTE.textContent = /403|yetki|forbidden/i.test(e.message)
            ? "Bu işlem için operatör yetkisi gerekiyor" : "İşlem başarısız: " + e.message;
    } finally {
        ctx.busy = false;
    }
}

// opts: title, meta, sub (extra line), sev (sound), ctx (event lookup)
function _openToast(opts) {
    if (!ALARM_TOAST) return;
    _toastSeq++;
    clearTimeout(_toastHideTimer);
    _toastCtx = opts.ctx || null;
    const title = ALARM_TOAST.querySelector("span.font-title-sm");
    const meta = ALARM_TOAST.querySelector("span.font-data-mono");
    if (title) title.textContent = opts.title;
    if (meta) meta.textContent = opts.meta;
    TOAST_NOTE.textContent = opts.sub || "";
    if (_toastBtns) _toastBtns.ack.style.display = _toastBtns.fp.style.display = "";
    ALARM_TOAST.style.display = "";
    const played = _playAlarmSound(opts.sev);
    if (BEEP_PLAN[opts.sev] && !played && _audioLocked() && !_isMuted()) {
        TOAST_NOTE.textContent = (opts.sub ? opts.sub + " · " : "") + "Sesli alarm için sayfaya bir kez tıklayın";
    }
}

function _showAlarmToast(alert) {
    _openToast({
        title: (TIP_ADI[alert.anomaly_type] || alert.anomaly_type) + " Tespit Edildi",
        meta: (alert.camera_name || alert.camera_id) + " - " + _fmtEpoch(alert.start_time),
        sev: TYPE_SEVERITY[alert.anomaly_type] || "medium",
        ctx: { cameraId: _camIdOf(alert), type: alert.anomaly_type, t: alert.start_time, win: 2 },
    });
}

// fall_outcome "down": critical toast bound to the FALL event (fall_time is the
// first candidate; the event starts at the session's earliest one, hence +-3 s).
function _showOutcomeToast(o) {
    const m = o.metrics || {};
    const sec = Math.round(Number(m.decided_after_sec) || 0);
    const stale = Number(m.last_seen_ago_sec) > 3.6;
    _openToast({
        title: "Kalkamadı — " + (o.camera_name || o.camera_id),
        meta: _fmtEpoch(o.fall_time),
        sub: stale ? "Düşmeden " + sec + " sn sonra kamerada görünmüyor"
            : "Düşmeden " + sec + " sn sonra hâlâ yerde",
        sev: "critical",
        ctx: { cameraId: _camIdOf(o), type: "FALL", t: o.fall_time, win: 3 },
    });
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

// Outcome card reuses the alarm card, then overrides title/badge/strip.
function _pushOutcomeCard(o) {
    if (!_fillEventCard) return;
    const card = _fillEventCard(o);
    _fillAlertCard(card, { anomaly_type: "FALL", start_time: o.fall_time, camera_name: o.camera_name, camera_id: o.camera_id, score: 0 });
    const down = o.outcome === "down";
    card.children[0].className = "absolute left-0 top-0 bottom-0 w-1 " + (down ? "bg-error" : "bg-outline-variant");
    card.children[1].children[1].textContent = down ? "KALKAMADI" : "KALKTI";
    card.children[2].children[0].textContent = down ? "Düşme: kalkamadı" : "Kalktı";
    EVENT_STREAM.prepend(card);
    while (EVENT_STREAM.children.length > 30) EVENT_STREAM.lastChild.remove();
}

function _startAlerts() {
    openReconnectingSocket(alertsWsUrl, {
        onMessage(data) {
            const alert = JSON.parse(data);
            if (alert.kind === "fall_outcome") {
                if (alert.outcome === "down") _showOutcomeToast(alert);
                _pushOutcomeCard(alert);
                return;
            }
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
            "Kameralar yüklenemedi: " + _escXml(e.message) + "</p>";
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
