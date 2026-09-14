// Ayarlar ekrani (ASAMA8_PLAN.md SS3, 8.5b). Global / kamera bazli kismi PUT,
// restart_required uyarisi. Sablonda karsiligi olan yalnizca alti alan
// baglanir (pose_conf, fall_tilt_deg, spark_min_sec.FALL, run_norm_speed,
// spark_min_sec.FIGHT, window_frames) -- SettingsIn'in geri kalani
// (track_conf, fall_norm_vy, run_gait_speed, loiter_sec, fight_proximity,
// spark_window_sec, spark_min_hits, tcn_min_conf) sablonda hicbir kontrole
// karsilik gelmiyor (ASAMA8_PLAN.md SS4: karsiligi olmayan ogeye
// dokunulmaz). Kismi PUT sayesinde bu alanlara zaten dokunulmuyor.
//
// Tek istisna Kur/Birak anahtaridir (armed): sablonda karsiligi yok ama
// islevin kendisi bir dugme olmadan kullanilamaz, bu yuzden camSelect gibi
// JS'te uretilip enjekte edilir.

requireAuth();

// ------------------------------------------------------------- DOM baglama
const headerTextWrap = document.querySelector("main h1").parentElement;
const tabsWrap = headerTextWrap.parentElement.children[1]; // "flex justify-between items-end" -> [baslik, sekmeler]
const [globalTab, cameraTab] = tabsWrap.querySelectorAll("button");

const [modelSection, fallSection, runSection, fightSection] = document.querySelectorAll("main section");
const poseRange = modelSection.querySelector('input[type="range"]');
const poseValueSpan = modelSection.querySelector("span.font-data-mono.text-data-mono.text-secondary");

const [tiltInput, fallSecInput] = fallSection.querySelectorAll('input[type="number"]');
const runSpeedInput = runSection.querySelector('input[type="number"]');
const [fightSecInput] = fightSection.querySelectorAll('input[type="number"]');
const windowSelect = fightSection.querySelector("select");

const actionBar = document.querySelector(".fixed.bottom-0.right-0");
const lastChangedP = actionBar.children[0];
const btnGroup = actionBar.children[1];
const [resetBtn, saveActionBtn] = btnGroup.querySelectorAll("button");

// ------------------------------------------------------ kapsam (global/kamera)
const TAB_ACTIVE = globalTab.className;
const TAB_INACTIVE = cameraTab.className;
let scope = "global";
let scopeCameraId = null;
let cameras = [];

const camSelect = document.createElement("select");
camSelect.className =
    "ml-3 bg-surface-container-lowest border border-outline-variant rounded px-3 py-2 " +
    "font-data-mono text-data-mono text-on-surface focus:border-secondary focus:ring-1 " +
    "focus:ring-secondary transition-all outline-none appearance-none";
camSelect.style.display = "none";
tabsWrap.insertAdjacentElement("afterend", camSelect);

// ------------------------------------------------------- Kur/Birak anahtari
// TEZ_KAPSAM.txt Faz 1: "Evde = bildirim yok, Koruma = alarm". Diger
// alanlardan farkli olarak Kaydet dugmesini BEKLEMEZ: kur/birak sik ve
// aceleyle yapilan bir islemdir, kaydedilmemis bir formda unutulmasi
// sistemin sessiz kalmasi demektir.
const armBtn = document.createElement("button");
armBtn.className = "ml-3 px-4 py-2 rounded font-body-sm text-body-sm transition-all";
tabsWrap.insertAdjacentElement("afterend", armBtn);

function _paintArm(armed) {
    armBtn.textContent = armed ? "Koruma açık" : "Evde — bildirim yok";
    armBtn.className = "ml-3 px-4 py-2 rounded font-body-sm text-body-sm transition-all " +
        (armed ? "bg-error text-on-error" : "bg-surface-container border border-outline-variant text-secondary");
    armBtn.title = armed
        ? "Anomali bildirimleri gönderiliyor. Tıklayınca Evde moduna geçer."
        : "Bildirim gönderilmiyor. Tespit ve kanıt üretimi sürüyor, olaylar kaydediliyor.";
}

armBtn.addEventListener("click", async () => {
    if (!loaded) return;
    const next = !loaded.armed;
    // Koruma KAPATILIRKEN onay istenir; acilirken istenmez. Yanlislikla
    // sessizlestirmenin bedeli, yanlislikla alarm acmanin bedelinden buyuk.
    if (!next && !confirm("Koruma kapatılsın mı? Anomali bildirimleri gönderilmeyecek; tespit ve kayıt sürecek.")) return;
    armBtn.disabled = true;
    try {
        const path = scope === "camera" ? "/api/settings/" + scopeCameraId : "/api/settings";
        loaded = await api(path, { method: "PUT", body: { armed: next } });
        _paintArm(loaded.armed);
        lastChangedP.textContent = "Son değişiklik: " + fmtDateTime(loaded.updated_at);
    } catch (e) {
        alert("Mod değiştirilemedi: " + e.message);
    } finally {
        armBtn.disabled = false;
    }
});

// Kamera kapsaminda source==="global" ise (henuz kameraya ozel satir yok)
// kullaniciya bunun devralinan deger oldugu belirtilir.
const sourceHint = document.createElement("p");
sourceHint.className = "font-body-sm text-body-sm text-secondary mt-1";
sourceHint.style.display = "none";
sourceHint.textContent = "Bu kamera için özel ayar yok, global değerler gösteriliyor. Kaydedince kameraya özel satır oluşturulur.";
headerTextWrap.appendChild(sourceHint);

// restart_required listesi sunucudan gelir (SettingsOut.restart_required) --
// istemcide sabit yazilmiyor.
const restartWarning = document.createElement("p");
restartWarning.className = "font-body-sm text-body-sm text-error mr-4";
restartWarning.style.display = "none";
restartWarning.textContent = "Bu değişiklik, vision yeniden başlatılmadan etkili olmaz.";
btnGroup.insertBefore(restartWarning, resetBtn);

function _updateResetButtonState() {
    if (scope === "camera") {
        resetBtn.disabled = false;
        resetBtn.classList.remove("opacity-50", "cursor-not-allowed");
        resetBtn.title = "";
    } else {
        // Sifirlama ucu yok (ASAMA8_PLAN.md SS4) -- gercek "varsayilan" global
        // kapsamin kendisi, bu yuzden global kapsamda anlamsiz.
        resetBtn.disabled = true;
        resetBtn.classList.add("opacity-50", "cursor-not-allowed");
        resetBtn.title = "Sıfırlama yalnızca kamera kapsamında kullanılabilir (global zaten taban değerdir)";
    }
}

globalTab.addEventListener("click", () => {
    if (scope === "global") return;
    scope = "global";
    globalTab.className = TAB_ACTIVE;
    cameraTab.className = TAB_INACTIVE;
    camSelect.style.display = "none";
    _updateResetButtonState();
    _loadSettings();
});

cameraTab.addEventListener("click", () => {
    if (scope === "camera") return;
    scope = "camera";
    cameraTab.className = TAB_ACTIVE;
    globalTab.className = TAB_INACTIVE;
    camSelect.style.display = "";
    if (scopeCameraId == null && cameras.length > 0) scopeCameraId = cameras[0].id;
    if (scopeCameraId != null) camSelect.value = String(scopeCameraId);
    _updateResetButtonState();
    _loadSettings();
});

camSelect.addEventListener("change", () => {
    scopeCameraId = Number(camSelect.value);
    _loadSettings();
});

// -------------------------------------------------------------- pose_conf
poseRange.addEventListener("input", () => { poseValueSpan.textContent = poseRange.value; });

// --------------------------------------------------------------------- form
let loaded = null; // sunucudan gelen son SettingsOut -- degisiklik karsilastirma tabani
let restartFields = [];

function _fillForm(s) {
    poseRange.value = s.pose_conf;
    poseValueSpan.textContent = s.pose_conf;
    tiltInput.value = s.fall_tilt_deg;
    fallSecInput.value = s.spark_min_sec.FALL;
    runSpeedInput.value = s.run_norm_speed;
    fightSecInput.value = s.spark_min_sec.FIGHT;
    _setWindowFrames(s.window_frames);
}

// Sablonun <select>'i yalniz 15/30/60/90 sunuyor; veritabani varsayilani 50
// (infra/postgres/init.sql) ve herhangi bir INT olabilir. Listede olmayan bir
// degeri atamak select.value'yu BOS birakir; Number("") = 0 olur ve her
// kaydetmede istenmeden window_frames=0 gonderilirdi (tarayici kosusunda
// yakalandi -- global satir gercekten 50'den 0'a dustu). Gercek deger listede
// yoksa listeye eklenir: hem gorunur kalir hem de fark hesabi dogru calisir.
function _setWindowFrames(value) {
    const v = String(value);
    if (![...windowSelect.options].some((o) => o.value === v)) {
        const opt = document.createElement("option");
        opt.value = v;
        opt.textContent = v + " Frame";
        windowSelect.appendChild(opt);
    }
    windowSelect.value = v;
}

async function _loadSettings() {
    try {
        const path = scope === "camera" ? "/api/settings/" + scopeCameraId : "/api/settings";
        loaded = await api(path);
    } catch (e) {
        alert("Ayarlar yüklenemedi: " + e.message);
        return;
    }
    restartFields = loaded.restart_required || [];
    restartWarning.style.display = "none";
    _fillForm(loaded);
    // _fillForm'un ICINDE degil: "Sifirla" dugmesi de _fillForm cagiriyor ama
    // sunucuya dokunmuyor. armed ANINDA uygulanan bir durumdur, formun
    // kaydedilmemis taslak degeri degil -- oradan boyanirsa dugme gercekte
    // olmayan bir modu gosterir.
    _paintArm(loaded.armed);
    sourceHint.style.display = scope === "camera" && loaded.source === "global" ? "" : "none";
    lastChangedP.textContent = "Son değişiklik: " + fmtDateTime(loaded.updated_at);
}

resetBtn.addEventListener("click", async () => {
    if (scope !== "camera") return; // dugme zaten devre disi, ikinci kontrol
    try {
        const g = await api("/api/settings");
        // Sunucuya DOKUNMAZ -- yalnizca formu global degerlerle doldurur;
        // kaydedilene kadar kalici olmaz. Sifirlama ucu yok, gercek
        // "varsayilan" budur (ASAMA8_PLAN.md SS4).
        _fillForm(g);
    } catch (e) {
        alert("Varsayılan değerler alınamadı: " + e.message);
    }
});

function _disableSave(msg) {
    saveActionBtn.disabled = true;
    saveActionBtn.classList.add("opacity-50", "cursor-not-allowed");
    saveActionBtn.title = msg;
}

saveActionBtn.addEventListener("click", async () => {
    if (!loaded) return;
    const current = {
        pose_conf: Number(poseRange.value),
        fall_tilt_deg: Number(tiltInput.value),
        run_norm_speed: Number(runSpeedInput.value),
        window_frames: Number(windowSelect.value),
    };
    const patch = {};
    for (const k of Object.keys(current)) {
        if (current[k] !== loaded[k]) patch[k] = current[k];
    }
    // TUZAK: spark_min_sec bir sozluk ve kismi PUT ALAN bazinda calisir,
    // sozluk ICI anahtar bazinda degil -- sunucudan gelen sozlugun TAMAMI
    // kopyalanip yalnizca degisen anahtar(lar) guncellenir. Yalnizca
    // {FALL: ...} gonderilirse FIGHT/LOITERING gibi diger tiplerin suresi
    // sessizce silinir.
    const sparkCurrent = Object.assign({}, loaded.spark_min_sec);
    let sparkChanged = false;
    const fallSec = Number(fallSecInput.value);
    const fightSec = Number(fightSecInput.value);
    if (fallSec !== loaded.spark_min_sec.FALL) { sparkCurrent.FALL = fallSec; sparkChanged = true; }
    if (fightSec !== loaded.spark_min_sec.FIGHT) { sparkCurrent.FIGHT = fightSec; sparkChanged = true; }
    if (sparkChanged) patch.spark_min_sec = sparkCurrent;

    if (Object.keys(patch).length === 0) return; // degisiklik yok, istek atma

    try {
        const path = scope === "camera" ? "/api/settings/" + scopeCameraId : "/api/settings";
        loaded = await api(path, { method: "PUT", body: patch });
        restartFields = loaded.restart_required || [];
        _fillForm(loaded);
        sourceHint.style.display = scope === "camera" && loaded.source === "global" ? "" : "none";
        lastChangedP.textContent = "Son değişiklik: " + fmtDateTime(loaded.updated_at);
        const touchedRestart = Object.keys(patch).some((k) => restartFields.includes(k));
        restartWarning.style.display = touchedRestart ? "" : "none";
    } catch (e) {
        if (e.message === FORBIDDEN_MSG) {
            alert(FORBIDDEN_MSG);
            _disableSave(FORBIDDEN_MSG);
        } else {
            alert("Kaydedilemedi: " + e.message);
        }
    }
});

// -------------------------------------------------------------------- init
async function _checkRole() {
    try {
        const me = await api("/api/auth/me");
        if (me.role !== "admin") _disableSave(FORBIDDEN_MSG);
    } catch (e) { /* api() zaten 401'de yonlendirir */ }
}

async function _init() {
    try {
        cameras = await api("/api/cameras");
    } catch (e) {
        cameras = [];
    }
    camSelect.innerHTML = cameras.map((c) => '<option value="' + c.id + '">' + _escXml(c.name) + "</option>").join("");
    _updateResetButtonState();
    _checkRole();
    await _loadSettings();
}

_init();
