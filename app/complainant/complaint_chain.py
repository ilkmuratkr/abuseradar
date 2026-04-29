"""Saldırgan target_domain için şikayet zinciri orkestratörü.

Bir gambling/spam target_domain için (örn. istanbulbahise.com):
  1. Hosting/IP info (WHOIS) — abuse@... bul
  2. Registrar info (WHOIS) — registrar abuse@... bul
  3. CF arkasında mı kontrol
  4. Şikayet zinciri (paralel):
       - CF abuse: form (OpenClaw) + mail (ZeptoMail)  ← sadece CF arkasındaysa
       - Hosting abuse: form (OpenClaw) + mail (ZeptoMail)
       - Registrar abuse: form (OpenClaw) + mail (ZeptoMail)
       - Google Safe Browsing: form (OpenClaw)
  5. complaints DB tablosuna kayıt

Mail kanalı OpenClaw timeout/fail olursa redundant ama bağımsız çalışır.
"""

import asyncio
import logging
from datetime import datetime

from . import hosting as hosting_mod
from . import openclaw

logger = logging.getLogger(__name__)


async def _safe(coro):
    """Coroutine'i çalıştır, exception'ı yakalayıp dict olarak döndür."""
    try:
        return await coro
    except Exception as e:
        logger.exception(f"complaint chain step failed: {e}")
        return {"status": "error", "reason": str(e)}


async def discover_attacker_meta(target_domain: str) -> dict:
    """Saldırgan domain için meta bilgi topla — paralel WHOIS + CF check."""
    info, cf = await asyncio.gather(
        _safe(hosting_mod.get_hosting_info(target_domain)),
        _safe(hosting_mod.is_behind_cloudflare(target_domain)),
    )
    info = info or {}
    info["is_cloudflare"] = bool(cf) if isinstance(cf, bool) else False
    # Registrar bilgisini de WHOIS ile dene
    try:
        import whois
        w = whois.whois(target_domain)
        info["registrar"] = getattr(w, "registrar", None) or ""
        ra = getattr(w, "registrar_abuse_contact_email", None)
        if isinstance(ra, list):
            ra = ra[0] if ra else None
        info["registrar_abuse_email"] = ra or ""
    except Exception as e:
        logger.debug(f"[{target_domain}] WHOIS hatası: {e}")
        info.setdefault("registrar", "")
        info.setdefault("registrar_abuse_email", "")
    return info


async def run_chain_for_target(
    target_domain: str,
    *,
    affected_gov_sites: list[str] | None = None,
    hacklink_count: int = 0,
    injection_method: str = "JS injection (hidden anchors)",
    report_url: str = "",
    enable_form: bool = True,
    enable_mail: bool = True,
) -> dict:
    """Tek bir target_domain için tüm şikayet zincirini çalıştır.

    Args:
        target_domain: Saldırgan domain (örn. istanbulbahise.com)
        affected_gov_sites: Bu domain'in bastığı kurban sitelerin listesi (örn. ["ulm.edu.pk", ...])
        hacklink_count: Bu target'a giden gözlemlenen anchor sayısı
        injection_method: Tespit metodu açıklaması
        report_url: Bu domain'in geçtiği rapor bundle'ının public URL'i
        enable_form: True → OpenClaw browser otomasyon (CF/Google/hosting/registrar formları)
        enable_mail: True → ZeptoMail abuse mail'leri (hosting + registrar)
    """
    affected_gov_sites = affected_gov_sites or []
    affected_str = ", ".join(affected_gov_sites[:10]) or "(see bundle)"

    logger.info(f"[{target_domain}] complaint chain başlıyor (form={enable_form}, mail={enable_mail})")

    meta = await discover_attacker_meta(target_domain)
    summary = (
        f"Observed on {len(affected_gov_sites)}+ compromised pages including: "
        f"{affected_str}\n"
        f"Hacklink anchors targeting this domain: {hacklink_count}\n"
        f"Injection method: {injection_method}"
    )

    # OpenClaw 'main' agent için session lock contention engelleyebilmek için
    # form görevleri SIRAYLA çalıştırılır. Mail görevleri (ZeptoMail) form'a
    # paralel — onlarda lock yok.
    form_steps: list[tuple[str, callable]] = []
    mail_steps: list[tuple[str, callable]] = []

    # 1. Cloudflare
    if meta.get("is_cloudflare"):
        if enable_form:
            form_steps.append(("cloudflare_form", lambda: openclaw.report_cloudflare(
                target_domain=target_domain,
                target_role="SEO spam destination (gambling/casino)",
                affected_gov_sites=affected_str,
                injection_method=injection_method,
                affected_count=len(affected_gov_sites) or 1,
                first_seen=datetime.utcnow().strftime("%Y-%m-%d"),
                report_url=report_url,
            )))
        if enable_mail:
            mail_steps.append(("cloudflare_mail", lambda: hosting_mod.report_to_hosting(
                domain=target_domain, abuse_email="abuse@cloudflare.com",
                issue_type="takeover", evidence_summary=summary, report_url=report_url,
            )))

    # 2. Hosting (CF arkasında değilse)
    if meta.get("abuse_email") and not meta.get("is_cloudflare"):
        if enable_mail:
            mail_steps.append(("hosting_mail", lambda: hosting_mod.report_to_hosting(
                domain=target_domain, abuse_email=meta["abuse_email"],
                issue_type="takeover", evidence_summary=summary, report_url=report_url,
            )))
        if enable_form:
            form_steps.append(("hosting_form", lambda: openclaw.report_hosting_form(
                target_domain=target_domain,
                hosting_provider=meta.get("hosting_provider", ""),
                abuse_email=meta.get("abuse_email", ""),
                ip=meta.get("ip", ""), asn=meta.get("asn", ""),
                injection_method=injection_method,
                hacklink_count=hacklink_count, report_url=report_url,
            )))

    # 3. Registrar
    if meta.get("registrar_abuse_email"):
        if enable_mail:
            mail_steps.append(("registrar_mail", lambda: hosting_mod.report_to_hosting(
                domain=target_domain, abuse_email=meta["registrar_abuse_email"],
                issue_type="takeover", evidence_summary=summary, report_url=report_url,
            )))
        if enable_form:
            form_steps.append(("registrar_form", lambda: openclaw.report_registrar_form(
                target_domain=target_domain, registrar=meta.get("registrar", ""),
                abuse_email=meta.get("registrar_abuse_email", ""),
                target_role="SEO spam infrastructure",
                affected_gov_sites=affected_str, report_url=report_url,
            )))

    # 4. Google Safe Browsing
    if enable_form:
        form_steps.append(("google_sb", lambda: openclaw.report_google_safebrowsing(
            target_url=f"https://{target_domain}/", domain=target_domain,
        )))

    # 5. ICANN
    if enable_form and meta.get("registrar"):
        form_steps.append(("icann", lambda: openclaw.report_icann(
            target_domain=target_domain, registrar=meta.get("registrar", ""),
            registrar_abuse_email=meta.get("registrar_abuse_email", ""),
            report_date=datetime.utcnow().strftime("%Y-%m-%d"),
            affected_count=len(affected_gov_sites) or 1,
        )))

    results: dict[str, dict] = {}

    # Mail görevleri paralel (ZeptoMail, lock yok)
    if mail_steps:
        mail_tasks = [asyncio.create_task(_safe(fn())) for _, fn in mail_steps]
        for (name, _), tsk in zip(mail_steps, mail_tasks):
            try:
                results[name] = await tsk
            except Exception as e:
                results[name] = {"status": "error", "reason": str(e)}

    # Form görevleri SIRAYLA — OpenClaw main agent session lock için
    for name, fn in form_steps:
        logger.info(f"[{target_domain}] form step başlıyor: {name}")
        try:
            results[name] = await _safe(fn())
        except Exception as e:
            results[name] = {"status": "error", "reason": str(e)}

    out = {
        "target_domain": target_domain,
        "meta": {
            "ip": meta.get("ip"),
            "is_cloudflare": meta.get("is_cloudflare"),
            "hosting_provider": meta.get("hosting_provider"),
            "registrar": meta.get("registrar"),
            "abuse_email": meta.get("abuse_email"),
            "registrar_abuse_email": meta.get("registrar_abuse_email"),
        },
        "complaints": results,
        "completed_at": datetime.utcnow().isoformat(),
    }
    logger.info(f"[{target_domain}] complaint chain tamamlandı: {list(results.keys())}")
    return out
