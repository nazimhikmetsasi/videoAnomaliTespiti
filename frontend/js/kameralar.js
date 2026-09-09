// Kameralar ekrani (ASAMA8_PLAN.md SS3, 8.3 ilk yarisi). GET /api/cameras
// tek istekte gelir, arama + durum/konum filtreleri istemci tarafinda calisir.

requireAuth();

// Kamera durumu icin ADI haritasi -- app.js'te DURUM_ADI (olay durumu) var
// ama kamera durumu (online/offline/error) icin yok. ponytail: app.js'e
// tasinmali (DURUM_ADI yaninda CAMERA_STATUS_ADI olarak).
const CAMERA_STATUS_ADI = { online: "Aktif", offline: "Devre Dışı", error: "Hata" };

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
    // Duzenle/Sil 8.5'in isi -- tiklaninca satir gezintisini tetiklemesinler.
    row.querySelectorAll("button").forEach((btn) => btn.addEventListener("click", (e) => e.stopPropagation()));
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
