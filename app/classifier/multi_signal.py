"""Coklu sinyal spam tespiti - keyword listesine guvenme, veri analiz et.

Temel prensip: Tek bir sinyal (keyword, subdomain, TLD) ile karar VERME.
Birden fazla bagimsiz sinyal birlestirilerek skor olustur.
"""

import logging
from urllib.parse import urlparse

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import Backlink, Site, async_session

logger = logging.getLogger(__name__)


async def calculate_multi_signal_score(referring_url: str, session: AsyncSession) -> dict:
    """Bir referring URL icin coklu sinyal spam skoru hesapla.

    Returns:
        {
            "total_score": 0-100,
            "signals": {sinyal_adi: {score, reason, value}},
            "classification": "MAGDUR" | "SALDIRGAN" | "ARAC" | "BELIRSIZ",
            "detail": str
        }
    """
    try:
        domain = urlparse(referring_url).hostname or ""
    except Exception:
        domain = ""

    signals = {}

    # ══════════════════════════════════════════
    # SİNYAL 1: Capraz CSV analizi (en guvenilir)
    # Ayni referring domain kac farkli target domain'e link veriyor?
    # 1 target = normal, 5+ target = kesin PBN
    # ══════════════════════════════════════════
    result = await session.execute(
        select(func.count(func.distinct(Backlink.target_domain)))
        .where(Backlink.referring_url.like(f"%{domain}%"))
    )
    target_count = result.scalar() or 0

    if target_count >= 10:
        signals["capraz_csv"] = {"score": 50, "reason": f"{target_count} farkli target domain'e link", "value": target_count}
    elif target_count >= 5:
        signals["capraz_csv"] = {"score": 35, "reason": f"{target_count} farkli target domain", "value": target_count}
    elif target_count >= 3:
        signals["capraz_csv"] = {"score": 20, "reason": f"{target_count} farkli target domain", "value": target_count}
    else:
        signals["capraz_csv"] = {"score": 0, "reason": "Normal link profili", "value": target_count}

    # ══════════════════════════════════════════
    # SİNYAL 2: Ayni referring domain'den kac backlink var?
    # Normal site: 1-5 link, PBN: 50+, Mega PBN: 1000+
    # ══════════════════════════════════════════
    result = await session.execute(
        select(func.count())
        .select_from(Backlink)
        .where(Backlink.referring_url.like(f"%{domain}%"))
    )
    link_count = result.scalar() or 0

    if link_count >= 100:
        signals["link_hacmi"] = {"score": 40, "reason": f"{link_count} backlink tek domain'den", "value": link_count}
    elif link_count >= 20:
        signals["link_hacmi"] = {"score": 25, "reason": f"{link_count} backlink", "value": link_count}
    elif link_count >= 5:
        signals["link_hacmi"] = {"score": 10, "reason": f"{link_count} backlink", "value": link_count}
    else:
        signals["link_hacmi"] = {"score": 0, "reason": "Normal hacim", "value": link_count}

    # ══════════════════════════════════════════
    # SİNYAL 3: Anchor text cesitliligi
    # Mesru site: az sayida tutarli anchor ("Anvil Pub", "restaurant")
    # PBN: cok cesitli alakasiz anchor ("casino", "escort", "tesisat")
    # ══════════════════════════════════════════
    result = await session.execute(
        select(func.count(func.distinct(Backlink.anchor_text)))
        .where(Backlink.referring_url.like(f"%{domain}%"))
    )
    unique_anchors = result.scalar() or 0

    if unique_anchors >= 20:
        signals["anchor_cesitlilik"] = {"score": 35, "reason": f"{unique_anchors} farkli anchor text", "value": unique_anchors}
    elif unique_anchors >= 10:
        signals["anchor_cesitlilik"] = {"score": 20, "reason": f"{unique_anchors} farkli anchor", "value": unique_anchors}
    else:
        signals["anchor_cesitlilik"] = {"score": 0, "reason": "Tutarli anchor profili", "value": unique_anchors}

    # ══════════════════════════════════════════
    # SİNYAL 4: Ahrefs spam flag orani
    # Ahrefs zaten kendi algoritmasiyla spam tespit ediyor
    # Eger bu domain'den gelen linklerin cogu "is_spam=true" ise guvenilir sinyal
    # ══════════════════════════════════════════
    result = await session.execute(
        select(
            func.count().filter(Backlink.is_spam_flag == True),
            func.count()
        )
        .select_from(Backlink)
        .where(Backlink.referring_url.like(f"%{domain}%"))
    )
    row = result.one()
    spam_count, total = row[0] or 0, row[1] or 1
    spam_ratio = spam_count / max(total, 1)

    if spam_ratio >= 0.8:
        signals["ahrefs_spam"] = {"score": 30, "reason": f"Ahrefs spam orani %{int(spam_ratio*100)}", "value": spam_ratio}
    elif spam_ratio >= 0.5:
        signals["ahrefs_spam"] = {"score": 15, "reason": f"Ahrefs spam orani %{int(spam_ratio*100)}", "value": spam_ratio}
    else:
        signals["ahrefs_spam"] = {"score": 0, "reason": f"Ahrefs spam orani %{int(spam_ratio*100)}", "value": spam_ratio}

    # ══════════════════════════════════════════
    # SİNYAL 5: JS enjeksiyon orani (rendered=true, raw=false)
    # Eger bu domain'e gelen linklerin cogu JS ile enjekte edilmisse
    # → referring site hacklenmis (MAGDUR)
    # ══════════════════════════════════════════
    result = await session.execute(
        select(
            func.count().filter(
                (Backlink.is_rendered == True) & (Backlink.is_raw == False)
            ),
            func.count()
        )
        .select_from(Backlink)
        .where(Backlink.referring_url.like(f"%{domain}%"))
    )
    row = result.one()
    js_count, total = row[0] or 0, row[1] or 1
    js_ratio = js_count / max(total, 1)

    if js_ratio >= 0.8:
        # Cogu JS enjeksiyon = bu site hacklenmis = MAGDUR
        signals["js_enjeksiyon"] = {"score": -30, "reason": f"JS enjeksiyon orani %{int(js_ratio*100)} → hacklenmis site", "value": js_ratio}
    else:
        signals["js_enjeksiyon"] = {"score": 0, "reason": f"JS enjeksiyon orani %{int(js_ratio*100)}", "value": js_ratio}

    # ══════════════════════════════════════════
    # SİNYAL 6: Domain Rating (DR)
    # PBN'ler genellikle dusuk DR (0-5)
    # Gov/edu siteleri yuksek DR (30+)
    # Bu TEK basina yeterli degil ama destekleyici sinyal
    # ══════════════════════════════════════════
    result = await session.execute(
        select(func.avg(Backlink.domain_rating))
        .where(Backlink.referring_url.like(f"%{domain}%"))
    )
    avg_dr = float(result.scalar() or 0)

    if avg_dr < 2:
        signals["domain_rating"] = {"score": 15, "reason": f"Cok dusuk DR: {avg_dr:.1f}", "value": avg_dr}
    elif avg_dr > 40:
        signals["domain_rating"] = {"score": -10, "reason": f"Yuksek DR: {avg_dr:.1f} → muhtemelen mesru", "value": avg_dr}
    else:
        signals["domain_rating"] = {"score": 0, "reason": f"DR: {avg_dr:.1f}", "value": avg_dr}

    # ══════════════════════════════════════════
    # SİNYAL 7: Gov/Edu TLD (kesin magdur sinyali)
    # ══════════════════════════════════════════
    gov_edu_tlds = [".gov.", ".gob.", ".gouv.", ".govt.", ".edu.", ".ac."]
    if any(tld in domain for tld in gov_edu_tlds):
        signals["gov_edu"] = {"score": -50, "reason": "Gov/Edu domain → kesin magdur", "value": domain}
    else:
        signals["gov_edu"] = {"score": 0, "reason": "Normal TLD", "value": domain}

    # ══════════════════════════════════════════
    # SİNYAL 8: Site konusu vs keyword uyumu
    # Ahrefs Page Category ile kontrol
    # Gambling kategorisindeki site icin bahis keywordu normaldir
    # Government kategorisindeki site icin bahis keywordu enfeksiyondur
    # ══════════════════════════════════════════
    result = await session.execute(
        select(Backlink.page_category, Backlink.anchor_text)
        .where(Backlink.referring_url.like(f"%{domain}%"))
        .limit(5)
    )
    rows = result.all()

    gambling_categories = ["gambling", "betting", "casino", "poker", "games > gambling"]
    hacked_categories = ["government", "education", "health", "university",
                         "food", "restaurants", "religion", "children",
                         "science", "medical", "hospital", "school"]

    gambling_anchor = any(
        any(kw in (r[1] or "").lower() for kw in ["deneme bonusu", "bahis", "casino", "bet", "slot"])
        for r in rows
    )

    if rows and gambling_anchor:
        page_cat = (rows[0][0] or "").lower()

        # Site gambling kategorisinde → keyword normal
        if any(gc in page_cat for gc in gambling_categories):
            signals["konu_uyumu"] = {
                "score": -40,
                "reason": f"Gambling kategorisi, keyword normal: {page_cat[:60]}",
                "value": page_cat,
            }
        # Site gov/edu/saglik kategorisinde → keyword kesin enjeksiyon
        elif any(hc in page_cat for hc in hacked_categories):
            signals["konu_uyumu"] = {
                "score": -20,
                "reason": f"Uyumsuz kategori, muhtemelen hacklenmis: {page_cat[:60]}",
                "value": page_cat,
            }
        else:
            signals["konu_uyumu"] = {"score": 0, "reason": "Belirsiz kategori", "value": page_cat}
    else:
        signals["konu_uyumu"] = {"score": 0, "reason": "Kategori/anchor verisi yok", "value": ""}

    # ══════════════════════════════════════════
    # TOPLAM SKOR HESAPLA
    # Pozitif = saldirgan yonunde
    # Negatif = magdur yonunde
    # ══════════════════════════════════════════
    total_score = sum(s["score"] for s in signals.values())

    if total_score >= 50:
        classification = "SALDIRGAN"
        if any("pbn" in s.get("reason", "").lower() or target_count >= 5 for s in signals.values()):
            detail = "pbn_network"
        else:
            detail = "spam_site"
    elif total_score <= -20:
        classification = "MAGDUR"
        if any(tld in domain for tld in gov_edu_tlds):
            detail = "hukumet_veya_egitim"
        elif js_ratio >= 0.8:
            detail = "js_enjeksiyonlu_site"
        else:
            detail = "hacklenmis_site"
    elif total_score <= 10:
        classification = "ARAC"
        detail = "muhtemelen_mesru"
    else:
        classification = "BELIRSIZ"
        detail = "daha_fazla_veri_gerekli"

    return {
        "domain": domain,
        "total_score": total_score,
        "signals": signals,
        "classification": classification,
        "detail": detail,
    }


async def reclassify_all():
    """Tum backlink'leri coklu sinyal ile yeniden siniflandir."""
    async with async_session() as session:
        # Unique referring domain'leri al
        result = await session.execute(
            text("""
                SELECT DISTINCT split_part(split_part(referring_url, '://', 2), '/', 1) as domain
                FROM backlinks
                LIMIT 5000
            """)
        )
        domains = [r[0] for r in result.all() if r[0]]

    logger.info(f"Coklu sinyal siniflandirma: {len(domains)} domain")
    results = {"SALDIRGAN": 0, "MAGDUR": 0, "ARAC": 0, "BELIRSIZ": 0}

    async with async_session() as session:
        for domain in domains:
            try:
                score = await calculate_multi_signal_score(f"https://{domain}/", session)

                # Bu domain'e ait tum backlink'leri guncelle
                await session.execute(
                    text("""
                        UPDATE backlinks
                        SET category = :cat, category_detail = :detail
                        WHERE referring_url LIKE :pattern
                    """),
                    {
                        "cat": score["classification"],
                        "detail": score["detail"],
                        "pattern": f"%{domain}%",
                    }
                )
                results[score["classification"]] = results.get(score["classification"], 0) + 1

            except Exception as e:
                logger.debug(f"[{domain}] Siniflandirma hatasi: {e}")

        await session.commit()

    logger.info(f"Coklu sinyal sonuc: {results}")
    return results
