"""Haftalık monitoring döngüsü - re-crawl, follow-up, C2 kontrol."""

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select, and_

from config import settings
from models.database import (
    C2Domain, Complaint, DetectedHacklink, Notification, Site,
    async_session,
)

logger = logging.getLogger(__name__)


async def recrawl_infected_sites():
    """Enjeksiyon doğrulanmış siteleri tekrar crawl et - hala hackli mi?"""
    from crawler.engine import crawl_and_analyze, save_crawl_results

    async with async_session() as session:
        result = await session.execute(
            select(Site).where(
                Site.injection_verified == True,
                Site.status == "infected",
            )
        )
        sites = result.scalars().all()

    logger.info(f"Re-crawl: {len(sites)} enfekte site kontrol edilecek")
    remediated = 0
    still_infected = 0

    for site in sites:
        url = site.url or f"https://{site.domain}/"
        try:
            crawl_result = await crawl_and_analyze(url, site.domain)

            async with async_session() as session:
                db_site = await session.get(Site, site.id)
                db_site.last_crawled_at = datetime.utcnow()

                if crawl_result["total_hacklinks"] == 0:
                    db_site.status = "remediated"
                    db_site.injection_verified = False
                    remediated += 1
                    logger.info(f"[{site.domain}] Düzeltilmiş!")

                    # Notification'ları güncelle
                    notifs = await session.execute(
                        select(Notification).where(
                            Notification.site_id == site.id,
                            Notification.injection_still_active == True,
                        )
                    )
                    for n in notifs.scalars().all():
                        n.injection_still_active = False
                        n.remediated_at = datetime.utcnow()
                        n.status = "remediated"
                else:
                    still_infected += 1
                    await save_crawl_results(crawl_result)

                await session.commit()

        except Exception as e:
            logger.error(f"[{site.domain}] Re-crawl hatası: {e}")

        await asyncio.sleep(settings.crawl_same_domain_delay)

    logger.info(
        f"Re-crawl tamamlandı: {remediated} düzeltilmiş, "
        f"{still_infected} hala enfekte"
    )
    return {"remediated": remediated, "still_infected": still_infected}


async def send_followups():
    """Yanıt vermeyen/düzeltmeyen sitelere follow-up email."""
    from notifier.sender import send_alert

    async with async_session() as session:
        result = await session.execute(
            select(Notification).where(
                and_(
                    Notification.injection_still_active == True,
                    Notification.status == "sent",
                    Notification.send_count < Notification.max_sends,
                    Notification.next_check_at <= datetime.utcnow(),
                )
            )
        )
        due_notifications = result.scalars().all()

    logger.info(f"Follow-up: {len(due_notifications)} bildirim kontrol edilecek")
    sent = 0

    for notif in due_notifications:
        async with async_session() as session:
            site = await session.get(Site, notif.site_id)
            if not site or site.status == "remediated":
                continue

            result = await send_alert(
                site_id=site.id,
                contact_id=notif.contact_id,
                domain=site.domain,
                url=site.url or f"https://{site.domain}/",
                hacklink_count=0,
                first_seen=str(site.created_at),
            )
            if result["status"] == "sent":
                sent += 1

    logger.info(f"Follow-up: {sent} email gönderildi")
    return {"followups_sent": sent}


async def check_c2_status():
    """C2 domainlerinin durumunu kontrol et - suspended/seized mi?"""
    import httpx

    async with async_session() as session:
        result = await session.execute(
            select(C2Domain).where(C2Domain.status == "active")
        )
        c2s = result.scalars().all()

    logger.info(f"C2 kontrol: {len(c2s)} aktif domain kontrol edilecek")
    changes = []

    for c2 in c2s:
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                resp = await client.get(f"https://{c2.domain}/", headers={
                    "User-Agent": settings.crawl_user_agent,
                })

                new_status = "active"
                if resp.status_code in (403, 404, 410, 451):
                    new_status = "blocked"
                elif resp.status_code >= 500:
                    new_status = "down"
                elif "suspended" in resp.text.lower() or "account has been" in resp.text.lower():
                    new_status = "suspended"

                if new_status != c2.status:
                    async with async_session() as session:
                        db_c2 = await session.get(C2Domain, c2.id)
                        old = db_c2.status
                        db_c2.status = new_status
                        await session.commit()
                    changes.append(f"{c2.domain}: {old} → {new_status}")
                    logger.warning(f"C2 durum değişikliği: {c2.domain} {old} → {new_status}")

        except httpx.ConnectError:
            async with async_session() as session:
                db_c2 = await session.get(C2Domain, c2.id)
                if db_c2.status != "unreachable":
                    db_c2.status = "unreachable"
                    await session.commit()
                    changes.append(f"{c2.domain}: {c2.status} → unreachable")
        except Exception as e:
            logger.debug(f"[{c2.domain}] Kontrol hatası: {e}")

    return {"checked": len(c2s), "changes": changes}


async def check_complaint_status():
    """Şikayetlerin durumunu kontrol et ve follow-up yap."""
    from complainant.tracker import check_and_followup
    count = await check_and_followup()
    return {"followups": count}


async def run_weekly_cycle():
    """Tam haftalık monitoring döngüsü."""
    logger.info("=" * 60)
    logger.info("HAFTALIK MONİTORİNG DÖNGÜSÜ BAŞLIYOR")
    logger.info("=" * 60)

    # 1. C2 durumu kontrol
    c2_result = await check_c2_status()
    logger.info(f"C2 kontrol: {c2_result}")

    # 2. Enfekte siteleri re-crawl
    recrawl_result = await recrawl_infected_sites()
    logger.info(f"Re-crawl: {recrawl_result}")

    # 3. Follow-up email
    followup_result = await send_followups()
    logger.info(f"Follow-up: {followup_result}")

    # 4. Şikayet durumu
    complaint_result = await check_complaint_status()
    logger.info(f"Şikayet: {complaint_result}")

    logger.info("=" * 60)
    logger.info("HAFTALIK DÖNGÜ TAMAMLANDI")
    logger.info("=" * 60)

    return {
        "c2": c2_result,
        "recrawl": recrawl_result,
        "followup": followup_result,
        "complaints": complaint_result,
        "timestamp": datetime.utcnow().isoformat(),
    }
