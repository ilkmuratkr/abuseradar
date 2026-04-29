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
    """Alıcının doğrulama yönergesi — spam-trigger keyword'sü mail'de geçmez,
    raporda gösterilir. Gmail/Outlook ML filtreleri 'gambling/adult/pharma'
    kelimelerini gördüğünde direkt spam'e atıyor.
    """
    if not keyword:
        return ""
    d = domain or "the page"

    blocks = {
        "en": (
            f"\nQuick verification:\n"
            f"  1. Open {d} in your browser\n"
            f"  2. View page source (Ctrl+U) or DevTools → Elements (F12)\n"
            f"  3. Search (Ctrl+F) for the highlighted anchor shown in the report's Findings section\n"
            f"  At least one view will surface the hidden links we observed.\n"
        ),
        "tr": (
            f"\nHızlı doğrulama:\n"
            f"  1. {d} sayfasını tarayıcıda açın\n"
            f"  2. Sayfa kaynağı (Ctrl+U) veya DevTools → Elements (F12) görüntüleyin\n"
            f"  3. Raporun bulgular bölümünde işaretli anahtar metni Ctrl+F ile arayın\n"
            f"  En az birinde tespit ettiğimiz gizli bağlantıları göreceksiniz.\n"
        ),
        "pt": (
            f"\nVerificação rápida:\n"
            f"  1. Abra {d} no seu navegador\n"
            f"  2. Veja o código-fonte (Ctrl+U) ou DevTools → Elements (F12)\n"
            f"  3. Pesquise (Ctrl+F) o termo destacado na seção de achados do relatório\n"
            f"  Em pelo menos uma das visões aparecerão os links ocultos.\n"
        ),
        "es": (
            f"\nVerificación rápida:\n"
            f"  1. Abra {d} en su navegador\n"
            f"  2. Vea el código fuente (Ctrl+U) o DevTools → Elements (F12)\n"
            f"  3. Busque (Ctrl+F) el término destacado en la sección de hallazgos del informe\n"
            f"  En al menos una vista aparecerán los enlaces ocultos.\n"
        ),
        "fr": (
            f"\nVérification rapide :\n"
            f"  1. Ouvrez {d} dans votre navigateur\n"
            f"  2. Affichez le code source (Ctrl+U) ou DevTools → Elements (F12)\n"
            f"  3. Recherchez (Ctrl+F) le terme mis en évidence dans la section constats du rapport\n"
            f"  Au moins une vue révélera les liens cachés.\n"
        ),
        "de": (
            f"\nSchnelle Überprüfung:\n"
            f"  1. Öffnen Sie {d} im Browser\n"
            f"  2. Quelltext (Strg+U) oder DevTools → Elements (F12) anzeigen\n"
            f"  3. Suchen Sie (Strg+F) nach dem im Bericht hervorgehobenen Begriff\n"
            f"  Mindestens eine Ansicht zeigt die versteckten Links.\n"
        ),
        "it": (
            f"\nVerifica rapida:\n"
            f"  1. Apri {d} nel browser\n"
            f"  2. Visualizza il sorgente (Ctrl+U) o DevTools → Elements (F12)\n"
            f"  3. Cerca (Ctrl+F) il termine evidenziato nella sezione risultati del rapporto\n"
            f"  In almeno una vista compariranno i link nascosti.\n"
        ),
        "ru": (
            f"\nБыстрая проверка:\n"
            f"  1. Откройте {d} в браузере\n"
            f"  2. Просмотрите исходный код (Ctrl+U) или DevTools → Elements (F12)\n"
            f"  3. Найдите (Ctrl+F) выделенный термин из раздела находок в отчёте\n"
            f"  Хотя бы один из видов покажет скрытые ссылки.\n"
        ),
        "ar": (
            f"\nالتحقق السريع:\n"
            f"  1. افتح {d} في المتصفح\n"
            f"  2. اعرض شيفرة المصدر (Ctrl+U) أو DevTools → Elements (F12)\n"
            f"  3. ابحث (Ctrl+F) عن المصطلح المظلل في قسم النتائج بالتقرير\n"
            f"  ستظهر الروابط المخفية في إحدى الواجهتين على الأقل.\n"
        ),
        "zh": (
            f"\n快速验证:\n"
            f"  1. 在浏览器中打开 {d}\n"
            f"  2. 查看页面源代码 (Ctrl+U) 或 DevTools → Elements (F12)\n"
            f"  3. 搜索 (Ctrl+F) 报告发现部分中高亮显示的关键词\n"
            f"  至少在其中一个视图中会显示这些隐藏链接。\n"
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
