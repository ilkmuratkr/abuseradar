"""Major service whitelist — bu domain'lere giden link'ler asla hacklink sayılmaz.

Frontend (web/r.html, evidence-detail.html) ile aynı listedir.
"""

# eTLD+1 listesi — `host == d` veya `host.endswith("." + d)` ile eşleşir.
SAFE_DOMAINS: frozenset[str] = frozenset({
    # Google
    "google.com", "gmail.com", "googleusercontent.com", "googleapis.com",
    "gstatic.com", "youtube.com", "youtu.be", "googleadservices.com",
    "doubleclick.net", "blogger.com",
    # Microsoft
    "microsoft.com", "outlook.com", "office.com", "live.com", "hotmail.com",
    "windows.com", "msn.com", "bing.com", "azure.com", "sharepoint.com",
    "onedrive.com",
    # Apple
    "apple.com", "icloud.com", "itunes.com", "appstore.com",
    # Amazon
    "amazon.com", "amazonaws.com",
    # Social
    "facebook.com", "fb.com", "twitter.com", "x.com", "instagram.com",
    "whatsapp.com", "linkedin.com", "tiktok.com", "snapchat.com",
    "pinterest.com", "reddit.com", "tumblr.com",
    # Comm
    "telegram.org", "discord.com", "slack.com", "zoom.us", "skype.com",
    # Dev / CDN
    "github.com", "gitlab.com", "bitbucket.org", "stackoverflow.com",
    "npmjs.com", "cloudflare.com", "jsdelivr.net", "cdnjs.com", "unpkg.com",
    "fontawesome.com", "mozilla.org", "w3.org", "w3schools.com",
    # Knowledge
    "wikipedia.org", "wikimedia.org", "wiktionary.org",
    # Media
    "yahoo.com", "vimeo.com", "dailymotion.com", "soundcloud.com",
    "spotify.com", "twitch.tv",
    # Commerce / SaaS
    "paypal.com", "stripe.com", "wordpress.com", "wordpress.org",
    "wix.com", "squarespace.com", "adobe.com", "behance.net", "dropbox.com",
})


def is_safe_domain(host: str) -> bool:
    """Host bir major service domain'ine ait mi?"""
    if not host:
        return False
    h = host.lower().lstrip(".")
    if h.startswith("www."):
        h = h[4:]
    return any(h == d or h.endswith("." + d) for d in SAFE_DOMAINS)
