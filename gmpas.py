import argparse
import json
import re
from urllib.parse import quote

import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

DEBUG = False
SORT_BTN = ("button[data-value='Sort'], button[data-value='Urutkan'], "
            "button[aria-label*='Sort' i], button[aria-label*='Urutkan' i]")
LANG = "id"  # bahasa UI Google Maps: "id" atau "en" (di-set dari --lang)

SORT_LABELS = {
    "Most relevant": ["Most relevant", "Paling relevan", "Relevan"],
    "Newest": ["Newest", "Terbaru"],
    "Highest rating": ["Highest rating", "Peringkat tertinggi", "Tertinggi"],
    "Lowest rating": ["Lowest rating", "Peringkat terendah", "Terendah"],
}

SEL = {
    "name": "h1.DUwDvf",
    "rating": "div.F7nice span[aria-hidden='true']",
    "review_count": "div.F7nice span[aria-label]",
    "category": "button.DkEaL",
    "address": "button[data-item-id='address']",
    "phone": "button[data-item-id^='phone']",
    "website": "a[data-item-id='authority']",
    "plus_code": "button[data-item-id='oloc']",
    "hours_rows": "table.eK4R0e tr",
    "review_card": "div.jftiEf",
}

# JavaScript yang dijalankan di dalam halaman (jauh lebih cepat daripada
# memanggil Playwright per-elemen, penting untuk ribuan review)
JS_MARK = """
(batch) => {
  let n = 0;
  document.querySelectorAll('div.jftiEf').forEach(c => {
    if (c.dataset.batch) return;
    c.dataset.batch = String(batch);
    n++;
    const more = c.querySelector('button.w8nwRe');   // tombol "More"/"Lainnya"
    if (more) more.click();
  });
  return n;
}
"""

JS_TRANSLATE = """
(batch) => {
  document.querySelectorAll(`div.jftiEf[data-batch="${batch}"]`).forEach(c => {
    const t = [...c.querySelectorAll('span.wiI7pd')].find(e => !e.closest('.CDe7pd'));
    c.dataset.disp = t ? t.innerText.trim() : '';
    const btn = c.querySelector('button.kPvgOb') ||
      [...c.querySelectorAll('button')].find(b => /see original|lihat (yang )?asli/i.test(b.innerText));
    if (btn) { c.dataset.translated = '1'; btn.click(); }
  });
}
"""

JS_READ = """
({batch, raw}) => {
  const out = [];
  document.querySelectorAll(`div.jftiEf[data-batch="${batch}"]`).forEach(c => {
    const txt = (s) => { const e = c.querySelector(s); return e ? e.innerText.trim() : null; };
    const stars = c.querySelector('span.kvMYJc');
    const label = stars ? stars.getAttribute('aria-label') : null;
    const m = label && label.match(/\\d+/);
    const meta = txt('div.RfnDt');
    const body = [...c.querySelectorAll('span.wiI7pd')].find(e => !e.closest('.CDe7pd'));
    const photos = [...c.querySelectorAll('button.Tya61d')].map(b => {
      const mm = (b.getAttribute('style') || '').match(/url\\("?(.*?)"?\\)/);
      return mm ? mm[1] : null;
    }).filter(Boolean);
    const prof = c.querySelector('button.WEBjve');
    const row = {
      review_id: c.getAttribute('data-review-id'),
      reviewer_name: txt('div.d4r55'),
      reviewer_profile_url: prof ? prof.getAttribute('data-href') : null,
      reviewer_meta: meta,
      is_local_guide: !!(meta && /local guide/i.test(meta)),
      rating: m ? parseInt(m[0]) : null,
      date_relative: txt('span.rsqaWe'),
      text: body ? body.innerText.trim() : null,          // bahasa asli penulis
      text_displayed: c.dataset.disp || null,             // versi tampil (bisa terjemahan)
      is_translated: c.dataset.translated === '1',
      likes: txt('span.pkWtMe'),
      details: [...c.querySelectorAll('div.PBK6be')].map(d => d.innerText.trim()),
      photos: photos,
      owner_response: txt('.CDe7pd .wiI7pd'),
      owner_response_date: txt('.CDe7pd span.DZSIDd'),
    };
    if (raw) row.raw_html = c.outerHTML;
    out.push(row);
  });
  return out;
}
"""

# cari elemen yang benar-benar bisa di-scroll di atas kartu review, lalu scroll
JS_SCROLL = """
() => {
  const cards = document.querySelectorAll('div.jftiEf');
  const res = {cards: cards.length, scroller: null};
  if (!cards.length) return res;
  cards[cards.length - 1].scrollIntoView({block: 'end'});
  let el = cards[0].parentElement;
  while (el) {
    const oy = getComputedStyle(el).overflowY;
    if ((oy === 'auto' || oy === 'scroll') && el.scrollHeight > el.clientHeight) {
      el.scrollTop = el.scrollHeight;
      res.scroller = {cls: el.className, sh: el.scrollHeight, ch: el.clientHeight, st: Math.round(el.scrollTop)};
      break;
    }
    el = el.parentElement;
  }
  return res;
}
"""


def text_of(page, selector, attr=None):
    try:
        el = page.locator(selector).first
        if el.count() == 0:
            return None
        return (el.get_attribute(attr) if attr else el.inner_text()).strip()
    except Exception:
        return None


def accept_consent(page):
    for label in ["Accept all", "Terima semua", "Reject all", "Tolak semua"]:
        try:
            btn = page.get_by_role("button", name=label)
            if btn.count():
                btn.first.click()
                page.wait_for_timeout(1500)
                return
        except Exception:
            pass


def open_place(page, query_or_url):
    if query_or_url.startswith("http"):
        url = query_or_url
        is_short = "goo.gl" in url
        if "hl=" not in url and not is_short:
            url += ("&" if "?" in url else "?") + f"hl={LANG}"
    else:
        url = f"https://www.google.com/maps/search/{quote(query_or_url)}?hl={LANG}"
    page.goto(url, wait_until="domcontentloaded")
    accept_consent(page)
    try:
        page.wait_for_selector(SEL["name"], timeout=8000)
    except PWTimeout:
        first = page.locator("a.hfpxzc").first
        if first.count():
            first.click()
            page.wait_for_selector(SEL["name"], timeout=15000)
    page.wait_for_timeout(1500)


def scrape_place_info(page):
    info = {
        "name": text_of(page, SEL["name"]),
        "category": text_of(page, SEL["category"]),
        "rating": text_of(page, SEL["rating"]),
        "review_count_label": text_of(page, "div.F7nice"),  # mis. "4,4 (1.234)"
        "address": text_of(page, SEL["address"], "aria-label"),
        "phone": text_of(page, SEL["phone"], "aria-label"),
        "website": text_of(page, SEL["website"], "href"),
        "plus_code": text_of(page, SEL["plus_code"], "aria-label"),
        "url": page.url,
    }
    m = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", page.url)
    info["latitude"], info["longitude"] = (m.group(1), m.group(2)) if m else (None, None)
    m = re.search(r"!1s(0x[0-9a-f]+:0x[0-9a-f]+)", page.url)
    info["place_id_hex"] = m.group(1) if m else None

    hours = {}
    for row in page.locator(SEL["hours_rows"]).all():
        try:
            cells = row.locator("td").all_inner_texts()
            if len(cells) >= 2:
                hours[cells[0].strip()] = cells[1].strip()
        except Exception:
            pass
    info["opening_hours"] = hours
    info["all_info_buttons"] = [
        (b.get_attribute("aria-label") or "").strip()
        for b in page.locator("button[data-item-id], a[data-item-id]").all()
    ]
    return info


def debug_dump(page, tag):
    """Simpan screenshot + HTML + ringkasan struktur untuk diagnosis."""
    try:
        info = page.evaluate("""() => {
          const tabs = [...document.querySelectorAll("[role='tab']")]
            .map(t => [t.innerText.trim(), t.getAttribute('aria-selected')]);
          const sorts = [...document.querySelectorAll('button')]
            .filter(b => /sort|urutkan/i.test((b.getAttribute('aria-label')||'') + ' ' +
                         (b.getAttribute('data-value')||'') + ' ' + b.innerText))
            .map(b => ({al: b.getAttribute('aria-label'), dv: b.getAttribute('data-value'),
                        txt: b.innerText.trim().slice(0, 40), vis: !!(b.offsetWidth || b.offsetHeight)}));
          return {tabs, sorts, cards: document.querySelectorAll('div.jftiEf').length,
                  title: document.title};
        }""")
        print(f"[debug:{tag}]", info)
        page.screenshot(path=f"debug_{tag}.png")
        with open(f"debug_{tag}.html", "w", encoding="utf-8") as f:
            f.write(page.content())
        print(f"[debug:{tag}] disimpan: debug_{tag}.png dan debug_{tag}.html")
    except Exception as e:
        print(f"[debug:{tag}] gagal dump: {e}")


def on_reviews_view(page, timeout=6000):
    """Tampilan review penuh punya tombol Urutkan/Sort; tab Ringkasan tidak punya."""
    try:
        page.wait_for_selector(SORT_BTN, timeout=timeout)
        return True
    except PWTimeout:
        return False


def open_reviews_tab(page):
    if DEBUG:
        tabs = [((t.get_attribute("aria-label") or ""), t.inner_text().strip())
                for t in page.locator("[role='tab']").all()]
        print("[debug] tab yang ditemukan:", tabs)
    candidates = [
        lambda: page.get_by_role("tab", name=re.compile(r"^(Reviews|Ulasan)", re.I)).first,
        lambda: page.locator("[role='tab']:has-text('Ulasan'), [role='tab']:has-text('Reviews')").first,
        lambda: page.locator("div.F7nice span[aria-label*='ulasan' i], "
                             "div.F7nice span[aria-label*='review' i]").first,
        lambda: page.locator("button:has-text('Ulasan lainnya'), button:has-text('More reviews')").first,
        lambda: page.get_by_role("button", name=re.compile(r"^(Reviews|Ulasan)", re.I)).first,
    ]
    for i, get in enumerate(candidates, 1):
        try:
            el = get()
            if el.count() == 0:
                continue
            el.click(timeout=4000)
            if on_reviews_view(page):
                print(f"[info] tampilan review terbuka (cara #{i})")
                try:
                    page.wait_for_selector(SEL["review_card"], timeout=10000)
                except PWTimeout:
                    print("[warn] kartu review belum muncul setelah 10 detik")
                return True
            print(f"[warn] cara #{i} diklik tapi belum masuk tampilan review")
        except Exception:
            continue
    return False


MENU_ITEMS = ("[role='menuitemradio'], [role='menu'] [role='menuitem'], "
              "[role='menu'] [role='radio'], div.fxNQSd")


def sort_reviews(page, mode="Newest"):
    """Pilih urutan di menu 'Urutkan'. Pencarian dibatasi ke item menu, karena kata
    'Terbaru' juga ada di sidebar kiri Maps (riwayat) dan klik di sana membuang kita
    dari halaman tempat."""
    labels = SORT_LABELS.get(mode, [mode])
    pattern = re.compile(r"^\s*(" + "|".join(re.escape(l) for l in labels) + r")\s*$", re.I)
    last_err = ""
    for use_js in (False, True):  # 1: klik biasa, 2: klik lewat JS (abaikan overlay)
        try:
            btn = page.locator(SORT_BTN).first
            btn.dispatch_event("click") if use_js else btn.click(timeout=4000)
            page.wait_for_timeout(800)
            items = page.locator(MENU_ITEMS).filter(has_text=pattern)
            if items.count() == 0:
                if DEBUG:
                    html = page.evaluate(
                        "() => { const m = document.querySelector(\"[role='menu']\"); "
                        "return m ? m.outerHTML.slice(0, 600) : 'tidak ada [role=menu]'; }")
                    print("[debug] isi menu urutan:", html)
                raise RuntimeError("item menu urutan tidak ditemukan")
            item = items.first
            item.dispatch_event("click") if use_js else item.click(timeout=4000)
            page.wait_for_timeout(2500)
            if not on_reviews_view(page, 4000):
                raise RuntimeError("halaman berpindah setelah memilih urutan")
            print(f"[info] urutan '{mode}' diterapkan" + (" (via JS)" if use_js else ""))
            return True
        except Exception as e:
            last_err = str(e).splitlines()[0]
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            page.wait_for_timeout(500)
            if not on_reviews_view(page, 1500):
                break  # sudah keluar dari tampilan review; biar ditangani recover
    print(f"[warn] gagal sort '{mode}', lanjut urutan default: {last_err}")
    return False


def recover_reviews_view(page, target):
    """Pastikan kita masih di tampilan review; kalau tidak, buka ulang tempatnya."""
    if on_reviews_view(page, 1500):
        return True
    print("[warn] keluar dari tampilan review, membuka ulang halaman tempat...")
    open_place(page, target)
    return open_reviews_tab(page)


def login_wall_detected(page):
    try:
        return page.evaluate("""() => {
          if (document.querySelector("iframe[src*='accounts.google.com']")) return true;
          const dlg = [...document.querySelectorAll("[role='dialog']")]
            .some(d => /sign in|masuk|log in/i.test(d.innerText));
          return dlg;
        }""")
    except Exception:
        return False


def scrape_reviews(page, store, max_reviews, keep_raw=False, patience=8, checkpoint=None):
    """store: dict review_id -> row (dipakai bersama agar bisa gabung beberapa sort)."""
    batch = int(page.evaluate("() => Date.now() % 100000000"))  # unik per pemanggilan
    stale = 0
    while len(store) < max_reviews and stale < patience:
        batch += 1
        n_new = page.evaluate(JS_MARK, batch)
        if n_new:
            page.wait_for_timeout(300)
            page.evaluate(JS_TRANSLATE, batch)
            page.wait_for_timeout(400)
            rows = page.evaluate(JS_READ, {"batch": batch, "raw": keep_raw})
            before = len(store)
            for r in rows:
                if r["review_id"] and r["review_id"] not in store:
                    store[r["review_id"]] = r
            added = len(store) - before
            if checkpoint and len(store) // 200 != before // 200:
                with open(checkpoint, "w", encoding="utf-8") as f:
                    json.dump(list(store.values()), f, ensure_ascii=False)
        else:
            added = 0
        stale = stale + 1 if added == 0 else 0
        print(f"[info] total review: {len(store)} (+{added}) stale={stale}/{patience}")

        if stale >= 2:  # "goyang" sedikit ke atas agar pemicu lazy-load aktif lagi
            try:
                page.mouse.wheel(0, -900)
                page.wait_for_timeout(500)
            except Exception:
                pass
        info = page.evaluate(JS_SCROLL)
        total_cards = info["cards"]
        try:  # scroll "asli" dengan roda mouse di atas daftar review
            box = page.locator(SEL["review_card"]).last.bounding_box(timeout=2000)
            if box:
                page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                for _ in range(4):
                    page.mouse.wheel(0, 1200)
                    page.wait_for_timeout(250)
        except Exception:
            pass
        if DEBUG:
            print(f"[debug] cards={total_cards} scroller={info['scroller']}")
            if stale >= patience:
                debug_dump(page, "stuck")
        if stale >= patience and login_wall_detected(page):
            print("[warn] Google meminta LOGIN untuk memuat review lainnya. "
                  "Jalankan dengan --profile (lihat --login) atau --cdp.")
        try:  # tunggu sampai kartu baru benar-benar ter-load
            page.wait_for_function(
                "n => document.querySelectorAll('div.jftiEf').length > n",
                arg=total_cards, timeout=7000)
        except PWTimeout:
            pass
        page.wait_for_timeout(500)
    return store


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", nargs="?", help="URL Google Maps atau nama tempat")
    ap.add_argument("--max-reviews", type=int, default=1000)
    ap.add_argument("--sort", default="Newest",
                    choices=["Most relevant", "Newest", "Highest rating", "Lowest rating", "all"],
                    help="'all' = ambil dengan 4 urutan lalu gabung (dedup) untuk tembus batas")
    ap.add_argument("--raw-html", action="store_true")
    ap.add_argument("--headful", action="store_true")
    ap.add_argument("--out", default="gmaps_output")
    ap.add_argument("--lang", default="id", choices=["id", "en"])
    ap.add_argument("--channel", default=None, choices=["chrome", "msedge"],
                    help="pakai Chrome/Edge terpasang, bukan Chromium bawaan Playwright")
    ap.add_argument("--profile", default=None,
                    help="folder profil browser permanen (menyimpan sesi login Google)")
    ap.add_argument("--login", action="store_true",
                    help="buka browser untuk login Google manual (dipakai bersama --profile)")
    ap.add_argument("--cdp", default=None,
                    help="sambung ke Chrome yang sudah jalan, mis. http://localhost:9222")
    ap.add_argument("--debug", action="store_true", help="cetak info scroll + screenshot saat macet")
    args = ap.parse_args()
    global LANG, DEBUG
    LANG = args.lang
    DEBUG = args.debug
    locale = "id-ID" if LANG == "id" else "en-US"
    stealth_args = ["--disable-blink-features=AutomationControlled"]
    webdriver_js = "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"

    # ---- mode login: simpan sesi ke profil lalu keluar ----
    if args.login:
        if not args.profile:
            ap.error("--login harus dipakai bersama --profile FOLDER")
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                args.profile, headless=False, channel=args.channel or "chrome",
                args=stealth_args, locale=locale, viewport=None)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto("https://accounts.google.com/")
            input("\n>>> Login ke akun Google di jendela browser, lalu tekan ENTER di sini... ")
            page.goto("https://www.google.com/maps")
            page.wait_for_timeout(2000)
            ctx.close()
        print("[done] sesi login tersimpan di:", args.profile)
        return

    if not args.target:
        ap.error("target (URL/nama tempat) wajib diisi")

    store, info = {}, {}
    with sync_playwright() as p:
        owned_browser, owned_ctx = None, None
        if args.cdp:  # Chrome milik Anda yang sudah login
            owned_browser = p.chromium.connect_over_cdp(args.cdp)
            ctx = owned_browser.contexts[0] if owned_browser.contexts else owned_browser.new_context()
            page = ctx.new_page()
        elif args.profile:  # profil permanen (sudah login lewat --login)
            ctx = owned_ctx = p.chromium.launch_persistent_context(
                args.profile, headless=not args.headful, channel=args.channel or "chrome",
                args=stealth_args, locale=locale, viewport={"width": 1366, "height": 900})
            ctx.add_init_script(webdriver_js)
            page = ctx.new_page()
        else:  # tanpa login (hanya ~5 review pertama)
            launch_kw = {"headless": not args.headful, "args": stealth_args}
            if args.channel:
                launch_kw["channel"] = args.channel
            owned_browser = p.chromium.launch(**launch_kw)
            ctx = owned_browser.new_context(
                locale=locale, viewport={"width": 1366, "height": 900},
                user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"))
            ctx.add_init_script(webdriver_js)
            page = ctx.new_page()
            print("[warn] mode TANPA login: Google biasanya hanya memberi ~5 review. "
                  "Pakai --profile atau --cdp untuk review lengkap.")

        if DEBUG:  # pantau permintaan data review ke server Google
            page.on("response", lambda r: print(f"[net] {r.status} {r.url[:120]}")
                    if ("listugcposts" in r.url or "/maps/rpc/" in r.url) else None)
        open_place(page, args.target)
        info = scrape_place_info(page)
        print("[info] tempat:", info["name"], "|", info["review_count_label"])

        if not open_reviews_tab(page):
            print("[error] gagal membuka tampilan review penuh -> tidak ada review diambil")
            if DEBUG:
                page.screenshot(path="debug_no_reviews_view.png")
                print("[debug] screenshot disimpan: debug_no_reviews_view.png")
        else:
            if DEBUG:
                debug_dump(page, "after_open")
            modes = (["Newest", "Most relevant", "Highest rating", "Lowest rating"]
                     if args.sort == "all" else [args.sort])
            for mode in modes:
                if len(store) >= args.max_reviews:
                    break
                print(f"[info] === urutan: {mode} ===")
                if not recover_reviews_view(page, args.target):
                    print("[error] tidak bisa kembali ke tampilan review")
                    break
                sort_reviews(page, mode)
                if not recover_reviews_view(page, args.target):
                    print("[error] tidak bisa kembali ke tampilan review")
                    break
                try:
                    page.wait_for_selector(SEL["review_card"], timeout=10000)
                except PWTimeout:
                    pass
                scrape_reviews(page, store, args.max_reviews, args.raw_html,
                               checkpoint=f"{args.out}_checkpoint.json")

        # tutup hanya yang kita buka sendiri
        if args.cdp:
            page.close()
        if owned_ctx:
            owned_ctx.close()
        if owned_browser:
            owned_browser.close()

    reviews = list(store.values())
    with open(f"{args.out}.json", "w", encoding="utf-8") as f:
        json.dump({"place": info, "reviews": reviews}, f, ensure_ascii=False, indent=2)
    df = pd.DataFrame(reviews)
    for col in ("details", "photos"):
        if col in df:
            df[col] = df[col].apply(lambda x: " | ".join(x) if isinstance(x, list) else x)
    df.to_csv(f"{args.out}_reviews.csv", index=False, encoding="utf-8-sig")
    print(f"[done] {len(reviews)} review -> {args.out}.json & {args.out}_reviews.csv")


if __name__ == "__main__":
    main()