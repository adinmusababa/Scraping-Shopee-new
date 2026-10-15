import re
from collections import Counter
import polars as pl
from Sastrawi.Stemmer.StemmerFactory import StemmerFactory

ROOT = set(StemmerFactory().get_words())
TOK = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")

def profil_korpus(df, raw_col, norm_col, min_freq=5, top=50):
    raw = df[raw_col].fill_null("").to_list()
    norm = df[norm_col].fill_null("").to_list()
    toks = [TOK.findall(s) for s in norm]
    freq = Counter(t for ts in toks for t in ts)
    total = sum(freq.values())

    pola = {  # seberapa banyak baris yang mengandung tiap jenis noise
        "url": r"https?://|t\.co", "mention": r"@\w+", "hashtag": r"#\w+",
        "emoji": "[\U0001F300-\U0001FAFF\u2600-\u27BF]", "huruf_berulang": r"(\w)\1{2,}",
        "kata_ulang_angka2": r"\b[a-zA-Z]+2\b", "angka": r"\d", "RT": r"^\s*RT\b",
    }
    print("baris:", len(raw), "| duplikat (norm):", len(norm) - len(set(norm)),
          "| kosong:", sum(1 for s in norm if not s.strip()))
    pj = sorted(len(ts) for ts in toks)
    print("panjang token  median:", pj[len(pj)//2], "p95:", pj[int(len(pj)*.95)], "maks:", pj[-1])
    print("token:", total, "| jenis kata:", len(freq),
          "| hapax (muncul 1x):", sum(1 for n in freq.values() if n == 1))
    print("\n% baris mengandung:")
    for k, p in pola.items():
        print(f"  {k:20s}", round(100 * sum(bool(re.search(p, s)) for s in raw) / len(raw), 1))

    oov = [(t, n) for t, n in freq.most_common()
           if not t.isdigit() and t not in ROOT and n >= min_freq]
    print(f"\nkandidat slang/nama/typo (bukan kata dasar, n>={min_freq}): {len(oov)}")
    print(oov[:top])
    caps = Counter(w for s in raw for w in re.findall(r"\b[A-Z][a-z]{2,}\b", s))
    print("\nkandidat PROTECTED (kapital):", caps.most_common(top))
    return freq