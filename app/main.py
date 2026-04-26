"""AbuseRadar - FastAPI Ana Uygulama."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from config import settings
from models.database import async_session, init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title=settings.project_name, lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "project": settings.project_name}


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
            "complaints_filed": "SELECT count(*) FROM complaints WHERE status != 'pending'",
        }
        result = {}
        for key, query in queries.items():
            r = await session.execute(text(query))
            result[key] = r.scalar() or 0

    return result


@app.post("/csv/process")
async def process_csv():
    """inbox/ klasöründeki CSV'leri işle."""
    from csv_processor.parser import process_inbox

    results = await process_inbox()
    return {"processed": len([r for r in results if r["status"] == "completed"]), "results": results}


@app.post("/classify")
async def classify_all():
    """Tüm BELIRSIZ backlink'leri sınıflandır."""
    from classifier.rules import classify_backlink
    from models.database import Backlink
    from sqlalchemy import select

    async with async_session() as session:
        result = await session.execute(
            select(Backlink).where(Backlink.category == "BELIRSIZ")
        )
        backlinks = result.scalars().all()
        counts = {}
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


@app.post("/crawl/{domain}")
async def crawl_site(domain: str):
    """Tek bir siteyi crawl et. Crawler container'da çalıştırılmalı."""
    return {
        "message": f"Crawler VPN-TR üzerinden çalışır. Komut:",
        "command": f"docker compose run --rm crawler python -m crawler.cli https://{domain}/",
    }


@app.get("/victims")
async def list_victims():
    """Mağdur siteleri listele."""
    from models.database import Backlink
    from sqlalchemy import select, func

    async with async_session() as session:
        result = await session.execute(
            select(
                Backlink.referring_url,
                Backlink.referring_title,
                Backlink.anchor_text,
                Backlink.domain_rating,
                Backlink.spam_score,
                Backlink.category_detail,
            )
            .where(Backlink.category == "MAGDUR")
            .order_by(Backlink.domain_rating.desc().nullslast())
            .limit(100)
        )
        victims = [
            {
                "url": r[0],
                "title": r[1],
                "anchor": r[2],
                "dr": float(r[3]) if r[3] else None,
                "spam_score": r[4],
                "detail": r[5],
            }
            for r in result.all()
        ]

    return {"count": len(victims), "victims": victims}


@app.post("/classify/multi-signal")
async def classify_multi_signal():
    """Coklu sinyal ile yeniden siniflandir (daha guvenilir)."""
    from classifier.multi_signal import reclassify_all
    results = await reclassify_all()
    return {"method": "multi_signal", "results": results}


@app.post("/classify/analyze/{domain}")
async def analyze_domain(domain: str):
    """Tek domain icin coklu sinyal analizi."""
    from classifier.multi_signal import calculate_multi_signal_score
    async with async_session() as session:
        result = await calculate_multi_signal_score(f"https://{domain}/", session)
    return result


@app.post("/pipeline/run")
async def run_pipeline(auto_crawl: bool = False):
    """Tam pipeline: CSV isle → siniflandir → saldirgan listesi → (opsiyonel) crawl."""
    from pipeline import run_full_pipeline
    return await run_full_pipeline(auto_crawl=auto_crawl)


@app.get("/pipeline/status")
async def pipeline_status():
    """Pipeline durumunu goster."""
    from pipeline import get_pipeline_status
    return await get_pipeline_status()


@app.get("/pipeline/attackers")
async def list_attackers():
    """Saldirgan domain listesi."""
    from pipeline import extract_attacker_domains
    attackers = await extract_attacker_domains()
    return {"count": len(attackers), "attackers": attackers}


@app.post("/contacts/{domain}")
async def find_contacts(domain: str):
    """Bir site için iletişim bilgisi bul."""
    from contacts.finder import find_all_contacts

    contacts = await find_all_contacts(f"https://{domain}/", domain)
    return {"domain": domain, "count": len(contacts), "contacts": contacts}


@app.post("/monitor/weekly")
async def run_monitoring():
    """Haftalık monitoring döngüsünü tetikle."""
    from monitoring.scheduler import run_weekly_cycle

    result = await run_weekly_cycle()
    return result


@app.get("/hosting/{domain}")
async def hosting_info(domain: str):
    """Domain'in hosting bilgisi: IP, provider, CF durumu, abuse email."""
    from complainant.hosting import get_hosting_info
    return await get_hosting_info(domain)


@app.get("/complaint-targets/{domain}")
async def complaint_targets(domain: str):
    """Bir domain icin tum sikayet hedeflerini goster."""
    from complainant.hosting import get_complaint_targets
    return await get_complaint_targets(domain)


@app.post("/complain/hosting/{domain}")
async def complain_hosting(domain: str):
    """Hosting provider'a abuse raporu gonder."""
    from complainant.hosting import get_hosting_info, report_to_hosting

    info = await get_hosting_info(domain)
    if not info.get("abuse_email"):
        return {"error": f"{domain} icin hosting abuse email bulunamadi", "info": info}

    result = await report_to_hosting(
        domain=domain,
        abuse_email=info["abuse_email"],
        issue_type="injection",
        evidence_summary=f"Hidden gambling backlinks detected on {domain}.",
    )
    return {"domain": domain, "hosting": info, "result": result}


@app.post("/complain/cloudflare/{domain}")
async def complain_cloudflare(domain: str):
    """OpenClaw ile Cloudflare abuse formu doldur."""
    from complainant.openclaw import report_cloudflare
    from models.database import C2Domain
    from sqlalchemy import select

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
    """OpenClaw ile tüm şikayet formlarını doldur (CF + Google + ICANN)."""
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


@app.get("/c2")
async def list_c2():
    """C2 domainlerini listele."""
    from models.database import C2Domain
    from sqlalchemy import select

    async with async_session() as session:
        result = await session.execute(select(C2Domain))
        c2s = [
            {
                "domain": c.domain,
                "role": c.role,
                "status": c.status,
                "ip": c.ip_address,
                "hosting": c.hosting_provider,
            }
            for c in result.scalars().all()
        ]

    return {"count": len(c2s), "c2_domains": c2s}
