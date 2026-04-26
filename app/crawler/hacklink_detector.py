"""6 kural ile hacklink tespiti - Playwright DOM analizi."""

import logging
import re
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

GAMBLING_KEYWORDS = [
    "deneme bonusu", "bahis", "casino", "slot ", "betting",
    "grandpashabet", "sahabet", "onwin", "jojobet", "perabet",
    "1xbet", "1win", "betgaranti", "cratosroyalbet", "superbet",
    "spinco", "betwoon", "radissonbet", "damabet", "ritzbet",
    "exonbet", "ramadabet", "royalbet", "leogrand", "slotday",
    "palazzobet", "escort", "porno",
    "สล็อต", "บาคาร่า", "토토사이트", "먹튀검증",
]

SUSPICIOUS_CLASSES = [
    "ureferencelinks", "sponsorlinks", "hidden-links",
    "sponsor-links", "seo-links", "hack-links",
]

# Playwright'ta çalışacak JS kodu
EXTRACT_ALL_LINKS_JS = """() => {
    const links = [];
    document.querySelectorAll('a[href]').forEach(a => {
        const cs = window.getComputedStyle(a);
        const ps = a.parentElement ? window.getComputedStyle(a.parentElement) : {};
        const gs = a.parentElement?.parentElement ? window.getComputedStyle(a.parentElement.parentElement) : {};
        const rect = a.getBoundingClientRect();

        links.push({
            href: a.href,
            text: (a.textContent || '').trim().substring(0, 300),
            title: a.title || '',
            // Kendi stilleri
            display: cs.display,
            visibility: cs.visibility,
            opacity: cs.opacity,
            position: cs.position,
            left: cs.left,
            top: cs.top,
            fontSize: cs.fontSize,
            height: cs.height,
            width: cs.width,
            pointerEvents: cs.pointerEvents,
            overflow: cs.overflow,
            // Parent stilleri
            pDisplay: ps.display || '',
            pVisibility: ps.visibility || '',
            pOpacity: ps.opacity || '',
            pPosition: ps.position || '',
            pLeft: ps.left || '',
            pHeight: ps.height || '',
            // Grandparent
            gDisplay: gs.display || '',
            gOpacity: gs.opacity || '',
            // Attribute'ler
            dataWpl: a.getAttribute('data-wpl') || '',
            style: a.getAttribute('style') || '',
            pClass: (a.parentElement?.className || '').substring(0, 200),
            gClass: (a.parentElement?.parentElement?.className || '').substring(0, 200),
            pTag: a.parentElement?.tagName || '',
            // Konum
            rx: rect.x, ry: rect.y, rw: rect.width, rh: rect.height,
        });
    });
    return links;
}"""


def _px(val: str) -> float | None:
    """CSS pixel değerini sayıya çevir."""
    if not val:
        return None
    try:
        return float(val.replace("px", "").replace("pt", "").replace("em", "").strip())
    except (ValueError, AttributeError):
        return None


def score_link(link: dict, site_domain: str, known_spam_domains: set | None = None) -> tuple[int, list[str]]:
    """Tek bir link için hacklink skoru hesapla.

    Returns:
        (score, reasons)
    """
    score = 0
    reasons = []

    # ═══ KURAL 1: CSS GİZLEME ═══
    # Kendisi
    if link.get("opacity") == "0":
        score += 40; reasons.append("opacity:0")
    if link.get("display") == "none":
        score += 40; reasons.append("display:none")
    if link.get("visibility") == "hidden":
        score += 40; reasons.append("visibility:hidden")
    left = _px(link.get("left"))
    if left is not None and left < -9000:
        score += 40; reasons.append(f"left:{link['left']}")
    if link.get("fontSize") == "0px":
        score += 30; reasons.append("font-size:0")
    h, w = _px(link.get("height")), _px(link.get("width"))
    if h == 0 and w == 0:
        score += 30; reasons.append("0x0 boyut")
    if link.get("pointerEvents") == "none":
        score += 20; reasons.append("pointer-events:none")

    # Parent
    if link.get("pOpacity") == "0":
        score += 35; reasons.append("parent opacity:0")
    if link.get("pDisplay") == "none":
        score += 35; reasons.append("parent display:none")
    p_left = _px(link.get("pLeft"))
    if p_left is not None and p_left < -9000:
        score += 35; reasons.append(f"parent left:{link['pLeft']}")
    if _px(link.get("pHeight")) == 0:
        score += 25; reasons.append("parent height:0")

    # Grandparent
    if link.get("gOpacity") == "0":
        score += 30; reasons.append("grandparent opacity:0")
    if link.get("gDisplay") == "none":
        score += 30; reasons.append("grandparent display:none")

    # ═══ KURAL 2: ANCHOR TEXT ═══
    link_text = (link.get("text", "") + " " + link.get("title", "")).lower()
    matched = [kw for kw in GAMBLING_KEYWORDS if kw in link_text]
    if matched:
        score += 50; reasons.append(f"gambling keyword: {matched[:3]}")

    # ═══ KURAL 3: BİLİNEN SPAM DOMAİN ═══
    try:
        link_domain = urlparse(link.get("href", "")).hostname or ""
    except Exception:
        link_domain = ""

    if known_spam_domains and link_domain in known_spam_domains:
        score += 60; reasons.append(f"known spam: {link_domain}")

    # ═══ KURAL 4: İNJECTION ATTRIBUTE ═══
    if link.get("dataWpl") == "Reference":
        score += 70; reasons.append("data-wpl=Reference")

    parent_class = (link.get("pClass", "") + " " + link.get("gClass", "")).lower()
    if any(cls in parent_class for cls in SUSPICIOUS_CLASSES):
        score += 50; reasons.append(f"suspicious class: {parent_class[:60]}")

    # ═══ KURAL 5: DİL UYUMSUZLUĞU ═══
    # Basit heuristik: Türkçe/Tayland/Kore anchor text İngilizce/Portekizce sitede
    tr_chars = set("çğıöşüÇĞİÖŞÜ")
    thai_range = any("\u0e00" <= c <= "\u0e7f" for c in link_text)
    korean_range = any("\uac00" <= c <= "\ud7af" for c in link_text)
    if (tr_chars & set(link_text)) or thai_range or korean_range:
        if site_domain and not any(tld in site_domain for tld in [".tr", ".th", ".kr"]):
            score += 30; reasons.append("dil uyumsuzluğu")

    # ═══ KURAL 6: EKRAN DIŞI ═══
    rx, ry = link.get("rx", 0), link.get("ry", 0)
    if isinstance(rx, (int, float)) and rx < -1000:
        score += 30; reasons.append(f"ekran dışı x={rx}")
    if isinstance(ry, (int, float)) and ry < -1000:
        score += 30; reasons.append(f"ekran dışı y={ry}")
    rw, rh = link.get("rw", 1), link.get("rh", 1)
    if rw == 0 and rh == 0:
        score += 20; reasons.append("0 boyutlu rect")

    return min(score, 100), reasons


def analyze_links(all_links: list[dict], site_domain: str, known_spam_domains: set | None = None) -> dict:
    """Tüm linkleri analiz edip hacklink'leri ayıkla."""
    hacklinks = []
    legitimate_count = 0

    for link in all_links:
        score, reasons = score_link(link, site_domain, known_spam_domains)
        if score >= 40:
            try:
                target_domain = urlparse(link.get("href", "")).hostname or ""
            except Exception:
                target_domain = ""
            hacklinks.append({
                "href": link.get("href", ""),
                "text": link.get("text", ""),
                "target_domain": target_domain,
                "score": score,
                "reasons": reasons,
                "hiding_method": _detect_hiding(link),
                "parent_class": link.get("pClass", ""),
                "data_wpl": link.get("dataWpl", ""),
                "found_in": "rendered_dom",
            })
        else:
            legitimate_count += 1

    return {
        "hacklinks": hacklinks,
        "hacklink_count": len(hacklinks),
        "legitimate_count": legitimate_count,
        "total_links": len(all_links),
    }


def _detect_hiding(link: dict) -> str:
    """Gizleme yöntemini belirle."""
    methods = []
    if link.get("opacity") == "0" or link.get("pOpacity") == "0":
        methods.append("opacity:0")
    if link.get("display") == "none" or link.get("pDisplay") == "none":
        methods.append("display:none")
    if link.get("visibility") == "hidden":
        methods.append("visibility:hidden")
    left = _px(link.get("left"))
    p_left = _px(link.get("pLeft"))
    if (left and left < -9000) or (p_left and p_left < -9000):
        methods.append("offscreen")
    if link.get("fontSize") == "0px":
        methods.append("font-size:0")
    return ", ".join(methods) if methods else "visible_spam"
