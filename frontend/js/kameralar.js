// Kameralar ekrani (ASAMA8_PLAN.md SS3, 8.3 ilk yarisi). GET /api/cameras
// tek istekte gelir, arama + durum/konum filtreleri istemci tarafinda calisir.

requireAuth();

let _tumKameralar = [];
let _fillRow = null;

const _tbody = document.querySelector("table tbody");
const _searchInput = document.querySelector('input[type="text"]');
const _selects = document.querySelectorAll("select");
const _statusSelect = _selects[0];
const _locationSelect = _selects[1];
// DIKKAT: kenar cubugu alt basligi ("Anomali Tespit Sistemi") AYNI sinif
// uclusunu tasiyor -- daha genis bir secici burayi da eslerdi (once tam
// boyle bir hata yapildi ve tarayici testinde yakalandi). Sayfalama
// kapsayicisiyla daraltiliyor.
const _countLabel = document.querySelector(".flex.items-center.justify-between.mt-2.px-2 span");
// bg-secondary-container yalniz bu dugmede var (tek eslesme dogrulandi --
// kenar cubugu yaniltmasi kameralar.js:14'teki notta anlatilan hatadir).
const _addBtn = document.querySelector("button.bg-secondary-container");
if (_addBtn) _addBtn.addEventListener("click", () => _openCameraForm(null));

function _showError(msg) {
    _tbody.innerHTML = "";
    const tr = document.createElement("tr");
    tr.innerHTML = '<td colspan="6" class="py-6 px-4 text-center text-error font-body-sm text-body-sm">' + msg + "</td>";
    _tbody.appendChild(tr);
}

function _populateLocationFilter(cameras) {
    const locations = [...new Set(cameras.map((c) => c.location).filter(Boolean))].sort();
    _locationSelect.innerHTML = "";
    const allOpt = document.createElement("option");
    allOpt.value = "";
    allOpt.textContent = "Tüm Konumlar";
    _locationSelect.appendChild(allOpt);
    for (const loc of locations) {
        const opt = document.createElement("option");
        opt.value = loc;
        opt.textContent = loc;
        _locationSelect.appendChild(opt);
    }
}

function _fillCameraRow(row, cam) {
    const tds = row.querySelectorAll("td");

    const nameSpans = tds[0].querySelectorAll("span");
    nameSpans[0].textContent = cam.name;
    nameSpans[1].textContent = cam.source;

    tds[1].textContent = cam.location || "—";

    const typeBadge = tds[2].querySelector("span");
    typeBadge.textContent = cam.source_type.toUpperCase();

    const resSpan = tds[3].querySelector("span.font-data-mono");
    const fpsSpan = tds[3].querySelector("span.text-on-surface-variant");
    resSpan.textContent = cam.width + "x" + cam.height;
    fpsSpan.textContent = cam.target_fps + " FPS";

    const dot = tds[4].querySelector("div.rounded-full");
    const statusText = tds[4].querySelector("span");
    statusText.textContent = CAMERA_STATUS_ADI[cam.status] || cam.status;
    // Durum noktasinin rengi gercek durumu yanlis gostermesin (sahte veri
    // birakma kurali) -- sablonun kendi iki varyanti (online/offline) burada
    // yeniden kullaniliyor, yeni renk uydurulmadi. "error" icin offline
    // gorunumu kullanilir, metin "Hata" oldugu icin ayirt edilebilir.
    if (cam.status === "online") {
        dot.className = "w-2 h-2 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]";
    } else {
        dot.className = "w-2 h-2 rounded-full bg-outline";
    }

    row.style.cursor = "pointer";
    row.addEventListener("click", () => {
        location.href = "kamera-detay.html?id=" + cam.id;
    });
    // Duzenle/Sil tiklaninca satir gezintisini (yukaridaki click) tetiklemesin.
    row.querySelectorAll("button").forEach((btn) => btn.addEventListener("click", (e) => e.stopPropagation()));

    const editBtn = row.querySelector('[title="Düzenle"]');
    if (editBtn) editBtn.addEventListener("click", () => _openCameraForm(cam));

    const delBtn = row.querySelector('[title="Sil"]');
    if (delBtn) delBtn.addEventListener("click", () => _deleteCamera(cam));
}

const _CAMERA_FIELDS = [
    { name: "name", label: "Ad", type: "text", required: true },
    { name: "source", label: "Kaynak", type: "text", required: true },
    {
        name: "source_type", label: "Kaynak Tipi", type: "select", required: true,
        options: [["webcam", "Webcam"], ["file", "Dosya"], ["rtsp", "RTSP"]],
    },
    { name: "location", label: "Konum", type: "text" },
    { name: "width", label: "Genişlik", type: "number" },
    { name: "height", label: "Yükseklik", type: "number" },
    { name: "target_fps", label: "Hedef FPS", type: "number" },
    { name: "is_active", label: "Aktif", type: "checkbox" },
];

// existing=null -> ekleme (POST), existing=kamera -> duzenleme (PUT, TAM govde).
// Hata durumunda diyalog onceki degerlerle + hata metniyle tekrar acilir --
// openFormDialog'un kendisi yazma istegi atmiyor (app.js).
async function _openCameraForm(existing) {
    let values = existing
        ? {
            name: existing.name, source: existing.source, source_type: existing.source_type,
            location: existing.location || "", width: existing.width, height: existing.height,
            target_fps: existing.target_fps, is_active: existing.is_active,
        }
        : { source_type: "webcam", width: 960, height: 540, target_fps: 25, is_active: true };

    for (;;) {
        const result = await openFormDialog({
            title: existing ? "Kamera Düzenle" : "Yeni Kamera Ekle",
            fields: _CAMERA_FIELDS,
            values,
        });
        if (result === null) return;
        try {
            if (existing) await api("/api/cameras/" + existing.id, { method: "PUT", body: result });
            else await api("/api/cameras", { method: "POST", body: result });
            _load();
            return;
        } catch (e) {
            values = Object.assign({}, result, { error: e.message === FORBIDDEN_MSG ? FORBIDDEN_MSG : e.message });
        }
    }
}

async function _deleteCamera(cam) {
    // Toplu bildirim katmani yok -- native confirm/alert (app.js'teki not).
    if (!confirm('"' + cam.name + '" kamerasını silmek istediğinize emin misiniz?')) return;
    try {
        await api("/api/cameras/" + cam.id, { method: "DELETE" });
        _load();
    } catch (e) {
        alert(e.message === FORBIDDEN_MSG ? "bu işlem için yetkiniz yok" : "silinemedi: " + e.message);
    }
}

function _applyFilters() {
    const q = (_searchInput.value || "").trim().toLowerCase();
    const status = _statusSelect.value;
    const loc = _locationSelect.value;

    const filtered = _tumKameralar.filter((cam) => {
        if (status && cam.status !== status) return false;
        if (loc && cam.location !== loc) return false;
        if (q) {
            const hay = [cam.name, cam.source, cam.location || ""].join(" ").toLowerCase();
            if (!hay.includes(q)) return false;
        }
        return true;
    });

    _tbody.innerHTML = "";
    if (filtered.length === 0) {
        const tr = document.createElement("tr");
        tr.innerHTML = '<td colspan="6" class="py-6 px-4 text-center text-on-surface-variant font-body-sm text-body-sm">Kayıt yok</td>';
        _tbody.appendChild(tr);
    } else {
        for (const cam of filtered) {
            const row = _fillRow(cam);
            _fillCameraRow(row, cam);
            _tbody.appendChild(row);
        }
    }
    _countLabel.textContent = "Toplam " + filtered.length + " kamera bulundu";
}

async function _load() {
    _fillRow = rowTemplate(_tbody);
    try {
        _tumKameralar = await api("/api/cameras");
    } catch (e) {
        _showError("Kameralar yüklenemedi: " + e.message);
        return;
    }
    _populateLocationFilter(_tumKameralar);
    _applyFilters();
}

_searchInput.addEventListener("input", _applyFilters);
_statusSelect.addEventListener("change", _applyFilters);
_locationSelect.addEventListener("change", _applyFilters);

_load();
