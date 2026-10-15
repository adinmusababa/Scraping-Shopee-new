from collections import Counter
ROOT = set(StemmerFactory().get_words())          # kata dasar Sastrawi
NOMINAL = re.compile(r"^(pe|per|ke)\w+an$")       # pemerintahan, kebijakan, pertahanan, ...
 
def analisis_lemma(df, token_col="tokens_no_stopwords", top=200):
    """Tabel kandidat untuk menentukan kamus lemma. Hanya ditampilkan, tidak disimpan.
    Urut dari kata paling sering. Kolom 'perlu_tinjau' menandai hasil stem yang patut dicurigai."""
    toks = [to_list(v) for v in df[token_col].to_list()]
    tf = Counter(t for ts in toks for t in ts)
    dfreq = Counter(t for ts in toks for t in set(ts))
    rows = []
    for t, n in tf.most_common():
        if t.isdigit() or t in PROTECTED or "-" in t:
            continue
        s = _stem(t)
        if s == t:
            continue
        alasan = []
        if len(s) <= 3:                 alasan.append("stem pendek")
        if len(s) < 0.5 * len(t):       alasan.append("stem <50% panjang")
        if s not in ROOT:               alasan.append("stem bukan kata dasar")
        if NOMINAL.match(t):            alasan.append("pe-an/ke-an/per-an: cek makna")
        rows.append({"token": t, "stem": s, "freq": n, "jml_dok": dfreq[t],
                     "perlu_tinjau": bool(alasan), "alasan": ", ".join(alasan)})
        if len(rows) >= top:
            break
    return pl.DataFrame(rows)
 
def lihat_konteks(df, kata, col="text_normalized", n=5):
    """Contoh kalimat tempat sebuah kata muncul (untuk memutuskan kata ambigu)."""
    return df.filter(pl.col(col).str.contains(rf"\b{re.escape(kata)}\b")).select(col).head(n)
 
def cek_lemma_dict(df, lemma_dict, token_col="tokens_no_stopwords"):
    """Seberapa banyak token yang terdampak kamus lemma, dan kata mana yang belum pernah muncul."""
    tf = Counter(t for v in df[token_col].to_list() for t in to_list(v))
    pakai = {k: tf[k] for k in lemma_dict if tf[k]}
    print("entri:", len(lemma_dict), "| muncul di data:", len(pakai),
          "| token terdampak:", sum(pakai.values()), "dari", sum(tf.values()))
    print("tidak muncul di data:", [k for k in lemma_dict if not tf[k]])
 
def lemmatization(df, text_col, output_col="tokens_lemmatized", lemma_dict=None):
    """Kamus lemma dulu; kalau tidak ada, pakai stem Sastrawi."""
    lemma_dict = lemma_dict or {}
    return _apply_list(df, text_col, output_col,
                       lambda toks: [lemma_dict.get(t) or _stem(t) for t in toks])