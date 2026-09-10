// Analitik ekrani (ASAMA8_PLAN.md SS3.8.3). Grafik kutuphanesi yok --
// cubuk grafik ve isi haritasi mevcut sablon siniflariyla, genislik/renk
// calisma zamaninda hesaplaniyor. app.js: requireAuth/api/rowTemplate/TIP_ADI.

requireAuth();

const DAY_NAMES = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"];

function pct(part, total) {
    return total ? (part / total) * 100 : null;
}

function fmtPct(v) {
    return v == null ? "—" : v.toFixed(1) + "%";
}

// ---- 4 ust metrik karti -------------------------------------------------
function fillMetricCards(summary) {
    const cards = document.querySelectorAll(".grid-cols-4 > div");
    if (cards.length < 4) return;

    const byStatus = {};
    for (const row of summary.by_status) byStatus[row.status] = row.count;
    const confirmed = (byStatus.acknowledged || 0) + (byStatus.resolved || 0);
    const falsePositive = byStatus.false_positive || 0;
    const confirmedRate = pct(confirmed, summary.total);
    const fpRate = pct(falsePositive, summary.total);

    // Kart 1: Toplam Olay -- karsilastirma verisi yok, trend satiri kaldirilir.
    const card1 = cards[0];
    card1.querySelector(".font-display-lg").textContent = summary.total.toLocaleString("tr-TR");
    const trend1 = card1.querySelector(".mt-auto.pt-4");
    if (trend1) trend1.remove();

    // Kart 2: Dogrulanmis Oran = (acknowledged+resolved) / toplam.
    const card2 = cards[1];
    card2.querySelector(".font-display-lg").textContent = fmtPct(confirmedRate);
    const bar2 = card2.querySelector(".bg-secondary.h-full");
    if (bar2) bar2.style.width = (confirmedRate || 0) + "%";

    // Kart 3: Yanlis Alarm Orani = false_positive / toplam. Karsilastirma yok.
    const card3 = cards[2];
    card3.querySelector(".font-display-lg").textContent = fmtPct(fpRate);
    const trend3 = card3.querySelector(".mt-auto.pt-4");
    if (trend3) trend3.remove();

    // Kart 4: Ort. Tespit Gecikmesi -- hicbir ucta yok (bkz. rapor).
    const card4 = cards[3];
    card4.querySelector(".font-display-lg").textContent = "—";
}

// ---- Cubuk grafik: anomali tipine gore dagilim --------------------------
function fillTypeBars(summary) {
    const container = document.querySelector(".flex-1.flex.flex-col.justify-around");
    if (!container) return;
    const makeRow = rowTemplate(container);
    const rows = [...summary.by_type].sort((a, b) => b.count - a.count);
    const max = Math.max(1, ...rows.map((r) => r.count));
    const fillClasses = ["bg-primary", "bg-secondary", "bg-error opacity-80", "bg-tertiary"];

    if (rows.length === 0) {
        const empty = document.createElement("p");
        empty.className = "font-body-sm text-body-sm text-on-surface-variant text-center py-4";
        empty.textContent = "kayıt yok";
        container.appendChild(empty);
        return;
    }

    rows.forEach((row, i) => {
        const el = makeRow(row);
        const spans = el.querySelectorAll(".flex.justify-between span");
        spans[0].textContent = TIP_ADI[row.anomaly_type] || row.anomaly_type;
        spans[1].textContent = row.count.toLocaleString("tr-TR");
        const fill = el.querySelector(".h-full.rounded-full");
        fill.className = "h-full rounded-full " + fillClasses[i % fillClasses.length];
        fill.style.width = (row.count / max) * 100 + "%";
        container.appendChild(el);
    });
}

// ---- Isi haritasi: by_hour zaman damgalarindan gun x saat -------------
function fillHeatmap(summary) {
    const grid = document.querySelector(".grid-cols-12.grid-rows-7");
    if (!grid) return;

    const cells = Array.from({ length: 7 }, () => new Array(12).fill(0));
    for (const row of summary.by_hour) {
        const d = new Date(row.hour);
        const day = (d.getDay() + 6) % 7; // Pzt=0 .. Paz=6
        const bucket = Math.floor(d.getHours() / 2);
        cells[day][bucket] += row.count;
    }
    const max = Math.max(1, ...cells.flat());

    grid.innerHTML = "";
    for (let day = 0; day < 7; day++) {
        for (let bucket = 0; bucket < 12; bucket++) {
            const count = cells[day][bucket];
            const ratio = count / max;
            let cls = "bg-surface-container-highest";
            if (count > 0) {
                if (ratio >= 0.7) cls = "bg-primary";
                else if (ratio >= 0.4) cls = "bg-primary-fixed/60";
                else cls = "bg-primary-fixed/30";
            }
            const cell = document.createElement("div");
            const h1 = String(bucket * 2).padStart(2, "0");
            const h2 = String(bucket * 2 + 2).padStart(2, "0");
            cell.className = "heatmap-cell rounded-sm " + cls;
            cell.title = `${DAY_NAMES[day]} ${h1}:00-${h2}:00 - ${count} olay`;
            grid.appendChild(cell);
        }
    }
}

// ---- Karar kaynagi kaslasi: /ablation'i baslikta ozetle -----------------
function fillAblationCaption(rows) {
    const caption = document.querySelector(
        "span.font-body-sm.text-body-sm.text-on-surface-variant.flex.items-center.gap-1"
    );
    if (!caption) return;
    // Sablon metni icon'dan once VE sonra bosluk metin dugumleri birakiyor;
    // ilk eslesmeyi degistirmek sondaki sablon metnini birakiyordu (ayni
    // hata quality tablosunda da vardi) -- hepsi silinip tek taze dugum eklenir.
    [...caption.childNodes].filter((n) => n.nodeType === 3).forEach((n) => n.remove());
    if (rows.length === 0) {
        caption.appendChild(document.createTextNode(" Karar kaynağı verisi yok"));
        return;
    }
    const bySource = {};
    let total = 0;
    for (const row of rows) {
        bySource[row.decided_by] = (bySource[row.decided_by] || 0) + row.count;
        total += row.count;
    }
    const parts = Object.entries(bySource).map(
        ([src, c]) => `${DECIDED_BY_ADI[src] || src} %${Math.round((c / total) * 100)} (${c})`
    );
    caption.appendChild(document.createTextNode(" Karar kaynağı: " + parts.join(", ")));
}

// ---- Alt tablo: tip basina precision (recall/f1 hesaplanamaz) -----------
function fillQualityTable(quality) {
    const tbody = document.querySelector("table tbody");
    if (!tbody) return;
    const makeRow = rowTemplate(tbody);
    const dotClasses = ["bg-secondary", "bg-primary-fixed-dim", "bg-tertiary"];

    if (quality.items.length === 0) {
        const tr = document.createElement("tr");
        tr.innerHTML = '<td colspan="5" class="px-4 py-6 text-center text-on-surface-variant">kayıt yok</td>';
        tbody.appendChild(tr);
    } else {
        quality.items.forEach((row, i) => {
            const tr = makeRow(row);
            const tds = tr.querySelectorAll("td");
            const labelTd = tds[0];
            const dot = labelTd.querySelector("span");
            dot.className = "w-2 h-2 rounded-full " + dotClasses[i % dotClasses.length];
            // Sablon metni (ornek "VADAP Core v4.2 (Derin Ogrenme)") birden
            // fazla metin dugumune bolunmus olabilir (bosluklar dahil) --
            // hepsi silinip tek taze dugum eklenir, ilk eslesmeyi degistirmek
            // sondaki sablon metnini birakiyordu.
            [...labelTd.childNodes].filter((n) => n.nodeType === 3).forEach((n) => n.remove());
            labelTd.appendChild(document.createTextNode(TIP_ADI[row.anomaly_type] || row.anomaly_type));
            // Dogruluk (accuracy) hicbir ucta yok. Duyarlilik/F1 asla hesaplanmaz.
            tds[1].className = "px-4 py-3 text-right";
            tds[1].textContent = "—";
            tds[2].className = "px-4 py-3 text-right";
            tds[2].textContent = row.precision != null ? num(row.precision).toFixed(3) : "—";
            tds[3].className = "px-4 py-3 text-right";
            tds[3].textContent = "—";
            tds[4].className = "px-4 py-3 text-right";
            tds[4].textContent = "—";
            tbody.appendChild(tr);
        });
    }

    // Dipnot: neden recall/f1 yok (QualityOut.note, ASAMA8_PLAN.md SS3.8.3).
    const tableWrap = tbody.closest("table").parentElement; // .overflow-x-auto
    const outer = tableWrap.parentElement;
    let note = outer.querySelector("#quality-note");
    if (!note) {
        note = document.createElement("p");
        note.id = "quality-note";
        note.className = "font-body-sm text-body-sm text-on-surface-variant px-4 py-2 border-t border-outline-variant";
        outer.appendChild(note);
    }
    note.textContent = quality.note;
}

async function load() {
    try {
        const [summary, quality, ablation] = await Promise.all([
            api("/api/analytics/summary"),
            api("/api/analytics/quality"),
            api("/api/analytics/ablation"),
        ]);
        fillMetricCards(summary);
        fillTypeBars(summary);
        fillHeatmap(summary);
        fillQualityTable(quality);
        fillAblationCaption(ablation);
    } catch (err) {
        const msg = err.message === FORBIDDEN_MSG ? "bu ekran için yetkiniz yok" : "veri alınamadı: " + err.message;
        const main = document.querySelector("main");
        const banner = document.createElement("p");
        banner.className = "font-body-sm text-body-sm text-error bg-red-950/40 border border-red-800/40 rounded px-3 py-2";
        banner.textContent = msg;
        main.prepend(banner);
    }
}

document.addEventListener("DOMContentLoaded", load);
