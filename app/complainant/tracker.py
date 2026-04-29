"""Şikayet durumu takibi - duplicate önleme ve follow-up."""

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import Complaint, async_session

logger = logging.getLogger(__name__)


async def submit_complaint(
    target_domain: str,
    target_type: str,
    platform: str,
    platform_detail: str = "",
    evidence_path: str = "",
    notes: str = "",
) -> dict:
    """Yeni şikayet oluştur veya mevcut olanı döndür."""

    async with async_session() as session:
        # Duplicate kontrol
        existing = await session.execute(
            select(Complaint).where(
                Complaint.target_domain == target_domain,
                Complaint.platform == platform,
            )
        )
        complaint = existing.scalar_one_or_none()

        if complaint:
            if complaint.status == "resolved":
                # Tekrar aktifleşmiş olabilir
                complaint.status = "reopened"
                complaint.notes = (complaint.notes or "") + f"\nReopened: {datetime.utcnow()}"
                await session.commit()
                return {"status": "reopened", "id": complaint.id}
            else:
                return {
                    "status": "already_exists",
                    "id": complaint.id,
                    "current_status": complaint.status,
                }

        # Yeni şikayet — status="pending" başlat. OpenClaw form gerçekten
        # submit edildiğinde mark_complaint_status() ile "submitted"a çevrilir.
        complaint = Complaint(
            target_domain=target_domain,
            target_type=target_type,
            platform=platform,
            platform_detail=platform_detail,
            status="pending",
            submitted_at=None,
            next_check_at=datetime.utcnow() + timedelta(days=14),
            evidence_path=evidence_path,
            notes=notes,
        )
        session.add(complaint)
        await session.commit()

        logger.info(f"Şikayet pending oluşturuldu: {target_domain} → {platform}")
        return {"status": "created", "id": complaint.id}


async def mark_complaint_status(
    complaint_id: int,
    *,
    new_status: str,
    notes_append: str | None = None,
    evidence_path: str | None = None,
) -> bool:
    """Şikayet durumunu güncelle (pending → submitted / failed / captcha_blocked).

    OpenClaw görevi tamamlandıktan sonra çağrılır.
    """
    async with async_session() as session:
        complaint = await session.get(Complaint, complaint_id)
        if not complaint:
            return False
        complaint.status = new_status
        if new_status == "submitted":
            complaint.submitted_at = datetime.utcnow()
        if notes_append:
            complaint.notes = (complaint.notes or "") + f"\n{datetime.utcnow().isoformat()}: {notes_append}"
        if evidence_path:
            complaint.evidence_path = evidence_path
        await session.commit()
        return True


async def check_and_followup():
    """Şikayetleri kontrol et ve gerekirse follow-up yap."""
    async with async_session() as session:
        result = await session.execute(
            select(Complaint).where(
                Complaint.status.in_(["submitted", "reopened"]),
                Complaint.next_check_at <= datetime.utcnow(),
                Complaint.followup_count < Complaint.max_followups,
            )
        )
        due_complaints = result.scalars().all()

        for complaint in due_complaints:
            complaint.check_count += 1
            complaint.last_checked_at = datetime.utcnow()
            complaint.followup_count += 1
            complaint.next_check_at = datetime.utcnow() + timedelta(days=14)
            complaint.notes = (complaint.notes or "") + f"\nFollow-up #{complaint.followup_count}: {datetime.utcnow()}"

            logger.info(
                f"Follow-up #{complaint.followup_count}: "
                f"{complaint.target_domain} → {complaint.platform}"
            )

        await session.commit()
        return len(due_complaints)
