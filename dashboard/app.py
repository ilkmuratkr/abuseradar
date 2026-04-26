"""AbuseRadar - Tam Yonetim Paneli."""

import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st
from sqlalchemy import create_engine, text

# ══════════════════════════════════════════════════
# YAPILANDIRMA
# ══════════════════════════════════════════════════

DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://spamwatch:spamwatch_secret_change_me@db:5432/spamwatch",
).replace("+asyncpg", "").split("?")[0]

API_URL = os.getenv("API_URL", "http://app:8000")
CSV_INBOX = os.getenv("CSV_INBOX", "/data/csv/inbox")
EVIDENCE_DIR = os.getenv("EVIDENCE_DIR", "/data/evidence")

engine = create_engine(DB_URL)

st.set_page_config(
    page_title="AbuseRadar",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ══════════════════════════════════════════════════
# YARDIMCI FONKSİYONLAR
# ══════════════════════════════════════════════════


def q(query: str) -> pd.DataFrame:
    """SQL sorgusu calistir."""
    try:
        with engine.connect() as conn:
            return pd.read_sql(text(query), conn)
    except Exception as e:
        st.error(f"DB hatasi: {e}")
        return pd.DataFrame()


def qval(query: str):
    """Tek deger donduren sorgu."""
    df = q(query)
    return df.iloc[0, 0] if len(df) > 0 else 0


def api(method: str, path: str, **kwargs) -> dict:
    """Backend API cagrisi."""
    try:
        url = f"{API_URL}{path}"
        resp = getattr(requests, method)(url, timeout=120, **kwargs)
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


# ══════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════

with st.sidebar:
    st.title("🔍 AbuseRadar")
    st.caption("Yonetim Paneli v1.0")
    st.divider()

    page = st.radio(
        "Sayfa",
        [
            "📊 Genel Bakis",
            "🚀 Pipeline",
            "📁 CSV Yonetimi",
            "🔗 Backlink Analizi",
            "🏛️ Magdur Siteler",
            "💀 Saldirgan Agi",
            "🖥️ C2 Altyapisi",
            "📋 Sikayet Takibi",
            "📧 Email Takibi",
            "🕷️ Crawler & Kanitlar",
            "⚙️ Ayarlar & Sistem",
        ],
        label_visibility="collapsed",
    )

    st.divider()
    # Hizli istatistik
    try:
        total_bl = qval("SELECT count(*) FROM backlinks")
        total_hl = qval("SELECT count(*) FROM detected_hacklinks")
        st.metric("Backlink", f"{total_bl:,}")
        st.metric("Hacklink", f"{total_hl:,}")
    except Exception:
        pass


# ══════════════════════════════════════════════════
# SAYFA 1: GENEL BAKIS
# ══════════════════════════════════════════════════

if page == "📊 Genel Bakis":
    st.header("📊 Genel Bakis")

    # KPI Kartlari
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("CSV Islenen", qval("SELECT count(*) FROM csv_files WHERE status='completed'"))
    c2.metric("Toplam Backlink", f"{qval('SELECT count(*) FROM backlinks'):,}")
    c3.metric("Magdur Site", qval("SELECT count(*) FROM backlinks WHERE category='MAGDUR'"))
    c4.metric("Saldirgan", qval("SELECT count(*) FROM backlinks WHERE category='SALDIRGAN'"))

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Dogrulanmis Enjeksiyon", qval("SELECT count(*) FROM sites WHERE injection_verified=true"))
    c6.metric("Tespit Hacklink", qval("SELECT count(*) FROM detected_hacklinks"))
    c7.metric("C2 Domain", qval("SELECT count(*) FROM c2_domains"))
    c8.metric("Gonderilen Email", qval("SELECT count(*) FROM notifications WHERE status='sent'"))

    st.divider()

    # Kategori dagilimi
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Kategori Dagilimi")
        cats = q("SELECT category, count(*) as sayi FROM backlinks GROUP BY category ORDER BY sayi DESC")
        if not cats.empty:
            fig = px.pie(cats, values="sayi", names="category", color_discrete_sequence=px.colors.qualitative.Set2)
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Spam Skor Dagilimi")
        scores = q("SELECT spam_score, count(*) as sayi FROM backlinks GROUP BY spam_score ORDER BY spam_score")
        if not scores.empty:
            fig = px.bar(scores, x="spam_score", y="sayi", color_discrete_sequence=["#e74c3c"])
            st.plotly_chart(fig, use_container_width=True)

    # Son islemler
    st.subheader("Son Islenen CSV'ler")
    csvs = q("SELECT filename, target_domain, total_rows, new_rows, skipped_rows, status, completed_at FROM csv_files ORDER BY created_at DESC LIMIT 10")
    if not csvs.empty:
        st.dataframe(csvs, use_container_width=True, hide_index=True)

    st.subheader("Son Crawl Edilen Siteler")
    crawled = q("SELECT domain, status, injection_verified, last_crawled_at FROM sites WHERE last_crawled_at IS NOT NULL ORDER BY last_crawled_at DESC LIMIT 10")
    if not crawled.empty:
        st.dataframe(crawled, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════
# SAYFA: PIPELINE (Tek tusla tum akis)
# ══════════════════════════════════════════════════

elif page == "🚀 Pipeline":
    st.header("🚀 Pipeline - CSV'den Sikayete Tam Akis")

    st.markdown("""
    ```
    CSV Yukle → Isle → Siniflandir → Crawl & Dogrula → Sikayet/Email
    ```
    **KURAL:** Crawl ile dogrulanmamis siteye ASLA sikayet veya email gonderilmez.
    """)

    # Pipeline durumu
    status = api("get", "/pipeline/status")
    if "error" not in status:
        st.subheader("Guncel Durum")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("CSV Islenen", status.get("csv_processed", 0))
        c2.metric("Toplam Backlink", f"{status.get('total_backlinks', 0):,}")
        c3.metric("Dogrulanmis Magdur", status.get("verified_victims", 0))
        c4.metric("Dogrulanmamis", status.get("unverified", 0))
        c5.metric("Duzeltilmis", status.get("remediated", 0))

        col1, col2 = st.columns(2)
        with col1:
            st.write("**Siniflandirma:**")
            cls = status.get("classification", {})
            for cat, count in cls.items():
                st.write(f"  {cat}: {count}")
        with col2:
            st.write("**Sikayetler:**")
            comp = status.get("complaints", {})
            if comp:
                for s, count in comp.items():
                    st.write(f"  {s}: {count}")
            else:
                st.write("  Henuz sikayet yok")

    st.divider()

    # Adim adim pipeline
    st.subheader("Adimlari Calistir")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**ADIM 1-2:** CSV Isle + Siniflandir")
        if st.button("📥 CSV Isle & Siniflandir", type="primary", use_container_width=True):
            with st.spinner("CSV'ler isleniyor ve siniflandiriliyor..."):
                result = api("post", "/pipeline/run")
            if "error" not in result:
                st.success(f"CSV: {result.get('csv', {}).get('processed', 0)} islendi")
                st.info(f"Siniflandirma: {result.get('classification', {})}")
            else:
                st.error(f"Hata: {result}")

    with col2:
        st.markdown("**ADIM 3:** Saldirgan Listesi")
        if st.button("💀 Saldirgan Domainleri Cikar", use_container_width=True):
            with st.spinner("Saldirgan domainler cikariliyor..."):
                result = api("get", "/pipeline/attackers")
            if "error" not in result:
                st.success(f"{result.get('count', 0)} saldirgan domain tespit edildi")
                attackers = result.get("attackers", [])
                if attackers:
                    df = pd.DataFrame(attackers)
                    st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("**ADIM 4:** Crawl & Dogrula (VPN-TR uzerinden)")
    st.warning("Crawl islemi VPN-TR konteynerinde calisir. Asagidaki komutu terminal'de calistirin:")

    unverified = qval("""
        SELECT count(DISTINCT split_part(split_part(referring_url, '://', 2), '/', 1))
        FROM backlinks b
        LEFT JOIN sites s ON s.domain = split_part(split_part(b.referring_url, '://', 2), '/', 1)
        WHERE b.category = 'MAGDUR' AND (s.last_crawled_at IS NULL OR s.injection_verified IS NULL)
    """)
    st.info(f"Dogrulanmamis magdur site: {unverified}")

    if unverified > 0:
        # Dogrulanmamis siteleri listele
        unv_sites = q("""
            SELECT DISTINCT
                split_part(split_part(b.referring_url, '://', 2), '/', 1) as domain,
                b.referring_url as url,
                b.category_detail as tip,
                b.domain_rating as dr
            FROM backlinks b
            LEFT JOIN sites s ON s.domain = split_part(split_part(b.referring_url, '://', 2), '/', 1)
            WHERE b.category = 'MAGDUR' AND (s.last_crawled_at IS NULL OR s.injection_verified IS NULL)
            ORDER BY b.domain_rating DESC NULLS LAST
            LIMIT 50
        """)
        if not unv_sites.empty:
            st.dataframe(unv_sites, use_container_width=True, hide_index=True)

            selected = st.selectbox("Crawl edilecek site secin", unv_sites["domain"].tolist())
            if selected:
                url = unv_sites[unv_sites["domain"] == selected]["url"].iloc[0]
                st.code(f'docker compose run --rm crawler python -m crawler.cli "{url}"')

    st.divider()

    # Dogrulanmis magdurlar
    st.subheader("Dogrulanmis Magdurlar (Sikayet/Email icin hazir)")
    verified_sites = q("""
        SELECT s.domain, s.status, s.platform,
               s.last_crawled_at,
               (SELECT count(*) FROM detected_hacklinks h WHERE h.site_id = s.id) as hacklink_sayisi,
               (SELECT count(*) FROM contacts c WHERE c.site_id = s.id) as iletisim_sayisi,
               (SELECT count(*) FROM notifications n WHERE n.site_id = s.id AND n.status = 'sent') as email_gonderildi
        FROM sites s
        WHERE s.injection_verified = true
        ORDER BY s.last_crawled_at DESC
    """)
    if not verified_sites.empty:
        st.dataframe(verified_sites, use_container_width=True, hide_index=True)
        st.success(f"{len(verified_sites)} site dogrulanmis ve sikayet/email icin hazir")
    else:
        st.info("Henuz dogrulanmis magdur yok. Once crawl yapın.")


# ══════════════════════════════════════════════════
# SAYFA 2: CSV YONETIMI
# ══════════════════════════════════════════════════

elif page == "📁 CSV Yonetimi":
    st.header("📁 CSV Yonetimi")

    # Dosya yukleme
    st.subheader("CSV Yukle")
    uploaded = st.file_uploader("Ahrefs backlink CSV dosyasi yukleyin", type=["csv"], accept_multiple_files=True)
    if uploaded:
        for f in uploaded:
            save_path = Path(CSV_INBOX) / f.name
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_bytes(f.getvalue())
            st.success(f"Yuklendi: {f.name} ({len(f.getvalue()) / 1024:.1f} KB)")

    # Isle butonu
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("📥 CSV'leri Isle", type="primary", use_container_width=True):
            with st.spinner("CSV'ler isleniyor..."):
                result = api("post", "/csv/process")
            if "error" in result:
                st.error(f"Hata: {result['error']}")
            else:
                st.success(f"{result.get('processed', 0)} CSV islendi")
                if result.get("results"):
                    for r in result["results"]:
                        if r["status"] == "completed":
                            st.info(f"✓ {r['filename']}: {r['new']} yeni, {r['skipped']} mevcut")
                        else:
                            st.warning(f"⊘ {r['filename']}: {r['reason']}")
                st.rerun()

    with col2:
        if st.button("🏷️ Siniflandir", use_container_width=True):
            with st.spinner("Backlinkler siniflandiriliyor..."):
                result = api("post", "/classify")
            if "error" not in result:
                st.success(f"{result.get('classified', 0)} backlink siniflandirildi: {result.get('breakdown', {})}")
                st.rerun()

    # Islenmis CSV listesi
    st.subheader("Islenmis CSV'ler")
    csvs = q("SELECT id, filename, target_domain, export_date, total_rows, new_rows, skipped_rows, status, completed_at FROM csv_files ORDER BY created_at DESC")
    if not csvs.empty:
        st.dataframe(csvs, use_container_width=True, hide_index=True)
    else:
        st.info("Henuz CSV islenmemis. Yukleyin ve 'Isle' butonuna basin.")


# ══════════════════════════════════════════════════
# SAYFA 3: BACKLINK ANALIZI
# ══════════════════════════════════════════════════

elif page == "🔗 Backlink Analizi":
    st.header("🔗 Backlink Analizi")

    # Filtreler
    col1, col2, col3 = st.columns(3)
    with col1:
        cat_filter = st.selectbox("Kategori", ["Tumu", "MAGDUR", "SALDIRGAN", "ARAC", "BELIRSIZ"])
    with col2:
        score_min = st.slider("Min Spam Skor", 0, 100, 0)
    with col3:
        limit = st.selectbox("Gosterim", [50, 100, 200, 500], index=1)

    where = "WHERE 1=1"
    if cat_filter != "Tumu":
        where += f" AND category='{cat_filter}'"
    if score_min > 0:
        where += f" AND spam_score >= {score_min}"

    # Backlink tablosu
    df = q(f"""
        SELECT referring_url, referring_title, anchor_text, target_domain,
               spam_score, category, category_detail, domain_rating, traffic,
               platform, is_rendered, is_raw, first_seen, last_seen
        FROM backlinks {where}
        ORDER BY spam_score DESC
        LIMIT {limit}
    """)

    if not df.empty:
        st.dataframe(df, use_container_width=True, hide_index=True, height=500)
        st.caption(f"Toplam {len(df)} kayit gosteriliyor")
    else:
        st.info("Filtre kriterlerine uyan backlink bulunamadi.")

    # Alt istatistikler
    col1, col2 = st.columns(2)
    with col1:
        detail = q(f"SELECT category_detail, count(*) as sayi FROM backlinks {where} GROUP BY category_detail ORDER BY sayi DESC LIMIT 15")
        if not detail.empty:
            st.subheader("Detay Dagilimi")
            fig = px.bar(detail, x="sayi", y="category_detail", orientation="h", color_discrete_sequence=["#3498db"])
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        platforms = q(f"SELECT platform, count(*) as sayi FROM backlinks {where} AND platform != '' GROUP BY platform ORDER BY sayi DESC LIMIT 10")
        if not platforms.empty:
            st.subheader("Platform Dagilimi")
            fig = px.pie(platforms, values="sayi", names="platform")
            st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════
# SAYFA 4: MAGDUR SITELER
# ══════════════════════════════════════════════════

elif page == "🏛️ Magdur Siteler":
    st.header("🏛️ Magdur Siteler")

    # Filtre
    col1, col2 = st.columns(2)
    with col1:
        type_filter = st.selectbox("Site Tipi", ["Tumu", "hukumet_sitesi", "egitim_sitesi", "hacklenmis_site"])
    with col2:
        verified_filter = st.selectbox("Crawl Durumu", ["Tumu", "Dogrulanmis", "Bekleyen"])

    where = "WHERE b.category='MAGDUR'"
    if type_filter != "Tumu":
        where += f" AND b.category_detail='{type_filter}'"

    victims = q(f"""
        SELECT DISTINCT ON (b.referring_url)
            b.referring_url as url, b.referring_title as baslik,
            b.anchor_text as anchor, b.domain_rating as dr,
            b.traffic, b.platform, b.spam_score,
            b.category_detail as tip, b.first_seen, b.last_seen,
            s.injection_verified as dogrulanmis, s.status as crawl_durum,
            s.last_crawled_at as son_crawl
        FROM backlinks b
        LEFT JOIN sites s ON s.domain = split_part(split_part(b.referring_url, '://', 2), '/', 1)
        {where}
        ORDER BY b.referring_url, b.domain_rating DESC NULLS LAST
        LIMIT 200
    """)

    if not victims.empty:
        st.dataframe(victims, use_container_width=True, hide_index=True, height=400)

        # Aksiyonlar
        st.divider()
        st.subheader("Aksiyonlar")

        col1, col2, col3 = st.columns(3)

        with col1:
            crawl_domain = st.text_input("Crawl edilecek domain", placeholder="ornek.com")
            if st.button("🕷️ Crawl Et", use_container_width=True) and crawl_domain:
                st.info(f"Crawl komutu: `docker compose run --rm crawler python -m crawler.cli https://{crawl_domain}/`")
                st.warning("Crawler VPN-TR konteynerinde calisir. Terminal'den calistirin.")

        with col2:
            contact_domain = st.text_input("Iletisim bulunacak domain", placeholder="ornek.com")
            if st.button("📇 Iletisim Bul", use_container_width=True) and contact_domain:
                with st.spinner("Iletisim aranıyor..."):
                    result = api("post", f"/contacts/{contact_domain}")
                if "error" not in result:
                    st.success(f"{result.get('count', 0)} iletisim bulundu")
                    if result.get("contacts"):
                        for c in result["contacts"]:
                            st.write(f"  📧 {c['email']} ({c['contact_type']}, kaynak: {c['source']})")

        with col3:
            st.write("Toplu email gondermek icin Email Takibi sayfasina gidin.")

    else:
        st.info("Magdur site bulunamadi. Once CSV yukleyip siniflandirin.")

    # Tip dagilimi
    tip_dist = q("SELECT category_detail, count(*) as sayi FROM backlinks WHERE category='MAGDUR' GROUP BY category_detail ORDER BY sayi DESC")
    if not tip_dist.empty:
        st.subheader("Magdur Tip Dagilimi")
        fig = px.pie(tip_dist, values="sayi", names="category_detail", color_discrete_sequence=px.colors.qualitative.Pastel)
        st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════
# SAYFA 5: SALDIRGAN AGI
# ══════════════════════════════════════════════════

elif page == "💀 Saldirgan Agi":
    st.header("💀 Saldirgan Agi")

    groups = q("""
        SELECT category_detail, count(*) as sayi
        FROM backlinks WHERE category='SALDIRGAN'
        GROUP BY category_detail ORDER BY sayi DESC
    """)

    if not groups.empty:
        fig = px.bar(groups, x="sayi", y="category_detail", orientation="h",
                     color="sayi", color_continuous_scale="Reds",
                     title="Saldirgan Kategorileri")
        st.plotly_chart(fig, use_container_width=True)

        # Secili kategori detay
        selected = st.selectbox("Detay gormek icin kategori secin",
                                groups["category_detail"].tolist())

        if selected:
            detail = q(f"""
                SELECT referring_url, referring_title, anchor_text, spam_score,
                       first_seen, last_seen
                FROM backlinks
                WHERE category='SALDIRGAN' AND category_detail='{selected}'
                ORDER BY spam_score DESC LIMIT 100
            """)
            if not detail.empty:
                st.dataframe(detail, use_container_width=True, hide_index=True)

            # Google'a sikayet
            if selected in ("pbn_culture_news", "pbn_moonalites", "spam_directory", "sahte_seo_servisi"):
                if st.button(f"🚨 '{selected}' grubunu Google'a sikayet et"):
                    st.info("Google spam raporu OpenClaw ile gonderilecek.")
    else:
        st.info("Saldirgan verisi yok. CSV yukleyip siniflandirin.")


# ══════════════════════════════════════════════════
# SAYFA 6: C2 ALTYAPISI
# ══════════════════════════════════════════════════

elif page == "🖥️ C2 Altyapisi":
    st.header("🖥️ C2 (Command & Control) Altyapisi")

    c2s = q("SELECT * FROM c2_domains ORDER BY created_at")
    if not c2s.empty:
        st.dataframe(c2s, use_container_width=True, hide_index=True)

    # Yeni C2 ekle
    st.divider()
    st.subheader("Yeni C2 Domain Ekle")
    col1, col2, col3 = st.columns(3)
    with col1:
        new_domain = st.text_input("Domain", placeholder="ornek.com")
    with col2:
        new_role = st.selectbox("Rol", ["primary_c2_panel", "fallback_c2_panel", "script_host", "pbn_hub"])
    with col3:
        new_status = st.selectbox("Durum", ["active", "suspended", "blocked", "down"])

    if st.button("➕ C2 Ekle") and new_domain:
        try:
            with engine.connect() as conn:
                conn.execute(text(
                    "INSERT INTO c2_domains (domain, role, status) VALUES (:d, :r, :s) ON CONFLICT (domain) DO NOTHING"
                ), {"d": new_domain, "r": new_role, "s": new_status})
                conn.commit()
            st.success(f"{new_domain} eklendi!")
            st.rerun()
        except Exception as e:
            st.error(str(e))

    # Sikayet butonlari
    st.divider()
    st.subheader("Sikayet Gonder")

    if c2s is not None and not c2s.empty:
        target = st.selectbox("Sikayet edilecek C2", c2s["domain"].tolist())

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            if st.button("☁️ Cloudflare", use_container_width=True):
                with st.spinner("OpenClaw CF formu dolduruyor..."):
                    result = api("post", f"/complain/cloudflare/{target}")
                st.json(result)
        with col2:
            if st.button("🔍 Google SB", use_container_width=True):
                st.info(f"Google Safe Browsing raporu: {target}")
        with col3:
            if st.button("🌐 ICANN", use_container_width=True):
                st.info(f"ICANN DNS abuse raporu: {target}")
        with col4:
            if st.button("🚀 Tumu", type="primary", use_container_width=True):
                with st.spinner("Tum sikayetler gonderiliyor..."):
                    result = api("post", f"/complain/all/{target}")
                st.json(result)


# ══════════════════════════════════════════════════
# SAYFA 7: SIKAYET TAKIBI
# ══════════════════════════════════════════════════

elif page == "📋 Sikayet Takibi":
    st.header("📋 Sikayet Takibi")

    # KPI
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Toplam", qval("SELECT count(*) FROM complaints"))
    c2.metric("Bekleyen", qval("SELECT count(*) FROM complaints WHERE status IN ('pending','submitted')"))
    c3.metric("Cozulmus", qval("SELECT count(*) FROM complaints WHERE status='resolved'"))
    c4.metric("Follow-up Gerekli", qval("SELECT count(*) FROM complaints WHERE next_check_at <= NOW() AND status NOT IN ('resolved')"))

    # Filtre
    col1, col2 = st.columns(2)
    with col1:
        platform_f = st.selectbox("Platform", ["Tumu", "cloudflare", "google_spam", "google_safebrowsing", "icann", "registrar"])
    with col2:
        status_f = st.selectbox("Durum", ["Tumu", "pending", "submitted", "resolved", "reopened"])

    where = "WHERE 1=1"
    if platform_f != "Tumu":
        where += f" AND platform='{platform_f}'"
    if status_f != "Tumu":
        where += f" AND status='{status_f}'"

    complaints = q(f"""
        SELECT target_domain, target_type, platform, status,
               submitted_at, followup_count, max_followups,
               next_check_at, resolved_at, notes
        FROM complaints {where}
        ORDER BY created_at DESC LIMIT 200
    """)
    if not complaints.empty:
        st.dataframe(complaints, use_container_width=True, hide_index=True)

        # Durum dagilimi
        status_dist = q("SELECT status, count(*) as sayi FROM complaints GROUP BY status")
        if not status_dist.empty:
            fig = px.pie(status_dist, values="sayi", names="status",
                         color_discrete_map={"resolved": "#2ecc71", "submitted": "#f39c12",
                                             "pending": "#95a5a6", "reopened": "#e74c3c"})
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Henuz sikayet gonderilmemis.")


# ══════════════════════════════════════════════════
# SAYFA 8: EMAIL TAKIBI
# ══════════════════════════════════════════════════

elif page == "📧 Email Takibi":
    st.header("📧 Email Takibi")

    # KPI
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Gonderilen", qval("SELECT count(*) FROM notifications WHERE status='sent'"))
    c2.metric("Duzeltilmis", qval("SELECT count(*) FROM notifications WHERE status='remediated'"))
    c3.metric("Bekleyen", qval("SELECT count(*) FROM notifications WHERE status='pending'"))
    c4.metric("Follow-up Gerekli", qval("SELECT count(*) FROM notifications WHERE injection_still_active=true AND send_count < max_sends AND next_check_at <= NOW()"))

    # Toplu email gonder butonu
    if st.button("📤 Dogrulanmis Magdurlara Toplu Email Gonder", type="primary"):
        st.warning("Bu islem dogrulanmis (crawl edilmis) magdur sitelere email gonderir. Onayliyor musunuz?")
        if st.button("Evet, Gonder"):
            st.info("Email gonderimi baslatildi. Sonuclari asagida gorebilirsiniz.")

    # Email listesi
    notifications = q("""
        SELECT s.domain, c.email, n.email_type, n.language, n.status,
               n.send_count, n.max_sends, n.sent_at,
               n.injection_still_active, n.remediated_at
        FROM notifications n
        JOIN sites s ON n.site_id = s.id
        JOIN contacts c ON n.contact_id = c.id
        ORDER BY n.created_at DESC LIMIT 200
    """)
    if not notifications.empty:
        st.dataframe(notifications, use_container_width=True, hide_index=True)
    else:
        st.info("Henuz email gonderilmemis. Once magdur siteleri crawl edin ve iletisim bilgisi bulun.")

    # Sablon onizleme
    st.divider()
    st.subheader("Email Sablonu Onizleme")
    lang = st.selectbox("Dil", ["en", "pt", "es", "tr", "fr"])
    template_path = f"/dashboard/../app/notifier/templates/alert_{lang}.txt"
    # Docker volume mount: ./app/notifier/templates:/app/notifier/templates:ro
    if not os.path.exists(template_path):
        template_path = f"/app/notifier/templates/alert_{lang}.txt"
    try:
        with open(template_path) as f:
            st.code(f.read(), language=None)
    except FileNotFoundError:
        st.warning(f"Sablon bulunamadi: {template_path}")


# ══════════════════════════════════════════════════
# SAYFA 9: CRAWLER & KANITLAR
# ══════════════════════════════════════════════════

elif page == "🕷️ Crawler & Kanitlar":
    st.header("🕷️ Crawler & Kanitlar")

    # Crawl edilmis siteler
    crawled = q("""
        SELECT s.domain, s.status, s.injection_verified, s.platform,
               s.last_crawled_at,
               (SELECT count(*) FROM detected_hacklinks h WHERE h.site_id = s.id) as hacklink_sayisi
        FROM sites s
        WHERE s.last_crawled_at IS NOT NULL
        ORDER BY s.last_crawled_at DESC
        LIMIT 100
    """)

    if not crawled.empty:
        st.dataframe(crawled, use_container_width=True, hide_index=True)

    # Tek site crawl
    st.divider()
    st.subheader("Tek Site Crawl")
    crawl_url = st.text_input("Crawl edilecek URL", placeholder="https://ornek.com/")
    if st.button("🕷️ Crawl Baslat", type="primary") and crawl_url:
        st.code(f"docker compose run --rm crawler python -m crawler.cli \"{crawl_url}\"")
        st.warning("Crawler VPN-TR konteynerinde calisir. Yukaridaki komutu terminal'de calistirin.")

    # Kanit goruntuleme
    st.divider()
    st.subheader("Kanit Goruntuleme")

    evidence_dir = Path(EVIDENCE_DIR)
    if evidence_dir.exists():
        domains = sorted([d.name for d in evidence_dir.iterdir() if d.is_dir()])
        if domains:
            selected_domain = st.selectbox("Site secin", domains)
            site_dir = evidence_dir / selected_domain

            tabs = st.tabs(["📸 Screenshot", "🔗 Hacklink'ler", "📄 DOM"])

            with tabs[0]:
                ss_dir = site_dir / "screenshots"
                if ss_dir.exists():
                    for img in sorted(ss_dir.glob("*.png")):
                        st.image(str(img), caption=img.name, use_container_width=True)
                else:
                    st.info("Screenshot bulunamadi")

            with tabs[1]:
                analysis_file = site_dir / "analysis" / "hacklinks.json"
                if analysis_file.exists():
                    import json
                    with open(analysis_file) as f:
                        data = json.load(f)

                    # Rendered hacklink'ler
                    rendered = data.get("rendered_hacklinks", [])
                    if rendered:
                        st.write(f"**Rendered DOM'da tespit edilen: {len(rendered)} hacklink**")
                        for hl in rendered[:30]:
                            with st.expander(f"[{hl.get('score', 0)}] {hl.get('text', '')[:60]}"):
                                st.write(f"**URL:** {hl.get('href', '')}")
                                st.write(f"**Skor:** {hl.get('score', 0)}")
                                st.write(f"**Gizleme:** {hl.get('hiding_method', '')}")
                                st.write(f"**Sebepler:** {', '.join(hl.get('reasons', []))}")

                    # JS diff
                    js_diff = data.get("js_diff_hacklinks", [])
                    if js_diff:
                        st.write(f"**JS ile enjekte edilen: {len(js_diff)} link**")
                        for hl in js_diff[:20]:
                            st.write(f"  - {hl.get('href', '')} ({hl.get('method', '')})")

                    # Enjeksiyon scriptleri
                    scripts = data.get("injection_scripts", [])
                    if scripts:
                        st.write(f"**Enjeksiyon scriptleri: {len(scripts)}**")
                        for s in scripts:
                            if s.get("decoded_c2_urls"):
                                st.error(f"C2 URL: {s['decoded_c2_urls']}")
                else:
                    st.info("Hacklink analizi bulunamadi")

            with tabs[2]:
                dom_dir = site_dir / "dom"
                if dom_dir.exists():
                    for f in sorted(dom_dir.glob("*.html")):
                        with st.expander(f.name):
                            content = f.read_text(encoding="utf-8", errors="replace")
                            st.code(content[:5000], language="html")
                else:
                    st.info("DOM dump bulunamadi")
        else:
            st.info("Henuz kanit toplanmamis. Bir site crawl edin.")
    else:
        st.info("Evidence klasoru bulunamadi.")


# ══════════════════════════════════════════════════
# SAYFA 10: AYARLAR & SISTEM
# ══════════════════════════════════════════════════

elif page == "⚙️ Ayarlar & Sistem":
    st.header("⚙️ Ayarlar & Sistem")

    # VPN Durumu
    st.subheader("🔒 VPN Durumu")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🇹🇷 VPN-TR Kontrol"):
            try:
                result = subprocess.run(
                    ["docker", "exec", "vpn-tr", "curl", "-s", "--max-time", "5", "https://ipinfo.io/json"],
                    capture_output=True, text=True, timeout=10,
                )
                if result.stdout:
                    import json
                    data = json.loads(result.stdout)
                    st.success(f"IP: {data['ip']} | {data.get('city', '')} {data.get('country', '')}")
                else:
                    st.error("VPN-TR yanit vermiyor")
            except Exception as e:
                st.error(f"Hata: {e}")
    with col2:
        if st.button("🇺🇸 VPN-US Kontrol"):
            try:
                result = subprocess.run(
                    ["docker", "exec", "vpn-us", "curl", "-s", "--max-time", "5", "https://ipinfo.io/json"],
                    capture_output=True, text=True, timeout=10,
                )
                if result.stdout:
                    import json
                    data = json.loads(result.stdout)
                    st.success(f"IP: {data['ip']} | {data.get('city', '')} {data.get('country', '')}")
                else:
                    st.error("VPN-US yanit vermiyor")
            except Exception as e:
                st.error(f"Hata: {e}")

    st.divider()

    # DB istatistikleri
    st.subheader("💾 Veritabani")
    db_stats = q("""
        SELECT
            (SELECT count(*) FROM csv_files) as csv_files,
            (SELECT count(*) FROM backlinks) as backlinks,
            (SELECT count(*) FROM sites) as sites,
            (SELECT count(*) FROM detected_hacklinks) as hacklinks,
            (SELECT count(*) FROM contacts) as contacts,
            (SELECT count(*) FROM notifications) as notifications,
            (SELECT count(*) FROM complaints) as complaints,
            (SELECT count(*) FROM c2_domains) as c2_domains
    """)
    if not db_stats.empty:
        st.dataframe(db_stats.T.rename(columns={0: "Kayit Sayisi"}), use_container_width=True)

    st.divider()

    # API durumu
    st.subheader("🔌 API Durumu")
    if st.button("API Health Check"):
        result = api("get", "/health")
        if "error" not in result:
            st.success(f"API: {result}")
        else:
            st.error(f"API hatasi: {result['error']}")

    st.divider()

    # Monitoring
    st.subheader("🔄 Monitoring")
    if st.button("Haftalik Monitoring Dongusunu Calistir", type="primary"):
        with st.spinner("Monitoring calisiyor (re-crawl + follow-up + C2 kontrol)..."):
            result = api("post", "/monitor/weekly")
        st.json(result)

    st.divider()

    # API key durumu
    st.subheader("🔑 API Key Durumu")
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    resend_key = os.getenv("RESEND_API_KEY", "")
    col1, col2 = st.columns(2)
    col1.metric("Gemini API", "✅ Ayarli" if gemini_key and gemini_key != "your_gemini_api_key_here" else "❌ Ayarlanmamis")
    col2.metric("Resend API", "✅ Ayarli" if resend_key and resend_key != "your_resend_api_key_here" else "❌ Ayarlanmamis")
