// Bolge cizim ekrani (ASAMA8_PLAN.md SS3, 8.5b). Sol: kamera listesi. Orta:
// canli kare arka plan + tiklayarak poligon cizme. Sag: bolge ozellikleri
// formu (ekle/duzenle/sil). Baglanti/yeniden-baglanma js/live.js'te ortak
// (kamera-detay.js ile ayni), burada kopyalanmiyor.
//
// zone_type="direction" arayuzde YOK: vision/rules/zone.py ve loiter.py
// yalnizca "forbidden" ve "restricted_hours" degerlerini tanir (grep
// dogrulandi) -- "direction" tipinde bolge olusturmak hicbir kurali beslemez,
// sablondaki "Ters Yon Tespiti" secenegi gercek karsiligi olmayan bir sablon
// ogesidir (ASAMA8_PLAN.md SS4). JS ile sadece iki gercek deger sunulur.

requireAuth();

let cameras = [];
let selectedCameraId = null;
let selectedCamera = null;
let zones = [];
let selectedZone = null;
let draftPoints = []; // [[x0-1, y0-1], ...] -- hem yeni cizim hem duzenlenen bolgenin calisma kopyasi
let drawMode = false;
let liveSock = null;

// ------------------------------------------------------------- DOM baglama
const [leftAside, rightAside] = document.querySelectorAll("main > aside");
const canvasSection = document.querySelector("main > section");

const searchInput = leftAside.querySelector('input[placeholder="Kamera ara..."]');
const cameraListEl = leftAside.querySelector(".flex-1.overflow-y-auto.p-2.flex.flex-col.gap-1");

const toolbar = canvasSection.querySelector(".bg-surface.border.border-outline-variant.rounded-t-lg");
const camLabel = toolbar.querySelector("span.font-data-mono");
const [pointBtn, finishBtn, clearBtn] = toolbar.querySelectorAll("button");

const canvasWrap = canvasSection.querySelector(".flex-1.relative.bg-black");
const bgFrameEl = canvasWrap.querySelector(".bg-cover");
const crosshairEl = canvasWrap.querySelector(".cursor-crosshair");
const svgEl = canvasWrap.querySelector("svg");
const statusOverlay = canvasWrap.querySelector(".absolute.top-4.right-4");
const statusDot = statusOverlay.children[0];
const statusText = statusOverlay.children[1];

const formList = rightAside.querySelector(".flex-1.overflow-y-auto.p-4.flex.flex-col.gap-5");
const nameGroup = formList.children[0];
const typeGroup = formList.children[1];
const activeGroup = formList.children[2];
const coordsGroup = formList.children[3];
const nameInput = nameGroup.querySelector("input");
const typeSelect = typeGroup.querySelector("select");
const activeCheckbox = activeGroup.querySelector('input[type="checkbox"]');
const coordsContainer = coordsGroup.querySelector(".bg-surface-container.border.border-outline-variant.rounded.font-data-mono");
const actionBar = rightAside.querySelector(".p-4.border-t.border-outline-variant.bg-surface-container-lowest.flex.gap-3.mt-auto.shrink-0");
const [cancelBtn, saveBtn] = actionBar.querySelectorAll("button");

// -------------------------------------------------------- sablon -> gercek deger
// Sablonun 4 sahte secenegi (yasak/ters_yon/bekleme/nesne_birakma) gercek
// veritabani degerleriyle ortusmuyor -- yalniz kural motorunun tanidigi
// ikisi sunulur.
typeSelect.innerHTML =
    '<option value="forbidden">Yasak Bölge</option>' +
    '<option value="restricted_hours">Saatli Kısıt</option>';

// restricted_hours icin saat araligi -- sablonda karsiligi yok, ayni sinif
// jetonlariyla JS'te eklenip tipe gore gizlenir/gosterilir.
const TIME_INPUT_CLASS =
    "w-full bg-surface-container-low border border-outline-variant rounded px-3 py-2 " +
    "text-body-sm text-on-surface focus:outline-none focus:border-secondary " +
    "focus:ring-1 focus:ring-secondary transition-all";
const timeGroup = document.createElement("div");
timeGroup.className = "flex flex-col gap-1.5";
timeGroup.style.display = "none";
timeGroup.innerHTML =
    '<label class="font-body-sm text-body-sm text-on-surface-variant">Kısıt Saatleri</label>' +
    '<div class="flex items-center gap-2">' +
    '<input id="zoneActiveFrom" type="time" class="' + TIME_INPUT_CLASS + '"/>' +
    '<span class="text-on-surface-variant">–</span>' +
    '<input id="zoneActiveTo" type="time" class="' + TIME_INPUT_CLASS + '"/>' +
    "</div>";
formList.insertBefore(timeGroup, activeGroup);
const fromInput = timeGroup.querySelector("#zoneActiveFrom");
const toInput = timeGroup.querySelector("#zoneActiveTo");

typeSelect.addEventListener("change", () => {
    timeGroup.style.display = typeSelect.value === "restricted_hours" ? "" : "none";
});

// Sil dugmesi -- yalnizca bir bolge seciliyken gorunur (sablonda yok, ayni
// jeton stiliyle -- text-error + border border-outline-variant).
const deleteBtn = document.createElement("button");
deleteBtn.type = "button";
deleteBtn.className =
    "flex-1 py-2 rounded font-body-sm text-body-sm border border-outline-variant " +
    "text-error hover:bg-error/10 transition-colors";
deleteBtn.textContent = "Sil";
deleteBtn.style.display = "none";
actionBar.insertBefore(deleteBtn, cancelBtn);

// Koordinat listesi satir sablonlari -- sablonun P1/P2/P3/P4 satirlarini
// klonlanabilir sablon olarak sokup container'i bosaltir.
const ROW_TPL = coordsContainer.children[0].cloneNode(true);
const ROW_LAST_TPL = coordsContainer.children[2].cloneNode(true); // vurgu cubuklu "son nokta" satiri
const ROW_PENDING_TPL = coordsContainer.children[3].cloneNode(true);
coordsContainer.innerHTML = "";

// Nokta Koy / Cizimi Bitir dugmelerinin orijinal sinif dizileri "acik"/"kapali"
// gorunumu olarak yeniden kullanilir (kamera-detay.js'teki katman dugmesi
// deseniyle ayni -- yeni sinif uydurulmuyor).
const POINT_BTN_ON = pointBtn.className;
const POINT_BTN_OFF = finishBtn.className;

// ------------------------------------------------------------- kamera listesi
const CAM_BTN_SELECTED =
    "w-full flex items-center gap-3 px-3 py-2.5 rounded text-left " +
    "bg-surface-container-highest border-l-2 border-secondary text-secondary";
const CAM_BTN_NORMAL =
    "w-full flex items-center gap-3 px-3 py-2.5 rounded text-left " +
    "hover:bg-surface-container transition-colors group";

function _renderCameraList(filter) {
    cameraListEl.innerHTML = "";
    const list = cameras.filter((c) => c.name.toLowerCase().includes(filter));
    if (list.length === 0) {
        const empty = document.createElement("p");
        empty.className = "text-on-surface-variant font-body-sm text-body-sm p-2 text-center";
        empty.textContent = cameras.length === 0 ? "Kamera yok" : "Eşleşen kamera yok";
        cameraListEl.appendChild(empty);
        return;
    }
    for (const cam of list) {
        const selected = cam.id === selectedCameraId;
        const btn = document.createElement("button");
        btn.className = selected ? CAM_BTN_SELECTED : CAM_BTN_NORMAL;
        if (!cam.is_active) btn.classList.add("opacity-60");
        const dotColor = cam.is_active ? "bg-green-500" : "bg-gray-500";
        btn.innerHTML =
            '<span class="w-2 h-2 rounded-full ' + dotColor + ' shrink-0"></span>' +
            '<span class="font-body-sm text-body-sm flex-1 truncate' +
            (selected ? " font-medium" : " text-on-surface group-hover:text-primary transition-colors") +
            (cam.is_active ? "" : " line-through") +
            '">' + _escXml(cam.name) + "</span>" +
            '<span class="material-symbols-outlined text-[16px]' +
            (selected ? "" : " text-transparent group-hover:text-on-surface-variant transition-colors") +
            '">chevron_right</span>';
        btn.addEventListener("click", () => _selectCamera(cam));
        cameraListEl.appendChild(btn);
    }
}

searchInput.addEventListener("input", () => _renderCameraList(searchInput.value.trim().toLowerCase()));

// ------------------------------------------------------------ canli arka plan
function _setLiveStatus(text, ok) {
    statusDot.className = "w-2 h-2 rounded-full " + (ok ? "bg-error animate-pulse" : "bg-outline-variant");
    statusText.textContent = text;
}

function _connectLive(cam) {
    if (liveSock) { liveSock.stop(); liveSock = null; }
    _setLiveStatus("Bağlantı Yok", false);
    liveSock = openReconnectingSocket(liveUrlFn("live", cam.name), {
        onMessage(blob) {
            setFrameImage(bgFrameEl, blob);
            // Ilk gercek kare gelince sablonun donuk/gri-ton onizleme
            // gorunumu kaldirilir (ASAMA8_PLAN.md SS4: sahte gorsel kalmaz).
            bgFrameEl.classList.remove("opacity-80", "mix-blend-luminosity", "grayscale-[30%]");
            _setLiveStatus("CANLI ÇİZİM MODU", true);
        },
        onClose() { _setLiveStatus("Bağlantı Yok", false); },
    });
}

// bg-cover -> contain: letterbox olmadan tiklama koordinatlari kayar
// (kamera-detay.js'teki ayni duzeltme, live.js drawOverlay yorumu).
bgFrameEl.style.backgroundSize = "contain";
bgFrameEl.style.backgroundPosition = "center";
bgFrameEl.style.backgroundRepeat = "no-repeat";

window.addEventListener("beforeunload", () => { if (liveSock) liveSock.stop(); });

// --------------------------------------------------------- olcek donusumu
// live.js drawOverlay ile AYNI formul (letterbox): scale = min(cssW/W, cssH/H).
function _scaleInfo() {
    const rect = crosshairEl.getBoundingClientRect();
    const W = selectedCamera.width, H = selectedCamera.height;
    const scale = Math.min(rect.width / W, rect.height / H);
    const offX = (rect.width - W * scale) / 2;
    const offY = (rect.height - H * scale) / 2;
    return { rect, scale, offX, offY, W, H };
}

function _toPx(nx, ny, info) {
    return [info.offX + nx * info.W * info.scale, info.offY + ny * info.H * info.scale];
}

// ------------------------------------------------------------------- cizim
function _polygonPoints(poly, info) {
    return poly.map(([x, y]) => _toPx(x, y, info).join(",")).join(" ");
}

function _zoneMarkup(zone, info, selected) {
    const pts = _polygonPoints(zone.polygon, info);
    const [lx, ly] = _toPx(zone.polygon[0][0], zone.polygon[0][1], info);
    let html = '<g class="transition-opacity hover:opacity-100 ' + (selected ? "opacity-100" : "opacity-80") + '">';
    html += '<polygon class="fill-error/20 stroke-error" points="' + pts + '" stroke-dasharray="4 2" stroke-width="' +
        (selected ? 3 : 2) + '"></polygon>';
    for (const [x, y] of zone.polygon) {
        const [px, py] = _toPx(x, y, info);
        html += '<circle class="fill-surface stroke-error" cx="' + px + '" cy="' + py + '" r="4" stroke-width="2"></circle>';
    }
    html += '<rect class="fill-error-container opacity-90" height="24" rx="4" width="90" x="' + (lx - 45) + '" y="' + (ly - 12) + '"></rect>';
    html += '<text class="font-data-mono text-label-caps fill-on-error-container font-bold" text-anchor="middle" x="' +
        lx + '" y="' + (ly + 4) + '">' + _escXml(zone.name) + "</text>";
    html += "</g>";
    return html;
}

function _draftMarkup(points, info, open) {
    const ptsAttr = points.map(([x, y]) => _toPx(x, y, info).join(",")).join(" ");
    const tag = open ? "polyline" : "polygon";
    const fillClass = open ? "fill-none stroke-secondary" : "fill-secondary/15 stroke-secondary";
    let html = '<g class="opacity-100"><' + tag + ' class="' + fillClass + '" points="' + ptsAttr +
        '" stroke-width="2"></' + tag + ">";
    points.forEach(([x, y], i) => {
        const [px, py] = _toPx(x, y, info);
        const last = i === points.length - 1;
        html += '<circle class="' + (last ? "fill-secondary stroke-white" : "fill-surface stroke-secondary") +
            '" cx="' + px + '" cy="' + py + '" r="4" stroke-width="2"></circle>';
    });
    html += "</g>";
    return html;
}

function _drawSvg() {
    if (!selectedCamera) { svgEl.innerHTML = ""; return; }
    const info = _scaleInfo();
    if (!info.rect.width || !info.rect.height) return;
    let html = "";
    for (const z of zones) {
        if (selectedZone && z.id === selectedZone.id) continue; // taslak onun yerine cizilir
        html += _zoneMarkup(z, info, false);
    }
    if (draftPoints.length > 0) html += _draftMarkup(draftPoints, info, drawMode || draftPoints.length < 3);
    svgEl.innerHTML = html;
}

window.addEventListener("resize", _drawSvg);

// ---------------------------------------------------------- koordinat listesi
function _renderCoords() {
    coordsContainer.innerHTML = "";
    draftPoints.forEach((p, i) => {
        const last = i === draftPoints.length - 1;
        const row = (last ? ROW_LAST_TPL : ROW_TPL).cloneNode(true);
        row.children[0].textContent = "P" + (i + 1);
        row.children[1].textContent = p[0].toFixed(3) + ", " + p[1].toFixed(3);
        coordsContainer.appendChild(row);
    });
    if (drawMode) {
        const row = ROW_PENDING_TPL.cloneNode(true);
        row.children[0].textContent = "P" + (draftPoints.length + 1) + " (Bekleniyor)";
        coordsContainer.appendChild(row);
    }
}

// ------------------------------------------------------------- nokta-icinde
// Standart ray-casting testi -- normalize (0-1) uzayda dogrudan calisir,
// piksel donusumune ihtiyac yok.
function _pointInPolygon(nx, ny, poly) {
    let inside = false;
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
        const [xi, yi] = poly[i], [xj, yj] = poly[j];
        const cross = ((yi > ny) !== (yj > ny)) && (nx < ((xj - xi) * (ny - yi)) / (yj - yi) + xi);
        if (cross) inside = !inside;
    }
    return inside;
}

function _hitTestZone(nx, ny) {
    for (let i = zones.length - 1; i >= 0; i--) {
        if (_pointInPolygon(nx, ny, zones[i].polygon)) return zones[i];
    }
    return null;
}

// ------------------------------------------------------------- tiklama kipi
function _setDrawButtonState() {
    pointBtn.className = drawMode ? POINT_BTN_ON : POINT_BTN_OFF;
    crosshairEl.style.cursor = drawMode ? "crosshair" : "pointer";
}

crosshairEl.addEventListener("click", (e) => {
    if (!selectedCamera) return;
    const info = _scaleInfo();
    const clickX = e.clientX - info.rect.left;
    const clickY = e.clientY - info.rect.top;
    const nx = (clickX - info.offX) / (info.W * info.scale);
    const ny = (clickY - info.offY) / (info.H * info.scale);
    // Letterbox seridine tiklama (0-1 disi) yok sayilir -- sunucu zaten
    // 422 ile reddediyor, v1'de piksel koordinat gonderilince bolge
    // kadraj disina sessizce dusmustu (docs/DURUM.md).
    if (nx < 0 || nx > 1 || ny < 0 || ny > 1) return;
    if (drawMode) {
        draftPoints.push([nx, ny]);
        _renderCoords();
        _drawSvg();
        return;
    }
    const hit = _hitTestZone(nx, ny);
    if (hit) _selectZone(hit);
});

pointBtn.addEventListener("click", () => {
    drawMode = !drawMode;
    _setDrawButtonState();
    _renderCoords();
});

finishBtn.addEventListener("click", () => {
    if (draftPoints.length < 3) { alert("Poligon en az 3 nokta içermeli."); return; }
    drawMode = false;
    _setDrawButtonState();
    _renderCoords();
    _drawSvg();
});

clearBtn.addEventListener("click", () => {
    // Yalnizca TASLAGI temizler -- var olan bolgeleri silmez (Sil dugmesi ayri).
    draftPoints = [];
    drawMode = false;
    _setDrawButtonState();
    _renderCoords();
    _drawSvg();
});

// --------------------------------------------------------------------- form
function _resetForm() {
    selectedZone = null;
    draftPoints = [];
    drawMode = false;
    _setDrawButtonState();
    nameInput.value = "";
    typeSelect.value = "forbidden";
    timeGroup.style.display = "none";
    fromInput.value = "";
    toInput.value = "";
    activeCheckbox.checked = true;
    deleteBtn.style.display = "none";
    _renderCoords();
    _drawSvg();
}

function _selectZone(zone) {
    selectedZone = zone;
    draftPoints = zone.polygon.map((p) => [p[0], p[1]]);
    drawMode = false;
    _setDrawButtonState();
    nameInput.value = zone.name;
    typeSelect.value = zone.zone_type;
    const isHours = zone.zone_type === "restricted_hours";
    timeGroup.style.display = isHours ? "" : "none";
    fromInput.value = zone.active_from ? zone.active_from.slice(0, 5) : "";
    toInput.value = zone.active_to ? zone.active_to.slice(0, 5) : "";
    activeCheckbox.checked = zone.is_active;
    deleteBtn.style.display = "";
    _renderCoords();
    _drawSvg();
}

cancelBtn.addEventListener("click", () => _resetForm());

saveBtn.addEventListener("click", async () => {
    if (!selectedCameraId) { alert("Önce bir kamera seçin."); return; }
    const name = nameInput.value.trim();
    if (!name) { alert("Bölge adı girin."); return; }
    if (draftPoints.length < 3) { alert("Poligon en az 3 nokta içermeli."); return; }
    const zoneType = typeSelect.value;
    const body = {
        camera_id: selectedCameraId,
        name,
        zone_type: zoneType,
        polygon: draftPoints,
        direction_vector: null,
        // <input type=time> "HH:MM" doner, sunucu "HH:MM:SS" bekliyor.
        active_from: zoneType === "restricted_hours" && fromInput.value ? fromInput.value + ":00" : null,
        active_to: zoneType === "restricted_hours" && toInput.value ? toInput.value + ":00" : null,
        is_active: activeCheckbox.checked,
    };
    try {
        if (selectedZone) {
            await api("/api/zones/" + selectedZone.id, { method: "PUT", body });
        } else {
            await api("/api/zones", { method: "POST", body });
        }
        await _loadZones();
        _resetForm();
    } catch (e) {
        // e.message: 403'te FORBIDDEN_MSG, 422'de Pydantic dogrulama
        // mesajlari (app.js _detailText() listeyi duz metne cevirir).
        alert("Kaydedilemedi: " + e.message);
    }
});

deleteBtn.addEventListener("click", async () => {
    if (!selectedZone) return;
    if (!confirm("'" + selectedZone.name + "' bölgesini silmek istediğinize emin misiniz?")) return;
    try {
        await api("/api/zones/" + selectedZone.id, { method: "DELETE" });
        await _loadZones();
        _resetForm();
    } catch (e) {
        alert("Silinemedi: " + e.message);
    }
});

// -------------------------------------------------------------------- yukleme
async function _loadZones() {
    if (!selectedCameraId) { zones = []; _drawSvg(); return; }
    try {
        zones = await api("/api/zones?camera_id=" + selectedCameraId);
    } catch (e) {
        // Sessizce bos liste gostermek "bolge yok" gibi okunur (sahte veri
        // birakma kurali) -- hata durum satirinda gorunur.
        zones = [];
        _setLiveStatus("Bölgeler yüklenemedi", false);
    }
    _drawSvg();
}

async function _selectCamera(cam) {
    selectedCameraId = cam.id;
    selectedCamera = cam;
    _resetForm();
    _renderCameraList(searchInput.value.trim().toLowerCase());
    camLabel.textContent = cam.name + " / " + cam.width + "x" + cam.height + " / " + cam.target_fps + "fps";
    _connectLive(cam);
    await _loadZones();
}

async function _init() {
    try {
        cameras = await api("/api/cameras");
    } catch (e) {
        alert("Kameralar yüklenemedi: " + e.message);
        return;
    }
    _renderCameraList("");
    if (cameras.length > 0) await _selectCamera(cameras[0]);
}

_resetForm();
_init();
