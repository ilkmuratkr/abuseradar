"""Email gönderim - Zoho ZeptoMail REST API entegrasyonu."""

import logging
from datetime import datetime, timedelta

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.database import Contact, MailLog, Notification, Site, Unsubscribe, async_session

from .evidence_picker import load_evidence_summary
from .html_renderer import render_html_email
from .provider import daily_limit_for, detect_email_provider, is_consumer_mail
from .language import (
    describe_category,
    get_complaint_block,
    get_language,
    get_subject,
    get_verification_block,
    render_template,
)

logger = logging.getLogger(__name__)


async def _zeptomail_send(
    *,
    to_email: str,
    to_name: str | None,
    subject: str,
    text_body: str,
    site_id: int | None = None,
    contact_id: int | None = None,
    language: str | None = None,
    enforce_daily_limit: bool = True,
) -> dict:
    """ZeptoMail REST API çağrısı.

    Her gönderim mail_log tablosuna yazılır (provider tespitiyle).
    enforce_daily_limit=True iken provider-bazlı günlük limit aşılırsa
    gönderim yapılmaz, status=skipped döner.

    RFC 8058 one-click List-Unsubscribe header'ı ile birlikte gönderilir
    — Gmail/Yahoo bulk sender requirements (Şubat 2024+) bunu zorunlu kılar.
    """
    to_email_lower = (to_email or "").strip().lower()
    to_domain = to_email_lower.split("@", 1)[1] if "@" in to_email_lower else ""

    # Consumer mail kısa-devre — gmail.com / hotmail.com / yahoo.com vb. adresler
    # gov/edu admin değil, kişisel posta. Bunlara mail atma (deliverability +
    # gerçek site sahibine ulaşmama riski).
    if is_consumer_mail(to_email_lower):
        await _log_mail(
            to_email=to_email_lower, to_domain=to_domain, provider="consumer",
            site_id=site_id, contact_id=contact_id, subject=subject,
            language=language, status="skipped_consumer_mail",
            error_message="recipient is a consumer mail provider", zeptomail_id=None,
        )
        return {"id": None, "status": "skipped", "reason": "consumer_mail", "to": to_email_lower}

    # Provider tespiti (MX lookup)
    provider = await detect_email_provider(to_email_lower)

    # Daily limit kontrolü — provider bazlı
    if enforce_daily_limit:
        limit = daily_limit_for(provider)
        async with async_session() as session:
            today_start = datetime.utcnow() - timedelta(hours=24)
            count_q = await session.execute(
                select(func.count(MailLog.id)).where(
                    MailLog.recipient_provider == provider,
                    MailLog.status == "sent",
                    MailLog.sent_at >= today_start,
                )
            )
            sent_today = count_q.scalar() or 0
        if sent_today >= limit:
            logger.warning(
                f"[{to_email_lower}] Provider {provider} günlük limit ({limit}) aşıldı "
                f"(bugün {sent_today} mail). Atlandı."
            )
            await _log_mail(
                to_email=to_email_lower,
                to_domain=to_domain,
                provider=provider,
                site_id=site_id,
                contact_id=contact_id,
                subject=subject,
                language=language,
                status="skipped_daily_limit",
                error_message=f"daily limit {limit} reached for provider {provider}",
                zeptomail_id=None,
            )
            return {
                "id": None,
                "status": "skipped",
                "reason": "daily_limit",
                "provider": provider,
                "sent_today": sent_today,
                "limit": limit,
            }

    token = settings.zeptomail_token.strip()
    if not token:
        await _log_mail(
            to_email=to_email_lower, to_domain=to_domain, provider=provider,
            site_id=site_id, contact_id=contact_id, subject=subject,
            language=language, status="simulated", error_message=None, zeptomail_id="simulated",
        )
        return {"id": "simulated", "status": "simulated", "provider": provider}

    if not token.lower().startswith("zoho-enczapikey "):
        token = f"Zoho-enczapikey {token}"

    # Public unsubscribe endpoint (token'lı) — alıcı bir tıkla çıkabilir.
    # POST /api/public/unsubscribe → 200, mailing list'e ekleme yapmaz çünkü
    # zaten liste yok — ama Gmail'in "this sender respects unsubscribe"
    # sinyali yine de gerekli. mailto: fallback de var.
    unsubscribe_url = f"{settings.public_base_url.rstrip('/')}/api/public/unsubscribe?e={to_email}"
    list_unsubscribe = f"<mailto:unsubscribe@abuseradar.org?subject=unsubscribe>, <{unsubscribe_url}>"

    payload = {
        "from": {
            "address": settings.email_from,
            "name": settings.email_from_name,
        },
        "to": [
            {
                "email_address": {
                    "address": to_email,
                    "name": to_name or to_email.split("@")[0],
                }
            }
        ],
        "reply_to": [
            {
                "address": settings.email_reply_to,
                "name": settings.email_reply_to_name,
            }
        ],
        "subject": subject,
        "textbody": text_body,
        "htmlbody": render_html_email(text_body),
        "mime_headers": {
            "List-Unsubscribe": list_unsubscribe,
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            "Precedence": "bulk",
        },
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": token,
    }

    # trust_env=False → HTTP_PROXY/HTTPS_PROXY env varlarını yoksay.
    # Mail gönderimi VPN üzerinden GİTMEMELİ — Zenlayer/Mullvad IP'sinden
    # mail atmak ZeptoMail nezdinde fraud sinyali, alıcı tarafında reputation
    # zararı yapar. Doğrudan host network ile ZeptoMail'e bağlan.
    try:
        async with httpx.AsyncClient(timeout=20.0, trust_env=False) as client:
            r = await client.post(settings.zeptomail_endpoint, json=payload, headers=headers)
        if r.status_code >= 400:
            err = f"ZeptoMail HTTP {r.status_code}: {r.text}"
            await _log_mail(
                to_email=to_email_lower, to_domain=to_domain, provider=provider,
                site_id=site_id, contact_id=contact_id, subject=subject,
                language=language, status="error", error_message=err, zeptomail_id=None,
            )
            raise RuntimeError(err)
        data = r.json()
        zid = (data.get("data") or [{}])[0].get("message_id", "unknown")
    except Exception as e:
        if "ZeptoMail HTTP" not in str(e):
            await _log_mail(
                to_email=to_email_lower, to_domain=to_domain, provider=provider,
                site_id=site_id, contact_id=contact_id, subject=subject,
                language=language, status="error", error_message=str(e), zeptomail_id=None,
            )
        raise

    await _log_mail(
        to_email=to_email_lower, to_domain=to_domain, provider=provider,
        site_id=site_id, contact_id=contact_id, subject=subject,
        language=language, status="sent", error_message=None, zeptomail_id=zid,
    )
    return {"id": zid, "status": "sent", "provider": provider}


async def _log_mail(
    *,
    to_email: str,
    to_domain: str,
    provider: str,
    site_id: int | None,
    contact_id: int | None,
    subject: str,
    language: str | None,
    status: str,
    error_message: str | None,
    zeptomail_id: str | None,
) -> None:
    """mail_log tablosuna kayıt ekle."""
    try:
        async with async_session() as session:
            session.add(MailLog(
                to_email=to_email,
                to_email_domain=to_domain,
                recipient_provider=provider,
                site_id=site_id,
                contact_id=contact_id,
                subject=subject[:500] if subject else None,
                language=language,
                status=status,
                error_message=error_message,
                zeptomail_id=zeptomail_id,
            ))
            await session.commit()
    except Exception as e:
        logger.warning(f"mail_log kayıt hatası: {e}")


async def send_alert(
    site_id: int,
    contact_id: int,
    domain: str,
    url: str,
    hacklink_count: int,
    first_seen: str,
    language: str | None = None,
) -> dict:
    """Tek bir siteye güvenlik uyarısı gönder."""

    async with async_session() as session:
        # Duplicate gönderim kontrolü
        existing = await session.execute(
            select(Notification).where(
                Notification.site_id == site_id,
                Notification.contact_id == contact_id,
            )
        )
        notif = existing.scalar_one_or_none()
        if notif and notif.send_count >= notif.max_sends:
            return {"status": "skipped", "reason": "max_sends_reached"}

        # İletişim bilgisini al
        contact = await session.get(Contact, contact_id)
        if not contact:
            return {"status": "error", "reason": "contact_not_found"}

        # Unsubscribe listesi kontrolü — RFC 8058 + Gmail/Yahoo bulk requirements
        unsub = await session.execute(
            select(Unsubscribe).where(Unsubscribe.email == contact.email.lower())
        )
        if unsub.scalar_one_or_none():
            logger.info(f"[{domain}] {contact.email} unsubscribed listesinde, atlandı")
            return {"status": "skipped", "reason": "unsubscribed"}

        # Email-bazlı dedup: AYNI mail adresine (farklı site_id/contact_id ile bile)
        # son 7 günde mail gittiyse atma. Aynı kuruma birden fazla subdomain'den
        # de gönderim olabilir, ama tek mail adresi 7 gün içinde tek uyarı alır.
        recent = await session.execute(
            select(Notification)
            .join(Contact, Contact.id == Notification.contact_id)
            .where(
                Contact.email == contact.email,
                Notification.status == "sent",
                Notification.sent_at >= datetime.utcnow() - timedelta(days=7),
            )
            .limit(1)
        )
        if recent.scalar_one_or_none() and (not notif or notif.send_count == 0):
            logger.info(f"[{domain}] {contact.email} son 7 günde zaten mail aldı, atlandı")
            return {"status": "skipped", "reason": "email_recently_notified"}

        # Dil tespit
        if not language:
            language = get_language(domain)

        report_url = f"{settings.report_base_url}/{domain}"

        # Evidence dosyasından gerçek sayı + kategori + doğrulama anahtarı
        ev = load_evidence_summary(domain)
        if ev:
            real_count = ev.get("total_hacklinks") or hacklink_count
            top_keyword = ev.get("top_keyword")
            top_source = ev.get("top_keyword_source", "raw")
            category = ev.get("category", "off_topic")
        else:
            real_count = hacklink_count
            top_keyword = None
            top_source = "raw"
            category = "off_topic"

        # Mail'de www. prefix'ini gösterme — daha temiz, daha az URL benzeri
        display_domain = domain[4:] if domain.startswith("www.") else domain

        verification_block = get_verification_block(
            language, top_keyword, top_source, domain=display_domain
        )
        content_category = describe_category(language, category)
        # Mail body temiz — CF mailto link rapor sayfasında. Mail spam'e
        # düşmesin diye URL sayısı 1 (sadece rapor URL'i).
        complaint_block = get_complaint_block(language)

        subject = get_subject(language, display_domain)
        body = render_template(
            language,
            url=url,
            domain=display_domain,
            hacklink_count=real_count,
            first_seen=first_seen,
            report_url=report_url,
            evidence_block=verification_block,
            complaint_block=complaint_block,
            content_category=content_category,
        )

        # ZeptoMail API ile gönder (provider-bazlı limit + mail_log otomatik)
        try:
            result = await _zeptomail_send(
                to_email=contact.email,
                to_name=None,
                subject=subject,
                text_body=body,
                site_id=site_id,
                contact_id=contact_id,
                language=language,
            )
            if result.get("status") == "skipped":
                return result

            # Notification kaydı
            if notif:
                notif.send_count += 1
                notif.sent_at = datetime.utcnow()
                notif.next_check_at = datetime.utcnow() + timedelta(days=settings.email_followup_days)
                notif.status = "sent"
            else:
                notif = Notification(
                    site_id=site_id,
                    contact_id=contact_id,
                    email_type="initial_alert",
                    language=language,
                    subject=subject,
                    send_count=1,
                    status="sent",
                    sent_at=datetime.utcnow(),
                    next_check_at=datetime.utcnow() + timedelta(days=settings.email_followup_days),
                )
                session.add(notif)

            await session.commit()

            logger.info(f"[{domain}] Email gönderildi → {contact.email} ({language})")

            # Site sahibine başarılı mail sonrası → mağdurun hosting sağlayıcısına
            # da bilgilendirme. hosting.json crawl sırasında yazıldı; oradan oku.
            # Hosting'e gönderim hatası, owner mail'inin başarılı dönüşünü
            # bozmamalı — exception swallow.
            try:
                await _dispatch_victim_hosting_mail(
                    domain=domain,
                    site_id=site_id,
                    report_url=report_url,
                    hacklink_count=real_count,
                    first_seen=first_seen,
                    owner_email=contact.email,
                )
            except Exception as e:
                logger.warning(f"[{domain}] victim hosting mail dispatch hatası: {e}")

            return {"status": "sent", "to": contact.email, "language": language}

        except Exception as e:
            logger.error(f"[{domain}] Email gönderim hatası: {e}")
            return {"status": "error", "reason": str(e)}


async def _dispatch_victim_hosting_mail(
    *,
    domain: str,
    site_id: int,
    report_url: str,
    hacklink_count: int,
    first_seen: str,
    owner_email: str,
) -> None:
    """Mağdur sitenin hosting sağlayıcısına bilgilendirme maili.

    Trigger: send_alert() içinde site sahibine başarılı mail atıldıktan sonra.
    Veri kaynağı: data/evidence/{domain}/analysis/hosting.json (crawl çıktısı).

    Skip koşulları:
      - hosting.json yok ya da abuse_email boş
      - Hosting Cloudflare ise (CF abuse kanalı saldırgan zincirinin parçası,
        mağdur tarafında CF'ye yazmak verim getirmez — site owner zaten haberdar)
      - Aynı abuse_email'e aynı site_id için son 14 gün içinde 'sent' kaydı var
      - abuse_email == owner_email (kendine kendi mail'i atma)
    """
    from utils.evidence_reader import get_hosting

    info = get_hosting(domain) or {}
    abuse_email = (info.get("abuse_email") or "").strip().lower()
    if not abuse_email:
        logger.info(f"[{domain}] victim hosting abuse_email yok, atlanıyor")
        return

    if "@" not in abuse_email:
        logger.info(f"[{domain}] victim hosting abuse_email geçersiz: {abuse_email!r}")
        return

    if info.get("is_cloudflare"):
        logger.info(f"[{domain}] victim CF arkasında, hosting mail atlanıyor")
        return

    if abuse_email == (owner_email or "").strip().lower():
        logger.info(f"[{domain}] victim hosting abuse_email site sahibiyle aynı, atlanıyor")
        return

    # Dedup — aynı site için son 14 gün içinde aynı abuse'a 'sent' kaydı var mı?
    async with async_session() as session:
        recent = await session.execute(
            select(MailLog).where(
                MailLog.to_email == abuse_email,
                MailLog.site_id == site_id,
                MailLog.status == "sent",
                MailLog.sent_at >= datetime.utcnow() - timedelta(days=14),
            ).limit(1)
        )
        if recent.scalar_one_or_none():
            logger.info(
                f"[{domain}] victim hosting {abuse_email} son 14 günde mail aldı, atlanıyor"
            )
            return

    from complainant.hosting import report_to_victim_hosting

    res = await report_to_victim_hosting(
        domain=domain,
        abuse_email=abuse_email,
        hosting_provider=info.get("hosting_provider") or "",
        ip=info.get("ip") or "",
        asn=info.get("asn") or "",
        report_url=report_url,
        hacklink_count=hacklink_count,
        first_seen=first_seen,
        site_owner_notified=True,
        site_id=site_id,
    )
    logger.info(
        f"[{domain}] victim hosting dispatch sonucu: {res.get('status')} → {abuse_email}"
    )


async def send_alerts_for_victims():
    """Tüm mağdur sitelere toplu email gönder."""
    async with async_session() as session:
        # İletişim bilgisi olan mağdur siteler
        result = await session.execute(
            select(Site, Contact)
            .join(Contact, Site.id == Contact.site_id)
            .where(
                Site.category == "MAGDUR",
                Site.injection_verified == True,
            )
        )
        pairs = result.all()

    sent = 0
    skipped = 0
    errors = 0

    for site, contact in pairs:
        # Günlük limit kontrolü
        if sent >= settings.email_daily_limit:
            logger.warning(f"Günlük limit ({settings.email_daily_limit}) aşıldı, durduruluyor")
            break

        result = await send_alert(
            site_id=site.id,
            contact_id=contact.id,
            domain=site.domain,
            url=site.url or f"https://{site.domain}/",
            hacklink_count=len(site.hacklinks) if site.hacklinks else 0,
            first_seen=str(site.created_at),
        )

        if result["status"] == "sent":
            sent += 1
        elif result["status"] == "skipped":
            skipped += 1
        else:
            errors += 1

    logger.info(f"Toplu email: {sent} gönderildi, {skipped} atlandı, {errors} hata")
    return {"sent": sent, "skipped": skipped, "errors": errors}
