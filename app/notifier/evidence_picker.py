"""Mail için evidence özeti — gerçek sayı, kategori, kaynak (raw/js), örnek anchor."""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

EVIDENCE_DIR = Path("/data/evidence")

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
    all_links = raw_links + js_links

    # Top keyword: önce skor + kategori yüksek; raw'dan gelenleri biraz öncele
    # (kullanıcı Ctrl+U ile en kolay raw'ı bulur)
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

    total = data.get("total_hacklinks") or len(all_links)

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

    # 1-4. Öncelik grupları — match varsa kısa display_keyword döner
    for display_kw, predicates in priority_groups:
        src = _has_match(predicates)
        if src:
            return display_kw, src

    # 5. Diğer kategori keyword'leri — match olan ilk keyword'ü kısa döndür
    for cat, kws in CATEGORY_KEYWORDS.items():
        for kw in kws:
            src = _has_match([kw])
            if src:
                return kw, src

    # 6. Fallback: ilk uzun anchor (anchor text'in kendisi)
    for link, src in tagged:
        text = (link.get("text") or "").strip()
        if text and 5 <= len(text) <= 60:
            return text, src
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
