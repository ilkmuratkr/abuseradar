"""Email provider tespiti — MX lookup ile gerçek mail sağlayıcısını bul.

Bir kurumsal mail (info@ulm.edu.pk) MX kaydıyla aslında Google Workspace'e
yönelmiş olabilir; bu durumda Gmail bulk sender requirements geçerli olur.
Provider-bazlı günlük limit için bu tespiti yaparız.
"""

import asyncio
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)


# Provider tespiti için MX hostname pattern'leri.
# Her pattern lower-case substring eşleşmesi ile aranır.
PROVIDER_PATTERNS = {
    "gmail": [
        "google.com",
        "googlemail.com",
        "aspmx.l.google.com",
        "aspmx.googlemail.com",
        "gmail-smtp-in",
    ],
    "microsoft": [
        "outlook.com",
        "protection.outlook.com",
        "mail.protection.outlook.com",
        "office365.com",
        "exchange.com",
    ],
    "yahoo": [
        "yahoodns.net",
        "yahoo.com",
        "yahoomail.com",
        "am0.yahoodns",
    ],
    "zoho": [
        "zoho.com",
        "zohomail.com",
        "zohomx.com",
    ],
    "fastmail": [
        "messagingengine.com",
        "fastmail.com",
        "fastmail.fm",
    ],
    "protonmail": [
        "protonmail.ch",
        "proton.me",
        "protonmail.com",
    ],
    "apple": [
        "icloud.com",
        "mail.icloud.com",
    ],
}


@lru_cache(maxsize=4096)
def _resolve_mx_sync(domain: str) -> tuple[str, ...]:
    """MX kayıtlarını çözer (cache'li). Hata olursa boş tuple döndürür."""
    try:
        import dns.resolver  # dnspython
        answers = dns.resolver.resolve(domain, "MX", lifetime=5.0)
        return tuple(str(r.exchange).rstrip(".").lower() for r in answers)
    except Exception as e:
        logger.debug(f"MX lookup failed for {domain}: {e}")
        return tuple()


async def detect_email_provider(email: str) -> str:
    """Email adresinin gerçek mail sağlayıcısını tespit et.

    Returns:
        'gmail' | 'microsoft' | 'yahoo' | 'zoho' | 'fastmail' |
        'protonmail' | 'apple' | 'other' | 'unknown'
    """
    if not email or "@" not in email:
        return "unknown"
    domain = email.split("@", 1)[1].strip().lower()
    if not domain:
        return "unknown"

    # Bilindik consumer domain'leri shortcut
    if domain in {"gmail.com", "googlemail.com"}:
        return "gmail"
    if domain in {"outlook.com", "hotmail.com", "live.com", "msn.com", "outlook.com.tr"}:
        return "microsoft"
    if domain in {"yahoo.com", "ymail.com", "rocketmail.com"}:
        return "yahoo"
    if domain in {"icloud.com", "me.com", "mac.com"}:
        return "apple"
    if domain in {"protonmail.com", "proton.me", "pm.me"}:
        return "protonmail"
    if domain in {"zoho.com", "zoho.eu", "zohomail.com"}:
        return "zoho"

    # Kurumsal domain — MX lookup gerekli (sync resolver event loop'u bloklamasın)
    loop = asyncio.get_event_loop()
    mx_hosts = await loop.run_in_executor(None, _resolve_mx_sync, domain)

    if not mx_hosts:
        return "unknown"

    for provider, patterns in PROVIDER_PATTERNS.items():
        for mx in mx_hosts:
            for pat in patterns:
                if pat in mx:
                    return provider

    return "other"


# Provider-bazlı günlük limit (warm-up Hafta 1)
# Gmail en sıkı, Outlook orta, diğerleri esnek.
PROVIDER_DAILY_LIMITS = {
    "gmail": 10,       # Hafta 1; sonra 25, 50, 100
    "microsoft": 30,   # Microsoft 365 daha esnek
    "yahoo": 20,
    "zoho": 30,
    "fastmail": 30,
    "protonmail": 30,
    "apple": 30,
    "other": 50,       # kurumsal, kendi MX'i — daha esnek
    "unknown": 20,     # MX bulunamadı, ihtiyatlı
}


def daily_limit_for(provider: str) -> int:
    """Provider için bugünkü gönderim limiti."""
    return PROVIDER_DAILY_LIMITS.get(provider, 20)
