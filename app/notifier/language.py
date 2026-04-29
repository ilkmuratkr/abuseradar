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


def get_verification_block(language: str, keyword: str | None, source: str = "raw") -> str:
    """Alıcının 15-30 saniyede mailin gerçekliğini doğrulayabileceği talimat.

    Kaynak ne olursa olsun her iki yöntemi de söyleriz — kullanıcı hangisi
    işe yaradıysa onu kullanır:
      - Ctrl+U → Ctrl+F: HTML'de düz gizli linkleri yakalar
      - F12 → Elements → Ctrl+F: JS ile çalışma anında eklenen linkleri yakalar
    """
    if not keyword:
        return ""
    kw = keyword.replace('"', '\\"')

    blocks = {
        "en": (
            f"\nQuick verification (30 seconds):\n"
            f"  1. Open the page in your browser\n"
            f"  2. Try either: Ctrl+U (page source) — or F12 → Elements\n"
            f"  3. Press Ctrl+F and search for: \"{kw}\"\n"
            f"  At least one view will show the hidden links we observed.\n"
        ),
        "tr": (
            f"\nHızlı doğrulama (30 saniye):\n"
            f"  1. Sayfayı tarayıcıda açın\n"
            f"  2. Ya Ctrl+U (sayfa kaynağı) ya da F12 → Elements ile içeriği görün\n"
            f"  3. Ctrl+F ile şunu arayın: \"{kw}\"\n"
            f"  En az birinde bizim de tespit ettiğimiz gizli bağlantıları göreceksiniz.\n"
        ),
        "pt": (
            f"\nVerificação rápida (30 segundos):\n"
            f"  1. Abra a página no navegador\n"
            f"  2. Use Ctrl+U (código-fonte) — ou F12 → Elements\n"
            f"  3. Pressione Ctrl+F e pesquise por: \"{kw}\"\n"
            f"  Em pelo menos uma das visões verá os mesmos links ocultos.\n"
        ),
        "es": (
            f"\nVerificación rápida (30 segundos):\n"
            f"  1. Abra la página en el navegador\n"
            f"  2. Use Ctrl+U (código fuente) — o F12 → Elements\n"
            f"  3. Pulse Ctrl+F y busque: \"{kw}\"\n"
            f"  En al menos una vista verá los mismos enlaces ocultos que detectamos.\n"
        ),
        "fr": (
            f"\nVérification rapide (30 secondes) :\n"
            f"  1. Ouvrez la page dans le navigateur\n"
            f"  2. Essayez Ctrl+U (code source) — ou F12 → Elements\n"
            f"  3. Appuyez sur Ctrl+F et recherchez : \"{kw}\"\n"
            f"  Au moins une des deux vues révélera les liens cachés que nous avons observés.\n"
        ),
        "de": (
            f"\nSchnelle Überprüfung (30 Sekunden):\n"
            f"  1. Öffnen Sie die Seite im Browser\n"
            f"  2. Versuchen Sie Strg+U (Quelltext) — oder F12 → Elements\n"
            f"  3. Drücken Sie Strg+F und suchen Sie: \"{kw}\"\n"
            f"  Mindestens eine Ansicht zeigt die versteckten Links, die wir beobachtet haben.\n"
        ),
        "it": (
            f"\nVerifica rapida (30 secondi):\n"
            f"  1. Apri la pagina nel browser\n"
            f"  2. Usa Ctrl+U (sorgente) — oppure F12 → Elements\n"
            f"  3. Premi Ctrl+F e cerca: \"{kw}\"\n"
            f"  In almeno una delle viste vedrai gli stessi link nascosti che abbiamo osservato.\n"
        ),
        "ru": (
            f"\nБыстрая проверка (30 секунд):\n"
            f"  1. Откройте страницу в браузере\n"
            f"  2. Используйте Ctrl+U (исходный код) — или F12 → Elements\n"
            f"  3. Нажмите Ctrl+F и найдите: «{kw}»\n"
            f"  Хотя бы один из видов покажет те же скрытые ссылки, что нашли мы.\n"
        ),
        "ar": (
            f"\nالتحقق السريع (30 ثانية):\n"
            f"  1. افتح الصفحة في المتصفح\n"
            f"  2. جرّب Ctrl+U (شيفرة المصدر) — أو F12 ثم Elements\n"
            f"  3. اضغط Ctrl+F وابحث عن: \"{kw}\"\n"
            f"  ستجد في إحدى الواجهتين على الأقل نفس الروابط المخفية التي رصدناها.\n"
        ),
        "zh": (
            f"\n快速验证(30秒):\n"
            f"  1. 在浏览器中打开页面\n"
            f"  2. 尝试 Ctrl+U(查看源代码)或 F12 → Elements\n"
            f"  3. 按 Ctrl+F 搜索:\"{kw}\"\n"
            f"  至少在其中一个视图中会显示我们观察到的相同隐藏链接。\n"
        ),
    }
    return blocks.get(language, blocks["en"])


def describe_category(language: str, category: str) -> str:
    """Hacklink kategorisi için kısa, spam-sızma riski düşük açıklayıcı sıfat.

    Mail'de "{count} adet üçüncü taraf bağlantı (kumar/yetişkin/...)
    promosyonu yapan içerikler" şeklinde kullanılır.
    """
    descriptions = {
        "gambling": {
            "en": "promoting unrelated betting/gambling sites",
            "tr": "alakasız bahis/kumar siteleri tanıtan",
            "pt": "promovendo sites de apostas/jogo sem relação",
            "es": "promocionando sitios de apuestas/juego no relacionados",
            "fr": "faisant la promotion de sites de paris/jeux sans rapport",
            "de": "mit Werbung für sachfremde Wett- und Glücksspielseiten",
            "it": "che promuovono siti di scommesse/gioco non correlati",
            "ru": "продвигающих сторонние сайты ставок/азартных игр",
            "ar": "تروج لمواقع مراهنات/قمار غير ذات صلة",
            "zh": "推广无关的博彩/赌博网站",
        },
        "adult": {
            "en": "promoting unrelated adult/escort services",
            "tr": "alakasız yetişkin/escort hizmetleri tanıtan",
            "pt": "promovendo serviços adultos/escort sem relação",
            "es": "promocionando servicios adultos/escort no relacionados",
            "fr": "faisant la promotion de services pour adultes sans rapport",
            "de": "mit Werbung für sachfremde Erwachseneninhalte",
            "it": "che promuovono servizi per adulti non correlati",
            "ru": "продвигающих сторонние сервисы для взрослых",
            "ar": "تروج لمحتوى للبالغين غير ذي صلة",
            "zh": "推广无关的成人/陪护服务",
        },
        "pharma": {
            "en": "promoting unauthorized pharmacy/RX content",
            "tr": "yetkisiz eczane/ilaç tanıtımı yapan",
            "pt": "promovendo farmácia/medicamentos não autorizados",
            "es": "promocionando farmacia/medicamentos no autorizados",
            "fr": "faisant la promotion de pharmacie non autorisée",
            "de": "mit Werbung für nicht autorisierte Arzneimittel",
            "it": "che promuovono farmacie/farmaci non autorizzati",
            "ru": "продвигающих несанкционированную фармацию",
            "ar": "تروج لصيدليات/أدوية غير مرخصة",
            "zh": "推广未经授权的药品内容",
        },
        "loan_scam": {
            "en": "promoting suspicious loan/credit offers",
            "tr": "şüpheli kredi/borç tekliflerini tanıtan",
            "pt": "promovendo ofertas suspeitas de empréstimo",
            "es": "promocionando ofertas sospechosas de préstamos",
            "fr": "faisant la promotion d'offres de prêts suspectes",
            "de": "mit Werbung für zweifelhafte Kreditangebote",
            "it": "che promuovono offerte di prestito sospette",
            "ru": "продвигающих подозрительные кредитные предложения",
            "ar": "تروج لعروض قروض مشبوهة",
            "zh": "推广可疑的贷款/信贷服务",
        },
        "off_topic": {
            "en": "pointing to off-topic, policy-violating sites",
            "tr": "alakasız, politika dışı sitelere yönlendiren",
            "pt": "apontando para sites fora de tópico e que violam políticas",
            "es": "que apuntan a sitios fuera de tema y que violan políticas",
            "fr": "renvoyant à des sites hors sujet et contraires aux règles",
            "de": "die auf themenfremde, richtlinienwidrige Seiten verweisen",
            "it": "che rimandano a siti fuori tema e in violazione delle policy",
            "ru": "ведущих на сторонние сайты, нарушающие правила",
            "ar": "تشير إلى مواقع خارج الموضوع تنتهك السياسات",
            "zh": "指向偏离主题且违反政策的网站",
        },
    }
    cat = descriptions.get(category, descriptions["off_topic"])
    return cat.get(language, cat["en"])


def get_complaint_block(language: str) -> str:
    """Mail'de tek satır profesyonel ipucu — detay raporda.

    URL/marka adı vermeyiz; spam görünümünü düşürür ve daha kurumsal durur.
    """
    blocks = {
        "en": (
            "\nThe report also documents the upstream providers behind the attacker "
            "infrastructure and the appropriate abuse-reporting channels for each.\n"
        ),
        "tr": (
            "\nSaldırgan altyapısının arkasındaki sağlayıcılar ve her biri için uygun "
            "şikayet kanalları raporda ayrıntılı olarak belgelenmiştir.\n"
        ),
        "pt": (
            "\nO relatório também documenta os provedores upstream por trás da "
            "infraestrutura atacante e os canais apropriados de denúncia de abuso.\n"
        ),
        "es": (
            "\nEl informe también documenta los proveedores upstream detrás de la "
            "infraestructura del atacante y los canales adecuados de denuncia de abuso.\n"
        ),
        "fr": (
            "\nLe rapport documente également les fournisseurs en amont de "
            "l'infrastructure de l'attaquant ainsi que les canaux de signalement appropriés.\n"
        ),
        "de": (
            "\nDer Bericht dokumentiert zudem die Upstream-Anbieter hinter der "
            "Angreifer-Infrastruktur sowie die jeweils passenden Abuse-Meldekanäle.\n"
        ),
        "it": (
            "\nIl rapporto documenta inoltre i provider upstream dietro "
            "l'infrastruttura dell'aggressore e i canali appropriati di segnalazione.\n"
        ),
        "ru": (
            "\nВ отчёте также задокументированы вышестоящие провайдеры за инфраструктурой "
            "злоумышленника и соответствующие каналы для подачи жалоб.\n"
        ),
        "ar": (
            "\nيوثّق التقرير أيضاً مزودي الخدمة الذين تقف خلف بنية المهاجم التحتية، "
            "إلى جانب قنوات الإبلاغ عن الإساءة المناسبة لكل منهم.\n"
        ),
        "zh": (
            "\n报告还记录了攻击者基础设施背后的上游服务提供商,以及针对每一方的适当滥用举报渠道。\n"
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
