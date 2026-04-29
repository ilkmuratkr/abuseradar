"""Dil tespiti ve şablon seçimi."""

from pathlib import Path

from utils.helpers import detect_language_from_domain

TEMPLATES_DIR = Path(__file__).parent / "templates"

AVAILABLE_LANGUAGES = {"en", "tr", "pt", "es", "fr", "de", "it", "ru", "ar", "zh"}


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
        "evidence_block": "",
    }
    defaults.update(kwargs)

    try:
        return template.format(**defaults)
    except KeyError:
        return template


def get_verification_block(language: str, url: str, keyword: str | None) -> str:
    """Alıcının 15 saniyede mailin gerçekliğini doğrulayabileceği talimat bloğu.

    Sayfanın kaynağına bakıp Ctrl+F ile keyword aratma yönergesi.
    Keyword yoksa boş string döner (template'de placeholder boşalır).
    """
    if not keyword:
        return ""
    # Tek tırnak/çift tırnak metin içinde olabilir, basit kaçış:
    kw = keyword.replace('"', '\\"')

    blocks = {
        "en": (
            f"\nQuick verification (15 seconds):\n"
            f"  1. Open {url} in your browser\n"
            f"  2. Press Ctrl+U (Cmd+Option+U on Mac) to view page source\n"
            f"  3. Press Ctrl+F and search for: \"{kw}\"\n"
            f"  You'll find the same hidden links we observed.\n"
        ),
        "tr": (
            f"\nHızlı doğrulama (15 saniye):\n"
            f"  1. Tarayıcıda {url} sayfasını açın\n"
            f"  2. Ctrl+U (Mac'te Cmd+Option+U) ile sayfa kaynağını açın\n"
            f"  3. Ctrl+F ile şunu arayın: \"{kw}\"\n"
            f"  Bizim de tespit ettiğimiz gizli bağlantıları siz de göreceksiniz.\n"
        ),
        "pt": (
            f"\nVerificação rápida (15 segundos):\n"
            f"  1. Abra {url} no seu navegador\n"
            f"  2. Pressione Ctrl+U (Cmd+Option+U no Mac) para ver o código-fonte\n"
            f"  3. Pressione Ctrl+F e pesquise por: \"{kw}\"\n"
            f"  Você verá os mesmos links ocultos que observamos.\n"
        ),
        "es": (
            f"\nVerificación rápida (15 segundos):\n"
            f"  1. Abra {url} en su navegador\n"
            f"  2. Pulse Ctrl+U (Cmd+Option+U en Mac) para ver el código fuente\n"
            f"  3. Pulse Ctrl+F y busque: \"{kw}\"\n"
            f"  Encontrará los mismos enlaces ocultos que detectamos.\n"
        ),
        "fr": (
            f"\nVérification rapide (15 secondes) :\n"
            f"  1. Ouvrez {url} dans votre navigateur\n"
            f"  2. Appuyez sur Ctrl+U (Cmd+Option+U sur Mac) pour voir le code source\n"
            f"  3. Appuyez sur Ctrl+F et recherchez : \"{kw}\"\n"
            f"  Vous trouverez les mêmes liens cachés que nous avons observés.\n"
        ),
        "de": (
            f"\nSchnelle Überprüfung (15 Sekunden):\n"
            f"  1. Öffnen Sie {url} in Ihrem Browser\n"
            f"  2. Drücken Sie Strg+U (Cmd+Option+U am Mac), um den Quelltext anzuzeigen\n"
            f"  3. Drücken Sie Strg+F und suchen Sie nach: \"{kw}\"\n"
            f"  Sie werden dieselben versteckten Links finden, die wir beobachtet haben.\n"
        ),
        "it": (
            f"\nVerifica rapida (15 secondi):\n"
            f"  1. Apri {url} nel tuo browser\n"
            f"  2. Premi Ctrl+U (Cmd+Option+U su Mac) per vedere il codice sorgente\n"
            f"  3. Premi Ctrl+F e cerca: \"{kw}\"\n"
            f"  Troverai gli stessi link nascosti che abbiamo osservato.\n"
        ),
        "ru": (
            f"\nБыстрая проверка (15 секунд):\n"
            f"  1. Откройте {url} в браузере\n"
            f"  2. Нажмите Ctrl+U (Cmd+Option+U на Mac), чтобы открыть исходный код\n"
            f"  3. Нажмите Ctrl+F и найдите: «{kw}»\n"
            f"  Вы найдёте те же скрытые ссылки, что и мы.\n"
        ),
        "ar": (
            f"\nالتحقق السريع (15 ثانية):\n"
            f"  1. افتح {url} في متصفحك\n"
            f"  2. اضغط Ctrl+U (أو Cmd+Option+U على الماك) لعرض شيفرة المصدر\n"
            f"  3. اضغط Ctrl+F وابحث عن: \"{kw}\"\n"
            f"  ستجد نفس الروابط المخفية التي رصدناها.\n"
        ),
        "zh": (
            f"\n快速验证(15秒):\n"
            f"  1. 在浏览器中打开 {url}\n"
            f"  2. 按 Ctrl+U(Mac 上 Cmd+Option+U)查看页面源代码\n"
            f"  3. 按 Ctrl+F 搜索:\"{kw}\"\n"
            f"  您会发现与我们观察到的相同的隐藏链接。\n"
        ),
    }
    return blocks.get(language, blocks["en"])


def get_subject(language: str, domain: str) -> str:
    """Dile göre email konusu — 'human' ton, spam tetik kelimeleri azaltılmış."""
    subjects = {
        "en": f"A finding on {domain} — quick note from AbuseRadar",
        "tr": f"{domain} sitesinde bir bulgu — AbuseRadar'dan kısa not",
        "pt": f"Algo encontrado em {domain} — uma nota rápida da AbuseRadar",
        "es": f"Algo detectado en {domain} — una nota breve de AbuseRadar",
        "fr": f"Un constat sur {domain} — note rapide d'AbuseRadar",
        "de": f"Ein Befund zu {domain} — kurze Notiz von AbuseRadar",
        "it": f"Un riscontro su {domain} — breve nota da AbuseRadar",
        "ru": f"Замечание по {domain} — короткое сообщение от AbuseRadar",
        "ar": f"ملاحظة بشأن {domain} — رسالة قصيرة من AbuseRadar",
        "zh": f"关于 {domain} 的一项发现 — AbuseRadar 简要通知",
    }
    return subjects.get(language, subjects["en"])
