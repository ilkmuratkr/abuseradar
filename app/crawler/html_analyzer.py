"""Raw HTML analizi - JS çalışmadan hacklink ve enjeksiyon tespiti."""

import base64
import logging
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Comment

logger = logging.getLogger(__name__)

HIDING_PATTERNS = [
    re.compile(r"display\s*:\s*none", re.I),
    re.compile(r"visibility\s*:\s*hidden", re.I),
    re.compile(r"opacity\s*:\s*0[^.]", re.I),
    re.compile(r"position\s*:\s*absolute.*left\s*:\s*-\d{4,}", re.I | re.S),
    re.compile(r"font-size\s*:\s*0", re.I),
    re.compile(r"height\s*:\s*0", re.I),
    re.compile(r"width\s*:\s*0", re.I),
    re.compile(r"text-indent\s*:\s*-\d{4,}", re.I),
]

GAMBLING_KEYWORDS = [
    "deneme bonusu", "bahis", "casino", "slot", "betting",
    "sahabet", "onwin", "jojobet", "grandpashabet", "escort",
]

C2_SIGNATURES = [
    "SponsorlinksHTML", "UReferenceLinks", "insertAdjacentHTML",
    "hacklinkbacklink", "backlinksatis", "scriptapi.dev",
    "js_api.php", "data-wpl",
]


def extract_hacklinks_from_html(raw_html: str, site_domain: str) -> list[dict]:
    """Raw HTML'den gizli hacklink'leri çıkar."""
    soup = BeautifulSoup(raw_html, "lxml")
    hacklinks = []

    # 1. Style attribute'ünde gizleme olan elementlerdeki linkler
    for el in soup.find_all(style=True):
        style = el.get("style", "")
        if any(p.search(style) for p in HIDING_PATTERNS):
            for a in el.find_all("a", href=True):
                href = a.get("href", "")
                if site_domain not in href and href.startswith("http"):
                    hacklinks.append({
                        "href": href,
                        "text": a.get_text(strip=True)[:200],
                        "method": "html_css_hidden",
                        "hiding_css": style[:200],
                        "found_in": "raw_html",
                    })

    # 2. <style> tag'larındaki gizleme kuralları ile eşleşen elementler
    for style_tag in soup.find_all("style"):
        css = style_tag.string or ""
        if any(sig.lower() in css.lower() for sig in C2_SIGNATURES[:3]):
            class_matches = re.findall(r"\.(\w+)\s*\{", css)
            for cls in class_matches:
                for el in soup.find_all(class_=cls):
                    for a in el.find_all("a", href=True):
                        if site_domain not in a["href"]:
                            hacklinks.append({
                                "href": a["href"],
                                "text": a.get_text(strip=True)[:200],
                                "method": "html_style_class",
                                "hiding_class": cls,
                                "found_in": "raw_html",
                            })

    # 3. HTML comment içindeki linkler
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        hrefs = re.findall(r'href=["\']?(https?://[^\s"\'<>]+)', str(comment))
        for href in hrefs:
            if any(kw in href.lower() for kw in GAMBLING_KEYWORDS):
                hacklinks.append({
                    "href": href,
                    "text": "",
                    "method": "html_comment",
                    "found_in": "raw_html",
                })

    # 4. data-wpl attribute'lü linkler
    for a in soup.find_all("a", attrs={"data-wpl": True}):
        hacklinks.append({
            "href": a.get("href", ""),
            "text": a.get_text(strip=True)[:200],
            "method": "data_wpl",
            "data_wpl": a["data-wpl"],
            "found_in": "raw_html",
        })

    return hacklinks


def extract_injection_scripts(raw_html: str) -> list[dict]:
    """HTML'den enjeksiyon yapan script kodlarını çıkar."""
    soup = BeautifulSoup(raw_html, "lxml")
    injections = []

    for script in soup.find_all("script", src=False):
        code = script.string or ""
        if not code.strip():
            continue

        matched = {sig: (sig in code) for sig in C2_SIGNATURES if sig in code}
        if not matched:
            continue

        # Base64 URL'leri decode et
        decoded_urls = []
        for b64 in re.findall(r'atob\(["\']([A-Za-z0-9+/=]+)["\']\)', code):
            try:
                decoded_urls.append(base64.b64decode(b64).decode("utf-8"))
            except Exception:
                pass

        injections.append({
            "code": code[:2000],
            "patterns": list(matched.keys()),
            "decoded_c2_urls": decoded_urls,
            "length": len(code),
        })

    # External C2 script'ler
    for script in soup.find_all("script", src=True):
        src = script["src"]
        if any(c2 in src for c2 in ["scriptapi.dev", "hacklinkbacklink", "backlinksatis"]):
            injections.append({
                "type": "external_c2_script",
                "src": src,
                "patterns": ["external_c2"],
            })

    return injections


def compare_raw_vs_rendered(raw_links: set[str], rendered_links: set[str], site_domain: str) -> list[dict]:
    """Raw'da olmayıp rendered'da olan linkler = JS ile enjekte edilmiş."""
    js_injected = rendered_links - raw_links
    suspicious = []

    safe_domains = {
        site_domain, "google.com", "facebook.com", "twitter.com",
        "youtube.com", "instagram.com", "cdnjs.cloudflare.com",
        "fonts.googleapis.com", "www.googletagmanager.com",
    }

    for href in js_injected:
        try:
            domain = urlparse(href).hostname or ""
        except Exception:
            continue
        if domain and domain not in safe_domains and not domain.endswith(f".{site_domain}"):
            suspicious.append({
                "href": href,
                "target_domain": domain,
                "method": "js_injection",
                "evidence": "raw HTML'de yok, rendered DOM'da var",
                "found_in": "js_diff",
            })

    return suspicious


