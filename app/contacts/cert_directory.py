"""Ülke CERT ekipleri iletişim dizini."""

CERT_CONTACTS = {
    "BR": {"name": "CERT.br", "email": "cert@cert.br", "url": "https://www.cert.br/"},
    "LK": {"name": "Sri Lanka CERT", "email": "cert@cert.gov.lk"},
    "NG": {"name": "ngCERT", "email": "info@cert.gov.ng"},
    "CO": {"name": "ColCERT", "email": "contacto@colcert.gov.co"},
    "CL": {"name": "CSIRT Chile", "email": "csirt@csirt.gob.cl"},
    "IN": {"name": "CERT-In", "email": "incident@cert-in.org.in"},
    "TH": {"name": "ThaiCERT", "email": "report@thaicert.or.th"},
    "MX": {"name": "CERT-MX", "email": "cert-mx@cert-mx.gob.mx"},
    "AR": {"name": "CERT.ar", "email": "incidentes@cert.ar"},
    "MZ": {"name": "MozCERT", "email": "info@mozcert.org.mz"},
    "TR": {"name": "USOM (TR-CERT)", "email": "bildirim@usom.gov.tr"},
    "US": {"name": "CISA", "email": "report@cisa.gov"},
    "GB": {"name": "NCSC UK", "email": "report@ncsc.gov.uk"},
    "AU": {"name": "ACSC", "email": "asd.assist@defence.gov.au"},
    "DE": {"name": "CERT-Bund", "email": "certbund@bsi.bund.de"},
    "FR": {"name": "CERT-FR", "email": "cert-fr@ssi.gouv.fr"},
    "JP": {"name": "JPCERT/CC", "email": "info@jpcert.or.jp"},
    "KR": {"name": "KrCERT/CC", "email": "cert@krcert.or.kr"},
    "ID": {"name": "ID-CERT", "email": "cert@cert.or.id"},
    "PK": {"name": "PakCERT", "email": "info@pakcert.org"},
}


def get_cert_for_country(country_code: str) -> dict | None:
    """Ülke kodu ile CERT iletişim bilgisi döndür."""
    return CERT_CONTACTS.get(country_code.upper())


def get_cert_for_domain(domain: str) -> dict | None:
    """Domain TLD'sinden ülke CERT'ini bul."""
    from utils.helpers import detect_country_from_domain
    country = detect_country_from_domain(domain)
    if country:
        return get_cert_for_country(country)
    return None
