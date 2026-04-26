"""Site sahibi iletişim bilgisi bulma - çoklu kaynak."""

import logging
import re
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from config import settings

logger = logging.getLogger(__name__)

EMAIL_REGEX = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)

CONTACT_PATHS = [
    "/contact", "/contact-us", "/contato", "/contacto",
    "/about", "/about-us", "/sobre", "/acerca",
    "/impressum", "/kontakt",
]

SKIP_EMAILS = {
    "example.com", "example.org", "test.com", "sentry.io",
    "gravatar.com", "wordpress.org", "w3.org", "schema.org",
    "wixpress.com", "googleapis.com",
}


def _is_valid_email(email: str) -> bool:
    """Geçerli ve kullanılabilir email mi?"""
    if not email or "@" not in email:
        return False
    domain = email.split("@")[1].lower()
    if domain in SKIP_EMAILS:
        return False
    if any(domain.endswith(f".{skip}") for skip in SKIP_EMAILS):
        return False
    if email.startswith("noreply") or email.startswith("no-reply"):
        return False
    return True


def _classify_email(email: str) -> str:
    """Email adresinin tipini belirle."""
    local = email.split("@")[0].lower()
    if local in ("abuse", "security", "cert"):
        return "security"
    if local in ("webmaster", "admin", "administrator", "root", "sysadmin"):
        return "admin"
    if local in ("info", "contact", "contato", "contacto"):
        return "general"
    if local in ("postmaster",):
        return "postmaster"
    return "other"


async def find_emails_from_site(url: str, domain: str) -> list[dict]:
    """Sitenin sayfalarından email adresleri çıkar."""
    found_emails = []
    seen = set()

    async with httpx.AsyncClient(
        timeout=15,
        follow_redirects=True,
        headers={"User-Agent": settings.crawl_user_agent},
    ) as client:
        # Ana sayfa + iletişim sayfaları
        urls_to_check = [url]
        for path in CONTACT_PATHS:
            urls_to_check.append(urljoin(url, path))

        for check_url in urls_to_check:
            try:
                resp = await client.get(check_url)
                if resp.status_code != 200:
                    continue

                emails = EMAIL_REGEX.findall(resp.text)
                for email in emails:
                    email = email.lower().strip()
                    if email not in seen and _is_valid_email(email):
                        seen.add(email)
                        found_emails.append({
                            "email": email,
                            "source": "site_crawl",
                            "contact_type": _classify_email(email),
                            "found_at": check_url,
                        })
            except Exception:
                continue

    logger.info(f"[{domain}] Site crawl: {len(found_emails)} email bulundu")
    return found_emails


async def find_security_txt(domain: str) -> dict | None:
    """RFC 9116 security.txt dosyasından iletişim bilgisi al."""
    urls = [
        f"https://{domain}/.well-known/security.txt",
        f"https://{domain}/security.txt",
    ]

    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        for url in urls:
            try:
                resp = await client.get(url)
                if resp.status_code == 200 and "Contact:" in resp.text:
                    for line in resp.text.split("\n"):
                        line = line.strip()
                        if line.startswith("Contact:"):
                            contact = line.split(":", 1)[1].strip()
                            if "@" in contact:
                                logger.info(f"[{domain}] security.txt: {contact}")
                                return {
                                    "email": contact.lower(),
                                    "source": "security_txt",
                                    "contact_type": "security",
                                }
                            elif contact.startswith("http"):
                                return {
                                    "url": contact,
                                    "source": "security_txt",
                                    "contact_type": "security",
                                }
            except Exception:
                continue
    return None


async def find_whois_contacts(domain: str) -> list[dict]:
    """WHOIS/RDAP'dan abuse iletişim bilgisi al."""
    contacts = []
    try:
        import whois
        w = whois.whois(domain)

        # Registrar abuse email
        abuse = None
        if hasattr(w, "registrar_abuse_contact_email"):
            abuse = w.registrar_abuse_contact_email
        if not abuse and hasattr(w, "emails"):
            emails = w.emails if isinstance(w.emails, list) else [w.emails]
            for e in emails:
                if e and "abuse" in e.lower():
                    abuse = e
                    break

        if abuse and _is_valid_email(abuse):
            contacts.append({
                "email": abuse.lower(),
                "source": "whois",
                "contact_type": "abuse",
            })

        # Registrant/admin email
        for attr in ("registrant_email", "admin_email", "tech_email"):
            val = getattr(w, attr, None)
            if val and _is_valid_email(val) and val.lower() not in {c["email"] for c in contacts}:
                contacts.append({
                    "email": val.lower(),
                    "source": "whois",
                    "contact_type": attr.replace("_email", ""),
                })

    except Exception as e:
        logger.debug(f"[{domain}] WHOIS hatası: {e}")

    logger.info(f"[{domain}] WHOIS: {len(contacts)} iletişim bulundu")
    return contacts


async def find_all_contacts(url: str, domain: str) -> list[dict]:
    """Tüm kaynaklardan iletişim bilgisi topla."""
    all_contacts = []
    seen_emails = set()

    # 1. security.txt (en güvenilir)
    sec_txt = await find_security_txt(domain)
    if sec_txt and sec_txt.get("email"):
        all_contacts.append(sec_txt)
        seen_emails.add(sec_txt["email"])

    # 2. WHOIS abuse email
    whois_contacts = await find_whois_contacts(domain)
    for c in whois_contacts:
        if c["email"] not in seen_emails:
            all_contacts.append(c)
            seen_emails.add(c["email"])

    # 3. Site crawl
    site_emails = await find_emails_from_site(url, domain)
    for c in site_emails:
        if c["email"] not in seen_emails:
            all_contacts.append(c)
            seen_emails.add(c["email"])

    # Öncelik sıralaması: security > abuse > admin > general > other
    priority = {"security": 0, "abuse": 1, "admin": 2, "general": 3, "postmaster": 4, "other": 5}
    all_contacts.sort(key=lambda c: priority.get(c.get("contact_type", "other"), 9))

    logger.info(f"[{domain}] Toplam {len(all_contacts)} iletişim bulundu")
    return all_contacts
