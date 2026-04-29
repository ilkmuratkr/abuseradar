from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, relationship

from config import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class CsvFile(Base):
    __tablename__ = "csv_files"

    id = Column(Integer, primary_key=True)
    filename = Column(String(500), nullable=False)
    file_hash = Column(String(64), unique=True, nullable=False)
    content_hash = Column(String(64))
    target_domain = Column(String(500))
    export_date = Column(DateTime)
    status = Column(String(50), default="pending")
    total_rows = Column(Integer, default=0)
    new_rows = Column(Integer, default=0)
    skipped_rows = Column(Integer, default=0)
    error_message = Column(Text)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    backlinks = relationship("Backlink", back_populates="csv_file")


class Site(Base):
    __tablename__ = "sites"

    id = Column(Integer, primary_key=True)
    domain = Column(String(500), unique=True, nullable=False)
    root_domain = Column(String(500))
    url = Column(Text)
    site_type = Column(String(50))
    category = Column(String(20), default="BELIRSIZ")
    category_detail = Column(String(100))
    country = Column(String(10))
    platform = Column(String(50))
    domain_rating = Column(Numeric)
    traffic = Column(BigInteger, default=0)
    language = Column(String(10))
    status = Column(String(50), default="pending")
    last_crawled_at = Column(DateTime(timezone=True))
    injection_verified = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    hacklinks = relationship("DetectedHacklink", back_populates="site")
    contacts = relationship("Contact", back_populates="site")
    notifications = relationship("Notification", back_populates="site")


class Backlink(Base):
    __tablename__ = "backlinks"

    id = Column(Integer, primary_key=True)
    csv_file_id = Column(Integer, ForeignKey("csv_files.id"))
    referring_site_id = Column(Integer, ForeignKey("sites.id"))
    referring_url = Column(Text, nullable=False)
    referring_title = Column(Text)
    referring_root_domain = Column(String(500))
    target_url = Column(Text, nullable=False)
    target_domain = Column(String(500))
    target_root_domain = Column(String(500))
    anchor_text = Column(Text)
    left_context = Column(Text)
    right_context = Column(Text)
    link_type = Column(String(20), default="text")
    is_spam_flag = Column(Boolean, default=False)
    is_rendered = Column(Boolean, default=False)
    is_raw = Column(Boolean, default=False)
    domain_rating = Column(Numeric)
    traffic = Column(BigInteger, default=0)
    http_code = Column(Integer)
    platform = Column(String(100))
    page_category = Column(Text)
    spam_score = Column(Integer, default=0)
    category = Column(String(20), default="BELIRSIZ")
    category_detail = Column(String(100))
    first_seen = Column(DateTime(timezone=True))
    last_seen = Column(DateTime(timezone=True))
    lost_date = Column(DateTime(timezone=True))
    lost_status = Column(String(50))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    csv_file = relationship("CsvFile", back_populates="backlinks")


class DetectedHacklink(Base):
    __tablename__ = "detected_hacklinks"

    id = Column(Integer, primary_key=True)
    site_id = Column(Integer, ForeignKey("sites.id"))
    href = Column(Text, nullable=False)
    anchor_text = Column(Text)
    target_domain = Column(String(500))
    detection_method = Column(String(50))
    hiding_technique = Column(Text)
    spam_score = Column(Integer, default=0)
    detection_reasons = Column(ARRAY(Text))
    found_in = Column(String(20))
    c2_domain = Column(String(500))
    status = Column(String(50), default="active")
    first_detected = Column(DateTime(timezone=True), server_default=func.now())
    last_checked = Column(DateTime(timezone=True))
    removed_at = Column(DateTime(timezone=True))

    site = relationship("Site", back_populates="hacklinks")


class C2Domain(Base):
    __tablename__ = "c2_domains"

    id = Column(Integer, primary_key=True)
    domain = Column(String(500), unique=True, nullable=False)
    role = Column(String(50))
    ip_address = Column(String(50))
    asn = Column(String(50))
    hosting_provider = Column(String(200))
    cloudflare_protected = Column(Boolean, default=False)
    registrar = Column(String(200))
    registrar_abuse_email = Column(String(500))
    status = Column(String(50), default="active")
    first_seen = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Contact(Base):
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True)
    site_id = Column(Integer, ForeignKey("sites.id"))
    email = Column(String(500), nullable=False)
    source = Column(String(50))
    contact_type = Column(String(50))
    language = Column(String(10))
    verified = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    site = relationship("Site", back_populates="contacts")


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True)
    site_id = Column(Integer, ForeignKey("sites.id"))
    contact_id = Column(Integer, ForeignKey("contacts.id"))
    email_type = Column(String(50), default="initial_alert")
    language = Column(String(10))
    subject = Column(Text)
    send_count = Column(Integer, default=0)
    max_sends = Column(Integer, default=3)
    status = Column(String(50), default="pending")
    sent_at = Column(DateTime(timezone=True))
    next_check_at = Column(DateTime(timezone=True))
    responded_at = Column(DateTime(timezone=True))
    remediated_at = Column(DateTime(timezone=True))
    injection_still_active = Column(Boolean, default=True)
    last_crawl_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    site = relationship("Site", back_populates="notifications")


class Complaint(Base):
    __tablename__ = "complaints"

    id = Column(Integer, primary_key=True)
    target_domain = Column(String(500), nullable=False)
    target_type = Column(String(50))
    platform = Column(String(50), nullable=False)
    platform_detail = Column(String(200))
    status = Column(String(50), default="pending")
    submitted_at = Column(DateTime(timezone=True))
    last_checked_at = Column(DateTime(timezone=True))
    next_check_at = Column(DateTime(timezone=True))
    resolved_at = Column(DateTime(timezone=True))
    check_count = Column(Integer, default=0)
    followup_count = Column(Integer, default=0)
    max_followups = Column(Integer, default=3)
    evidence_path = Column(Text)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class MailLog(Base):
    __tablename__ = "mail_log"

    id = Column(Integer, primary_key=True)
    to_email = Column(String(500), nullable=False)
    to_email_domain = Column(String(500))
    recipient_provider = Column(String(20))
    site_id = Column(Integer)
    contact_id = Column(Integer)
    subject = Column(Text)
    language = Column(String(10))
    status = Column(String(50))
    error_message = Column(Text)
    zeptomail_id = Column(String(200))
    sent_at = Column(DateTime(timezone=True), server_default=func.now())


class Unsubscribe(Base):
    __tablename__ = "unsubscribes"

    id = Column(Integer, primary_key=True)
    email = Column(String(500), unique=True, nullable=False)
    reason = Column(String(100))
    source = Column(String(50))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ReportToken(Base):
    __tablename__ = "report_tokens"

    id = Column(Integer, primary_key=True)
    token = Column(String(64), unique=True, nullable=False)
    domain = Column(String(500), nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True))
    view_count = Column(Integer, default=0)
    last_viewed_at = Column(DateTime(timezone=True))
    revoked = Column(Boolean, default=False)


async def init_db():
    """Veritabanı bağlantısını test et + eksik tabloları yarat.

    `metadata.create_all` mevcut tabloları korur, yalnızca eksik olanları
    oluşturur. Yeni eklenen modeller (MailLog, Unsubscribe vb.) için manuel
    migration gerekmiyor.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
