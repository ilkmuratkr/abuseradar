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


def _suffix_of(domain: str) -> str:
    """tldextract ile gerçek public suffix'i (örn. 'com.tr', 'co.uk') döndür.

    Domain'in sonuna eşleşen efektif TLD; substring eşleşmesi yapmaz.
    """
    if not domain:
        return ""
    raw = domain.strip().lower()
    if "://" in raw:
        try:
            raw = urlparse(raw).hostname or ""
        except Exception:
            raw = ""
    return _extract(raw).suffix or ""


def detect_country_from_domain(domain: str) -> str | None:
    """Domain'in public suffix'inden ülke kodu çıkar."""
    suffix = _suffix_of(domain)
    if not suffix:
        return None
    # Hem 'com.tr' gibi multi-part hem '.tr' gibi tek-part suffix'ler için
    # son segmenti ülke kodu olarak değerlendir.
    last = suffix.rsplit(".", 1)[-1]

    country_map = {
        "br": "BR", "pt": "PT", "mz": "MZ", "ao": "AO",
        "mx": "MX", "ar": "AR", "co": "CO", "cl": "CL",
        "pe": "PE", "ve": "VE", "ec": "EC",
        "tr": "TR",
        "th": "TH",
        "in": "IN",
        "ng": "NG",
        "lk": "LK",
        "fr": "FR", "sn": "SN", "ci": "CI",
        "de": "DE", "at": "AT",
        "uk": "GB", "au": "AU",
    }
    return country_map.get(last)


def detect_language_from_domain(domain: str) -> str:
    """Domain'in public suffix'inden dil çıkar (default 'en')."""
    suffix = _suffix_of(domain)
    if not suffix:
        return "en"
    last = suffix.rsplit(".", 1)[-1]

    lang_map = {
        "br": "pt", "pt": "pt", "mz": "pt", "ao": "pt",
        "mx": "es", "ar": "es", "co": "es", "cl": "es",
        "pe": "es", "ve": "es", "ec": "es", "es": "es",
        "tr": "tr",
        "fr": "fr", "sn": "fr", "ci": "fr",
        "de": "de", "at": "de",
        "it": "it",
        "ru": "ru",
        "cn": "zh",
    }
    return lang_map.get(last, "en")
