"""CSV parse ve DB'ye yazma."""

import logging
import shutil
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from config import settings
from models.database import Backlink, CsvFile, Site, async_session
from utils.helpers import extract_root_domain

from .scorer import calculate_spam_score
from .tracker import (
    calculate_content_hash,
    calculate_file_hash,
    is_already_processed,
    parse_filename,
)

logger = logging.getLogger(__name__)


def _parse_ts(val):
    """Timestamp parse - timezone-aware döndür."""
    if pd.isna(val) or val is None or str(val).strip() in ("", "nan"):
        return None
    try:
        ts = pd.to_datetime(val, utc=True)
        return ts.to_pydatetime()
    except Exception:
        return None


def extract_domain(url: str) -> str:
    """URL'den domain çıkar."""
    try:
        parsed = urlparse(url)
        return parsed.hostname or ""
    except Exception:
        return ""


async def get_or_create_site(session, domain: str, row: dict) -> int:
    """Site kaydı yoksa oluştur, varsa id'sini döndür."""
    result = await session.execute(select(Site).where(Site.domain == domain))
    site = result.scalar_one_or_none()

    if site:
        # Mevcut kayıt root_domain boşsa doldur (geriye dönük migration)
        if not site.root_domain:
            site.root_domain = extract_root_domain(domain) or domain
        return site.id

    new_site = Site(
        domain=domain,
        root_domain=extract_root_domain(domain) or domain,
        url=row.get("referring_url", ""),
        platform=row.get("platform", ""),
        domain_rating=row.get("domain_rating"),
        traffic=row.get("traffic", 0),
    )
    session.add(new_site)
    await session.flush()
    return new_site.id


async def process_csv_file(filepath: str | Path) -> dict:
    """Tek bir CSV dosyasını işle."""
    filepath = Path(filepath)
    filename = filepath.name
    logger.info(f"CSV işleniyor: {filename}")

    async with async_session() as session:
        # 1. Duplicate kontrol
        is_dup, reason, existing = await is_already_processed(session, filepath)
        if is_dup:
            dup_path = Path(settings.csv_duplicate_path) / filename
            shutil.move(str(filepath), str(dup_path))
            logger.info(f"Duplicate atlandı ({reason}): {filename}")
            return {"status": "skipped", "reason": reason, "filename": filename}

        # 2. Processing'e taşı
        proc_path = Path(settings.csv_processing_path) / filename
        shutil.move(str(filepath), str(proc_path))

        # 3. CSV kaydı oluştur
        file_hash = calculate_file_hash(proc_path)
        content_hash = calculate_content_hash(proc_path)
        target_domain, export_date_str = parse_filename(filename)

        from datetime import date as date_type

        try:
            export_date = (
                date_type.fromisoformat(export_date_str) if export_date_str else None
            )
        except ValueError:
            export_date = None

        csv_record = CsvFile(
            filename=filename,
            file_hash=file_hash,
            content_hash=content_hash,
            target_domain=target_domain,
            export_date=export_date,
            status="processing",
            started_at=datetime.utcnow(),
        )
        session.add(csv_record)
        await session.flush()

        # 4. Parse
        try:
            try:
                df = pd.read_csv(proc_path, on_bad_lines="skip", encoding="utf-8")
            except UnicodeDecodeError:
                df = pd.read_csv(proc_path, on_bad_lines="skip", encoding="utf-16")
            except Exception:
                df = pd.read_csv(proc_path, on_bad_lines="skip", encoding="latin-1")
            total_rows = len(df)
            new_rows = 0
            skipped_rows = 0

            for _, row in df.iterrows():
                referring_url = str(row.get("Referring page URL", ""))
                target_url = str(row.get("Target URL", ""))

                if not referring_url or not target_url:
                    skipped_rows += 1
                    continue

                # Satır bazlı deduplicate
                exists = await session.execute(
                    select(Backlink.id).where(
                        Backlink.referring_url == referring_url,
                        Backlink.target_url == target_url,
                    )
                )
                if exists.scalar_one_or_none():
                    skipped_rows += 1
                    continue

                referring_domain = extract_domain(referring_url)
                rendered = str(row.get("Rendered", "")).lower() == "true"
                raw = str(row.get("Raw", "")).lower() == "true"

                def _clean(val):
                    s = str(val) if pd.notna(val) else ""
                    return "" if s == "nan" else s

                target_dom = extract_domain(target_url)
                backlink_data = {
                    "csv_file_id": csv_record.id,
                    "referring_url": referring_url,
                    "referring_title": _clean(row.get("Referring page title")),
                    "referring_root_domain": extract_root_domain(referring_domain) or referring_domain,
                    "target_url": target_url,
                    "target_domain": target_dom,
                    "target_root_domain": extract_root_domain(target_dom) or target_dom,
                    "anchor_text": _clean(row.get("Anchor")),
                    "left_context": _clean(row.get("Left context")),
                    "right_context": _clean(row.get("Right context")),
                    "link_type": _clean(row.get("Type")) or "text",
                    "is_spam_flag": str(row.get("Is spam", "")).lower() == "true",
                    "is_rendered": rendered,
                    "is_raw": raw,
                    "domain_rating": (
                        float(row["Domain rating"])
                        if pd.notna(row.get("Domain rating"))
                        else None
                    ),
                    "traffic": (
                        int(row["Domain traffic"])
                        if pd.notna(row.get("Domain traffic"))
                        else 0
                    ),
                    "http_code": (
                        int(row["Referring page HTTP code"])
                        if pd.notna(row.get("Referring page HTTP code"))
                        else None
                    ),
                    "platform": _clean(row.get("Platform")),
                    "page_category": _clean(row.get("Page category")),
                    "first_seen": _parse_ts(row.get("First seen")),
                    "last_seen": _parse_ts(row.get("Last seen")),
                    "lost_date": _parse_ts(row.get("Lost")),
                    "lost_status": _clean(row.get("Lost status")),
                }

                # Spam skor
                backlink_data["spam_score"] = calculate_spam_score(backlink_data)

                # Site kaydı
                if referring_domain:
                    site_id = await get_or_create_site(
                        session, referring_domain, backlink_data
                    )
                    backlink_data["referring_site_id"] = site_id

                backlink = Backlink(**backlink_data)
                session.add(backlink)
                new_rows += 1

                # Her 100 satırda bir flush (bellek yönetimi)
                if new_rows % 100 == 0:
                    await session.flush()

            # 5. Tamamla
            csv_record.status = "completed"
            csv_record.total_rows = total_rows
            csv_record.new_rows = new_rows
            csv_record.skipped_rows = skipped_rows
            csv_record.completed_at = datetime.utcnow()
            await session.commit()

            # 6. Processed'a taşı
            today = datetime.now().strftime("%Y-%m-%d")
            done_dir = Path(settings.csv_processed_path) / today
            done_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(proc_path), str(done_dir / filename))

            logger.info(
                f"CSV tamamlandı: {filename} | "
                f"Toplam: {total_rows}, Yeni: {new_rows}, Atlandı: {skipped_rows}"
            )
            return {
                "status": "completed",
                "filename": filename,
                "total": total_rows,
                "new": new_rows,
                "skipped": skipped_rows,
            }

        except Exception as e:
            csv_record.status = "error"
            csv_record.error_message = str(e)
            await session.commit()

            error_path = Path(settings.csv_error_path) / filename
            if proc_path.exists():
                shutil.move(str(proc_path), str(error_path))

            logger.error(f"CSV hatası: {filename} → {e}")
            raise


async def process_inbox():
    """inbox/ klasöründeki tüm CSV'leri işle."""
    # Tüm gerekli klasörlerin var olduğundan emin ol (bind-mount edilmiş volume'da
    # yokların oluşturulması — deploy.sh init bu klasörleri oluşturmuyor).
    for p in (
        settings.csv_inbox_path,
        settings.csv_processing_path,
        settings.csv_processed_path,
        settings.csv_duplicate_path,
        settings.csv_error_path,
    ):
        Path(p).mkdir(parents=True, exist_ok=True)

    inbox = Path(settings.csv_inbox_path)
    csv_files = sorted(inbox.glob("*.csv"))

    if not csv_files:
        logger.info("inbox/ klasöründe CSV yok.")
        return []

    logger.info(f"{len(csv_files)} CSV bulundu, işleniyor...")
    results = []
    for csv_file in csv_files:
        result = await process_csv_file(csv_file)
        results.append(result)

    return results
