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
            detail = (await res.json()).detail || detail;
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

// container'in ilk cocugunu satir sablonu olarak soker, sahte satirlari siler,
// her cagrida sablonun temiz bir klonunu doner. Veri doldurma 8.3'in isi.
function rowTemplate(container) {
    const tpl = container.children[0];
    container.innerHTML = "";
    return function (_veri) {
        return tpl.cloneNode(true);
    };
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
