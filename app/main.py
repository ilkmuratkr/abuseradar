"""AbuseRadar — FastAPI Ana Uygulama."""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from sqlalchemy import func, select, text

from config import settings
from models.database import (
    Backlink,
    C2Domain,
    Complaint,
    Contact,
    CsvFile,
    DetectedHacklink,
    Notification,
    ReportToken,
    Site,
    async_session,
    init_db,
)
from utils import evidence_reader


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title=settings.project_name, lifespan=lifespan)


# ═══════════════════════════════════════════════════════════════
# HEALTH & STATS
# ═══════════════════════════════════════════════════════════════


@app.get("/health")
async def health():
    return {"status": "ok", "project": settings.project_name}


@app.get("/health/detailed")
async def health_detailed():
    """DB + Redis + VPN + Crawler + Notifier durumu."""
    out: dict = {"db": "unknown", "redis": "unknown"}

    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        out["db"] = "healthy"
    except Exception as e:
        out["db"] = f"error: {e}"

    try:
        import redis.asyncio as redis_async

        r = redis_async.from_url(settings.redis_url)
        await r.ping()
        await r.aclose()
        out["redis"] = "healthy"
    except Exception as e:
        out["redis"] = f"error: {e}"

    out["gemini_key"] = "set" if settings.gemini_api_key and not settings.gemini_api_key.startswith("your_") else "missing"
    tok = (settings.zeptomail_token or "").strip()
    out["zeptomail_token"] = "set" if tok and "your_token" not in tok.lower() else "missing"
    out["email_from"] = settings.email_from
    out["email_reply_to"] = settings.email_reply_to

    return out


@app.get("/stats")
async def stats():
    async with async_session() as session:
        queries = {
            "csv_files": "SELECT count(*) FROM csv_files WHERE status='completed'",
            "total_backlinks": "SELECT count(*) FROM backlinks",
            "victim_sites": "SELECT count(*) FROM backlinks WHERE category='MAGDUR'",
            "attacker_sites": "SELECT count(*) FROM backlinks WHERE category='SALDIRGAN'",
            "verified_injections": "SELECT count(*) FROM sites WHERE injection_verified=true",
            "detected_hacklinks": "SELECT count(*) FROM detected_hacklinks",
            "c2_domains": "SELECT count(*) FROM c2_domains",
            "notifications_sent": "SELECT count(*) FROM notifications WHERE status='sent'",
            "notifications_remediated": "SELECT count(*) FROM notifications WHERE status='remediated'",
            "complaints_total": "SELECT count(*) FROM complaints",
            "complaints_pending": "SELECT count(*) FROM complaints WHERE status IN ('pending','submitted')",
            "complaints_resolved": "SELECT count(*) FROM complaints WHERE status='resolved'",
            "contacts_found": "SELECT count(*) FROM contacts",
        }
        result: dict = {}
        for key, query in queries.items():
            r = await session.execute(text(query))
            result[key] = r.scalar() or 0

        # Kategori dağılımı
        cat_q = await session.execute(
            text("SELECT category, count(*) FROM backlinks GROUP BY category ORDER BY 2 DESC")
        )
        result["category_breakdown"] = [{"category": r[0], "count": r[1]} for r in cat_q.all()]

        # Mağdur tip dağılımı
        type_q = await session.execute(
            text(
                "SELECT category_detail, count(*) FROM backlinks "
                "WHERE category='MAGDUR' GROUP BY category_detail ORDER BY 2 DESC"
            )
        )
        result["victim_type_breakdown"] = [{"type": r[0], "count": r[1]} for r in type_q.all()]

    return result


# ═══════════════════════════════════════════════════════════════
# CSV
# ═══════════════════════════════════════════════════════════════


@app.post("/csv/process")
async def process_csv():
    """inbox/ klasöründeki CSV'leri işle."""
    from csv_processor.parser import process_inbox

    results = await process_inbox()
    return {
        "processed": len([r for r in results if r["status"] == "completed"]),
        "results": results,
    }


@app.post("/csv/upload")
async def csv_upload(file: UploadFile = File(...)):
    """CSV upload — inbox/'a yazar."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "CSV dosyası bekleniyor")

    inbox = Path(settings.csv_inbox_path)
    inbox.mkdir(parents=True, exist_ok=True)

    safe_name = Path(file.filename).name
    target = inbox / safe_name

    body = await file.read()
    target.write_bytes(body)

    return {
        "filename": safe_name,
        "size": len(body),
        "saved_to": str(target),
        "next_step": "POST /csv/process",
    }


@app.get("/csv-files")
async def list_csv_files(limit: int = 50):
    """İşlenmiş CSV listesi."""
    async with async_session() as session:
        rows = await session.execute(
            text(
                "SELECT id, filename, target_domain, export_date, total_rows, "
                "new_rows, skipped_rows, status, completed_at, created_at "
                "FROM csv_files ORDER BY created_at DESC LIMIT :limit"
            ),
            {"limit": limit},
        )
        out = []
        for r in rows.all():
            out.append(
                {
                    "id": r[0],
                    "filename": r[1],
                    "target_domain": r[2],
                    "export_date": r[3].isoformat() if r[3] else None,
                    "total_rows": r[4],
                    "new_rows": r[5],
                    "skipped_rows": r[6],
                    "status": r[7],
                    "completed_at": r[8].isoformat() if r[8] else None,
                    "created_at": r[9].isoformat() if r[9] else None,
                }
            )
    return {"count": len(out), "files": out}


# ═══════════════════════════════════════════════════════════════
# CLASSIFY
# ═══════════════════════════════════════════════════════════════


@app.post("/classify")
async def classify_all():
    """Tüm BELIRSIZ backlink'leri sınıflandır."""
    from classifier.rules import classify_backlink

    async with async_session() as session:
        result = await session.execute(
            select(Backlink).where(Backlink.category == "BELIRSIZ")
        )
        backlinks = result.scalars().all()
        counts: dict = {}
        for bl in backlinks:
            row = {
                "referring_url": bl.referring_url,
                "referring_title": bl.referring_title or "",
                "anchor_text": bl.anchor_text or "",
                "is_spam_flag": bl.is_spam_flag,
            }
            cat, detail = classify_backlink(row)
            bl.category = cat
            bl.category_detail = detail
            counts[cat] = counts.get(cat, 0) + 1
        await session.commit()

    return {"classified": sum(counts.values()), "breakdown": counts}


@app.post("/classify/multi-signal")
async def classify_multi_signal():
    from classifier.multi_signal import reclassify_all

    results = await reclassify_all()
    return {"method": "multi_signal", "results": results}


@app.post("/classify/analyze/{domain}")
async def analyze_domain(domain: str):
    from classifier.multi_signal import calculate_multi_signal_score

    async with async_session() as session:
        result = await calculate_multi_signal_score(f"https://{domain}/", session)
    return result


# ═══════════════════════════════════════════════════════════════
# BACKLINKS
# ═══════════════════════════════════════════════════════════════


@app.get("/backlinks")
async def list_backlinks(
    category: str | None = Query(None),
    min_spam_score: int = Query(0, ge=0, le=100),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """Backlink listesi (filter + paginated)."""
    where = "WHERE 1=1"
    params: dict = {"limit": limit, "offset": offset, "min_score": min_spam_score}
    if category and category != "all":
        where += " AND category = :cat"
        params["cat"] = category
    if min_spam_score > 0:
        where += " AND spam_score >= :min_score"

    async with async_session() as session:
        total_q = await session.execute(
            text(f"SELECT count(*) FROM backlinks {where}"), params
        )
        total = total_q.scalar() or 0

        rows = await session.execute(
            text(
                f"SELECT id, referring_url, referring_title, anchor_text, target_domain, "
                f"spam_score, category, category_detail, domain_rating, traffic, "
                f"platform, is_rendered, is_raw, first_seen, last_seen "
                f"FROM backlinks {where} "
                f"ORDER BY spam_score DESC, domain_rating DESC NULLS LAST "
                f"LIMIT :limit OFFSET :offset"
            ),
            params,
        )
        out = []
        for r in rows.all():
            out.append(
                {
                    "id": r[0],
                    "referring_url": r[1],
                    "referring_title": r[2],
                    "anchor_text": r[3],
                    "target_domain": r[4],
                    "spam_score": r[5],
                    "category": r[6],
                    "category_detail": r[7],
                    "domain_rating": float(r[8]) if r[8] else None,
                    "traffic": r[9],
                    "platform": r[10],
                    "is_rendered": r[11],
                    "is_raw": r[12],
                    "first_seen": r[13].isoformat() if r[13] else None,
                    "last_seen": r[14].isoformat() if r[14] else None,
                }
            )

        # Detay dağılımı (filtreye göre)
        detail_q = await session.execute(
            text(
                f"SELECT category_detail, count(*) FROM backlinks {where} "
                f"GROUP BY category_detail ORDER BY 2 DESC LIMIT 15"
            ),
            {k: v for k, v in params.items() if k not in ("limit", "offset")},
        )
        detail_dist = [{"detail": r[0] or "—", "count": r[1]} for r in detail_q.all()]

    return {
        "total": total,
        "count": len(out),
        "offset": offset,
        "limit": limit,
        "backlinks": out,
        "detail_breakdown": detail_dist,
    }


# ═══════════════════════════════════════════════════════════════
# VICTIMS / SITES
# ═══════════════════════════════════════════════════════════════


@app.get("/victims")
async def list_victims(
    site_type: str | None = Query(None),
    verified: str | None = Query(None),
    limit: int = Query(200, ge=1, le=2000),
):
    """Mağdur siteleri listele (filter destekli)."""
    where = "WHERE b.category='MAGDUR'"
    params: dict = {"limit": limit}
    if site_type and site_type != "all":
        where += " AND b.category_detail = :tip"
        params["tip"] = site_type
    if verified == "verified":
        where += " AND s.injection_verified IS TRUE"
    elif verified == "pending":
        where += " AND (s.injection_verified IS NULL OR s.injection_verified = FALSE)"

    async with async_session() as session:
        rows = await session.execute(
            text(
                f"SELECT DISTINCT ON (b.referring_url) "
                f"b.referring_url, b.referring_title, b.anchor_text, "
                f"b.domain_rating, b.traffic, b.platform, b.spam_score, "
                f"b.category_detail, b.first_seen, b.last_seen, "
                f"s.injection_verified, s.status, s.last_crawled_at "
                f"FROM backlinks b "
                f"LEFT JOIN sites s ON s.domain = split_part(split_part(b.referring_url, '://', 2), '/', 1) "
                f"{where} "
                f"ORDER BY b.referring_url, b.domain_rating DESC NULLS LAST "
                f"LIMIT :limit"
            ),
            params,
        )
        out = []
        for r in rows.all():
            out.append(
                {
                    "url": r[0],
                    "title": r[1],
                    "anchor": r[2],
                    "dr": float(r[3]) if r[3] else None,
                    "traffic": r[4],
                    "platform": r[5],
                    "spam_score": r[6],
                    "type": r[7],
                    "first_seen": r[8].isoformat() if r[8] else None,
                    "last_seen": r[9].isoformat() if r[9] else None,
                    "verified": r[10],
                    "crawl_status": r[11],
                    "last_crawl": r[12].isoformat() if r[12] else None,
                }
            )

    return {"count": len(out), "victims": out}


@app.get("/sites/recent")
async def recent_sites(limit: int = 20):
    """Son crawl edilen siteler."""
    async with async_session() as session:
        rows = await session.execute(
            text(
                "SELECT s.domain, s.status, s.injection_verified, s.platform, "
                "s.last_crawled_at, "
                "(SELECT count(*) FROM detected_hacklinks h WHERE h.site_id = s.id) "
                "FROM sites s WHERE s.last_crawled_at IS NOT NULL "
                "ORDER BY s.last_crawled_at DESC LIMIT :limit"
            ),
            {"limit": limit},
        )
        out = []
        for r in rows.all():
            out.append(
                {
                    "domain": r[0],
                    "status": r[1],
                    "verified": r[2],
                    "platform": r[3],
                    "last_crawled_at": r[4].isoformat() if r[4] else None,
                    "hacklink_count": r[5],
                }
            )
    return {"count": len(out), "sites": out}


# ═══════════════════════════════════════════════════════════════
# CRAWL & CONTACTS
# ═══════════════════════════════════════════════════════════════


@app.post("/crawl/{domain}")
async def crawl_site(domain: str):
    """Bir siteyi crawl kuyruğuna ekle. Crawler container BLPOP ile dinliyor."""
    import json as _json
    import redis.asyncio as aioredis

    url = f"https://{domain}/" if not domain.startswith("http") else domain
    r = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        await r.lpush("abuseradar:crawl_queue", url)
        # Status'u "queued" olarak işaretle
        await r.set(
            f"abuseradar:crawl_status:{domain}",
            _json.dumps({"status": "queued", "url": url}),
            ex=86400,
        )
    finally:
        await r.aclose()
    return {"queued": True, "domain": domain, "url": url}


@app.get("/crawl/{domain}/status")
async def crawl_status(domain: str):
    """Crawl durumunu öğren (queued / running / completed / error)."""
    import json as _json
    import redis.asyncio as aioredis

    r = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        raw = await r.get(f"abuseradar:crawl_status:{domain}")
    finally:
        await r.aclose()
    if not raw:
        return {"domain": domain, "status": "unknown"}
    try:
        return {"domain": domain, **_json.loads(raw)}
    except Exception:
        return {"domain": domain, "status": "unknown"}


@app.post("/contacts/{domain}")
async def find_contacts(domain: str):
    """Bir site için iletişim bilgisi bul + DB'ye kaydet (Site + Contact row)."""
    from contacts.finder import find_all_contacts

    contacts_data = await find_all_contacts(f"https://{domain}/", domain)

    saved = []
    async with async_session() as session:
        # Site row'u var mı, yoksa oluştur
        site_q = await session.execute(select(Site).where(Site.domain == domain))
        site = site_q.scalar_one_or_none()
        if not site:
            site = Site(domain=domain, url=f"https://{domain}/", status="contact_search")
            session.add(site)
            await session.commit()
            await session.refresh(site)

        for c in contacts_data:
            email = c.get("email")
            if not email:
                continue
            # Var mı kontrol
            existing_q = await session.execute(
                select(Contact).where(Contact.site_id == site.id, Contact.email == email)
            )
            existing = existing_q.scalar_one_or_none()
            if existing:
                saved.append({
                    "id": existing.id, "email": existing.email,
                    "source": existing.source, "contact_type": existing.contact_type,
                })
                continue
            new_c = Contact(
                site_id=site.id,
                email=email,
                source=c.get("source", "unknown"),
                contact_type=c.get("contact_type", "other"),
                language=c.get("language"),
            )
            session.add(new_c)
            await session.commit()
            await session.refresh(new_c)
            saved.append({
                "id": new_c.id, "email": new_c.email,
                "source": new_c.source, "contact_type": new_c.contact_type,
            })

    return {"domain": domain, "count": len(saved), "contacts": saved}


@app.get("/contacts/{domain}/saved")
async def list_saved_contacts(domain: str):
    """DB'deki kayıtlı contact'ları döndür."""
    async with async_session() as session:
        site_q = await session.execute(select(Site).where(Site.domain == domain))
        site = site_q.scalar_one_or_none()
        if not site:
            return {"domain": domain, "count": 0, "contacts": []}
        rows = await session.execute(
            select(Contact).where(Contact.site_id == site.id).order_by(Contact.id)
        )
        contacts = [
            {
                "id": c.id, "email": c.email,
                "source": c.source, "contact_type": c.contact_type,
                "language": c.language,
            }
            for c in rows.scalars().all()
        ]
    return {"domain": domain, "count": len(contacts), "contacts": contacts}


@app.post("/notifications/send-batch")
async def send_batch(payload: dict):
    """Seçili contact_id'lere mail at. Max 10 cap.

    Body: {"contact_ids": [int], "language": "tr|en|..."}
    """
    contact_ids = payload.get("contact_ids") or []
    language = payload.get("language")
    if not contact_ids:
        raise HTTPException(400, "contact_ids gerekli")
    if len(contact_ids) > 10:
        raise HTTPException(400, "Max 10 contact (spam koruması)")

    from notifier.sender import send_alert

    results = []
    async with async_session() as session:
        for cid in contact_ids:
            c = await session.get(Contact, int(cid))
            if not c:
                results.append({"contact_id": cid, "status": "error", "reason": "contact_not_found"})
                continue
            site = await session.get(Site, c.site_id)
            if not site:
                results.append({"contact_id": cid, "status": "error", "reason": "site_not_found"})
                continue

            r = await send_alert(
                site_id=site.id,
                contact_id=c.id,
                domain=site.domain,
                url=site.url or f"https://{site.domain}/",
                hacklink_count=0,
                first_seen=str(site.created_at),
                language=language,
            )
            r["email"] = c.email
            r["domain"] = site.domain
            results.append(r)

    sent = sum(1 for r in results if r.get("status") == "sent")
    skipped = sum(1 for r in results if r.get("status") == "skipped")
    errors = sum(1 for r in results if r.get("status") == "error")
    return {"sent": sent, "skipped": skipped, "errors": errors, "results": results}


# ═══════════════════════════════════════════════════════════════
# PIPELINE
# ═══════════════════════════════════════════════════════════════


@app.post("/pipeline/run")
async def run_pipeline(auto_crawl: bool = False):
    from pipeline import run_full_pipeline

    return await run_full_pipeline(auto_crawl=auto_crawl)


@app.get("/pipeline/status")
async def pipeline_status():
    from pipeline import get_pipeline_status

    return await get_pipeline_status()


@app.get("/pipeline/attackers")
async def list_attackers():
    from pipeline import extract_attacker_domains

    attackers = await extract_attacker_domains()
    return {"count": len(attackers), "attackers": attackers}


@app.get("/pipeline/unverified")
async def pipeline_unverified(limit: int = 50):
    """Doğrulanmamış mağdur siteler (crawl bekliyor)."""
    async with async_session() as session:
        rows = await session.execute(
            text(
                "SELECT DISTINCT "
                "  split_part(split_part(b.referring_url, '://', 2), '/', 1) AS domain, "
                "  b.referring_url, b.category_detail, b.domain_rating, b.traffic "
                "FROM backlinks b "
                "LEFT JOIN sites s ON s.domain = split_part(split_part(b.referring_url, '://', 2), '/', 1) "
                "WHERE b.category = 'MAGDUR' "
                "  AND (s.last_crawled_at IS NULL OR s.injection_verified IS NULL) "
                "ORDER BY b.domain_rating DESC NULLS LAST LIMIT :limit"
            ),
            {"limit": limit},
        )
        out = [
            {
                "domain": r[0],
                "url": r[1],
                "type": r[2],
                "dr": float(r[3]) if r[3] else None,
                "traffic": r[4],
            }
            for r in rows.all()
        ]
    return {"count": len(out), "sites": out}


@app.get("/pipeline/verified")
async def pipeline_verified(limit: int = 100):
    """Doğrulanmış mağdurlar — sikayet/email için hazır."""
    async with async_session() as session:
        rows = await session.execute(
            text(
                "SELECT s.domain, s.status, s.platform, s.last_crawled_at, "
                "(SELECT count(*) FROM detected_hacklinks h WHERE h.site_id = s.id) AS hacklink_count, "
                "(SELECT count(*) FROM contacts c WHERE c.site_id = s.id) AS contact_count, "
                "(SELECT count(*) FROM notifications n WHERE n.site_id = s.id AND n.status = 'sent') AS sent_count "
                "FROM sites s WHERE s.injection_verified = true "
                "ORDER BY s.last_crawled_at DESC LIMIT :limit"
            ),
            {"limit": limit},
        )
        out = [
            {
                "domain": r[0],
                "status": r[1],
                "platform": r[2],
                "last_crawled_at": r[3].isoformat() if r[3] else None,
                "hacklink_count": r[4],
                "contact_count": r[5],
                "notifications_sent": r[6],
            }
            for r in rows.all()
        ]
    return {"count": len(out), "sites": out}


# ═══════════════════════════════════════════════════════════════
# COMPLAINTS & NOTIFICATIONS
# ═══════════════════════════════════════════════════════════════


@app.get("/complaints")
async def list_complaints(
    platform: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
):
    where = "WHERE 1=1"
    params: dict = {"limit": limit}
    if platform and platform != "all":
        where += " AND platform = :p"
        params["p"] = platform
    if status and status != "all":
        where += " AND status = :s"
        params["s"] = status

    async with async_session() as session:
        rows = await session.execute(
            text(
                f"SELECT id, target_domain, target_type, platform, status, "
                f"submitted_at, followup_count, max_followups, next_check_at, "
                f"resolved_at, notes, created_at "
                f"FROM complaints {where} ORDER BY created_at DESC LIMIT :limit"
            ),
            params,
        )
        out = []
        for r in rows.all():
            out.append(
                {
                    "id": r[0],
                    "target_domain": r[1],
                    "target_type": r[2],
                    "platform": r[3],
                    "status": r[4],
                    "submitted_at": r[5].isoformat() if r[5] else None,
                    "followup_count": r[6],
                    "max_followups": r[7],
                    "next_check_at": r[8].isoformat() if r[8] else None,
                    "resolved_at": r[9].isoformat() if r[9] else None,
                    "notes": r[10],
                    "created_at": r[11].isoformat() if r[11] else None,
                }
            )

        # Status dağılımı
        dist_q = await session.execute(
            text("SELECT status, count(*) FROM complaints GROUP BY status")
        )
        dist = [{"status": r[0], "count": r[1]} for r in dist_q.all()]

    return {"count": len(out), "complaints": out, "status_breakdown": dist}


@app.get("/notifications")
async def list_notifications(
    status: str | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
):
    where = "WHERE 1=1"
    params: dict = {"limit": limit}
    if status and status != "all":
        where += " AND n.status = :s"
        params["s"] = status

    async with async_session() as session:
        rows = await session.execute(
            text(
                f"SELECT n.id, s.domain, c.email, n.email_type, n.language, n.status, "
                f"n.send_count, n.max_sends, n.sent_at, n.injection_still_active, "
                f"n.remediated_at, n.created_at "
                f"FROM notifications n "
                f"JOIN sites s ON n.site_id = s.id "
                f"JOIN contacts c ON n.contact_id = c.id "
                f"{where} ORDER BY n.created_at DESC LIMIT :limit"
            ),
            params,
        )
        out = []
        for r in rows.all():
            out.append(
                {
                    "id": r[0],
                    "domain": r[1],
                    "email": r[2],
                    "email_type": r[3],
                    "language": r[4],
                    "status": r[5],
                    "send_count": r[6],
                    "max_sends": r[7],
                    "sent_at": r[8].isoformat() if r[8] else None,
                    "injection_still_active": r[9],
                    "remediated_at": r[10].isoformat() if r[10] else None,
                    "created_at": r[11].isoformat() if r[11] else None,
                }
            )
    return {"count": len(out), "notifications": out}


@app.get("/notification-templates/{lang}")
async def get_notification_template(lang: str):
    """Email şablonunu oku (tr, en, pt, es, fr)."""
    if lang not in ("tr", "en", "pt", "es", "fr"):
        raise HTTPException(404, "Geçerli diller: tr, en, pt, es, fr")
    p = Path("/app/notifier/templates") / f"alert_{lang}.txt"
    if not p.exists():
        # Local fallback
        p = Path(__file__).parent / "notifier" / "templates" / f"alert_{lang}.txt"
    if not p.exists():
        raise HTTPException(404, f"Şablon bulunamadı: {lang}")
    return PlainTextResponse(p.read_text(encoding="utf-8"))


# ═══════════════════════════════════════════════════════════════
# C2
# ═══════════════════════════════════════════════════════════════


@app.get("/c2")
async def list_c2():
    async with async_session() as session:
        result = await session.execute(select(C2Domain))
        c2s = [
            {
                "id": c.id,
                "domain": c.domain,
                "role": c.role,
                "status": c.status,
                "ip_address": c.ip_address,
                "asn": c.asn,
                "hosting_provider": c.hosting_provider,
                "cloudflare_protected": c.cloudflare_protected,
                "registrar": c.registrar,
                "first_seen": c.first_seen.isoformat() if c.first_seen else None,
            }
            for c in result.scalars().all()
        ]

    return {"count": len(c2s), "c2_domains": c2s}


@app.post("/c2")
async def add_c2(payload: dict):
    """Yeni C2 domain ekle. Body: {domain, role, status}"""
    domain = (payload.get("domain") or "").strip().lower()
    role = payload.get("role") or "primary_c2_panel"
    status = payload.get("status") or "active"

    if not domain:
        raise HTTPException(400, "domain gerekli")
    if role not in (
        "primary_c2_panel", "fallback_c2_panel", "script_host", "pbn_hub"
    ):
        raise HTTPException(400, "Geçersiz rol")

    async with async_session() as session:
        existing = await session.execute(
            select(C2Domain).where(C2Domain.domain == domain)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(409, f"{domain} zaten mevcut")

        c2 = C2Domain(domain=domain, role=role, status=status)
        session.add(c2)
        await session.commit()
        await session.refresh(c2)

    return {"id": c2.id, "domain": c2.domain, "role": c2.role, "status": c2.status}


# ═══════════════════════════════════════════════════════════════
# COMPLAIN
# ═══════════════════════════════════════════════════════════════


@app.get("/hosting/{domain}")
async def hosting_info(domain: str):
    from complainant.hosting import get_hosting_info

    return await get_hosting_info(domain)


@app.get("/complaint-targets/{domain}")
async def complaint_targets(domain: str):
    from complainant.hosting import get_complaint_targets

    return await get_complaint_targets(domain)


@app.post("/complain/hosting/{domain}")
async def complain_hosting(domain: str):
    from complainant.hosting import get_hosting_info, report_to_hosting

    info = await get_hosting_info(domain)
    if not info.get("abuse_email"):
        return {"error": f"{domain} için hosting abuse email bulunamadı", "info": info}

    result = await report_to_hosting(
        domain=domain,
        abuse_email=info["abuse_email"],
        issue_type="injection",
        evidence_summary=f"Hidden gambling backlinks detected on {domain}.",
    )
    return {"domain": domain, "hosting": info, "result": result}


@app.post("/complain/cloudflare/{domain}")
async def complain_cloudflare(domain: str):
    from complainant.openclaw import report_cloudflare

    async with async_session() as session:
        result = await session.execute(
            select(C2Domain).where(C2Domain.domain == domain)
        )
        c2 = result.scalar_one_or_none()

    if not c2:
        return {"error": f"{domain} C2 listesinde bulunamadı"}

    res = await report_cloudflare(
        target_domain=domain,
        target_role=c2.role or "C2 panel",
        reporter_email=settings.email_from,
        affected_gov_sites="(see database for full list)",
        injection_method="JavaScript injection via js_api.php",
        script_endpoint=f"https://{domain}/panel/js_api.php",
        affected_count=500,
        first_seen=str(c2.first_seen or "2025-01"),
    )
    return {"domain": domain, "platform": "cloudflare", "result": res}


@app.post("/complain/all/{domain}")
async def complain_all(domain: str):
    from complainant.openclaw import run_all_complaints_for_c2

    evidence = {
        "role": "C2 panel",
        "gov_sites": "saogoncalo.rj.gov.br, fundec.rj.gov.br, psc.gov.lk, ui.edu.ng",
        "method": "JavaScript injection via js_api.php",
        "endpoint": f"https://{domain}/panel/js_api.php",
        "affected_count": 500,
        "first_seen": "2025-01",
    }

    results = await run_all_complaints_for_c2(domain, evidence)
    return {"domain": domain, "results": results}


# ═══════════════════════════════════════════════════════════════
# EVIDENCE
# ═══════════════════════════════════════════════════════════════


@app.get("/evidence")
async def evidence_list():
    """Tüm evidence bundle'larını listele."""
    bundles = evidence_reader.list_bundles()
    # captured_at'ı ISO string'e çevir
    for b in bundles:
        if b.get("captured_at"):
            b["captured_at"] = datetime.fromtimestamp(b["captured_at"]).isoformat()
    return {"count": len(bundles), "bundles": bundles}


@app.get("/evidence/{domain}")
async def evidence_detail(domain: str):
    bundle = evidence_reader.get_bundle(domain)
    if not bundle:
        raise HTTPException(404, f"Bundle bulunamadı: {domain}")
    if bundle.get("captured_at"):
        bundle["captured_at"] = datetime.fromtimestamp(bundle["captured_at"]).isoformat()
    return bundle


@app.get("/evidence/{domain}/screenshot/{idx}")
async def evidence_screenshot(domain: str, idx: int):
    p = evidence_reader.get_screenshot_path(domain, idx)
    if not p:
        raise HTTPException(404, "Screenshot bulunamadı")
    return FileResponse(str(p), media_type="image/png")


@app.post("/reports/{domain}/share")
async def share_report(domain: str):
    """Public token üret/varsa varolanı dön. URL: https://abuseradar.org/r.html?t={token}"""
    import secrets
    from datetime import timedelta

    safe = domain.strip().lower()
    async with async_session() as session:
        existing_q = await session.execute(
            select(ReportToken).where(ReportToken.domain == safe)
        )
        existing = existing_q.scalar_one_or_none()
        if existing and not existing.revoked:
            token = existing.token
        else:
            # 8 byte = ~11 char URL-safe = 64-bit entropy. Brute-force imkansız
            # ama URL'i kısa/insan-dostu tutar (24 char rastgele görünmez).
            token = secrets.token_urlsafe(8)
            if existing:
                existing.token = token
                existing.revoked = False
                existing.created_at = datetime.now(timezone.utc)
                existing.expires_at = datetime.now(timezone.utc) + timedelta(days=180)
                existing.view_count = 0
            else:
                session.add(ReportToken(
                    token=token, domain=safe,
                    expires_at=datetime.now(timezone.utc) + timedelta(days=180),
                ))
            await session.commit()

    # Human-readable URL with domain visible: /r/{domain}/{token}
    public_url = f"{settings.public_base_url}/r/{safe}/{token}"
    return {
        "domain": safe,
        "token": token,
        "public_url": public_url,
        "expires_in_days": 180,
    }


@app.delete("/reports/{domain}/share")
async def revoke_report(domain: str):
    """Public link'i iptal et."""
    safe = domain.strip().lower()
    async with async_session() as session:
        existing_q = await session.execute(
            select(ReportToken).where(ReportToken.domain == safe)
        )
        existing = existing_q.scalar_one_or_none()
        if not existing:
            raise HTTPException(404, "No public link to revoke")
        existing.revoked = True
        await session.commit()
    return {"revoked": True, "domain": safe}


@app.get("/public/reports/{token}")
async def public_report(token: str):
    """AUTH GEREKMEZ. Token doğrulayıp aggregate bundle JSON'ı döner.

    nginx config'inde /api/public/* basic auth'tan exempt edilmiş olmalı.
    """
    async with async_session() as session:
        rt_q = await session.execute(
            select(ReportToken).where(ReportToken.token == token)
        )
        rt = rt_q.scalar_one_or_none()
        if not rt:
            raise HTTPException(404, "Invalid or expired link")
        if rt.revoked:
            raise HTTPException(403, "Link revoked")
        if rt.expires_at and rt.expires_at < datetime.now(timezone.utc):
            raise HTTPException(410, "Link expired")
        # View tracking
        rt.view_count = (rt.view_count or 0) + 1
        rt.last_viewed_at = datetime.now(timezone.utc)
        await session.commit()
        domain = rt.domain

    # Bundle ve hacklinks verisini döndür
    bundle = evidence_reader.get_bundle(domain)
    if not bundle:
        raise HTTPException(404, "Bundle not found for this domain")
    if bundle.get("captured_at"):
        bundle["captured_at"] = datetime.fromtimestamp(bundle["captured_at"]).isoformat()

    hacklinks = evidence_reader.get_hacklinks(domain) or {}

    # Hosting info AYRI endpoint'e taşındı (WHOIS yavaş, lazy load).
    return {
        "domain": domain,
        "bundle": bundle,
        "hacklinks": hacklinks,
        "view_count": rt.view_count,
    }


@app.get("/public/reports/{token}/hosting")
async def public_report_hosting(token: str):
    """AUTH GEREKMEZ. Hosting/WHOIS info — CACHE'TEN (crawl sırasında yazılan hosting.json).
    Cache yoksa anlık WHOIS fallback (sadece bir kez)."""
    async with async_session() as session:
        rt_q = await session.execute(
            select(ReportToken).where(ReportToken.token == token)
        )
        rt = rt_q.scalar_one_or_none()
        if not rt or rt.revoked:
            raise HTTPException(404, "Invalid link")
        if rt.expires_at and rt.expires_at < datetime.now(timezone.utc):
            raise HTTPException(410, "Link expired")
        domain = rt.domain
    # Cache hit
    cached = evidence_reader.get_hosting(domain)
    if cached:
        cached["_cached"] = True
        return cached
    # Fallback — anlık WHOIS
    try:
        from complainant.hosting import get_hosting_info
        info = await get_hosting_info(domain)
        # Cache'e yaz (sonraki çağrılar için)
        try:
            from pathlib import Path
            out = Path(settings.evidence_path) / domain / "analysis"
            out.mkdir(parents=True, exist_ok=True)
            import json as _json
            (out / "hosting.json").write_text(_json.dumps(info, default=str), encoding="utf-8")
        except Exception:
            pass
        return info
    except Exception as e:
        return {"error": str(e)}


@app.post("/complain/target/{target_domain}")
async def complain_target(target_domain: str, request: Request):
    """Tek bir saldırgan target_domain için tüm şikayet zincirini tetikle.

    Body (JSON, opsiyonel):
      {
        "affected_gov_sites": ["ulm.edu.pk", "..."],
        "hacklink_count": 12,
        "report_url": "https://abuseradar.org/r/.../...",
        "enable_form": true,    # OpenClaw browser otomasyon
        "enable_mail": true     # ZeptoMail abuse mail
      }
    """
    from complainant.complaint_chain import run_chain_for_target

    body: dict = {}
    try:
        body = await request.json()
    except Exception:
        pass

    target_domain = (target_domain or "").strip().lower()
    if not target_domain or "." not in target_domain:
        raise HTTPException(400, "Invalid target_domain")

    result = await run_chain_for_target(
        target_domain=target_domain,
        affected_gov_sites=body.get("affected_gov_sites") or [],
        hacklink_count=int(body.get("hacklink_count") or 0),
        injection_method=body.get("injection_method") or "JS injection (hidden anchors)",
        report_url=body.get("report_url") or "",
        enable_form=bool(body.get("enable_form", True)),
        enable_mail=bool(body.get("enable_mail", True)),
    )
    return result


@app.get("/complain/discover-targets")
async def discover_complaint_targets(min_count: int = 2, limit: int = 50):
    """DB'den şikayet edilebilecek target_domain'leri çıkar.

    Kriter:
      - DetectedHacklink tablosunda en az `min_count` defa görülmüş
      - Major service değil (safe_domains)
      - Eşsiz target_domain
    """
    from sqlalchemy import select, func as sa_func
    from models.database import DetectedHacklink, Site
    from utils.safe_domains import is_safe_domain

    async with async_session() as session:
        rows = (await session.execute(
            select(
                DetectedHacklink.target_domain,
                sa_func.count(sa_func.distinct(DetectedHacklink.site_id)).label("victim_count"),
                sa_func.count(DetectedHacklink.id).label("link_count"),
            )
            .where(DetectedHacklink.target_domain.isnot(None))
            .group_by(DetectedHacklink.target_domain)
            .having(sa_func.count(sa_func.distinct(DetectedHacklink.site_id)) >= min_count)
            .order_by(sa_func.count(sa_func.distinct(DetectedHacklink.site_id)).desc())
            .limit(limit)
        )).all()

    out = []
    for r in rows:
        td = (r.target_domain or "").strip().lower()
        if not td or is_safe_domain(td):
            continue
        out.append({
            "target_domain": td,
            "victim_count": r.victim_count,
            "link_count": r.link_count,
        })
    return {"count": len(out), "targets": out}


@app.get("/complain/target/{target_domain}/timeline")
async def complain_target_timeline(target_domain: str):
    """Bir target_domain için tüm şikayet aktivitesi (mail + form).

    Frontend Complaint detail sayfası bunu kullanır.
    """
    from models.database import Complaint, MailLog
    target_domain = target_domain.strip().lower()

    async with async_session() as session:
        comps = (await session.execute(
            select(Complaint)
            .where(Complaint.target_domain == target_domain)
            .order_by(Complaint.created_at.desc())
        )).scalars().all()

        # Mail kanalı için mail_log'da target_domain'i abuse@cloudflare.com vb.
        # gönderim yapmadığımız için bağlantıyı subject'tan kuruyoruz.
        # subject "AbuseRadar notice: <td>" ile başlar.
        mails = (await session.execute(
            select(MailLog)
            .where(MailLog.subject.like(f"%: {target_domain}%"))
            .order_by(MailLog.sent_at.desc())
            .limit(50)
        )).scalars().all()

    return {
        "target_domain": target_domain,
        "complaints": [
            {
                "id": c.id,
                "platform": c.platform,
                "platform_detail": c.platform_detail,
                "status": c.status,
                "submitted_at": c.submitted_at.isoformat() if c.submitted_at else None,
                "next_check_at": c.next_check_at.isoformat() if c.next_check_at else None,
                "evidence_path": c.evidence_path,
                "notes": c.notes,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "kind": "form",
            }
            for c in comps
        ],
        "mails": [
            {
                "id": m.id,
                "to_email": m.to_email,
                "provider": m.recipient_provider,
                "subject": m.subject,
                "status": m.status,
                "sent_at": m.sent_at.isoformat() if m.sent_at else None,
                "kind": "mail",
            }
            for m in mails
        ],
    }


@app.get("/complain/evidence/{filename}")
async def complain_evidence_screenshot(filename: str):
    """Playwright filler tarafından alınan abuse form screenshot'ı."""
    from pathlib import Path
    if "/" in filename or ".." in filename or not filename.endswith(".png"):
        raise HTTPException(400, "Invalid filename")
    p = Path("/data/openclaw-workspace/evidence") / filename
    if not p.is_file():
        raise HTTPException(404, "Screenshot bulunamadı")
    return FileResponse(str(p), media_type="image/png")


@app.get("/complaints/log")
async def complaints_log(limit: int = 200, target_domain: str | None = None):
    """Tüm complaint kayıtları (audit trail). Frontend Complaints sayfasında listele."""
    from models.database import Complaint

    q = select(Complaint).order_by(Complaint.created_at.desc()).limit(min(limit, 1000))
    if target_domain:
        q = q.where(Complaint.target_domain == target_domain.strip().lower())
    async with async_session() as session:
        rows = (await session.execute(q)).scalars().all()
    return [
        {
            "id": r.id,
            "target_domain": r.target_domain,
            "target_type": r.target_type,
            "platform": r.platform,
            "platform_detail": r.platform_detail,
            "status": r.status,
            "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
            "evidence_path": r.evidence_path,
            "notes": (r.notes or "")[:200],
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@app.get("/mail-stats/today")
async def mail_stats_today():
    """Bugünkü gönderim istatistikleri — provider bazında.

    Warm-up sürecini izlemek için: hangi provider'a kaç mail gitti, limit ne.
    """
    from notifier.provider import PROVIDER_DAILY_LIMITS, daily_limit_for
    from models.database import MailLog

    async with async_session() as session:
        today_start = datetime.utcnow() - timedelta(hours=24)
        rows = await session.execute(
            select(
                MailLog.recipient_provider,
                MailLog.status,
                func.count(MailLog.id).label("n"),
            ).where(MailLog.sent_at >= today_start)
            .group_by(MailLog.recipient_provider, MailLog.status)
        )
        result = {}
        total = {"sent": 0, "skipped": 0, "error": 0, "skipped_daily_limit": 0, "simulated": 0}
        for r in rows:
            prov = r.recipient_provider or "unknown"
            st = r.status or "unknown"
            n = r.n
            result.setdefault(prov, {"sent": 0, "skipped_daily_limit": 0, "error": 0, "limit": daily_limit_for(prov)})
            if st in result[prov]:
                result[prov][st] = n
            total[st] = total.get(st, 0) + n

    # Eksik provider'ları da göster
    for prov, lim in PROVIDER_DAILY_LIMITS.items():
        if prov not in result:
            result[prov] = {"sent": 0, "skipped_daily_limit": 0, "error": 0, "limit": lim}

    return {
        "window_hours": 24,
        "total": total,
        "by_provider": result,
    }


@app.get("/mail-stats/contacts")
async def mail_stats_contacts():
    """Mevcut tüm contact'ların MX-based provider dağılımı.

    'Kaç kontak gerçekte Gmail'e yönleniyor?' sorusunun cevabı.
    Bu MX lookup'ları bir defa yapar, ileride limit planlamasına temel.
    """
    from notifier.provider import detect_email_provider

    async with async_session() as session:
        contacts = (await session.execute(select(Contact))).scalars().all()

    counts: dict[str, int] = {}
    domain_seen: dict[str, str] = {}
    for c in contacts:
        email = (c.email or "").strip().lower()
        if "@" not in email:
            continue
        domain = email.split("@", 1)[1]
        if domain not in domain_seen:
            domain_seen[domain] = await detect_email_provider(email)
        prov = domain_seen[domain]
        counts[prov] = counts.get(prov, 0) + 1

    return {
        "total_contacts": len(contacts),
        "by_provider": counts,
        "unique_domains_scanned": len(domain_seen),
    }


@app.get("/mail-log/recent")
async def mail_log_recent(limit: int = 100, status: str | None = None):
    """Son gönderim log'u (audit trail)."""
    from models.database import MailLog

    q = select(MailLog).order_by(MailLog.sent_at.desc()).limit(min(limit, 500))
    if status:
        q = q.where(MailLog.status == status)
    async with async_session() as session:
        rows = (await session.execute(q)).scalars().all()
    return [
        {
            "id": r.id,
            "to_email": r.to_email,
            "to_email_domain": r.to_email_domain,
            "recipient_provider": r.recipient_provider,
            "subject": r.subject,
            "language": r.language,
            "status": r.status,
            "error_message": r.error_message,
            "sent_at": r.sent_at.isoformat() if r.sent_at else None,
        }
        for r in rows
    ]


@app.api_route("/public/unsubscribe", methods=["GET", "POST"])
async def public_unsubscribe(request: Request):
    """RFC 8058 List-Unsubscribe one-click + manuel link.

    Gmail/Yahoo (Şubat 2024+) bulk sender requirements: alıcı tek tıkla
    çıkabilmeli. Bu listedeki email'e bir daha mail gönderilmez.
    """
    email = (request.query_params.get("e", "") or "").strip().lower()
    if not email and request.method == "POST":
        try:
            form = await request.form()
            # one-click POST'ta body 'List-Unsubscribe=One-Click'; email query'de
            email = (form.get("e", "") or "").strip().lower()
        except Exception:
            pass
    if not email or "@" not in email:
        raise HTTPException(400, "Email parameter required")

    from models.database import Unsubscribe
    async with async_session() as session:
        existing = await session.execute(
            select(Unsubscribe).where(Unsubscribe.email == email)
        )
        if not existing.scalar_one_or_none():
            session.add(Unsubscribe(
                email=email,
                source="one_click",
                reason="user_request",
            ))
            await session.commit()

    # Plain text response (one-click), HTML render edilmez
    return PlainTextResponse(
        "You have been unsubscribed.\n"
        "AbuseRadar will not send any further notifications to this address.",
        status_code=200,
    )


@app.get("/public/reports/{token}/screenshot/{name}")
async def public_report_screenshot(token: str, name: str):
    """AUTH GEREKMEZ. Token doğrulayıp screenshot dosyasını döndür."""
    from pathlib import Path
    if "/" in name or ".." in name or not name.endswith(".png"):
        raise HTTPException(400, "Invalid filename")
    async with async_session() as session:
        rt_q = await session.execute(
            select(ReportToken).where(ReportToken.token == token)
        )
        rt = rt_q.scalar_one_or_none()
        if not rt or rt.revoked:
            raise HTTPException(404, "Invalid link")
        if rt.expires_at and rt.expires_at < datetime.now(timezone.utc):
            raise HTTPException(410, "Link expired")
        domain = rt.domain
    p = Path(settings.evidence_path) / domain / "screenshots" / name
    if not p.is_file():
        raise HTTPException(404, "Screenshot not found")
    return FileResponse(str(p), media_type="image/png")


@app.get("/evidence/{domain}/screenshot-by-name/{name}")
async def evidence_screenshot_by_name(domain: str, name: str):
    """Multi-page evidence için filename-tabanlı erişim (01_root_user-view.png vs.)."""
    from pathlib import Path
    if "/" in name or ".." in name or not name.endswith(".png"):
        raise HTTPException(400, "Geçersiz dosya adı")
    p = Path(settings.evidence_path) / domain / "screenshots" / name
    if not p.is_file():
        raise HTTPException(404, "Screenshot bulunamadı")
    return FileResponse(str(p), media_type="image/png")


@app.get("/evidence/{domain}/hacklinks")
async def evidence_hacklinks(domain: str):
    data = evidence_reader.get_hacklinks(domain)
    if data is None:
        raise HTTPException(404, "Hacklinks analizi bulunamadı")
    return data


@app.get("/evidence/{domain}/dom")
async def evidence_dom_list(domain: str):
    return {"files": evidence_reader.list_dom_files(domain)}


@app.get("/evidence/{domain}/dom/{name}")
async def evidence_dom_content(domain: str, name: str):
    content = evidence_reader.get_dom_content(domain, name)
    if content is None:
        raise HTTPException(404, "DOM dosyası bulunamadı")
    return PlainTextResponse(content)


@app.delete("/evidence/{domain}")
async def delete_evidence(domain: str):
    """Bundle'ı sil — filesystem + DB cleanup.

    - /data/evidence/{domain}/ klasörünü tamamen siler
    - sites.last_crawled_at, injection_verified, status sıfırlanır (site row kalır)
    - DetectedHacklink rows site_id'ye göre silinir
    """
    import shutil
    from pathlib import Path

    safe = domain.strip().replace("/", "").replace("..", "")
    if not safe:
        raise HTTPException(400, "domain gerekli")

    # 1. Filesystem
    bundle_dir = Path(settings.evidence_path) / safe
    fs_removed = False
    if bundle_dir.exists() and bundle_dir.is_dir():
        shutil.rmtree(str(bundle_dir))
        fs_removed = True

    # 2. DB cleanup
    async with async_session() as session:
        site_q = await session.execute(select(Site).where(Site.domain == safe))
        site = site_q.scalar_one_or_none()
        if site:
            # Bağlı hacklink'leri sil
            from sqlalchemy import delete
            await session.execute(
                delete(DetectedHacklink).where(DetectedHacklink.site_id == site.id)
            )
            site.last_crawled_at = None
            site.injection_verified = False
            site.status = "pending"
            await session.commit()

    return {"deleted": True, "domain": safe, "filesystem": fs_removed}


@app.delete("/c2/{domain}")
async def delete_c2(domain: str):
    """C2 domain'i sil."""
    from sqlalchemy import delete
    safe = domain.strip().lower()
    async with async_session() as session:
        result = await session.execute(
            delete(C2Domain).where(C2Domain.domain == safe)
        )
        await session.commit()
        if result.rowcount == 0:
            raise HTTPException(404, f"{safe} bulunamadı")
    return {"deleted": True, "domain": safe}


@app.delete("/csv-files/{file_id}")
async def delete_csv_file(file_id: int, purge_backlinks: bool = False):
    """CSV file row sil.

    purge_backlinks=True ise bu CSV'den gelen tüm backlink rows da silinir.
    Default: backlink'ler korunur (csv_file_id NULL'lanır).
    """
    from sqlalchemy import delete, update
    async with async_session() as session:
        cf = await session.get(CsvFile, file_id)
        if not cf:
            raise HTTPException(404, "CSV not found")
        if purge_backlinks:
            await session.execute(delete(Backlink).where(Backlink.csv_file_id == file_id))
        else:
            await session.execute(
                update(Backlink).where(Backlink.csv_file_id == file_id).values(csv_file_id=None)
            )
        await session.delete(cf)
        await session.commit()
    return {"deleted": True, "id": file_id, "purged_backlinks": purge_backlinks}


@app.delete("/backlinks/{backlink_id}")
async def delete_backlink(backlink_id: int):
    from sqlalchemy import delete
    async with async_session() as session:
        result = await session.execute(delete(Backlink).where(Backlink.id == backlink_id))
        await session.commit()
        if result.rowcount == 0:
            raise HTTPException(404, "Backlink not found")
    return {"deleted": True, "id": backlink_id}


@app.delete("/notifications/{notif_id}")
async def delete_notification(notif_id: int):
    from sqlalchemy import delete
    async with async_session() as session:
        result = await session.execute(delete(Notification).where(Notification.id == notif_id))
        await session.commit()
        if result.rowcount == 0:
            raise HTTPException(404, "Notification not found")
    return {"deleted": True, "id": notif_id}


@app.delete("/complaints/{complaint_id}")
async def delete_complaint(complaint_id: int):
    from sqlalchemy import delete
    async with async_session() as session:
        result = await session.execute(delete(Complaint).where(Complaint.id == complaint_id))
        await session.commit()
        if result.rowcount == 0:
            raise HTTPException(404, "Complaint not found")
    return {"deleted": True, "id": complaint_id}


@app.delete("/contacts/saved/{contact_id}")
async def delete_contact(contact_id: int):
    from sqlalchemy import delete
    async with async_session() as session:
        result = await session.execute(delete(Contact).where(Contact.id == contact_id))
        await session.commit()
        if result.rowcount == 0:
            raise HTTPException(404, "Contact not found")
    return {"deleted": True, "id": contact_id}


@app.delete("/sites/{domain}")
async def delete_site(domain: str):
    """Mağdur site kaydını ve bağlı her şeyi sil (cascade).

    - DetectedHacklink, Notification, Contact, Site siler
    - Backlink rows DOKUNULMAZ (CSV intake source-of-truth)
    - Filesystem evidence DOKUNULMAZ (DELETE /evidence/{domain} ayrı)
    """
    from sqlalchemy import delete
    safe = domain.strip().lower()

    async with async_session() as session:
        site_q = await session.execute(select(Site).where(Site.domain == safe))
        site = site_q.scalar_one_or_none()
        if not site:
            raise HTTPException(404, f"{safe} bulunamadı")

        await session.execute(
            delete(Notification).where(Notification.site_id == site.id)
        )
        await session.execute(
            delete(Contact).where(Contact.site_id == site.id)
        )
        await session.execute(
            delete(DetectedHacklink).where(DetectedHacklink.site_id == site.id)
        )
        await session.delete(site)
        await session.commit()

    return {"deleted": True, "domain": safe}


# ═══════════════════════════════════════════════════════════════
# SYSTEM
# ═══════════════════════════════════════════════════════════════


@app.get("/vpn/{name}/status")
async def vpn_status(name: str):
    """VPN egress IP — name: tr veya us. Doğrudan VPN container'ının
    SOCKS proxy'sine bağlanıp ipinfo.io çağırır (docker CLI gerektirmez)."""
    if name not in ("tr", "us"):
        raise HTTPException(400, "name: tr veya us")
    container = f"vpn-{name}"
    proxy_url = f"socks5h://{container}:1080"
    try:
        import httpx
        async with httpx.AsyncClient(proxy=proxy_url, timeout=8.0) as client:
            r = await client.get("https://ipinfo.io/json")
        if r.status_code != 200:
            return {"container": container, "status": "unreachable", "http": r.status_code}
        return {"container": container, "status": "ok", **r.json()}
    except Exception as e:
        return {"container": container, "status": "error", "error": str(e)}


@app.post("/monitor/weekly")
async def run_monitoring():
    from monitoring.scheduler import run_weekly_cycle

    return await run_weekly_cycle()
