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
        "complaint_block": "",
        "content_category": "",
    }
    defaults.update(kwargs)

    try:
        return template.format(**defaults)
    except KeyError:
        return template


def get_verification_block(
    language: str,
    keyword: str | None,
    source: str = "raw",
    domain: str = "",
) -> str:
    """Hızlı doğrulama bloğu — sayfa kaynağı/F12 + Ctrl+F ile spam-safe keyword.
    Anchor'dan seçilen 'veren siteler' gibi nötr kelime öbeği mail'e konur;
    spam trigger içermez ama gizli linklerin source'unda yine geçer.

    Keyword bulunamamışsa pasif gözlem cümlesi döner.
    """
    passive = {
        "en": "\nThe page-source view (Ctrl+U) and the DevTools Elements view (F12) both surface the inserted nodes; the report highlights the relevant anchors.\n",
        "tr": "\nSayfa kaynağı görünümü (Ctrl+U) ve DevTools Elements görünümü (F12), eklenen düğümleri ortaya çıkarır; rapor ilgili bağlantıları vurgular.\n",
        "pt": "\nA visualização do código-fonte (Ctrl+U) e a visualização DevTools Elements (F12) revelam os nós inseridos; o relatório destaca as âncoras relevantes.\n",
        "es": "\nLa vista del código fuente (Ctrl+U) y la vista DevTools Elements (F12) muestran los nodos insertados; el informe destaca los anclajes relevantes.\n",
        "fr": "\nLe code source (Ctrl+U) et la vue DevTools Elements (F12) font apparaître les nœuds insérés ; le rapport met en évidence les ancres concernées.\n",
        "de": "\nDie Quelltextansicht (Strg+U) und die DevTools-Elements-Ansicht (F12) zeigen die eingefügten Knoten; der Bericht hebt die relevanten Anker hervor.\n",
        "it": "\nLa vista del sorgente (Ctrl+U) e la vista DevTools Elements (F12) mostrano i nodi inseriti; il rapporto evidenzia gli anchor rilevanti.\n",
        "ru": "\nИсходный код (Ctrl+U) и панель DevTools Elements (F12) показывают вставленные узлы; в отчёте выделены соответствующие якоря.\n",
        "ar": "\nيُظهر عرض شيفرة المصدر (Ctrl+U) وعرض DevTools Elements (F12) العقد المُدرجة؛ ويبرز التقرير المراسي ذات الصلة.\n",
        "zh": "\n页面源代码视图 (Ctrl+U) 和 DevTools Elements 视图 (F12) 都会显示被插入的节点;报告中突出显示了相关锚点。\n",
    }
    if not keyword:
        return passive.get(language, passive["en"])

    kw = keyword.replace('"', '\\"')
    d = domain or "the page"

    blocks = {
        "en": (
            f"\nQuick verification:\n"
            f"  1. Open {d} → press Ctrl+U (page source) or F12 → Elements\n"
            f"  2. Press Ctrl+F and search for: \"{kw}\"\n"
            f"  The match will be inside the hidden anchors we observed.\n"
        ),
        "tr": (
            f"\nHızlı doğrulama:\n"
            f"  1. {d} sayfasını açın → Ctrl+U (sayfa kaynağı) veya F12 → Elements\n"
            f"  2. Ctrl+F ile şunu arayın: \"{kw}\"\n"
            f"  Eşleşme, tespit ettiğimiz gizli bağlantıların içinde olacaktır.\n"
        ),
        "pt": (
            f"\nVerificação rápida:\n"
            f"  1. Abra {d} → Ctrl+U (código-fonte) ou F12 → Elements\n"
            f"  2. Pesquise (Ctrl+F): \"{kw}\"\n"
            f"  A ocorrência estará dentro dos links ocultos que observamos.\n"
        ),
        "es": (
            f"\nVerificación rápida:\n"
            f"  1. Abra {d} → Ctrl+U (código fuente) o F12 → Elements\n"
            f"  2. Busque (Ctrl+F): \"{kw}\"\n"
            f"  La coincidencia estará dentro de los enlaces ocultos detectados.\n"
        ),
        "fr": (
            f"\nVérification rapide :\n"
            f"  1. Ouvrez {d} → Ctrl+U (code source) ou F12 → Elements\n"
            f"  2. Recherchez (Ctrl+F) : \"{kw}\"\n"
            f"  La correspondance se trouve dans les liens cachés observés.\n"
        ),
        "de": (
            f"\nSchnelle Überprüfung:\n"
            f"  1. Öffnen Sie {d} → Strg+U (Quelltext) oder F12 → Elements\n"
            f"  2. Suchen (Strg+F): \"{kw}\"\n"
            f"  Der Treffer befindet sich in den verborgenen Ankern.\n"
        ),
        "it": (
            f"\nVerifica rapida:\n"
            f"  1. Apri {d} → Ctrl+U (sorgente) o F12 → Elements\n"
            f"  2. Cerca (Ctrl+F): \"{kw}\"\n"
            f"  Il riscontro è all'interno degli anchor nascosti osservati.\n"
        ),
        "ru": (
            f"\nБыстрая проверка:\n"
            f"  1. Откройте {d} → Ctrl+U (исходный код) или F12 → Elements\n"
            f"  2. Найдите (Ctrl+F): «{kw}»\n"
            f"  Совпадение находится внутри обнаруженных скрытых ссылок.\n"
        ),
        "ar": (
            f"\nالتحقق السريع:\n"
            f"  1. افتح {d} → Ctrl+U (المصدر) أو F12 → Elements\n"
            f"  2. ابحث (Ctrl+F): \"{kw}\"\n"
            f"  ستجد التطابق داخل الروابط المخفية التي رصدناها.\n"
        ),
        "zh": (
            f"\n快速验证:\n"
            f"  1. 打开 {d} → Ctrl+U(源代码)或 F12 → Elements\n"
            f"  2. 搜索 (Ctrl+F): \"{kw}\"\n"
            f"  匹配项会出现在我们观察到的隐藏锚点中。\n"
        ),
    }
    return blocks.get(language, blocks["en"])


def describe_category(language: str, category: str) -> str:
    """Spam-trigger kelimeleri (gambling, casino, escort, pharmacy, vs.)
    mail'de geçmez. Tüm kategoriler aynı nötr ifadeye düşer; detay rapora bırakılır.
    """
    neutral = {
        "en": "pointing to off-topic, policy-violating third-party sites",
        "tr": "alakasız, politika dışı üçüncü taraf sitelere yönlendiren",
        "pt": "apontando para sites de terceiros fora de tópico e que violam políticas",
        "es": "que apuntan a sitios de terceros fuera de tema y que violan políticas",
        "fr": "renvoyant à des sites tiers hors sujet et contraires aux règles",
        "de": "die auf themenfremde, richtlinienwidrige Drittseiten verweisen",
        "it": "che rimandano a siti terzi fuori tema e in violazione delle policy",
        "ru": "ведущих на сторонние сайты, нарушающие правила",
        "ar": "تشير إلى مواقع لأطراف ثالثة خارج السياق وتنتهك السياسات",
        "zh": "指向偏离主题且违反政策的第三方网站",
    }
    return neutral.get(language, neutral["en"])


def get_complaint_block(language: str) -> str:
    """Spam-trigger kelimeler (abuse, Cloudflare, complaint, report)
    mail içeriğinde minimum tutuluyor — alıcı raporda Section 7'yi okur.
    """
    blocks = {
        "en": (
            "\nThe report also lists the upstream providers behind the attacker "
            "infrastructure and the appropriate reporting channels for each.\n"
        ),
        "tr": (
            "\nSaldırgan altyapısının arkasındaki sağlayıcılar ve uygun bildirim "
            "kanalları raporda ayrıntılı şekilde yer alıyor.\n"
        ),
        "pt": (
            "\nO relatório também lista os provedores upstream e os canais "
            "apropriados de notificação.\n"
        ),
        "es": (
            "\nEl informe también enumera los proveedores upstream y los canales "
            "adecuados de notificación.\n"
        ),
        "fr": (
            "\nLe rapport répertorie aussi les fournisseurs en amont et les canaux "
            "de notification adaptés.\n"
        ),
        "de": (
            "\nDer Bericht listet zudem die Upstream-Anbieter und die jeweils "
            "passenden Meldekanäle auf.\n"
        ),
        "it": (
            "\nIl rapporto elenca anche i provider upstream e i canali di "
            "segnalazione adatti.\n"
        ),
        "ru": (
            "\nВ отчёте также перечислены вышестоящие провайдеры и подходящие "
            "каналы уведомления.\n"
        ),
        "ar": (
            "\nيسرد التقرير أيضاً مزودي الخدمة في الأعلى وقنوات الإبلاغ المناسبة لكل منهم.\n"
        ),
        "zh": (
            "\n报告还列出了上游服务提供商和针对每一方的适当通知渠道。\n"
        ),
    }
    return blocks.get(language, blocks["en"])


def get_subject(language: str, domain: str) -> str:
    """Dile göre email konusu — pasif gözlem tonu."""
    subjects = {
        "en": f"AbuseRadar index entry: {domain}",
        "tr": f"AbuseRadar dizin kaydı: {domain}",
        "pt": f"Entrada no índice AbuseRadar: {domain}",
        "es": f"Entrada en el índice AbuseRadar: {domain}",
        "fr": f"Entrée d'index AbuseRadar : {domain}",
        "de": f"AbuseRadar Index-Eintrag: {domain}",
        "it": f"Voce nell'indice AbuseRadar: {domain}",
        "ru": f"Запись в индексе AbuseRadar: {domain}",
        "ar": f"إدخال في فهرس AbuseRadar: {domain}",
        "zh": f"AbuseRadar 索引条目:{domain}",
    }
    return subjects.get(language, subjects["en"])
