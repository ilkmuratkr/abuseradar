from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    postgres_user: str = "spamwatch"
    postgres_password: str = "spamwatch_secret_change_me"
    postgres_db: str = "spamwatch"
    database_url: str = "postgresql+asyncpg://spamwatch:spamwatch_secret_change_me@db:5432/spamwatch"
    redis_url: str = "redis://redis:6379/0"

    gemini_api_key: str = ""

    # ZeptoMail (transactional email)
    zeptomail_token: str = ""  # "Zoho-enczapikey ..." veya sadece token
    zeptomail_endpoint: str = "https://api.zeptomail.eu/v1.1/email"
    email_from: str = "research@abuseradar.org"
    email_from_name: str = "AbuseRadar Research"
    email_reply_to: str = "team@abuseradar.org"
    email_reply_to_name: str = "AbuseRadar Team"

    project_name: str = "AbuseRadar"
    public_base_url: str = "https://abuseradar.org"
    report_base_url: str = "https://abuseradar.org/report"
    log_level: str = "INFO"

    # Crawl ayarları
    crawl_concurrent: int = 5
    crawl_same_domain_delay: int = 5
    crawl_page_timeout: int = 30000
    crawl_user_agent: str = "AbuseRadar/1.0 (Security Research; +https://abuseradar.org)"
    googlebot_ua: str = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"

    # Email ayarları
    email_daily_limit: int = 100
    email_max_followups: int = 3
    email_followup_days: int = 7

    # CSV
    csv_inbox_path: str = "/data/csv/inbox"
    csv_processing_path: str = "/data/csv/processing"
    csv_processed_path: str = "/data/csv/processed"
    csv_duplicate_path: str = "/data/csv/duplicate"
    csv_error_path: str = "/data/csv/error"
    evidence_path: str = "/data/evidence"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
