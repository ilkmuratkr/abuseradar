"""Mail için evidence özeti — aggregate.json'dan gerçek sayı + örnek anchor seç."""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

EVIDENCE_DIR = Path("/data/evidence")

# Bir sitede bulunduğunda kullanıcıya en hızlı kanıt sağlayan kelimeler.
# Sayfa kaynağında Ctrl+F ile aratıldığında anında "evet, var" diyebileceği şeyler.
GAMBLING_KEYWORDS = (
    "bahis", "bonus", "casino", "slot", "kumar",
    "1xbet", "deneme", "iddaa", "betting", "poker",
    "escort", "viagra", "cialis",
)


def load_evidence_summary(domain: str) -> dict | None:
    """Domain için aggregate.json'dan özet bilgi.

    Returns:
        {
            "total_hacklinks": int,        # tüm sayfalardaki gerçek toplam
            "pages_crawled": int,
            "top_keyword": str | None,     # mail'de Ctrl+F için örnek anchor
            "top_target_domains": list,    # ilk birkaç saldırgan domain
        }
        Evidence yoksa None.
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

    # En çarpıcı anchor: önce skor yüksek + gambling keyword içeren
    top_keyword = _pick_top_keyword(all_links)

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

    total = data.get("total_hacklinks")
    if not total:
        total = len(all_links)

    return {
        "total_hacklinks": total,
        "pages_crawled": data.get("pages_crawled", 1),
        "top_keyword": top_keyword,
        "top_target_domains": target_doms,
    }


def _pick_top_keyword(links: list[dict]) -> str | None:
    """Doğrulama için en uygun anchor text'i seç."""
    # 1. Skor yüksek + gambling keyword'lü (en güçlü kanıt)
    scored = sorted(links, key=lambda l: l.get("score", 0) or 0, reverse=True)
    for link in scored:
        text = (link.get("text") or "").strip()
        if not text or len(text) < 3 or len(text) > 60:
            continue
        low = text.lower()
        if any(g in low for g in GAMBLING_KEYWORDS):
            return text

    # 2. Herhangi bir uzun, anlamlı anchor
    for link in links:
        text = (link.get("text") or "").strip()
        if text and 5 <= len(text) <= 60:
            return text

    return None
