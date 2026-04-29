"""Site sahibi iletişim bilgisi bulma - çoklu kaynak.

Subdomain hacklenmiş olsa bile, kök domain'den (eTLD+1) iletişim bilgisi
toplayabilmek için her iki seviyede de tarama yaparız:

  hacklenen host:   foo.bar.example.co.uk   (subdomain hacklenmiş)
  kök kayıtlı:      example.co.uk           (WHOIS + iletişim sayfaları burada)

WHOIS yalnızca kök domain üzerinden çalışır. security.txt ve site crawl
hem subdomain hem kök domain üzerinden denenir; bulunan email kaydında
`source` alanına hangi seviyeden geldiği yazılır (site_crawl_sub /
site_crawl_root / security_txt_sub / security_txt_root).
"""

import logging
import re
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from config import settings
from utils.helpers import extract_root_domain, is_subdomain_of

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


def _email_relevance(email: str, victim_root: str) -> int:
    """Email domain'i kurban kök domain ile ne kadar alakalı?

    3 → tam aynı kök (best — info@example.de, victim=example.de)
    2 → aynı kök'ün subdomain'i (mail.example.de gibi)
    1 → farklı domain (gmail.com, hotmail.com — third-party hosted)
    0 → SKIP_EMAILS (zaten _is_valid_email filtreler)
    """
    if not email or "@" not in email or not victim_root:
        return 1
    edom = email.split("@")[1].lower()
    eroot = extract_root_domain(edom)
    if eroot == victim_root:
        return 3 if edom == victim_root else 2
    return 1


async def _fetch_emails_from_url(client: httpx.AsyncClient, url: str) -> set[str]:
    """Tek URL'den email setini çek — text + mailto: linkleri."""
    found: set[str] = set()
    try:
        resp = await client.get(url)
        if resp.status_code != 200:
            return found
        # Düz metin regex
        for e in EMAIL_REGEX.findall(resp.text):
            found.add(e.lower().strip())
        # mailto: linkleri (BS4 ile sadece anchor href)
        try:
            soup = BeautifulSoup(resp.text, "lxml")
            for a in soup.select("a[href^='mailto:']"):
                href = a.get("href", "")
                addr = href.split(":", 1)[1].split("?")[0].strip().lower()
                if addr:
                    found.add(addr)
        except Exception:
            pass
    except Exception:
        return found
    return found


async def find_emails_from_site(url: str, host: str, source_label: str) -> list[dict]:
    """Bir host (subdomain veya kök) için anasayfa + iletişim sayfalarından email çıkar."""
    found_emails: list[dict] = []
    seen: set[str] = set()

    base_url = url if url else f"https://{host}/"

    async with httpx.AsyncClient(
        timeout=15,
        follow_redirects=True,
        headers={"User-Agent": settings.crawl_user_agent},
    ) as client:
        urls_to_check = [base_url, f"https://{host}/"]
        for path in CONTACT_PATHS:
            urls_to_check.append(urljoin(f"https://{host}/", path))

        for check_url in urls_to_check:
            emails = await _fetch_emails_from_url(client, check_url)
            for email in emails:
                if email in seen or not _is_valid_email(email):
                    continue
                seen.add(email)
                found_emails.append({
                    "email": email,
                    "source": source_label,
                    "contact_type": _classify_email(email),
                    "found_at": check_url,
                })

    logger.info(f"[{host}] {source_label}: {len(found_emails)} email bulundu")
    return found_emails


async def find_security_txt(host: str, source_label: str) -> dict | None:
    """RFC 9116 security.txt — verilen host (sub veya kök) üzerinde dene."""
    urls = [
        f"https://{host}/.well-known/security.txt",
        f"https://{host}/security.txt",
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
                                logger.info(f"[{host}] security.txt: {contact}")
                                return {
                                    "email": contact.lower(),
                                    "source": source_label,
                                    "contact_type": "security",
                                }
            except Exception:
                continue
    return None


async def find_whois_contacts(root_domain: str) -> list[dict]:
    """WHOIS/RDAP — yalnızca kök domain (subdomain'de WHOIS yok)."""
    contacts = []
    try:
        import whois
        w = whois.whois(root_domain)

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

        for attr in ("registrant_email", "admin_email", "tech_email"):
            val = getattr(w, attr, None)
            if val and _is_valid_email(val) and val.lower() not in {c["email"] for c in contacts}:
                contacts.append({
                    "email": val.lower(),
                    "source": "whois",
                    "contact_type": attr.replace("_email", ""),
                })

    except Exception as e:
        logger.debug(f"[{root_domain}] WHOIS hatası: {e}")

    logger.info(f"[{root_domain}] WHOIS: {len(contacts)} iletişim bulundu")
    return contacts


async def find_all_contacts(url: str, host: str) -> list[dict]:
    """Tüm kaynaklardan iletişim bilgisi topla.

    host: hacklenen tam hostname (subdomain dahil olabilir)
    Otomatik olarak eTLD+1 (kök) çıkarılır; kök != sub ise her ikisi taranır.
    """
    all_contacts: list[dict] = []
    seen_emails: set[str] = set()

    host = (host or "").lower().strip()
    root = extract_root_domain(host)
    sub_is_distinct = root and host and host != root and is_subdomain_of(host, root)

    # 1. security.txt — subdomain (varsa) + kök
    if sub_is_distinct:
        sec_sub = await find_security_txt(host, "security_txt_sub")
        if sec_sub and sec_sub.get("email") and sec_sub["email"] not in seen_emails:
            all_contacts.append(sec_sub)
            seen_emails.add(sec_sub["email"])
    if root:
        sec_root = await find_security_txt(root, "security_txt_root")
        if sec_root and sec_root.get("email") and sec_root["email"] not in seen_emails:
            all_contacts.append(sec_root)
            seen_emails.add(sec_root["email"])

    # 2. WHOIS — yalnızca kök
    if root:
        for c in await find_whois_contacts(root):
            if c["email"] not in seen_emails:
                all_contacts.append(c)
                seen_emails.add(c["email"])

    # 3. Site crawl — subdomain (hacklenen) + kök ana site
    if sub_is_distinct:
        for c in await find_emails_from_site(url, host, "site_crawl_sub"):
            if c["email"] not in seen_emails:
                all_contacts.append(c)
                seen_emails.add(c["email"])
    if root:
        for c in await find_emails_from_site(f"https://{root}/", root, "site_crawl_root"):
            if c["email"] not in seen_emails:
                all_contacts.append(c)
                seen_emails.add(c["email"])

    # Önce alaka düzeyi (kurban domain'iyle uyum), sonra contact_type önceliği.
    type_priority = {"security": 0, "abuse": 1, "admin": 2, "general": 3, "postmaster": 4, "other": 5}
    for c in all_contacts:
        c["_relevance"] = _email_relevance(c["email"], root)
    all_contacts.sort(
        key=lambda c: (
            -c.get("_relevance", 1),
            type_priority.get(c.get("contact_type", "other"), 9),
        )
    )
    for c in all_contacts:
        c.pop("_relevance", None)

    logger.info(f"[{host}] Toplam {len(all_contacts)} iletişim bulundu (root={root})")
    return all_contacts
