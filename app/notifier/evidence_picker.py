"""Mail için evidence özeti — gerçek sayı, kategori, kaynak (raw/js), örnek anchor."""

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

EVIDENCE_DIR = Path("/data/evidence")

# Spam-trigger kelimeler — Gmail/Outlook ML filtresi mail'de bunları görürse
# direkt phishing/spam olarak işaretler. Anchor text'inden çıkarılır,
# yerine geriye kalan nötr kelimeler kullanılır (örn. 'veren', 'siteler').
SPAM_TRIGGER_TOKENS = {
    # Gambling — TR
    "deneme", "bonus", "bonusu", "bonuslu", "casino", "kasino",
    "slot", "slots", "kumar", "bahis", "bahisçi", "bahsegel",
    "iddaa", "iddia", "tipobet", "betpark", "betboo", "betturkey",
    "poker", "1xbet", "stake", "rulet", "ruleta", "tombala",
    "jackpot", "kazandıran", "kazanc", "yatırımsız", "freebet",
    "freespin", "freespins", "spin", "spinoyna", "casinoyu",
    # Gambling — EN
    "gamble", "gambling", "betting", "wager", "blackjack",
    "sportsbook", "lottery", "jackpot", "winnings", "wagering",
    # Adult
    "porno", "porn", "xxx", "xnxx", "xvideos", "pornhub",
    "erotik", "erotic", "sex", "seks", "adult", "fetish", "fetiş",
    "escort", "eskort", "milf", "anal", "fuck",
    # Pharma
    "viagra", "cialis", "kamagra", "pharma", "pharmacy", "rxonline",
    "rxshop", "tabletim", "ilac",
    # Crypto / loan scam (sıkça spamlanan)
    "ico", "airdrop", "cashback", "kredibank",
    # Şehir adları — escort/bahis spam'i çok kullanır
    # ('izmir escort' anchor'ında 'izmir' de trigger sayılırsa keyword=None olur,
    #  mail keyword'süz pasif cümleye düşer; bu da güvenli)
    "istanbul", "izmir", "ankara", "bursa", "antalya", "kayseri",
    "mersin", "gaziantep", "konya", "samsun", "adana", "eskişehir",
    "eskisehir", "diyarbakır", "diyarbakir", "balıkesir", "balikesir",
    "trabzon", "denizli", "sakarya", "manisa", "kocaeli", "şanlıurfa",
    "sanliurfa", "malatya", "erzurum", "hatay", "tekirdağ", "tekirdag",
    # Istanbul ilçeleri (escort spam yoğun)
    "mecidiyeköy", "mecidiyekoy", "taksim", "beşiktaş", "besiktas",
    "kadıköy", "kadikoy", "ataşehir", "atasehir", "beylikdüzü",
    "beylikduzu", "şişli", "sisli", "etiler", "ataköy", "atakoy",
    "bakırköy", "bakirkoy", "levent", "maslak", "fatih",
    # Diğer TR spam çağrışım kelimeleri
    "bayan", "bayanlar", "altyazılı", "altyazili", "türbanlı", "turbanli",
}

# Kategori → keyword set. Her zaman en yüksek skorla en iyi kategori seçilir.
CATEGORY_KEYWORDS = {
    "gambling": (
        "bahis", "bonus", "casino", "slot", "kumar",
        "1xbet", "deneme", "iddaa", "betting", "poker", "ruleta",
        "blackjack", "sportsbook", "wager",
    ),
    "adult": (
        "escort", "porn", "xxx", "erotik", "sex", "adult",
        "cam", "webcam", "fetish",
    ),
    "pharma": (
        "viagra", "cialis", "kamagra", "pharmacy", "pharma", "rx",
        "tablet", "pill", "medication",
    ),
    "loan_scam": (
        "loan", "credit", "kredi", "borç", "para", "cash advance",
    ),
}


def load_evidence_summary(domain: str) -> dict | None:
    """Domain için aggregate.json'dan özet bilgi.

    Returns:
        {
            "total_hacklinks": int,
            "pages_crawled": int,
            "top_keyword": str | None,        # Ctrl+F için örnek anchor
            "top_keyword_source": str,        # "raw" | "js" — talimatlar bunu kullanır
            "category": str,                  # "gambling" | "adult" | ... | "off_topic"
            "has_raw": bool,                  # HTML'de gizlenmiş link var mı (Ctrl+U yakalar)
            "has_js": bool,                   # JS injection var mı (F12 → Elements yakalar)
            "top_target_domains": list,       # ilk 5 saldırgan domain
        }
    """
    aggr = EVIDENCE_DIR / domain / "analysis" / "aggregate.json"
    if not aggr.exists():
        return None
    try:
        data = json.loads(aggr.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"[{domain}] aggregate.json okunamadı: {e}")
        return None

    raw_links = data.get("raw_hacklinks", []) or []
    js_links = data.get("js_diff_hacklinks", []) or []
    rendered_links = data.get("rendered_hacklinks", []) or []
    # Raw + js boşsa (VPN SOCKS hatası gibi durumlarda Playwright rendered'ı tek kanıt),
    # rendered'ı fallback olarak kullan.
    all_links = raw_links + js_links if (raw_links or js_links) else rendered_links

    # Top keyword: önce skor + kategori yüksek; raw'dan gelenleri biraz öncele
    # (kullanıcı Ctrl+U ile en kolay raw'ı bulur)
    # Raw/JS boşsa rendered'ı js gibi değerlendir
    if not raw_links and not js_links and rendered_links:
        top_keyword, top_source = _pick_top_keyword([], rendered_links)
    else:
        top_keyword, top_source = _pick_top_keyword(raw_links, js_links)

    # Kategori
    category = _detect_category(all_links)

    # Top target domains
    target_doms = []
    seen = set()
    for l in all_links:
        td = (l.get("target_domain") or "").strip().lower()
        if td and td not in seen:
            seen.add(td)
            target_doms.append(td)
        if len(target_doms) >= 5:
            break

    total = data.get("total_hacklinks") or len(all_links) or len(rendered_links)

    return {
        "total_hacklinks": total,
        "pages_crawled": data.get("pages_crawled", 1),
        "top_keyword": top_keyword,
        "top_keyword_source": top_source,
        "category": category,
        "has_raw": len(raw_links) > 0,
        "has_js": len(js_links) > 0,
        "top_target_domains": target_doms,
    }


def _spam_safe_token(text: str) -> str | None:
    """Anchor text'inden mail'e konabilecek 'spam-safe' bir kelime ÖBEĞİ seç.

    Gmail TR filtresinde 'deneme bonusu' direkt phishing → mail'e koyamayız.
    Ama anchor 'deneme bonusu veren siteler' → 'veren siteler' nötrdür ve
    sayfa kaynağında Ctrl+F yapan alıcı gizli linkleri bulur.

    Strateji:
      1. Anchor'ı tokenize et (orijinal sırayı koru)
      2. Trigger kelimeleri çıkar
      3. 4+ harfli komşu nötr kelimelerden 2'sini al → 'veren siteler'
      4. Tek kelime kalmışsa onu döndür
    """
    if not text:
        return None
    # Orijinal sırayı koruyarak tokenize
    tokens = re.findall(r"[\wçğıöşüÇĞİÖŞÜ]+", text.lower(), re.UNICODE)

    safe_seq = []  # (orijinal sırada nötr kelimeler)
    for t in tokens:
        if len(t) < 4:
            continue
        if t in SPAM_TRIGGER_TOKENS:
            continue
        if any(trig in t for trig in SPAM_TRIGGER_TOKENS):
            continue
        safe_seq.append(t)

    if not safe_seq:
        return None

    # Öncelik 1 — TR spam pattern'inde en yaygın: 'veren siteler' / 'siteleri' / 'siteler'
    if "veren" in safe_seq and "siteler" in safe_seq:
        return "veren siteler"
    for kw in ("siteleri", "veren", "siteler"):
        if kw in safe_seq:
            return kw

    # Öncelik 2 — Anchor'daki ilk 2 nötr kelime (orijinal sıra)
    if len(safe_seq) >= 2:
        return f"{safe_seq[0]} {safe_seq[1]}"
    return safe_seq[0]


def _pick_top_keyword(raw_links: list[dict], js_links: list[dict]) -> tuple[str | None, str]:
    """En kanıt değeri yüksek anchor + hangi kaynaktan geldiğini döndür.

    Katı öncelik sırası — kullanıcının "anlık doğrulama"
    refleksini en güçlü tetikleyecek kelimeler önce:

      1. "deneme bonusu" / "deneme"   (gambling, çoğu TR sitede var)
      2. "casino" / "kasino"          (gambling, evrensel)
      3. "porno" / "porn"             (adult)
      4. "escort" / "eskort"          (adult)
      5. herhangi bir kategori keyword (bahis, slot, viagra, vs.)
      6. fallback: ilk uzun anchor

    Aynı öncelik grubunda en yüksek skorlu anchor kazanır.
    """
    # (display_keyword, eşleşme listesi)
    # display_keyword → mail'e yazılan kısa, net arama terimi
    # eşleşme listesi → bu grubun anchor text'lerinde geçen tüm formlar
    priority_groups = [
        ("deneme bonusu", ["deneme bonusu", "deneme"]),
        ("casino", ["casino", "kasino"]),
        ("porno", ["porno", "porn"]),
        ("escort", ["escort", "eskort"]),
    ]

    tagged = [(l, "raw") for l in raw_links] + [(l, "js") for l in js_links]

    def _has_match(predicates) -> str | None:
        """Bu predicate'lardan biri herhangi bir anchor'da geçiyorsa,
        o anchor'un kaynağını ('raw' veya 'js') döndür. Yoksa None."""
        # Skor sıralı en güçlü matchin source'unu seç
        candidates = []
        for link, src in tagged:
            text = (link.get("text") or "").strip().lower()
            if not text or len(text) > 200:
                continue
            if any(p in text for p in predicates):
                candidates.append((link.get("score", 0) or 0, src))
        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            return candidates[0][1]
        return None

    # Her bir öncelik grubunda eşleşen anchor'lar varsa, ANCHOR TEXT'inden
    # spam-safe nötr bir kelime seç (örn 'deneme bonusu veren siteler' → 'veren').
    for display_kw, predicates in priority_groups:
        candidates = []
        for link, src in tagged:
            text = (link.get("text") or "").strip().lower()
            if not text or len(text) > 200:
                continue
            if any(p in text for p in predicates):
                candidates.append((link.get("score", 0) or 0, link.get("text", ""), src))
        if not candidates:
            continue
        candidates.sort(key=lambda x: x[0], reverse=True)
        for _, anchor_text, src in candidates:
            safe = _spam_safe_token(anchor_text)
            if safe:
                return safe, src

    # Diğer kategori keyword'leri için de anchor'dan nötr kelime çıkar
    for cat, kws in CATEGORY_KEYWORDS.items():
        for kw in kws:
            for link, src in tagged:
                text = (link.get("text") or "").strip().lower()
                if kw in text:
                    safe = _spam_safe_token(link.get("text", ""))
                    if safe:
                        return safe, src

    # Son fallback: ilk uzun anchor'dan nötr kelime
    for link, src in tagged:
        text = (link.get("text") or "").strip()
        if text and len(text) >= 5:
            safe = _spam_safe_token(text)
            if safe:
                return safe, src
    return None, "raw"


def _detect_category(links: list[dict]) -> str:
    """Hacklinklerin baskın kategorisi."""
    counts = {cat: 0 for cat in CATEGORY_KEYWORDS}
    for link in links:
        text_blob = " ".join([
            (link.get("text") or ""),
            (link.get("title") or ""),
            (link.get("target_domain") or ""),
        ]).lower()
        # reasons listesinde "gambling keyword" gibi metadata olabilir
        reasons = link.get("reasons") or []
        if isinstance(reasons, list):
            text_blob += " " + " ".join(str(r).lower() for r in reasons)
        for cat, kws in CATEGORY_KEYWORDS.items():
            if any(k in text_blob for k in kws):
                counts[cat] += 1
                break

    best_cat, best_n = max(counts.items(), key=lambda kv: kv[1])
    if best_n == 0:
        return "off_topic"
    return best_cat
