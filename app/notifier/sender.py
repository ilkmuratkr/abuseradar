"""Email gönderim - Zoho ZeptoMail REST API entegrasyonu."""

import logging
from datetime import datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.database import Contact, Notification, Site, Unsubscribe, async_session

from .evidence_picker import load_evidence_summary
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
) -> dict:
    """ZeptoMail REST API çağrısı.

    RFC 8058 one-click List-Unsubscribe header'ı ile birlikte gönderilir
    — Gmail/Yahoo bulk sender requirements (Şubat 2024+) bunu zorunlu kılar.
    """
    token = settings.zeptomail_token.strip()
    if not token:
        return {"id": "simulated", "status": "simulated"}

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
    async with httpx.AsyncClient(timeout=20.0, trust_env=False) as client:
        r = await client.post(settings.zeptomail_endpoint, json=payload, headers=headers)

    if r.status_code >= 400:
        raise RuntimeError(f"ZeptoMail HTTP {r.status_code}: {r.text}")
    data = r.json()
    return {"id": (data.get("data") or [{}])[0].get("message_id", "unknown"), "status": "sent"}


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

        # ZeptoMail API ile gönder
        try:
            result = await _zeptomail_send(
                to_email=contact.email,
                to_name=None,
                subject=subject,
                text_body=body,
            )

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
            return {"status": "sent", "to": contact.email, "language": language}

        except Exception as e:
            logger.error(f"[{domain}] Email gönderim hatası: {e}")
            return {"status": "error", "reason": str(e)}


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
