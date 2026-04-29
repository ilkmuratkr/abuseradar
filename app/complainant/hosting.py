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
    report_url: str = "",
) -> dict:
    """Hosting provider'in abuse adresine pasif tonlu rapor gonder.

    Mail tonu: data observatory, sansasyonel dil yok ('illegal' yerine
    'policy-violating'), 'immediate' yerine 'investigation requested'.

    Args:
        domain: Hacklenmiş ya da saldırgan domain
        abuse_email: Hosting/IP block abuse contact
        issue_type: "injection" (kurban) veya "takeover" (saldırgan)
        evidence_summary: Kısa kanıt özeti
        report_url: Public report linki (varsa eklenir)
    """
    from notifier.sender import _zeptomail_send

    if issue_type == "takeover":
        subject = f"AbuseRadar notice: {domain} — possible policy violation"
        body = f"""Hello,

A short note from AbuseRadar, an independent web-data observatory.

In our recent index of public pages, the domain {domain} hosted on your
infrastructure surfaces patterns associated with off-topic, policy-violating
third-party content (typical SEO-spam infrastructure).

{evidence_summary}

This pattern is part of a long-running, publicly documented SEO-spam
injection campaign tracked since January 2025 by independent researchers:

  - cside Research (original disclosure):
    https://cside.com/blog/government-and-university-websites-targeted-in-scriptapi-dev-client-side-attack
  - Cyber Security News: https://cybersecuritynews.com/javascript-attacks-targeting/
  - Joe Sandbox automated analysis: https://www.joesandbox.com/analysis/1684428/0/html
  - PublicWWW live footprint: https://publicwww.com/websites/scriptapi.dev/

The operators rotate payload hostnames and increasingly host destination
domains behind major providers — per-domain takedowns alone are insufficient.

This is forwarded to your abuse channel for review under your acceptable-use
policy. We are not requesting any specific action — only that the case is
visible to your team.
{('Full technical bundle (no sign-in): ' + report_url) if report_url else ''}

Reply to abuse@abuseradar.org if a follow-up is useful.

— AbuseRadar Research
abuseradar.org
"""
    else:
        subject = f"AbuseRadar notice: {domain} — third-party content observed"
        body = f"""Hello,

A short note from AbuseRadar, an independent web-data observatory.

In our recent index of public pages, the website {domain} hosted on your
infrastructure surfaces third-party links that do not fit the site's normal
content profile. Patterns like this commonly originate from a CMS plugin or
template file altered outside the site's usual editorial flow.

{evidence_summary}

This is forwarded to your abuse channel so the site owner can be notified
and assisted with remediation.
{('Full technical bundle (no sign-in): ' + report_url) if report_url else ''}

This is an automated, one-off notice. Reply to abuse@abuseradar.org if a
follow-up is useful.

— AbuseRadar Research
abuseradar.org
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


async def report_to_victim_hosting(
    *,
    domain: str,
    abuse_email: str,
    hosting_provider: str = "",
    ip: str = "",
    asn: str = "",
    report_url: str,
    hacklink_count: int = 0,
    first_seen: str = "",
    site_owner_notified: bool = True,
    site_id: int | None = None,
) -> dict:
    """Mağdur sitenin hosting sağlayıcısına profesyonel bilgilendirme maili.

    Saldırgan domain'in hosting'inden FARKLI bir akış: burada hedef, mağdurun
    yanlışlıkla sahibi/teknik sorumlusu olduğu hosting hesabıdır. Sağlayıcının
    AUP'u (acceptable use policy) gereği, müşterilerinin compromise olduğunu
    bildirme yükümlülüğü vardır. Mail tonu pasif/danışman; aksiyon talebi yok.

    `report_url` site sahibine atılan rapor URL'idir; auditor view ile (?for=auditor)
    gönderilir — hosting reviewer'ı 'Forward to Cloudflare' CTA'sı görmez,
    bunun yerine "evidence package" tonunda raporu inceler.

    Args:
        domain: Mağdur domain (örn. www.saogoncalo.rj.gov.br)
        abuse_email: Hosting'in abuse contact'ı (data/evidence/{domain}/analysis/hosting.json)
        hosting_provider: Provider org adı (ipinfo)
        ip: Mağdur sitenin IP'si
        asn: AS number
        report_url: Site sahibine giden rapor URL'i (?for=auditor eklenecek)
        hacklink_count: Tespit edilen hacklink sayısı
        first_seen: İlk tespit tarihi (str)
        site_owner_notified: True ise mail'e "we have already notified the site
                             owner directly" cümlesi eklenir
        site_id: mail_log için site referansı
    """
    from notifier.sender import _zeptomail_send

    # Auditor URL — site sahibine giden rapor URL'inin auditor view'i.
    auditor_url = report_url
    if report_url:
        auditor_url = f"{report_url}?for=auditor" if "?" not in report_url else f"{report_url}&for=auditor"

    owner_line = (
        "The site's registered technical contact has been notified separately "
        "via the WHOIS / domain-listed email."
    ) if site_owner_notified else (
        "We have not been able to identify a working technical contact for the "
        "site directly; this notification is therefore routed to the hosting "
        "abuse channel as the most reliable path to reach the account holder."
    )

    infra_lines = []
    if hosting_provider:
        infra_lines.append(f"  Hosting provider: {hosting_provider}")
    if ip:
        infra_lines.append(f"  Server IP: {ip}")
    if asn:
        infra_lines.append(f"  ASN: {asn}")
    infra_block = "\n".join(infra_lines) if infra_lines else ""

    fs_line = f"  First observed: {first_seen}\n" if first_seen else ""
    hl_line = f"  Hidden third-party anchors observed on rendered pages: {hacklink_count}\n" if hacklink_count else ""

    subject = f"AbuseRadar notice: {domain} — third-party content observed on your customer's site"
    body = f"""Hello,

This is a passive notification from AbuseRadar (abuseradar.org), an
independent web-data observatory tracking SEO-spam injection patterns
across public pages.

During our routine indexing, the website {domain} — hosted on your
infrastructure — was observed serving third-party hyperlinks that do not
fit the site's normal content profile. Patterns of this shape commonly
originate from a CMS plugin, theme file, or template altered outside the
site's editorial flow (i.e. a compromise rather than intentional content).

Affected site:
  Domain: {domain}
{infra_block + chr(10) if infra_block else ''}{hl_line}{fs_line}
The full technical bundle (no sign-in required) — the same evidence
package shared with the site's technical contact — is available here:

  {auditor_url}

The bundle includes: rendered-vs-source DOM diffs, the injected anchors
verbatim, screenshots of the compromised pages, the upstream payload
hostnames, and the observed C2 / loader infrastructure.

{owner_line}

This injection pattern has been publicly documented since January 2025 by
independent researchers and is part of a long-running campaign:

  - cside Research (original disclosure):
    https://cside.com/blog/government-and-university-websites-targeted-in-scriptapi-dev-client-side-attack
  - Cyber Security News:
    https://cybersecuritynews.com/javascript-attacks-targeting/
  - Joe Sandbox automated analysis:
    https://www.joesandbox.com/analysis/1684428/0/html
  - PublicWWW live footprint:
    https://publicwww.com/websites/scriptapi.dev/

We are not requesting any specific action under your AUP — this is shared
so the case is visible to your abuse / trust-and-safety team and so the
account holder can be assisted with remediation if helpful.

This is an automated, one-off informational notice. If a follow-up or
additional evidence (logs, samples, anchor lists) would be useful, please
reply to abuse@abuseradar.org.

— AbuseRadar Research
abuseradar.org
"""

    try:
        result = await _zeptomail_send(
            to_email=abuse_email,
            to_name=hosting_provider or None,
            subject=subject,
            text_body=body,
            site_id=site_id,
        )
        if result.get("status") == "simulated":
            logger.warning(f"[{domain}] Victim hosting mail simulated (no token) → {abuse_email}")
            return {"status": "simulated", "to": abuse_email, "subject": subject}
        if result.get("status") == "skipped":
            return {"status": "skipped", "to": abuse_email, "reason": result.get("reason")}
        logger.info(f"[{domain}] Victim hosting abuse mail sent → {abuse_email} ({hosting_provider})")
        return {"status": "sent", "to": abuse_email, "message_id": result.get("id")}
    except Exception as e:
        logger.error(f"[{domain}] Victim hosting mail error: {e}")
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
