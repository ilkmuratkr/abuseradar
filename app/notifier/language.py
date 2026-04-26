"""Dil tespiti ve şablon seçimi."""

from pathlib import Path

from utils.helpers import detect_language_from_domain

TEMPLATES_DIR = Path(__file__).parent / "templates"

AVAILABLE_LANGUAGES = {"en", "pt", "es", "tr", "fr"}


def get_language(domain: str, csv_language: str | None = None) -> str:
    """Domain ve CSV verisinden dil tespit et."""
    # 1. CSV'deki Language sütunu
    if csv_language:
        lang = csv_language.split(",")[0].strip().lower()[:2]
        if lang in AVAILABLE_LANGUAGES:
            return lang

    # 2. Domain TLD'si
    lang = detect_language_from_domain(domain)
    if lang in AVAILABLE_LANGUAGES:
        return lang

    return "en"


def render_template(language: str, **kwargs) -> str:
    """Dile göre email şablonu render et."""
    if language not in AVAILABLE_LANGUAGES:
        language = "en"

    template_path = TEMPLATES_DIR / f"alert_{language}.txt"
    if not template_path.exists():
        template_path = TEMPLATES_DIR / "alert_en.txt"

    template = template_path.read_text(encoding="utf-8")

    # Varsayılan değerler
    defaults = {
        "url": "",
        "domain": "",
        "hacklink_count": 0,
        "first_seen": "N/A",
        "report_url": "#",
    }
    defaults.update(kwargs)

    try:
        return template.format(**defaults)
    except KeyError:
        return template


def get_subject(language: str, domain: str) -> str:
    """Dile göre email konusu."""
    subjects = {
        "en": f"Security notice for {domain} - unauthorized content detected",
        "pt": f"Aviso de seguranca para {domain} - conteudo nao autorizado detectado",
        "es": f"Aviso de seguridad para {domain} - contenido no autorizado detectado",
        "tr": f"{domain} icin guvenlik bildirimi - yetkisiz icerik tespit edildi",
        "fr": f"Avis de securite pour {domain} - contenu non autorise detecte",
    }
    return subjects.get(language, subjects["en"])
