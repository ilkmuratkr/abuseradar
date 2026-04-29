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
    priority_groups = [
        ("deneme bonusu", "deneme"),
        ("casino", "kasino"),
        ("porno", "porn"),
        ("escort", "eskort"),
    ]

    tagged = [(l, "raw") for l in raw_links] + [(l, "js") for l in js_links]

    def _best_match(predicates) -> tuple[str | None, str]:
        candidates = []
        for link, src in tagged:
            text = (link.get("text") or "").strip()
            if not text or len(text) < 3 or len(text) > 60:
                continue
            low = text.lower()
            if any(p in low for p in predicates):
                candidates.append((link.get("score", 0) or 0, text, src))
        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            _, text, src = candidates[0]
            return text, src
        return None, ""

    # 1-4. Öncelik grupları
    for group in priority_groups:
        text, src = _best_match(group)
        if text:
            return text, src

    # 5. Diğer kategori keyword'leri (bahis, slot, 1xbet, viagra, vs.)
    other = set()
    for s in CATEGORY_KEYWORDS.values():
        other.update(s)
    text, src = _best_match(other)
    if text:
        return text, src

    # 6. Fallback: ilk uzun anchor
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
