"""CSV dosya takibi - duplicate detection ve durum yönetimi."""

import hashlib
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import CsvFile


def calculate_file_hash(filepath: str | Path) -> str:
    """Dosyanın SHA256 hash'ini hesapla."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def calculate_content_hash(filepath: str | Path, sample_rows: int = 10) -> str:
    """İlk N satırın hash'i (dosya adı farklı olsa bile aynı veriyi yakalar)."""
    h = hashlib.sha256()
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f):
            if i >= sample_rows + 1:
                break
            h.update(line.encode())
    return h.hexdigest()


def parse_filename(filename: str) -> tuple[str | None, str | None]:
    """Ahrefs CSV dosya adından domain ve tarih çıkar.

    Pattern: domain-backlinks-subdomains_2026-04-24_11-54-35.csv
    """
    match = re.match(
        r"^(.+?)[-_]backlinks.*?_(\d{4}-\d{2}-\d{2}).*\.csv$",
        filename,
    )
    if match:
        return match.group(1), match.group(2)
    return None, None


async def is_already_processed(
    session: AsyncSession, filepath: str | Path
) -> tuple[bool, str, CsvFile | None]:
    """3 katmanlı duplicate kontrol."""
    filepath = Path(filepath)
    filename = filepath.name

    # Kontrol 1: Dosya hash (birebir aynı dosya)
    file_hash = calculate_file_hash(filepath)
    result = await session.execute(
        select(CsvFile).where(CsvFile.file_hash == file_hash)
    )
    existing = result.scalar_one_or_none()
    if existing:
        return True, "exact_duplicate", existing

    # Kontrol 2: Aynı domain + aynı veya daha yeni tarih
    domain, date_str = parse_filename(filename)
    if domain and date_str:
        from datetime import date as date_type

        try:
            parsed_date = date_type.fromisoformat(date_str)
        except ValueError:
            parsed_date = None

        if parsed_date:
            result = await session.execute(
                select(CsvFile).where(
                    CsvFile.target_domain == domain,
                    CsvFile.export_date >= parsed_date,
                    CsvFile.status == "completed",
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                return True, "same_or_newer_exists", existing

    # Kontrol 3: İçerik hash (farklı isimle aynı veri)
    content_hash = calculate_content_hash(filepath)
    result = await session.execute(
        select(CsvFile).where(CsvFile.content_hash == content_hash)
    )
    existing = result.scalar_one_or_none()
    if existing:
        return True, "content_duplicate", existing

    return False, "new", None
