"""Yardımcı fonksiyonlar."""

from urllib.parse import urlparse


def extract_domain(url: str) -> str:
    """URL'den domain çıkar."""
    try:
        parsed = urlparse(url if "://" in url else f"https://{url}")
        return parsed.hostname or ""
    except Exception:
        return ""


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
