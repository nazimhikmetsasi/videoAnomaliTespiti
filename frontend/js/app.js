// Ortak istemci katmani (ASAMA8_PLAN.md SS3, 8.1). Derleme adimi yok --
// her sayfa <script src="js/app.js" defer> ile </body> oncesinde ekler.
// Aktif sekme vurgusu sablonda sayfa basina gomulu, burada dokunulmuyor.

const TOKEN_KEY = "vadap_token";

function token() {
    return localStorage.getItem(TOKEN_KEY);
}

function setToken(value) {
    if (value) localStorage.setItem(TOKEN_KEY, value);
    else localStorage.removeItem(TOKEN_KEY);
}

function _currentPage() {
    return location.pathname.split("/").pop() || "index.html";
}

function requireAuth() {
    // Her sayfa betiginin ILK satiri bunu cagirir (SS3).
    if (!token()) {
        location.href = "login.html?next=" + encodeURIComponent(_currentPage());
    }
}

function logout() {
    setToken(null);
    location.href = "login.html";
}

// FastAPI'nin 422 govdesi metin DEGIL, [{loc, msg, type}, ...] listesidir --
// dogrudan Error(detail) yazilinca kullaniciya "[object Object]" gorunuyordu
// (8.5b'de bolge poligonu dogrulamasinda yakalandi). Tek yer burasi: tum
// ekranlar api() uzerinden gectigi icin duzeltme de tek yerde.
function _detailText(detail) {
    if (detail == null) return null;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
        return detail.map((d) => (d && d.msg) ? d.msg : JSON.stringify(d)).join("; ");
    }
    return typeof detail === "object" ? JSON.stringify(detail) : String(detail);
}

async function api(path, opts = {}) {
    const headers = Object.assign({}, opts.headers);
    if (token()) headers["Authorization"] = "Bearer " + token();
    let body = opts.body;
    if (body && typeof body === "object" && !(body instanceof URLSearchParams)) {
        headers["Content-Type"] = "application/json";
        body = JSON.stringify(body);
    }
    const res = await fetch(path, Object.assign({}, opts, { headers, body }));
    if (res.status === 401) {
        setToken(null);
        location.href = "login.html?next=" + encodeURIComponent(_currentPage());
        throw new Error("oturum sona erdi");
    }
    if (!res.ok) {
        let detail = res.statusText;
        try {
            detail = _detailText((await res.json()).detail) || detail;
        } catch (_e) { /* govde JSON degil */ }
        throw new Error(detail);
    }
    if (res.status === 204) return null;
    const ct = res.headers.get("content-type") || "";
    return ct.includes("application/json") ? res.json() : res.text();
}

// -------------------------------------------------------------- bicimleyiciler
function fmtTime(iso) {
    if (!iso) return "--";
    return new Date(iso).toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function fmtDateTime(iso) {
    if (!iso) return "--";
    return new Date(iso).toLocaleString("tr-TR");
}

function fmtDuration(ms) {
    if (ms == null) return "--";
    const s = Math.round(ms / 1000);
    if (s < 60) return s + " sn";
    return Math.floor(s / 60) + " dk " + (s % 60) + " sn";
}

const TIP_ADI = {
    FALL: "Düşme", RUN: "Koşma", ZONE_VIOLATION: "Bölge İhlali",
    RUN_ZONE: "Bölgede Koşma", FIGHT: "Kavga", LOITERING: "Oyalanma",
    WRONG_DIRECTION: "Ters Yön",
};

const SEVERITY_ADI = { low: "Düşük", medium: "Orta", high: "Yüksek", critical: "Kritik" };

// infra/postgres/init.sql events.status CHECK: new/acknowledged/false_positive/resolved
const DURUM_ADI = {
    new: "Yeni", acknowledged: "Görüldü", false_positive: "Yanlış Alarm", resolved: "Çözüldü",
};

// CameraHeartbeatIn (api/schemas.py): online/offline/error -- baglanti durumu,
// ac/pasif degil. 8.3'te kameralar.js ve kamera-detay.js'de ayri ayri (ve
// birbirinden FARKLI: "Aktif/Devre Dışı" vs "Çevrimiçi/Çevrimdışı) kopyalanmisti;
// ikinci metin yanlisti (kamera durumu baglanti anlamina gelir, ac/pasif degil).
const CAMERA_STATUS_ADI = { online: "Çevrimiçi", offline: "Çevrimdışı", error: "Hata" };

const ROLE_ADI = { admin: "Yönetici", operator: "Operatör", viewer: "Görüntüleyici" };

const DECIDED_BY_ADI = { rule: "Kural Motoru", model: "Model", hybrid: "Hibrit (Kural+Model)" };

// api/auth.py require_role() tek yerde bu metni dondurur -- 403'u ayirt
// etmenin tek yolu budur, api() durum kodunu disari vermiyor.
const FORBIDDEN_MSG = "bu islem icin yetkiniz yok";

function num(x) {
    return x == null ? null : Number(x);
}

// Kimlik dogrulamali binary (jpeg/mp4) indirme -- api()'nin JSON/metin
// varsayimi kanit dosyalari icin uygun degil (Authorization basligi olmadan
// <img src=...> 401 doner). 8.3'te uc dosyada ayri ayri kopyalanmisti.
async function _fetchAuthedBlobUrl(path) {
    const res = await fetch(path, { headers: { Authorization: "Bearer " + token() } });
    if (!res.ok) throw new Error("kanit alinamadi (" + res.status + ")");
    const blob = await res.blob();
    return URL.createObjectURL(blob);
}

// innerHTML ile kurulan satirlarda kullanici verisi (kamera/bolge adi)
// once kacislanir -- 8.5b'de bolgeler.js ve ayarlar.js'de ayri ayri
// kopyalanmisti (live.js'in "kopyalanmis yardimci" notuyla ayni gerekce).
function _escXml(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// container'in ilk cocugunu satir sablonu olarak soker, sahte satirlari siler,
// her cagrida sablonun temiz bir klonunu doner. Veri doldurma 8.3'in isi.
function rowTemplate(container) {
    const tpl = container.children[0];
    container.innerHTML = "";
    return function (_veri) {
        return tpl.cloneNode(true);
    };
}

// Kamera ve kullanici formlarinin ortak diyaloğu (8.5, iki tuketicisi var --
// ucuncu bir soyutlama katmani eklenmedi). Kaydedilirse alan degerlerini
// iceren nesne, iptalde/Esc'te null doner. Yazma istegini BURASI atmaz --
// hata olursa diyalog kapanip girdi kaybolmamali, o yuzden cagiran taraf
// hata mesajini `values.error` ile onceki degerlere ekleyip fonksiyonu
// tekrar cagirir (bkz. kameralar.js/kullanicilar.js).
//
// Toast/bildirim katmani bilincli olarak yazilmadi -- satir islemlerindeki
// (silme/pasiflestirme) hatalar icin native alert(), onay icin native
// confirm() yeterli (ASAMA8_PLAN.md 8.5 gorev tanimi, "bilincli sadelestirme").
async function openFormDialog({ title, fields, values = {} }) {
    return new Promise((resolve) => {
        const dialog = document.createElement("dialog");
        dialog.className = "bg-surface-container border border-outline-variant rounded-lg p-6";

        const form = document.createElement("form");
        form.className = "flex flex-col gap-4 w-[22rem] max-w-full";

        const heading = document.createElement("h3");
        heading.className = "font-title-sm text-title-sm text-on-surface";
        heading.textContent = title;
        form.appendChild(heading);

        if (values.error) {
            const err = document.createElement("p");
            err.className = "font-body-sm text-body-sm text-error";
            err.textContent = values.error;
            form.appendChild(err);
        }

        const inputs = {};
        for (const f of fields) {
            const wrap = document.createElement("div");
            wrap.className = "flex flex-col gap-1";

            if (f.type === "checkbox") {
                const label = document.createElement("label");
                label.className = "flex items-center gap-2 font-body-sm text-body-sm text-on-surface-variant";
                const input = document.createElement("input");
                input.type = "checkbox";
                input.checked = values[f.name] != null ? !!values[f.name] : !!f.value;
                label.appendChild(input);
                label.appendChild(document.createTextNode(f.label));
                wrap.appendChild(label);
                inputs[f.name] = input;
            } else {
                const label = document.createElement("label");
                label.className = "font-body-sm text-body-sm text-on-surface-variant";
                label.textContent = f.label;
                wrap.appendChild(label);

                let input;
                if (f.type === "select") {
                    input = document.createElement("select");
                    for (const [val, lbl] of f.options || []) {
                        const opt = document.createElement("option");
                        opt.value = val;
                        opt.textContent = lbl;
                        input.appendChild(opt);
                    }
                } else {
                    input = document.createElement("input");
                    input.type = f.type || "text";
                    if (f.step != null) input.step = f.step;
                }
                input.className = "w-full bg-surface-container-lowest border border-outline-variant rounded px-3 py-2 font-body-sm text-body-sm text-on-surface focus:outline-none focus:border-secondary";
                if (f.required) input.required = true;
                const val = values[f.name] != null ? values[f.name] : f.value;
                if (val != null) input.value = val;
                wrap.appendChild(input);
                inputs[f.name] = input;
            }
            form.appendChild(wrap);
        }

        const actions = document.createElement("div");
        actions.className = "flex justify-end gap-2 pt-2";
        const cancelBtn = document.createElement("button");
        cancelBtn.type = "button";
        cancelBtn.className = "px-4 py-2 rounded border border-outline-variant text-on-surface";
        cancelBtn.textContent = "İptal";
        const saveBtn = document.createElement("button");
        saveBtn.type = "submit";
        saveBtn.className = "px-4 py-2 rounded bg-secondary-container text-on-secondary-container font-title-sm text-title-sm";
        saveBtn.textContent = "Kaydet";
        actions.appendChild(cancelBtn);
        actions.appendChild(saveBtn);
        form.appendChild(actions);

        dialog.appendChild(form);
        document.body.appendChild(dialog);

        function cleanup(result) {
            dialog.close();
            dialog.remove();
            resolve(result);
        }

        cancelBtn.addEventListener("click", () => cleanup(null));
        dialog.addEventListener("cancel", () => cleanup(null)); // Esc tusu
        form.addEventListener("submit", (e) => {
            e.preventDefault();
            const out = {};
            for (const f of fields) {
                const input = inputs[f.name];
                if (f.type === "checkbox") out[f.name] = input.checked;
                else if (f.type === "number") out[f.name] = Number(input.value);
                else out[f.name] = input.value;
            }
            cleanup(out);
        });

        dialog.showModal();
    });
}

// Ust cubuktaki profil dugmesi sablonda her sayfada ayni yerde degil --
// varsa baglanir, yoksa sessizce atlanir (ASAMA8_PLAN.md SS4).
async function _wireProfileButton() {
    const avatar = document.querySelector('img[alt="Kullanıcı Profili"]');
    const btn = document.querySelector('[title="Profil"]') || (avatar ? avatar.closest("button") : null);
    if (!btn) return;
    btn.addEventListener("click", logout);
    try {
        const me = await api("/api/auth/me");
        btn.title = me.full_name;
    } catch (_e) { /* api() zaten 401'de yonlendirir */ }
}

document.addEventListener("DOMContentLoaded", _wireProfileButton);
