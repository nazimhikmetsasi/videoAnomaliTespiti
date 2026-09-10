// Canli goru katmani, ortak (ASAMA8_PLAN.md SS3, 8.4). index.js (izgara) ve
// kamera-detay.js (tekli) paylasir -- baglanti/yeniden-baglanma/cizim burada
// TEK yerde yazilir (DURUM.md "Acik sorular": kopyalanmis yardimcilar).
//
// Canli goru sunucusu (vision/ws_server.py) API ile AYNI host, FARKLI port
// (8001) -- ASAMA8_PLAN.md SS1. /ws/alerts ise API ile ayni origin'de.

const RECONNECT_MAX_MS = 15000;
// Saglik ucu (GET /api/health/cameras) kisa sureli onbellegi -- izgarada N
// kutu ayni anda soruyor, N istek DEGIL tek paylasilan istek (zonesFor'daki
// desenle ayni ruh, farki kamera basina degil TEK anahtarli olmasi).
const HEALTH_POLL_MS = 3000;
// sistem-sagligi.js'teki STALE_SEC (ASAMA8_PLAN.md SS3.8.3) ile AYNI esik --
// ayri sayfa betikleri arasinda modul yok, deger burada bilerek tekrarlanir.
const STALE_SEC = 60;

function _wsProto() {
    return location.protocol === "https:" ? "wss:" : "ws:";
}

function liveWsUrl(kind, cameraId, port) {
    return _wsProto() + "//" + location.hostname + ":" + port + "/ws/" + kind + "/" +
        encodeURIComponent(cameraId) + "?token=" + encodeURIComponent(token());
}

function alertsWsUrl() {
    return _wsProto() + "//" + location.host + "/ws/alerts?token=" + encodeURIComponent(token());
}

// --------------------------------------------------------------- saglik/port
// Kamera basina ws_port + age_sec: TEK arka plan yoklayici, sayfada ilk
// kullanildiginda baslar, HEALTH_POLL_MS'de bir tazelenir. Eszamanli N
// cagri N istek ATMAZ -- hepsi ayni son sonucu okur.
let _healthByName = {};
let _healthPolling = false;

async function _pollHealthOnce() {
    try {
        const rows = await api("/api/health/cameras");
        const byName = {};
        for (const row of rows) byName[row.name] = row;
        _healthByName = byName;
    } catch (_e) {
        // ag hatasi: onceki bilinen durum korunur, sonraki yoklamada tekrar denenir.
    }
}

let _healthFirst = null;

function _ensureHealthPolling() {
    if (_healthPolling) return _healthFirst;
    _healthPolling = true;
    _healthFirst = _pollHealthOnce();
    setInterval(_pollHealthOnce, HEALTH_POLL_MS);
    return _healthFirst;
}

// Izgara kurulmadan ONCE ilk yoklamanin bitmesini bekler -- kutu sirasi
// "yayinda olan once" olacaksa (index.js) veri gelmeden siralama yapilamaz.
function healthReady() {
    return _ensureHealthPolling() || Promise.resolve();
}

// ws_port yoksa VEYA kayit STALE_SEC'ten bayatsa null -- cagiran taraf soket
// ACMAZ (ASAMA8_PLAN.md 8.6 SS3, madde 3: olu kameraya korlemesine baglanma).
function healthWsPort(cameraName) {
    _ensureHealthPolling();
    const doc = _healthByName[cameraName];
    if (!doc || doc.ws_port == null) return null;
    if (doc.age_sec != null && doc.age_sec > STALE_SEC) return null;
    return doc.ws_port;
}

// openReconnectingSocket'in urlFn'i icin hazir kapanis -- port cozumu HER
// denemede burada yapilir (bagli/kopuk bilgisi acildiktan sonra degil,
// tam da baglanma aninda taze olsun diye).
function liveUrlFn(kind, cameraName) {
    return () => {
        const port = healthWsPort(cameraName);
        return port ? liveWsUrl(kind, cameraName, port) : null;
    };
}

// Kopmada ustel geri cekilmeli yeniden baglanma (1s, 2s, 4s... tavan 15s).
// stop() cagrilinca bir sonraki deneme iptal edilir -- sayfa gizlenince veya
// izgara boyutu degisince kapatilan kutunun soketi GERCEKTEN kapanir
// (ASAMA8_PLAN.md SS3, madde "yalniz gorunen kameralar WS acar").
function openReconnectingSocket(urlFn, { onOpen, onMessage, onClose } = {}) {
    let ws = null;
    let stopped = false;
    let retryMs = 1000;
    let retryTimer = null;

    function connect() {
        if (stopped) return;
        const url = urlFn();
        if (!url) {
            // Port bilinmiyor / kamera saglik kaydi yok ya da bayat -- soket
            // hic ACILMAZ, HEALTH_POLL_MS sonra tekrar denenir (kamera ayaga
            // kalkinca kendiliginden baglanir).
            if (onClose) onClose();
            retryTimer = setTimeout(connect, HEALTH_POLL_MS);
            return;
        }
        ws = new WebSocket(url);
        ws.binaryType = "blob";
        ws.onopen = () => { retryMs = 1000; if (onOpen) onOpen(); };
        ws.onmessage = (ev) => { if (onMessage) onMessage(ev.data); };
        ws.onclose = () => {
            if (onClose) onClose();
            if (stopped) return;
            retryTimer = setTimeout(connect, retryMs);
            retryMs = Math.min(retryMs * 2, RECONNECT_MAX_MS);
        };
        ws.onerror = () => { try { ws.close(); } catch (_e) { /* zaten kapaniyor */ } };
    }
    connect();

    return {
        stop() {
            stopped = true;
            if (retryTimer) clearTimeout(retryTimer);
            if (ws) ws.close();
        },
    };
}

// Dogrulama olcumu icin (ASAMA8_PLAN.md dogrulama maddesi 3): kamera basina
// gercek karsi gelen kare zamanlari. UI'da gosterilmez, tarayici konsolundan
// `window.__vadapLiveStats` ile okunur.
window.__vadapLiveStats = window.__vadapLiveStats || {};

function _noteFrame(cameraId) {
    const s = window.__vadapLiveStats[cameraId] || (window.__vadapLiveStats[cameraId] = { times: [] });
    const now = performance.now();
    s.times.push(now);
    if (s.times.length > 100) s.times.shift();
    if (s.times.length > 1) {
        s.fps = Math.round(((s.times.length - 1) / ((now - s.times[0]) / 1000)) * 10) / 10;
    }
}

// Onceki blob URL birakilmazsa bellek sizar (ASAMA8_PLAN.md SS1, madde 1).
// Once yeni gorsele gecilir, sonra eskisi serbest birakilir.
function setFrameImage(videoAreaEl, blob) {
    const url = URL.createObjectURL(blob);
    const prevUrl = videoAreaEl.dataset.liveUrl;
    videoAreaEl.style.backgroundImage = "url('" + url + "')";
    videoAreaEl.dataset.liveUrl = url;
    if (prevUrl) URL.revokeObjectURL(prevUrl);
}

// GET /api/zones?camera_id= yalnizca vision kural motoru kapaliyken (meta
// govdesinde zones bos geldiginde) tamamlayici olarak cagrilir -- kamera
// basina onbelleklenir, bolgeler calisirken degismez.
const _zoneCache = {};
async function zonesFor(cameraId) {
    if (_zoneCache[cameraId]) return _zoneCache[cameraId];
    try {
        const zones = await api("/api/zones?camera_id=" + encodeURIComponent(cameraId));
        _zoneCache[cameraId] = zones;
        return zones;
    } catch (_e) {
        return [];
    }
}

// COCO 17 nokta iskelet baglantilari -- vision/run.py SKELETON ile ayni.
const SKELETON = [
    [15, 13], [13, 11], [16, 14], [14, 12], [11, 12], [5, 11], [6, 12],
    [5, 6], [5, 7], [7, 9], [6, 8], [8, 10], [1, 2], [0, 1], [0, 2],
    [1, 3], [2, 4], [3, 5], [4, 6],
];

// Uzerine cizilecek video gosterimi HER ZAMAN "contain" (bkz. cagiran taraf:
// backgroundSize=contain) -- letterbox'lu, oranti bozulmaz. Olcek hesabi da
// bununla eslesir: bbox PIKSEL (meta.width/height), zon poligonu 0-1
// NORMALIZE (ASAMA8_PLAN.md SS1, madde "Olcek donusumu kritik"). "cover"
// (kirpma) kullanilsaydi bu hesap konteynerin en-boy oranina gore kayardi --
// tam da uyarilan "en olasi hata".
function drawOverlay(canvas, meta, zones, layers) {
    const cssW = canvas.clientWidth, cssH = canvas.clientHeight;
    if (!cssW || !cssH) return;
    if (canvas.width !== cssW) canvas.width = cssW;
    if (canvas.height !== cssH) canvas.height = cssH;
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, cssW, cssH);
    if (!meta || !meta.width || !meta.height) return;

    const scale = Math.min(cssW / meta.width, cssH / meta.height);
    const offX = (cssW - meta.width * scale) / 2;
    const offY = (cssH - meta.height * scale) / 2;
    const toPx = (x, y) => [offX + x * scale, offY + y * scale];
    const toNormPx = (x, y) => [offX + x * meta.width * scale, offY + y * meta.height * scale];

    if (layers.zone && zones && zones.length) {
        ctx.lineWidth = 2;
        ctx.strokeStyle = "rgba(173,198,255,0.9)";
        ctx.fillStyle = "rgba(173,198,255,0.15)";
        for (const z of zones) {
            const poly = z.polygon;
            if (!poly || poly.length < 3) continue;
            ctx.beginPath();
            poly.forEach(([x, y], i) => {
                const [px, py] = toNormPx(x, y);
                if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
            });
            ctx.closePath();
            ctx.fill();
            ctx.stroke();
        }
    }

    for (const t of (meta.tracks || [])) {
        const [x1, y1, x2, y2] = t.bbox;
        const [bx1, by1] = toPx(x1, y1);
        const [bx2, by2] = toPx(x2, y2);
        if (layers.box) {
            ctx.lineWidth = 2;
            ctx.strokeStyle = "#adc6ff";
            ctx.strokeRect(bx1, by1, bx2 - bx1, by2 - by1);
        }
        if (layers.id) {
            ctx.fillStyle = "#adc6ff";
            ctx.font = "10px 'JetBrains Mono', monospace";
            ctx.fillText("ID " + t.id, bx1 + 2, Math.max(10, by1 - 4));
        }
        if (layers.skeleton && t.kp) {
            ctx.lineWidth = 2;
            ctx.strokeStyle = "#fbbf24";
            for (const [a, b] of SKELETON) {
                const ka = t.kp[a], kb = t.kp[b];
                if (ka[2] > 0.5 && kb[2] > 0.5) {
                    const [ax, ay] = toPx(ka[0], ka[1]);
                    const [bxp, byp] = toPx(kb[0], kb[1]);
                    ctx.beginPath();
                    ctx.moveTo(ax, ay);
                    ctx.lineTo(bxp, byp);
                    ctx.stroke();
                }
            }
        }
    }
}

// Metin dugumu tuzagi (DURUM.md Asama 8.3 dersi): ikon span'inden SONRA gelen
// serbest metin dugumune yazmak icin oncekileri silip TEK yeni dugum eklemek
// gerekir -- childNodes[i]'ye dogrudan yazmak sablon metnini yaninda birakir.
function setTrailingText(el, text) {
    for (const node of Array.from(el.childNodes)) {
        if (node.nodeType === Node.TEXT_NODE) el.removeChild(node);
    }
    el.appendChild(document.createTextNode(text));
}
