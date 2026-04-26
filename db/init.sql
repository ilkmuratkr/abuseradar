-- AbuseRadar - Veritabanı Şeması

-- İşlenen CSV dosyaları
CREATE TABLE IF NOT EXISTS csv_files (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(500) NOT NULL,
    file_hash VARCHAR(64) UNIQUE NOT NULL,
    content_hash VARCHAR(64),
    target_domain VARCHAR(500),
    export_date DATE,
    status VARCHAR(50) DEFAULT 'pending',
    total_rows INTEGER DEFAULT 0,
    new_rows INTEGER DEFAULT 0,
    skipped_rows INTEGER DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Tespit edilen siteler (hem mağdur hem saldırgan)
CREATE TABLE IF NOT EXISTS sites (
    id SERIAL PRIMARY KEY,
    domain VARCHAR(500) UNIQUE NOT NULL,
    url TEXT,
    site_type VARCHAR(50),
    category VARCHAR(20) DEFAULT 'BELIRSIZ',
    category_detail VARCHAR(100),
    country VARCHAR(10),
    platform VARCHAR(50),
    domain_rating DECIMAL,
    traffic INTEGER DEFAULT 0,
    language VARCHAR(10),
    status VARCHAR(50) DEFAULT 'pending',
    last_crawled_at TIMESTAMPTZ,
    injection_verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Backlink kayıtları (CSV'den)
CREATE TABLE IF NOT EXISTS backlinks (
    id SERIAL PRIMARY KEY,
    csv_file_id INTEGER REFERENCES csv_files(id),
    referring_site_id INTEGER REFERENCES sites(id),
    referring_url TEXT NOT NULL,
    referring_title TEXT,
    target_url TEXT NOT NULL,
    target_domain VARCHAR(500),
    anchor_text TEXT,
    left_context TEXT,
    right_context TEXT,
    link_type VARCHAR(20) DEFAULT 'text',
    is_spam_flag BOOLEAN DEFAULT FALSE,
    is_rendered BOOLEAN DEFAULT FALSE,
    is_raw BOOLEAN DEFAULT FALSE,
    domain_rating DECIMAL,
    traffic INTEGER DEFAULT 0,
    http_code INTEGER,
    platform VARCHAR(100),
    page_category TEXT,
    spam_score INTEGER DEFAULT 0,
    category VARCHAR(20) DEFAULT 'BELIRSIZ',
    category_detail VARCHAR(100),
    first_seen TIMESTAMPTZ,
    last_seen TIMESTAMPTZ,
    lost_date TIMESTAMPTZ,
    lost_status VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(referring_url, target_url)
);

-- Tespit edilen hacklink'ler (crawl sonucu)
CREATE TABLE IF NOT EXISTS detected_hacklinks (
    id SERIAL PRIMARY KEY,
    site_id INTEGER REFERENCES sites(id),
    href TEXT NOT NULL,
    anchor_text TEXT,
    target_domain VARCHAR(500),
    detection_method VARCHAR(50),
    hiding_technique TEXT,
    spam_score INTEGER DEFAULT 0,
    detection_reasons TEXT[],
    found_in VARCHAR(20),
    c2_domain VARCHAR(500),
    status VARCHAR(50) DEFAULT 'active',
    first_detected TIMESTAMPTZ DEFAULT NOW(),
    last_checked TIMESTAMPTZ,
    removed_at TIMESTAMPTZ
);

-- C2 (Command & Control) domainleri
CREATE TABLE IF NOT EXISTS c2_domains (
    id SERIAL PRIMARY KEY,
    domain VARCHAR(500) UNIQUE NOT NULL,
    role VARCHAR(50),
    ip_address VARCHAR(50),
    asn VARCHAR(50),
    hosting_provider VARCHAR(200),
    cloudflare_protected BOOLEAN DEFAULT FALSE,
    registrar VARCHAR(200),
    registrar_abuse_email VARCHAR(500),
    status VARCHAR(50) DEFAULT 'active',
    first_seen TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Site iletişim bilgileri
CREATE TABLE IF NOT EXISTS contacts (
    id SERIAL PRIMARY KEY,
    site_id INTEGER REFERENCES sites(id),
    email VARCHAR(500) NOT NULL,
    source VARCHAR(50),
    contact_type VARCHAR(50),
    language VARCHAR(10),
    verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(site_id, email)
);

-- Gönderilen bildirimler (site sahiplerine)
CREATE TABLE IF NOT EXISTS notifications (
    id SERIAL PRIMARY KEY,
    site_id INTEGER REFERENCES sites(id),
    contact_id INTEGER REFERENCES contacts(id),
    email_type VARCHAR(50) DEFAULT 'initial_alert',
    language VARCHAR(10),
    subject TEXT,
    send_count INTEGER DEFAULT 0,
    max_sends INTEGER DEFAULT 3,
    status VARCHAR(50) DEFAULT 'pending',
    sent_at TIMESTAMPTZ,
    next_check_at TIMESTAMPTZ,
    responded_at TIMESTAMPTZ,
    remediated_at TIMESTAMPTZ,
    injection_still_active BOOLEAN DEFAULT TRUE,
    last_crawl_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(site_id, contact_id)
);

-- Şikayetler (platformlara)
CREATE TABLE IF NOT EXISTS complaints (
    id SERIAL PRIMARY KEY,
    target_domain VARCHAR(500) NOT NULL,
    target_type VARCHAR(50),
    platform VARCHAR(50) NOT NULL,
    platform_detail VARCHAR(200),
    status VARCHAR(50) DEFAULT 'pending',
    submitted_at TIMESTAMPTZ,
    last_checked_at TIMESTAMPTZ,
    next_check_at TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ,
    check_count INTEGER DEFAULT 0,
    followup_count INTEGER DEFAULT 0,
    max_followups INTEGER DEFAULT 3,
    evidence_path TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(target_domain, platform)
);

-- İndeksler
CREATE INDEX IF NOT EXISTS idx_backlinks_referring_url ON backlinks(referring_url);
CREATE INDEX IF NOT EXISTS idx_backlinks_target_domain ON backlinks(target_domain);
CREATE INDEX IF NOT EXISTS idx_backlinks_category ON backlinks(category);
CREATE INDEX IF NOT EXISTS idx_backlinks_spam_score ON backlinks(spam_score DESC);
CREATE INDEX IF NOT EXISTS idx_sites_domain ON sites(domain);
CREATE INDEX IF NOT EXISTS idx_sites_category ON sites(category);
CREATE INDEX IF NOT EXISTS idx_detected_hacklinks_site_id ON detected_hacklinks(site_id);
CREATE INDEX IF NOT EXISTS idx_notifications_status ON notifications(status);
CREATE INDEX IF NOT EXISTS idx_complaints_status ON complaints(status);

-- Bilinen C2'leri ekle
INSERT INTO c2_domains (domain, role, status) VALUES
    ('hacklinkbacklink.com', 'primary_c2_panel', 'active'),
    ('backlinksatis.net', 'fallback_c2_panel', 'suspended'),
    ('scriptapi.dev', 'script_host', 'active')
ON CONFLICT (domain) DO NOTHING;
