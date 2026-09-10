"""sablon/*/code.html -> frontend/*.html (ASAMA8_PLAN.md SS3, 8.1).

Tasarima dokunmaz: yalnizca kenar cubugu <a href="#"> baglantilari etiket
metnine gore gercek dosyaya cevrilir ve js/app.js </body> oncesine eklenir.
Tek istisna login.html (sablon/girisekrani): sahte simulateLogin() gercek
POST /api/auth/login'e baglanir, demo kimlik bilgileri ve gercek karsiligi
olmayan "2FA Aktif"/"Oturumu acik tut" ogeleri kaldirilir (asama koordinasyonu,
docs/DURUM.md). Idempotent -- tekrar calistirilinca frontend/*.html'in ustune
yazar, frontend/js/ altina dokunmaz. Sablon guncellenirse yeniden calistirilir:

    python scripts/build_frontend.py
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SABLON = ROOT / "sablon"
FRONTEND = ROOT / "frontend"

# sablon alt dizini -> frontend dosya adi (gorev tanimindaki esleme, SS1)
PAGES = {
    "canl_i_zleme_vadap_kontrol_paneli": "index.html",
    "olaylar_vadap": "olaylar.html",
    "olay_detay_vadap": "olay-detay.html",
    "kameralar_vadap": "kameralar.html",
    "kamera_detay_vadap": "kamera-detay.html",
    "b_lgeler_vadap": "bolgeler.html",
    "analitik_vadap": "analitik.html",
    "ayarlar_vadap": "ayarlar.html",
    "kullan_c_lar_vadap": "kullanicilar.html",
    "sistem_sa_l_vadap": "sistem-sagligi.html",
    "denetim_kayd_vadap": "denetim-kaydi.html",
    "girisekrani": "login.html",
}

# kenar cubugu etiket metni -> gercek dosya (SS2). Sira onemli degil, hicbir
# etiket digerinin alt dizesi degil ("Olaylar" haric -- o da yalnizca <a>
# etiketleri icinde araniyor, sablonda "Olaylari" gecen yerler <button>).
NAV_TARGETS = {
    "Canlı İzleme": "index.html",
    "Olaylar": "olaylar.html",
    "Kameralar": "kameralar.html",
    "Bölgeler": "bolgeler.html",
    "Analitik": "analitik.html",
    "Sistem Sağlığı": "sistem-sagligi.html",
    "Kullanıcılar": "kullanicilar.html",
    "Denetim Kaydı": "denetim-kaydi.html",
    "Ayarlar": "ayarlar.html",
}

# Sablonun uzak gorselleri (tasarim aracinin urettigi lh3.googleusercontent
# baglantilari) artik yok: her biri 404 doner ve konsolu kirletir. Ustelik
# kamera kareleri olarak konulmus stok fotograflar SAHTE VERIDIR -- gercek
# kare 8.4'te canli akistan gelir. Yerel bir yer tutucuyla degistirilir;
# yerlesim, boyut ve sinif aynen kalir.
_REMOTE_IMG = re.compile(r"https://lh3\.googleusercontent\.com/[^\"')]+")
PLACEHOLDER_IMG = "img/placeholder.svg"


_A_HASH = re.compile(r'<a\b[^>]*?href="#"[^>]*?>.*?</a>', re.DOTALL)
_TAG = re.compile(r"<[^>]+>")
def _versioned(rel_path: str) -> str:
    """js/<ad>.js?v=<icerik ozeti>. Surumsuz sunulunca tarayici dosyayi
    SEZGISEL onbellekliyor (FastAPI StaticFiles Cache-Control gondermiyor) ve
    dagitimdan sonra ESKI betikle calisiyor. Bu gercekten yasandi: 8.6'da
    index.js yeni, live.js onbellekten eski geldi ve panel "liveUrlFn is not
    defined" ile tek kutuda takildi. Ozet ICERIKTEN uretilir -- degismeyen
    dosyanin URL'si de degismez, onbellek bosa harcanmaz."""
    data = (FRONTEND / rel_path).read_bytes()
    return f"{rel_path}?v={hashlib.sha256(data).hexdigest()[:8]}"


def _script_tag(rel_path: str) -> str:
    return f'<script src="{_versioned(rel_path)}" defer></script>\n'

# index.js (izgara), kamera-detay.js (tekli) ve bolgeler.js (cizim arka
# planinda canli kare) canli goru baglantisini/cizimini js/live.js'ten
# paylasir (Asama 8.4/8.5b, DURUM.md "Acik sorular" -- kopyalanmis yardimci
# onlenir). Bu sayfalar 3 betik yukler: app.js + live.js + kendi betigi.
# _page_script_tag'in "sayfa basina tek betik" kurali burada genisler.
LIVE_PAGES = {"index.html", "kamera-detay.html", "bolgeler.html"}


def _page_script_tag(out_name: str) -> str:
    """Sayfaya ozel betik VARSA eklenir (frontend/js/<ad>.js). Dosya yoksa
    satir da yok -- olmayan betige <script> koymak konsola 404 dokuyor.
    Boylece 8.3/8.4/8.5 sayfa betiklerini tek tek ekleyebilir, burada
    tutulacak ikinci bir liste olmadan. LIVE_PAGES'teki sayfalar ayrica
    js/live.js'i kendi betiklerinden ONCE yukler (live.js'in tanimladigi
    fonksiyonlara sayfa betigi bagimlidir)."""
    stem = out_name.removesuffix(".html")
    tags = ""
    if out_name in LIVE_PAGES and (FRONTEND / "js" / "live.js").is_file():
        tags += _script_tag("js/live.js")
    if (FRONTEND / "js" / f"{stem}.js").is_file():
        tags += _script_tag(f"js/{stem}.js")
    return tags



def _nav_target(a_block: str) -> str | None:
    text = _TAG.sub(" ", a_block)
    for label, target in NAV_TARGETS.items():
        if label in text:
            return target
    return None


def _rewrite_nav_links(html: str) -> str:
    def repl(m: re.Match) -> str:
        block = m.group(0)
        target = _nav_target(block)
        if target is None:
            return block
        return block.replace('href="#"', f'href="{target}"', 1)

    return _A_HASH.sub(repl, html)


def _replace_once(html: str, old: str, new: str) -> str:
    """str.replace ama sablon degisirse sessizce atlamak yerine patlar --
    login.html'in davranis degisiklikleri (asagida) tek seferlik, elle
    dogrulanmis satirlara baglidir."""
    n = html.count(old)
    assert n == 1, f"beklenmeyen eslesme sayisi ({n}): {old[:60]!r}..."
    return html.replace(old, new, 1)


# login.html'e ozgu: sablonun sahte simulateLogin()'i gercek POST
# /api/auth/login'e baglanir, demo kimlik bilgileri temizlenir, gercek
# karsiligi olmayan "2FA"/"oturum suresi" ogeleri kaldirilir (koordinasyon
# karari, docs/DURUM.md'de Asama 8 kararı olarak da yazilir). js/app.js'in
# token()/setToken()'i yalnizca GEC calisan (DOMContentLoaded / submit
# handler icindeki) kod yollarindan cagrilir -- js/app.js defer'dir, sayfa
# ayristirilirken calisan bir kod yolu token() henuz tanimsizken patlardi.
_LOGIN_REPLACEMENTS = [
    # 1) demo kimlik bilgileri: value="..." nitelikleri kaldirilir.
    (
        'id="identityInput" placeholder="Örn: 489201 veya ad.soyad@vadap.gov.tr" '
        'required="" type="text" value="op.demir@vadap.gov.tr">',
        'id="identityInput" placeholder="Örn: 489201 veya ad.soyad@vadap.gov.tr" '
        'required="" type="text">',
    ),
    (
        'id="passwordInput" placeholder="••••••••••••" required="" type="password" '
        'value="Guvenlik*2025">',
        'id="passwordInput" placeholder="••••••••••••" required="" type="password">',
    ),
    # 2) hizli-doldur cipleri: sabit e-posta/sifre ciftleri kaldirilir.
    (
        "onclick=\"quickFill('op.demir@vadap.gov.tr', 'Guvenlik*2025')\"",
        'onclick="quickFill()"',
    ),
    (
        "onclick=\"quickFill('admin.kaya@vadap.gov.tr', 'Root#Secure99')\"",
        'onclick="quickFill()"',
    ),
    # 3) "2FA Aktif" rozeti + "Oturumu 8 saat acik tut" onay kutusu: gercek
    #    karsiligi yok (2FA yok, jeton suresi sunucuda sabit) -- silinir.
    #    Blok bu ikisinden ibaretti, sarmalayici div de kalkiyor; yerine
    #    hatali giris mesaji icin tek satirlik bos alan geliyor.
    (
        '<!-- Security Options & 2FA Check -->\n'
        '<div class="flex items-center justify-between pt-1">\n'
        '<label class="flex items-center gap-2 cursor-pointer select-none">\n'
        '<input checked="" class="w-4 h-4 rounded border-slate-700 bg-slate-900 '
        'text-blue-600 focus:ring-offset-0 focus:ring-cyan-500" type="checkbox">\n'
        '<span class="text-xs text-slate-400">Oturumu 8 saat açık tut</span>\n'
        '</label>\n'
        '<div class="flex items-center gap-1.5 text-xs text-slate-400 font-mono">\n'
        '<span class="w-2 h-2 rounded-full bg-emerald-500"></span>\n'
        '<span>2FA Aktif</span>\n'
        '</div>\n'
        '</div>',
        '<p class="text-[11px] font-mono text-red-400 bg-red-950/40 border '
        'border-red-800/40 rounded px-2.5 py-1.5 text-center" hidden="" '
        'id="loginError"></p>',
    ),
    # 4) quickFill: artik parametresiz de cagriliyor -- bos deger yazmasin.
    (
        "        function quickFill(user, pass) {\n"
        "            document.getElementById('identityInput').value = user;\n"
        "            document.getElementById('passwordInput').value = pass;\n"
        "        }",
        "        function quickFill(user, pass) {\n"
        "            if (user) document.getElementById('identityInput').value = user;\n"
        "            if (pass) document.getElementById('passwordInput').value = pass;\n"
        "        }",
    ),
    # 5) Operatör/Yönetici sekmeleri: yalnizca kendi sinifini degistirir,
    #    alani doldurmaz -- rolu sunucu belirler, istemci secmez.
    (
        "            tabAdmin.className = \"py-1.5 px-3 rounded-md transition-all "
        "duration-200 text-slate-400 hover:text-slate-200 flex items-center "
        "justify-center gap-1.5\";\n"
        "            quickFill('op.demir@vadap.gov.tr', 'Guvenlik*2025');\n"
        "        });",
        "            tabAdmin.className = \"py-1.5 px-3 rounded-md transition-all "
        "duration-200 text-slate-400 hover:text-slate-200 flex items-center "
        "justify-center gap-1.5\";\n"
        "        });",
    ),
    (
        "            tabOperator.className = \"py-1.5 px-3 rounded-md transition-all "
        "duration-200 text-slate-400 hover:text-slate-200 flex items-center "
        "justify-center gap-1.5\";\n"
        "            quickFill('admin.kaya@vadap.gov.tr', 'Root#Secure99');\n"
        "        });",
        "            tabOperator.className = \"py-1.5 px-3 rounded-md transition-all "
        "duration-200 text-slate-400 hover:text-slate-200 flex items-center "
        "justify-center gap-1.5\";\n"
        "        });",
    ),
    # 6) simulateLogin(): sahte setTimeout yerine gercek POST /api/auth/login.
    #    Basarida jeton js/app.js setToken() ile saklanir ve ?next= (yoksa
    #    index.html) yonlendirilir; hatada eski dugme durumuna doner ve
    #    sunucunun 'detail' mesaji #loginError'a yazilir.
    (
        "        // Simulated Login Feedback\n"
        "        function simulateLogin() {\n"
        "            const btn = document.getElementById('loginBtn');\n"
        "            const btnText = document.getElementById('btnText');\n"
        "            const btnIcon = document.getElementById('btnIcon');\n"
        "\n"
        "            btn.disabled = true;\n"
        "            btnText.textContent = \"Doğrulanıyor...\";\n"
        "            btnIcon.textContent = \"hourglass_empty\";\n"
        "            btnIcon.classList.add(\"animate-spin\");\n"
        "\n"
        "            setTimeout(() => {\n"
        "                btnText.textContent = \"Erişim Yetkilendirildi\";\n"
        "                btnIcon.classList.remove(\"animate-spin\");\n"
        "                btnIcon.textContent = \"check_circle\";\n"
        "                btn.className = \"w-full mt-2 bg-emerald-600 text-white "
        "font-medium text-sm py-2.5 px-4 rounded-lg flex items-center "
        "justify-center gap-2 transition-all\";\n"
        "                \n"
        "                setTimeout(() => {\n"
        "                    btnText.textContent = \"Sisteme Giriş Yap\";\n"
        "                    btnIcon.textContent = \"arrow_forward\";\n"
        "                    btn.className = \"w-full mt-2 btn-shimmer "
        "bg-gradient-to-r from-blue-600 via-blue-500 to-cyan-600 "
        "hover:from-blue-500 hover:to-cyan-500 text-white font-medium text-sm "
        "py-2.5 px-4 rounded-lg shadow-lg shadow-blue-600/25 flex items-center "
        "justify-center gap-2 transition-all duration-200 border "
        "border-cyan-400/20\";\n"
        "                    btn.disabled = false;\n"
        "                }, 1800);\n"
        "            }, 1000);\n"
        "        }",
        "        // Gercek giris (ASAMA8_PLAN.md SS3, madde 4)\n"
        "        async function simulateLogin() {\n"
        "            const btn = document.getElementById('loginBtn');\n"
        "            const btnText = document.getElementById('btnText');\n"
        "            const btnIcon = document.getElementById('btnIcon');\n"
        "            const errorBox = document.getElementById('loginError');\n"
        "\n"
        "            errorBox.hidden = true;\n"
        "            btn.disabled = true;\n"
        "            btnText.textContent = \"Doğrulanıyor...\";\n"
        "            btnIcon.textContent = \"hourglass_empty\";\n"
        "            btnIcon.classList.add(\"animate-spin\");\n"
        "\n"
        "            try {\n"
        "                const body = new URLSearchParams();\n"
        "                body.set('username', document.getElementById('identityInput').value);\n"
        "                body.set('password', document.getElementById('passwordInput').value);\n"
        "                const res = await fetch('/api/auth/login', { method: 'POST', body });\n"
        "                const data = await res.json().catch(() => ({}));\n"
        "                if (!res.ok) throw new Error(data.detail || \"giris basarisiz\");\n"
        "\n"
        "                setToken(data.access_token);\n"
        "                btnIcon.classList.remove(\"animate-spin\");\n"
        "                btnText.textContent = \"Erişim Yetkilendirildi\";\n"
        "                btnIcon.textContent = \"check_circle\";\n"
        "                btn.className = \"w-full mt-2 bg-emerald-600 text-white "
        "font-medium text-sm py-2.5 px-4 rounded-lg flex items-center "
        "justify-center gap-2 transition-all\";\n"
        "\n"
        "                const params = new URLSearchParams(location.search);\n"
        "                location.href = params.get('next') || 'index.html';\n"
        "            } catch (err) {\n"
        "                btnIcon.classList.remove(\"animate-spin\");\n"
        "                btnText.textContent = \"Sisteme Giriş Yap\";\n"
        "                btnIcon.textContent = \"arrow_forward\";\n"
        "                btn.className = \"w-full mt-2 btn-shimmer "
        "bg-gradient-to-r from-blue-600 via-blue-500 to-cyan-600 "
        "hover:from-blue-500 hover:to-cyan-500 text-white font-medium text-sm "
        "py-2.5 px-4 rounded-lg shadow-lg shadow-blue-600/25 flex items-center "
        "justify-center gap-2 transition-all duration-200 border "
        "border-cyan-400/20\";\n"
        "                btn.disabled = false;\n"
        "                errorBox.textContent = err.message;\n"
        "                errorBox.hidden = false;\n"
        "            }\n"
        "        }\n"
        "\n"
        "        // Jeton zaten varsa formu tekrar gostermeye gerek yok. DOMContentLoaded\n"
        "        // icinde -- js/app.js defer'dir, sayfa parse edilirken henuz calismamis olur.\n"
        "        document.addEventListener('DOMContentLoaded', function () {\n"
        "            if (token()) {\n"
        "                const params = new URLSearchParams(location.search);\n"
        "                location.href = params.get('next') || 'index.html';\n"
        "            }\n"
        "        });",
    ),
]


def _transform_login(html: str) -> str:
    for old, new in _LOGIN_REPLACEMENTS:
        html = _replace_once(html, old, new)
    return html


def build() -> None:
    FRONTEND.mkdir(exist_ok=True)
    for src_dir, out_name in PAGES.items():
        # newline="" : sablon LF kullanir, Windows'ta metin modu CRLF'e
        # cevirir -- bu satir/script disinda tek karakter fark birakmamak icin
        # ikisi de ham birakilir.
        with open(SABLON / src_dir / "code.html", encoding="utf-8", newline="") as f:
            html = f.read()
        html = _rewrite_nav_links(html)
        html = _REMOTE_IMG.sub(PLACEHOLDER_IMG, html)
        if out_name == "login.html":
            html = _transform_login(html)
        assert "</body>" in html, f"{src_dir}: </body> bulunamadi"
        html = html.replace("</body>", _script_tag("js/app.js") + _page_script_tag(out_name) + "</body>", 1)
        (FRONTEND / out_name).write_text(html, encoding="utf-8", newline="")
        print(f"yazildi: frontend/{out_name}")


if __name__ == "__main__":
    build()
