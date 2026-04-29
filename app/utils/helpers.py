"""Yardımcı fonksiyonlar."""

from urllib.parse import urlparse

import tldextract

# Public Suffix List'i container içinde cache'lemek için.
# TLDEXTRACT_CACHE env'i Dockerfile/compose tarafından /data/.tldextract-cache
# klasörüne işaret eder; PSL bir defa indirilip kalıcı volume'da kalır.
_extract = tldextract.TLDExtract(include_psl_private_domains=True)


def extract_domain(url: str) -> str:
    """URL'den FULL hostname (subdomain dahil) — geriye dönük uyumluluk."""
    try:
        parsed = urlparse(url if "://" in url else f"https://{url}")
        return (parsed.hostname or "").lower()
    except Exception:
        return ""


def extract_root_domain(url_or_host: str) -> str:
    """eTLD+1 — kök kayıt edilebilir domain.

    Örnekler:
      foo.bar.example.co.uk → example.co.uk
      mail.example.com.tr   → example.com.tr
      sub.example.de        → example.de
      example.de            → example.de
    """
    if not url_or_host:
        return ""
    raw = url_or_host.strip().lower()
    # urlparse hostname'e indir; sadece host verildiyse de çalışsın.
    if "://" in raw:
        try:
            host = urlparse(raw).hostname or ""
        except Exception:
            host = ""
    else:
        host = raw.split("/")[0].split("?")[0]
    if not host:
        return ""
    ext = _extract(host)
    if ext.domain and ext.suffix:
        return f"{ext.domain}.{ext.suffix}"
    # Suffix yoksa (intranet/IP) host'u olduğu gibi döndür.
    return host


def extract_subdomain(url_or_host: str) -> str:
    """Subdomain kısmı (boş olabilir).

    Örnekler:
      foo.bar.example.co.uk → 'foo.bar'
      www.example.com       → 'www'
      example.com           → ''
    """
    if not url_or_host:
        return ""
    raw = url_or_host.strip().lower()
    if "://" in raw:
        try:
            host = urlparse(raw).hostname or ""
        except Exception:
            host = ""
    else:
        host = raw.split("/")[0].split("?")[0]
    if not host:
        return ""
    return _extract(host).subdomain or ""


def is_subdomain_of(host: str, root: str) -> bool:
    """host, root'un alt alanı mı? (root kendisi de True döner)."""
    h = (host or "").lower().strip(".")
    r = (root or "").lower().strip(".")
    if not h or not r:
        return False
    return h == r or h.endswith("." + r)


def detect_country_from_domain(domain: str) -> str | None:
    """Domain TLD'sinden ülke kodu çıkar."""
    country_tlds = {
        ".br": "BR", ".pt": "PT", ".mz": "MZ", ".ao": "AO",
        ".mx": "MX", ".ar": "AR", ".co": "CO", ".cl": "CL",
        ".pe": "PE", ".ve": "VE", ".ec": "EC",
        ".tr": "TR",
        ".th": "TH",
        ".in": "IN",
        ".ng": "NG",
        ".lk": "LK",
        ".fr": "FR", ".sn": "SN", ".ci": "CI",
        ".de": "DE", ".at": "AT",
        ".uk": "GB", ".au": "AU",
    }
    for tld, country in country_tlds.items():
        if tld in domain:
            return country
    return None


def detect_language_from_domain(domain: str) -> str:
    """Domain TLD'sinden dil çıkar."""
    lang_tlds = {
        ".br": "pt", ".pt": "pt", ".mz": "pt", ".ao": "pt",
        ".mx": "es", ".ar": "es", ".co": "es", ".cl": "es",
        ".pe": "es", ".ve": "es", ".ec": "es",
        ".tr": "tr",
        ".fr": "fr", ".sn": "fr", ".ci": "fr",
    }
    for tld, lang in lang_tlds.items():
        if tld in domain:
            return lang
    return "en"
