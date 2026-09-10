// Olaylar ekrani (ASAMA8_PLAN.md SS3, 8.3 ilk yarisi). GET /api/events
// (filtre + limit/offset sayfalama). Kamera acilir listesi GET /api/cameras'tan
// doldurulur -- bu ikinci istek burada acikca isteniyor (kameralar.html'in
// aksine, orada tek istek kurali vardi).

requireAuth();

const SEVERITY_STYLE = {
    critical: { text: "text-error", icon: "error", pulse: true, bar: "bg-error" },
    high: { text: "text-[#f59e0b]", icon: "warning", pulse: false, bar: "bg-[#f59e0b]" },
    medium: { text: "text-yellow-500", icon: "warning", pulse: false, bar: "bg-yellow-500" },
    low: { text: "text-on-surface-variant", icon: "info", pulse: false, bar: "bg-on-surface-variant" },
};

const STATUS_DOT = {
    new: "bg-secondary-fixed", acknowledged: "bg-outline",
    false_positive: "bg-outline", resolved: "bg-emerald-500",
};

const LIMIT = 20;
let _offset = 0;
let _total = 0;
let _fillRow = null;
let _cameras = [];
let _selected = new Set(); // yalniz o an gorunen sayfadaki secili olay id'leri

const _tbody = document.querySelector("table tbody");
const _filterBar = document.querySelector(".flex.flex-wrap.gap-4.items-end");
const _selects = _filterBar.querySelectorAll("select");
const _cameraSelect = _selects[0];
const _typeSelect = _selects[1];
const _severitySelect = _selects[2];
const _statusSelect = _selects[3];
const _filterBtn = _filterBar.querySelector("button");
const _pageInfo = document.querySelector(".p-3.border-t.border-outline-variant span");
const _pagerButtons = document.querySelectorAll(".p-3.border-t.border-outline-variant button");
const _prevBtn = _pagerButtons[0];
const _nextBtn = _pagerButtons[_pagerButtons.length - 1];
const _selectAllCb = document.querySelector("thead input[type=\"checkbox\"]");
// data-icon="done_all" sayfada tek yerde geciyor (grep ile dogrulandi).
const _bulkAckBtn = document.querySelector('[data-icon="done_all"]').closest("button");
_bulkAckBtn.disabled = true;

function _updateBulkBtn() {
    _bulkAckBtn.disabled = _selected.size === 0;
}

function _fillSelect(select, entries, allLabel) {
    select.innerHTML = "";
    const allOpt = document.createElement("option");
    allOpt.value = "";
    allOpt.textContent = allLabel;
    select.appendChild(allOpt);
    for (const [value, label] of entries) {
        const opt = document.createElement("option");
        opt.value = value;
        opt.textContent = label;
        select.appendChild(opt);
    }
}

async function _loadFilters() {
    _fillSelect(_typeSelect, Object.entries(TIP_ADI), "Tüm Tipler");
    _fillSelect(_severitySelect, Object.entries(SEVERITY_ADI), "Tüm Seviyeler");
    _fillSelect(_statusSelect, Object.entries(DURUM_ADI), "Tüm Durumlar");
    try {
        _cameras = await api("/api/cameras");
        _fillSelect(_cameraSelect, _cameras.map((c) => [String(c.id), c.name]), "Tüm Kameralar");
    } catch (_e) {
        _fillSelect(_cameraSelect, [], "Tüm Kameralar");
    }
}

function _showError(msg) {
    _tbody.innerHTML = "";
    const tr = document.createElement("tr");
    tr.innerHTML = '<td colspan="9" class="p-6 text-center text-error font-body-sm text-body-sm">' + msg + "</td>";
    _tbody.appendChild(tr);
}

function _cameraName(id) {
    const cam = _cameras.find((c) => c.id === id);
    return cam ? cam.name : "Kamera #" + id;
}

function _cameraLocation(id) {
    const cam = _cameras.find((c) => c.id === id);
    return cam && cam.location ? cam.location : "";
}

function _fillEventRow(row, ev) {
    const tds = row.querySelectorAll("td");
    // tds[0] = checkbox (8.5'in isi, dokunulmuyor)
    const thumbWrap = tds[1].querySelector("div");
    const img = tds[1].querySelector("img");
    if (ev.frame_path) {
        _fetchAuthedBlobUrl("/api/events/" + ev.id + "/frame")
            .then((url) => { img.src = url; })
            .catch(() => { thumbWrap.remove(); });
    } else {
        thumbWrap.remove();
    }

    tds[2].textContent = fmtTime(ev.started_at);
    tds[3].innerHTML = _cameraName(ev.camera_id) + "<br><span class=\"text-on-surface-variant text-[10px]\">" + (_cameraLocation(ev.camera_id) || "—") + "</span>";

    // Anomali tipi ikonu sablona ait, degismiyor -- yalnizca etiket metni.
    const typeBadge = tds[4].querySelector("span");
    typeBadge.childNodes[typeBadge.childNodes.length - 1].textContent = " " + (TIP_ADI[ev.anomaly_type] || ev.anomaly_type);

    const sevStyle = SEVERITY_STYLE[ev.severity] || SEVERITY_STYLE.low;
    const sevSpan = tds[5].querySelector("span");
    sevSpan.className = "inline-flex items-center gap-1 " + sevStyle.text;
    const sevIcon = sevSpan.querySelector("span");
    sevIcon.className = "material-symbols-outlined text-[14px]" + (sevStyle.pulse ? " animate-pulse" : "");
    sevIcon.textContent = sevStyle.icon;
    sevSpan.childNodes[sevSpan.childNodes.length - 1].textContent = " " + (SEVERITY_ADI[ev.severity] || ev.severity);

    // confidence NUMERIC(4,3) -- EventOut'ta float alan, ama gercek yanitta
    // dogrulanmadan sayi varsayilmiyor (ASAMA7'nin Decimal tuzagi, gorev
    // tanimi notu). Number() cevrilemezse "-" gosterilir.
    const conf = Number(ev.confidence);
    const pct = Number.isFinite(conf) ? Math.round(conf * 100) : null;
    const confLabel = tds[6].querySelector("span.font-data-mono");
    const confBar = tds[6].querySelector("div[style]");
    confLabel.textContent = pct === null ? "—" : "%" + pct;
    confBar.className = "h-full " + sevStyle.bar;
    confBar.style.width = (pct === null ? 0 : pct) + "%";

    const statusSpan = tds[7].querySelector("span");
    const statusDot = statusSpan.querySelector("span");
    statusDot.className = "w-2 h-2 rounded-full " + (STATUS_DOT[ev.status] || "bg-outline");
    statusSpan.childNodes[statusSpan.childNodes.length - 1].textContent = " " + (DURUM_ADI[ev.status] || ev.status);

    row.style.cursor = "pointer";
    row.addEventListener("click", (e) => {
        if (e.target.closest('input[type="checkbox"]')) return;
        location.href = "olay-detay.html?id=" + ev.id;
    });
    const inceleBtn = tds[8].querySelector("button");
    if (inceleBtn) inceleBtn.addEventListener("click", (e) => { e.stopPropagation(); location.href = "olay-detay.html?id=" + ev.id; });
    const checkbox = tds[0].querySelector('input[type="checkbox"]');
    if (checkbox) {
        checkbox.addEventListener("click", (e) => e.stopPropagation());
        // DOM sirasina degil olay id'sine gore eslenir (gorev tanimi notu).
        checkbox.dataset.eventId = String(ev.id);
        checkbox.checked = _selected.has(ev.id);
        checkbox.addEventListener("change", () => {
            if (checkbox.checked) _selected.add(ev.id);
            else _selected.delete(ev.id);
            const all = [..._tbody.querySelectorAll('input[type="checkbox"]')];
            _selectAllCb.checked = all.length > 0 && all.every((cb) => cb.checked);
            _updateBulkBtn();
        });
    }
}

// Basliktaki onay kutusu = o an gorunen (bu sayfadaki) tum satirlari sec/birak.
_selectAllCb.addEventListener("change", () => {
    const checked = _selectAllCb.checked;
    _tbody.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
        cb.checked = checked;
        const id = Number(cb.dataset.eventId);
        if (checked) _selected.add(id);
        else _selected.delete(id);
    });
    _updateBulkBtn();
});

// Toplu uc yok -- istemci tarafinda N tekil PATCH. Promise.all kullanilir;
// her istek kendi .catch()'i ile basari/hata nesnesine cevrilir ki tek
// reddedilen istek digerlerini iptal etmesin, kac tanesinin basarisiz
// oldugu sayilabilsin (gorev tanimi notu). Bildirim katmani yok -- native alert().
_bulkAckBtn.addEventListener("click", async () => {
    const ids = [..._selected];
    if (ids.length === 0) return;
    _bulkAckBtn.disabled = true;
    const outcomes = await Promise.all(
        ids.map((id) =>
            api("/api/events/" + id, { method: "PATCH", body: { status: "acknowledged" } })
                .then(() => ({ ok: true }))
                .catch((err) => ({ ok: false, err }))
        )
    );
    const failed = outcomes.filter((o) => !o.ok);
    if (failed.length > 0) {
        const firstErr = failed[0].err;
        const msg = firstErr && firstErr.message === FORBIDDEN_MSG ? FORBIDDEN_MSG : (firstErr ? firstErr.message : "bilinmeyen hata");
        alert(failed.length + " / " + ids.length + " olay güncellenemedi: " + msg);
    }
    _selected.clear();
    _load();
});

function _buildQuery() {
    const params = new URLSearchParams();
    if (_cameraSelect.value) params.set("camera_id", _cameraSelect.value);
    if (_typeSelect.value) params.set("anomaly_type", _typeSelect.value);
    if (_severitySelect.value) params.set("severity", _severitySelect.value);
    if (_statusSelect.value) params.set("status", _statusSelect.value);
    params.set("limit", String(LIMIT));
    params.set("offset", String(_offset));
    return params.toString();
}

async function _load() {
    let result;
    try {
        result = await api("/api/events?" + _buildQuery());
    } catch (e) {
        _showError("Olaylar yüklenemedi: " + e.message);
        return;
    }
    _selected.clear();
    _selectAllCb.checked = false;
    _updateBulkBtn();
    _total = result.total;
    _tbody.innerHTML = "";
    if (result.items.length === 0) {
        const tr = document.createElement("tr");
        tr.innerHTML = '<td colspan="9" class="p-6 text-center text-on-surface-variant font-body-sm text-body-sm">Kayıt yok</td>';
        _tbody.appendChild(tr);
    } else {
        for (const ev of result.items) {
            const row = _fillRow(ev);
            _fillEventRow(row, ev);
            _tbody.appendChild(row);
        }
    }
    const from = _total === 0 ? 0 : _offset + 1;
    const to = Math.min(_offset + LIMIT, _total);
    _pageInfo.textContent = "Toplam " + _total + " kayıttan " + from + "-" + to + " arası gösteriliyor";
    _prevBtn.disabled = _offset === 0;
    _nextBtn.disabled = _offset + LIMIT >= _total;
}

_filterBtn.addEventListener("click", (e) => { e.preventDefault(); _offset = 0; _load(); });
_prevBtn.addEventListener("click", () => { _offset = Math.max(0, _offset - LIMIT); _load(); });
_nextBtn.addEventListener("click", () => { _offset += LIMIT; _load(); });

async function _init() {
    _fillRow = rowTemplate(_tbody);
    await _loadFilters();
    await _load();
}

_init();
