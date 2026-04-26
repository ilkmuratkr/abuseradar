"""Kural tabanlı mağdur/saldırgan sınıflandırma."""

import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

BET_DOMAIN_KEYWORDS = [
    "bet", "casino", "slot", "poker", "bahis", "bonus",
    "giris", "giriş", "spin", "jackpot", "gambl", "wager",
]

KNOWN_C2_DOMAINS = [
    "hacklinkbacklink.com",
    "backlinksatis.net",
    "scriptapi.dev",
]

SEO_SPAM_KEYWORDS = [
    "itxoft", "seoexpress", "rankzly", "buyseolink", "skylinkseo",
    "primeseo", "zoldexlinks", "seodaro", "royalseohub",
    "rank-top", "rank-fast", "prolinkbox", "linksjump",
    "linkbox.agency", "seolink.info",
]

ESCORT_KEYWORDS = ["escort", "eskort"]

GAMBLING_ANCHORS = [
    "deneme bonusu", "bahis", "casino", "slot ",
    "sahabet", "onwin", "jojobet", "grandpashabet",
    "perabet", "1xbet", "1win", "betgaranti",
]

NEGATIVE_SEO_ANCHORS = [
    "child porn", "child abuse", "csam",
    "illegal", "terrorism", "bomb",
]

PBN_SHOP_PATTERNS = [
    "rank faster on google",
    "pbn & high authority backlinks",
    "@moonalites",
]

GOV_TLDS = [".gov.", ".gob.", ".gouv.", ".govt."]
EDU_TLDS = [".edu.", ".ac.", ".edu"]


def classify_backlink(row: dict) -> tuple[str, str]:
    """Backlink kaydını sınıflandır.

    Returns:
        (category, detail): ("MAGDUR", "hukumet_sitesi") gibi
    """
    url = (row.get("referring_url") or "").lower()
    anchor = (row.get("anchor_text") or "").lower()
    title = (row.get("referring_title") or "").lower()
    is_spam = row.get("is_spam_flag", False)

    try:
        domain = urlparse(url).hostname or ""
    except Exception:
        domain = ""

    # ═══ KESİN SALDIRGAN ═══

    # Bahis keyword'ü domain'de
    if any(kw in domain for kw in BET_DOMAIN_KEYWORDS):
        return "SALDIRGAN", "bahis_sitesi"

    # Bilinen C2
    if domain in KNOWN_C2_DOMAINS:
        return "SALDIRGAN", "c2_panel"

    # PBN pattern'leri
    if "culture news" in title:
        return "SALDIRGAN", "pbn_culture_news"
    if domain.endswith(".shop") and "moonalites" in title:
        return "SALDIRGAN", "pbn_moonalites"

    # Telegram satıcılar
    if "SALESOVEN" in title.upper():
        return "SALDIRGAN", "telegram_salesoven"
    if "LINKS_DEALER" in title.upper():
        return "SALDIRGAN", "telegram_links_dealer"

    # Sahte SEO servisi
    if any(kw in domain for kw in SEO_SPAM_KEYWORDS):
        return "SALDIRGAN", "sahte_seo_servisi"

    # Spam directory
    if "website list 1276" in title or "changes in the world of seo" in title:
        return "SALDIRGAN", "spam_directory"

    # PBN .shop siteleri (@moonalites)
    if domain.endswith(".shop") and any(p in title for p in PBN_SHOP_PATTERNS):
        # Anchor text'e göre alt sınıflandır
        if any(neg in anchor for neg in NEGATIVE_SEO_ANCHORS):
            return "SALDIRGAN", "pbn_negatif_seo"
        return "SALDIRGAN", "pbn_moonalites"

    # Genel PBN .shop (moonalites dışı da olabilir)
    if domain.endswith(".shop") and is_spam and any(kw in anchor for kw in GAMBLING_ANCHORS):
        return "SALDIRGAN", "pbn_shop"

    # Negatif SEO (herhangi bir kaynaktan toksik anchor)
    if any(neg in anchor for neg in NEGATIVE_SEO_ANCHORS):
        return "SALDIRGAN", "negatif_seo"

    # Escort
    if any(kw in domain for kw in ESCORT_KEYWORDS):
        return "SALDIRGAN", "escort_sitesi"

    # Domain satıcı
    if ("aged domains" in title or "backlinks" in title) and is_spam:
        return "SALDIRGAN", "domain_satici"

    # ═══ KESİN MAĞDUR ═══

    # Hükümet sitesi + spam anchor
    if any(tld in domain for tld in GOV_TLDS):
        return "MAGDUR", "hukumet_sitesi"

    # Eğitim sitesi
    if any(tld in domain for tld in EDU_TLDS):
        return "MAGDUR", "egitim_sitesi"

    # ═══ MUHTEMEL MAĞDUR ═══

    has_gambling_anchor = any(kw in anchor for kw in GAMBLING_ANCHORS)

    if has_gambling_anchor and not any(kw in domain for kw in BET_DOMAIN_KEYWORDS):
        return "MAGDUR", "hacklenmis_site"

    # ═══ MEŞRU ═══

    if not is_spam and not has_gambling_anchor:
        return "ARAC", "mesru_backlink"

    # ═══ BELİRSİZ ═══
    return "BELIRSIZ", "gemini_ile_siniflandir"


def classify_all(backlinks: list[dict]) -> list[dict]:
    """Toplu sınıflandırma."""
    for bl in backlinks:
        category, detail = classify_backlink(bl)
        bl["category"] = category
        bl["category_detail"] = detail
    return backlinks
