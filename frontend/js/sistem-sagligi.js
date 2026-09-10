// Sistem sagligi ekrani (ASAMA8_PLAN.md SS3.8.3). /health kimlik istemez
// ama api() zaten jetonu ekliyor, zararsiz. Kafka/Spark/GPU sicaklik-model
// icin API karsiligi yok -- olcusuz alanlar "—" / "ÖLÇÜLMÜYOR" olarak
// birakilir, yenisi uydurulmaz. app.js: requireAuth/api/fmtDateTime.

requireAuth();

const STALE_SEC = 60; // ASAMA8_PLAN.md SS3.8.3: age_sec bu esigi gecince "canli" degil

function ageText(ageSec) {
    if (ageSec == null) return "";
    const s = Math.round(ageSec);
    if (s < 60) return `${s} sn önce`;
    if (s < 3600) return `${Math.round(s / 60)} dk önce`;
    return `${(s / 3600).toFixed(1)} sa önce`;
}

// icon(span[data-icon]) -> servis karti kok elemani (4 ust parent, sablonun
// sabit ic ice yapisina bagli -- bkz. frontend/sistem-sagligi.html).
function cardOf(icon) {
    return icon.parentElement.parentElement.parentElement.parentElement;
}

function setServiceCard(icon, { online, label, metric1, metric2 }) {
    const card = cardOf(icon);
    if (!card) return;
    const pill = card.querySelector(".px-2.py-1.rounded-sm.border");
    if (pill) {
        const dot = pill.querySelector("span:first-child");
        const text = pill.querySelector("span:last-child");
        dot.className = "w-2 h-2 rounded-full " + (online ? "bg-primary animate-subtle-pulse" : "bg-outline");
        text.className = "font-label-caps text-label-caps " + (online ? "text-on-surface" : "text-on-surface-variant");
        text.textContent = label;
    }
    const metrics = card.querySelectorAll(".grid.grid-cols-2.gap-4.mt-auto > div");
    if (metrics[0]) metrics[0].querySelector("p:last-child").textContent = metric1;
    if (metrics[1]) metrics[1].querySelector("p:last-child").textContent = metric2;
}

function fillHealthCards(health) {
    const dbIcon = document.querySelector('[data-icon="database"]');
    if (dbIcon) {
        const allOk = !!health.postgres && !!health.mongo;
        setServiceCard(dbIcon, {
            online: allOk,
            label: allOk ? "ONLİNE" : "ÇEVRİMDIŞI",
            metric1: "—",
            metric2: "—",
        });
        const pill = cardOf(dbIcon).querySelector(".px-2.py-1.rounded-sm.border");
        // postgres/mongo ayri ayri -- kartta tek durum var, ayrinti tooltip'te.
        if (pill) pill.title = `postgres: ${health.postgres ? "ok" : "cevrimdisi"}, mongo: ${health.mongo ? "ok" : "cevrimdisi"}`;
    }
    const kafkaIcon = document.querySelector('[data-icon="route"]');
    if (kafkaIcon) {
        setServiceCard(kafkaIcon, { online: false, label: "ÖLÇÜLMÜYOR", metric1: "—", metric2: "—" });
    }
    const sparkIcon = document.querySelector('[data-icon="memory"]');
    if (sparkIcon) {
        setServiceCard(sparkIcon, { online: false, label: "ÖLÇÜLMÜYOR", metric1: "—", metric2: "—" });
    }

    const syncIcon = document.querySelector('[data-icon="sync"]');
    if (syncIcon) {
        const label = syncIcon.parentElement.querySelector("span:last-child");
        if (label) label.textContent = `Son Güncelleme: ${new Date().toLocaleTimeString("tr-TR")} TSİ`;
    }
}

// GPU karti: gpu_mem gercek veri (kamera basina), sicaklik/model adi yok --
// halkanin yuzdesi icin payda (toplam VRAM) bilinmiyor, uydurulmaz.
function fillGpuCard(cameras) {
    const icon = document.querySelector('[data-icon="developer_board"]');
    if (!icon) return;
    const card = icon.parentElement.parentElement;
    // vision/health_client.py: gpu_mem = torch.cuda.memory_reserved() -- BAYT,
    // MB degil (105 istekle olculdu: 104857600 bayt = tam 100 MiB).
    const values = cameras.map((c) => num(c.gpu_mem)).filter((v) => v != null);
    const maxBytes = values.length ? Math.max(...values) : null;
    const maxMb = maxBytes != null ? Math.round(maxBytes / (1024 * 1024)) : null;

    const ring = card.querySelector(".circle");
    if (ring) ring.setAttribute("stroke-dasharray", "0, 100");
    const centerText = card.querySelector(".font-display-lg");
    if (centerText) {
        centerText.innerHTML =
            maxMb != null ? `${maxMb}<span class="text-[16px] text-on-surface-variant">MB</span>` : "—";
    }
    const captions = card.querySelectorAll(".mt-4.text-center p");
    if (captions[0]) captions[0].textContent = "GPU bellek (kamera başına en yüksek)";
    if (captions[1]) captions[1].textContent = "Sıcaklık ölçülmüyor";
}

function fillCameraTable(cameras) {
    const tbody = document.querySelector("table tbody");
    if (!tbody) return;
    const makeRow = rowTemplate(tbody);

    if (cameras.length === 0) {
        const tr = document.createElement("tr");
        tr.innerHTML = '<td colspan="6" class="px-4 py-6 text-center text-on-surface-variant">kayıt yok</td>';
        tbody.appendChild(tr);
        return;
    }

    for (const cam of cameras) {
        const tr = makeRow(cam);
        const tds = tr.querySelectorAll("td");

        const nameTd = tds[0];
        // Sablon metni icon'dan once VE sonra bosluk metin dugumleri birakiyor;
        // ilk eslesmeyi degistirmek sondaki kamera adini birakiyordu.
        [...nameTd.childNodes].filter((n) => n.nodeType === 3).forEach((n) => n.remove());
        nameTd.appendChild(document.createTextNode(cam.name));

        tds[1].textContent = cam.fps_actual != null ? num(cam.fps_actual).toFixed(1) : "—";
        tds[2].textContent = cam.dropped != null ? String(cam.dropped) : "—";
        tds[3].textContent = cam.infer_ms != null ? Math.round(num(cam.infer_ms)) + "ms" : "—";
        tds[4].innerHTML = ""; // TREND: sablonun karsiligi yok (tek anlik olcum), uydurulmaz.

        const hasDoc = cam.fps_actual != null || cam.dropped != null || cam.infer_ms != null || cam.age_sec != null;
        let state, dotClass, textClass;
        if (!hasDoc) {
            state = "Bağlantı Yok";
            dotClass = "bg-outline";
            textClass = "text-on-surface-variant";
        } else if (cam.age_sec != null && cam.age_sec > STALE_SEC) {
            state = "Bayat";
            dotClass = "bg-tertiary animate-subtle-pulse";
            textClass = "text-tertiary";
            tr.classList.add("bg-tertiary/5");
        } else {
            state = "Canlı";
            dotClass = "bg-primary";
            textClass = "text-primary";
        }
        tds[5].innerHTML = `<span class="inline-flex items-center gap-1 ${textClass}">
            <span class="w-1.5 h-1.5 rounded-full ${dotClass}"></span> ${state}
        </span>${cam.age_sec != null ? `<div class="text-[10px] text-on-surface-variant mt-0.5 text-right">${ageText(cam.age_sec)}</div>` : ""}`;

        tbody.appendChild(tr);
    }
}

async function load() {
    try {
        const [health, cameras] = await Promise.all([api("/health"), api("/api/health/cameras")]);
        fillHealthCards(health);
        fillGpuCard(cameras);
        fillCameraTable(cameras);
    } catch (err) {
        const main = document.querySelector("main");
        const banner = document.createElement("p");
        banner.className = "font-body-sm text-body-sm text-error bg-red-950/40 border border-red-800/40 rounded px-3 py-2";
        banner.textContent = "sistem sağlığı verisi alınamadı: " + err.message;
        main.prepend(banner);
    }
}

document.addEventListener("DOMContentLoaded", load);
