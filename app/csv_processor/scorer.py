"""Spam skor hesaplama - kural tabanlı."""

GAMBLING_KEYWORDS = [
    "deneme bonusu",
    "bahis",
    "casino",
    "slot ",
    "betting",
    "grandpashabet",
    "sahabet",
    "onwin",
    "jojobet",
    "perabet",
    "1xbet",
    "1win",
    "betgaranti",
    "cratosroyalbet",
    "superbet",
    "betwoon",
    "radissonbet",
    "damabet",
    "escort",
    "porno",
]

TELEGRAM_PATTERNS = [
    "@SALESOVEN",
    "@moonalites",
    "@LINKS_DEALER",
    "t.me/SALESOVEN",
    "t.me/moonalites",
]

PBN_TITLE_PATTERNS = [
    "Culture News",
    "website list 1276",
    "Changes In The World of SEO",
    "Rank Faster on Google",
    "TELEGRAM @SALESOVEN",
    "TELEGRAM @LINKS_DEALER",
]

SEO_SPAM_DOMAINS = [
    "itxoft",
    "seoexpress",
    "rankzly",
    "buyseolink",
    "skylinkseo",
    "primeseo",
    "zoldexlinks",
    "seodaro",
    "royalseohub",
    "rank-top",
    "rank-fast",
    "prolinkbox",
    "linksjump",
]


def calculate_spam_score(row: dict) -> int:
    """CSV satırı için spam skoru hesapla (0-100+)."""
    score = 0
    anchor = (row.get("anchor_text") or "").lower()
    title = (row.get("referring_title") or "").lower()
    domain = (row.get("referring_url") or "").lower()
    is_spam = str(row.get("is_spam_flag", "")).lower() == "true"
    rendered = str(row.get("is_rendered", "")).lower() == "true"
    raw = str(row.get("is_raw", "")).lower() == "true"
    dr = float(row.get("domain_rating") or 0)
    traffic = int(row.get("traffic") or 0)

    # Anchor text bahis keyword'ü
    if any(kw in anchor for kw in GAMBLING_KEYWORDS):
        score += 50

    # Ahrefs spam flag
    if is_spam:
        score += 30

    # JS enjeksiyon (rendered=true, raw=false)
    if rendered and not raw:
        score += 40

    # DR çok düşük
    if dr < 5:
        score += 20

    # Trafik sıfır
    if traffic == 0:
        score += 15

    # PBN title pattern'i
    if any(p.lower() in title for p in PBN_TITLE_PATTERNS):
        score += 50

    # Telegram satıcı referansı
    if any(p.lower() in title for p in TELEGRAM_PATTERNS):
        score += 60

    # SEO spam domain
    if any(s in domain for s in SEO_SPAM_DOMAINS):
        score += 40

    # .gov veya .edu domain (mağdur olma olasılığı yüksek - farklı anlam)
    gov_edu = any(tld in domain for tld in [".gov.", ".edu.", ".ac."])
    if gov_edu and any(kw in anchor for kw in GAMBLING_KEYWORDS):
        score += 30

    return min(score, 100)
