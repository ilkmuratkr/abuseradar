"""Hosting provider abuse - magdur site CF'de degilse hosting'e sikayet.

Akis:
  1. Domain → IP cozumle
  2. IP → WHOIS → hosting provider + abuse email bul
  3. CF arkasinda mi kontrol et
  4. Abuse email'e rapor gonder
"""

import logging
import socket

import httpx

logger = logging.getLogger(__name__)


async def resolve_ip(domain: str) -> str | None:
    """Domain'in IP adresini cozumle."""
    try:
        ip = socket.gethostbyname(domain)
        return ip
    except socket.gaierror:
        return None


async def is_behind_cloudflare(domain: str) -> bool:
    """Domain Cloudflare arkasinda mi?"""
    try:
        ip = await resolve_ip(domain)
        if not ip:
            return False

        # Cloudflare IP araliklari (basit kontrol)
        cf_ranges = [
            "104.16.", "104.17.", "104.18.", "104.19.", "104.20.",
            "104.21.", "104.22.", "104.23.", "104.24.", "104.25.",
            "172.64.", "172.65.", "172.66.", "172.67.",
            "162.158.", "198.41.",
        ]
        if any(ip.startswith(r) for r in cf_ranges):
            return True

        # Header kontrolu
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.head(f"https://{domain}/")
            server = resp.headers.get("server", "").lower()
            if "cloudflare" in server:
                return True
            if resp.headers.get("cf-ray"):
                return True

    except Exception:
        pass

    return False


async def get_hosting_info(domain: str) -> dict:
    """Domain'in hosting bilgisini bul: IP, provider, abuse email."""
    result = {
        "domain": domain,
        "ip": None,
        "is_cloudflare": False,
        "hosting_provider": None,
        "abuse_email": None,
        "asn": None,
    }

    # 1. IP cozumle
    ip = await resolve_ip(domain)
    if not ip:
        return result
    result["ip"] = ip

    # 2. CF kontrolu
    result["is_cloudflare"] = await is_behind_cloudflare(domain)

    # 3. IP WHOIS - hosting provider ve abuse email
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # ipinfo.io ile hizli lookup
            resp = await client.get(f"https://ipinfo.io/{ip}/json")
            if resp.status_code == 200:
                data = resp.json()
                result["hosting_provider"] = data.get("org", "")
                result["asn"] = data.get("org", "").split(" ")[0] if data.get("org") else None
    except Exception as e:
        logger.debug(f"[{domain}] IP info hatasi: {e}")

    # 4. abuse_finder ile abuse email bul
    try:
        from abuse_finder import ip_abuse
        abuse_info = ip_abuse(ip)
        abuse_emails = abuse_info.get("abuse", [])
        if abuse_emails:
            result["abuse_email"] = abuse_emails[0]
    except ImportError:
        # abuse_finder yoksa WHOIS'ten dene
        try:
            import whois
            w = whois.whois(domain)
            if hasattr(w, "registrar_abuse_contact_email") and w.registrar_abuse_contact_email:
                result["abuse_email"] = w.registrar_abuse_contact_email
        except Exception:
            pass
    except Exception as e:
        logger.debug(f"[{domain}] Abuse finder hatasi: {e}")

    return result


async def report_to_hosting(
    domain: str,
    abuse_email: str,
    issue_type: str,
    evidence_summary: str,
) -> dict:
    """Hosting provider'a abuse raporu gonder.

    Args:
        domain: Hacklenmiş/ele geçirilmiş domain
        abuse_email: Hosting provider'ın abuse email'i
        issue_type: "injection" veya "takeover"
        evidence_summary: Kanıt özeti
    """
    from notifier.sender import send_alert
    from config import settings

    if issue_type == "takeover":
        subject = f"Abuse Report: Domain {domain} - unauthorized use for illegal gambling"
        body = f"""Dear Abuse Team,

We are reporting that the domain {domain}, hosted on your infrastructure,
has been compromised and is being used for illegal online gambling operations.

Type: Domain takeover / unauthorized content
Domain: {domain}
Issue: The domain appears to have been taken over and is now serving
illegal gambling content instead of its legitimate purpose.

{evidence_summary}

This domain was previously a legitimate government/educational website.
We request immediate investigation and suspension of the malicious content.

Best regards,
AbuseRadar Research Team
"""
    else:
        subject = f"Abuse Report: {domain} - malicious code injection detected"
        body = f"""Dear Abuse Team,

We are reporting that a website hosted on your infrastructure has been
compromised with malicious code injection.

Domain: {domain}
Issue: Hidden gambling/casino backlinks have been injected into the
website's source code without the site owner's knowledge.

{evidence_summary}

We request that you notify the site owner and assist with remediation.

Best regards,
AbuseRadar Research Team
"""

    try:
        from notifier.sender import _zeptomail_send

        result = await _zeptomail_send(
            to_email=abuse_email,
            to_name=None,
            subject=subject,
            text_body=body,
        )
        if result.get("status") == "simulated":
            logger.warning(f"[{domain}] ZeptoMail token yok, simule ediliyor")
            return {"status": "simulated", "to": abuse_email, "subject": subject}
        logger.info(f"[{domain}] Hosting abuse raporu gonderildi → {abuse_email}")
        return {"status": "sent", "to": abuse_email, "message_id": result.get("id")}
    except Exception as e:
        logger.error(f"[{domain}] Hosting abuse raporu hatasi: {e}")
        return {"status": "error", "reason": str(e)}


async def get_complaint_targets(domain: str) -> dict:
    """Bir magdur site icin tum sikayet hedeflerini bul.

    Returns:
        {
            "site_owner": [email listesi],
            "hosting": {"provider", "abuse_email", "ip"},
            "cloudflare": True/False (CF'ye de sikayet gerekli mi),
            "registrar": {"name", "abuse_email"},
            "cert": {"name", "email"} veya None,
        }
    """
    hosting = await get_hosting_info(domain)

    targets = {
        "domain": domain,
        "hosting": {
            "provider": hosting["hosting_provider"],
            "abuse_email": hosting["abuse_email"],
            "ip": hosting["ip"],
        },
        "is_cloudflare": hosting["is_cloudflare"],
        "complaint_to": [],
    }

    # Nereye sikayet edilecek?
    if hosting["abuse_email"]:
        targets["complaint_to"].append(f"Hosting: {hosting['abuse_email']}")

    if hosting["is_cloudflare"]:
        targets["complaint_to"].append("Cloudflare: abuse.cloudflare.com")

    # WHOIS registrar
    try:
        import whois
        w = whois.whois(domain)
        targets["registrar"] = {
            "name": getattr(w, "registrar", None),
            "abuse_email": getattr(w, "registrar_abuse_contact_email", None),
        }
        if targets["registrar"]["abuse_email"]:
            targets["complaint_to"].append(f"Registrar: {targets['registrar']['abuse_email']}")
    except Exception:
        targets["registrar"] = None

    # CERT (gov/edu icin)
    from contacts.cert_directory import get_cert_for_domain
    cert = get_cert_for_domain(domain)
    if cert:
        targets["cert"] = cert
        targets["complaint_to"].append(f"CERT: {cert['email']}")

    return targets
