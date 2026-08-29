
import os
import re
import sys
import json
import time
import html
import urllib.parse
import datetime

from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import feedparser
from bs4 import BeautifulSoup
from dateutil import parser

from database import (
    upsert_article,
    get_all_articles,
    get_article_by_link,
    update_article,
    save_run_log,
)


# ============================================================
# KONFIGURASI
# ============================================================

TAHUN_TARGET = 2026
MAX_WORKERS = 10
REQUEST_TIMEOUT = 15

FIRST_PARAGRAPH_LIMIT = 5
MIN_ARTICLE_TEXT = 100

NAMA_SATKER = os.getenv(
    "NAMA_SATKER",
    "Kejaksaan Negeri Deli Serdang"
).strip()

TELEGRAM_TOKEN = os.getenv(
    "TELEGRAM_TOKEN",
    ""
).strip()

CHAT_ID = os.getenv(
    "CHAT_ID",
    ""
).strip()


# ============================================================
# TARGET SATKER
# ============================================================

TARGET_KEJARI_KEYWORDS = [
    "kejaksaan negeri deli serdang",
    "kejari deli serdang",
    "kajari deli serdang",
    "kejari deliserdang",
    "kejaksaan deliserdang",
    "kejaksaan deli serdang",

    "cabang kejaksaan negeri pancur batu",
    "cabjari pancur batu",
    "kacabjari pancur batu",

    "cabang kejaksaan negeri labuhan deli",
    "cabjari labuhan deli",
    "kacabjari labuhan deli",
]


SEARCH_TARGETS = [
    '"Kejaksaan Negeri Deli Serdang"',
    '"Kejari Deli Serdang"',
    '"Kajari Deli Serdang"',
    '"Kejari Deliserdang"',
    '"Kejaksaan Deli Serdang"',
    '"Cabjari Pancur Batu"',
    '"Cabjari Labuhan Deli"',
]


# ============================================================
# ATURAN NEGATIF KUAT
# ============================================================

NEGATIVE_STRONG_RULES = {

    "skandal": 12,
    "skandal perselingkuhan": 18,
    "perselingkuhan": 15,
    "selingkuh": 14,
    "pelakor": 15,
    "dugaan skandal": 14,
    "dugaan perselingkuhan": 16,

    "dicopot": 15,
    "pencopotan": 15,
    "copot kajari": 20,
    "kajari dicopot": 22,
    "kejagung copot kajari": 25,

    "pelanggaran etik": 20,
    "pelanggaran kode etik": 22,
    "melanggar kode etik": 22,

    "didesak mundur": 20,
    "didesak dicopot": 22,

    "maladministrasi": 18,

    "pemerasan": 18,
    "dugaan pemerasan": 22,

    "suap": 18,
    "dugaan suap": 22,

    "gratifikasi": 18,
    "dugaan gratifikasi": 22,

    "pungli": 18,
    "dugaan pungli": 22,

    "mafia hukum": 22,
    "kolusi": 18,
    "nepotisme": 17,

    "penyalahgunaan wewenang": 22,
    "penyelewengan": 18,

    "batal dilantik": 22,
    "pelantikan batal": 22,
    "pelantikan dibatalkan": 25,
    "pelantikan ditunda": 20,

    "pelantikan cpns dibatalkan": 28,
    "pelantikan cpns ditunda": 25,
}


# ============================================================
# KONTEKS NEGATIF
# ============================================================

STRONG_NEGATIVE_CONTEXT = [

    "skandal perselingkuhan",
    "dugaan perselingkuhan",
    "papan bunga pelakor",
    "karangan bunga pelakor",

    "kajari dicopot",
    "kejari dicopot",
    "kepala kejari dicopot",

    "pelanggaran etik",
    "pelanggaran kode etik",
    "melanggar kode etik",

    "didesak mundur",
    "didesak dicopot",

    "dugaan pemerasan",
    "dugaan suap",
    "dugaan gratifikasi",
    "dugaan pungli",

    "mafia hukum",
    "penyalahgunaan wewenang",

    "pelantikan dibatalkan",
    "pelantikan cpns dibatalkan",
]


SOFT_NEGATIVE_CONTEXT = [
    "menuai sorotan",
    "disorot",
    "menuai kritik",
    "kritik keras",
    "diprotes",
    "demonstrasi",
    "unjuk rasa",
    "unjuk rasa menuntut",
    "dipersoalkan",
    "dipertanyakan",
    "janggal",
]


# ============================================================
# ATURAN PERLU PENANGANAN
# ============================================================

HANDLING_RULES = {

    "dugaan korupsi": 8,
    "kasus korupsi": 7,
    "korupsi": 5,

    "penyelidikan": 5,
    "penyidikan": 5,

    "diperiksa": 6,
    "diperiksa kejagung": 10,

    "dipanggil": 5,
    "dipanggil kejagung": 10,

    "dilaporkan": 6,
    "laporan masyarakat": 6,
    "pengaduan": 6,
    "pengaduan masyarakat": 7,

    "tersangka": 5,
    "terlapor": 6,

    "tuntutan": 5,
    "dituntut": 5,

    "narkotika": 4,
    "kasus narkotika": 6,

    "keluhan pelayanan": 8,
    "pelayanan buruk": 8,
}


# ============================================================
# KONTEKS POSITIF
# ============================================================

POSITIVE_RULES = {

    # Keberhasilan penegakan hukum
    "berhasil mengungkap": 15,
    "berhasil menangkap": 15,
    "berhasil mengamankan": 13,
    "berhasil menyita": 13,

    "berhasil mengungkap kasus": 15,
    "berhasil mengungkap korupsi": 15,
    "berhasil mengungkap perkara": 14,

    "menangkap tersangka": 12,
    "mengamankan tersangka": 12,
    "menyita barang bukti": 12,

    "ungkap kasus": 10,
    "pengungkapan kasus": 10,

    "penindakan": 8,
    "penegakan hukum": 8,

    # Prestasi
    "penghargaan": 12,
    "prestasi": 12,
    "capaian kinerja": 12,
    "kinerja positif": 10,

    # Pelayanan
    "pelayanan prima": 12,
    "pelayanan publik": 7,
    "pelayanan terbaik": 10,

    # Kegiatan resmi
    "penyuluhan hukum": 12,
    "sosialisasi hukum": 10,
    "jaksa masuk sekolah": 12,
    "jaksa menyapa": 10,

    "upacara": 8,
    "apel": 8,
    "apel pagi": 8,

    "kunjungan kerja": 10,
    "kunjungan": 7,

    "rapat koordinasi": 10,
    "rapat": 5,

    "focus group discussion": 10,
    "fgd": 10,

    "penandatanganan mou": 12,
    "nota kesepahaman": 10,
    "kerja sama": 10,

    "peresmian": 10,
    "pelantikan": 9,

    "bakti sosial": 12,
    "kegiatan sosial": 9,

    "upacara hari": 8,
    "peringatan hari": 8,
}


OFFICIAL_ACTIVITY_CONTEXT = [

    "upacara",
    "apel",
    "apel pagi",
    "kunjungan kerja",
    "kunjungan",
    "rapat koordinasi",
    "rapat",
    "focus group discussion",
    "fgd",
    "penandatanganan mou",
    "nota kesepahaman",
    "kerja sama",
    "peresmian",
    "pelantikan",
    "bakti sosial",
    "penyuluhan hukum",
    "sosialisasi hukum",
    "jaksa masuk sekolah",
    "jaksa menyapa",
]


SUCCESS_LAW_ENFORCEMENT_CONTEXT = [

    "berhasil mengungkap",
    "berhasil menangkap",
    "berhasil mengamankan",
    "berhasil menyita",
    "berhasil mengungkap kasus",
    "berhasil mengungkap korupsi",
    "berhasil mengungkap perkara",
    "menangkap tersangka",
    "mengamankan tersangka",
    "menyita barang bukti",
    "ungkap kasus",
    "pengungkapan kasus",
]


LEGAL_RISK_TERMS = [

    "dugaan korupsi",
    "korupsi",
    "penyelidikan",
    "penyidikan",
    "diperiksa",
    "dipanggil",
    "dilaporkan",
    "pengaduan",
    "tersangka",
    "terlapor",
    "tuntutan",
    "narkotika",
]


DANGER_TITLE_TERMS = [

    "dicopot",
    "copot",
    "dipanggil kejagung",
    "diperiksa kejagung",
    "skandal",
    "perselingkuhan",
    "pelakor",
    "didesak mundur",
    "didesak dicopot",
    "batal dilantik",
    "pelantikan dibatalkan",
]


CANCELLATION_CONTEXT = [

    "pelantikan dibatalkan",
    "pelantikan cpns dibatalkan",
    "pelantikan ditunda",
    "batal dilantik",
]


# ============================================================
# CLEANING
# ============================================================

def clean_html_text(text):

    if not text:
        return ""

    text = html.unescape(str(text))

    text = re.sub(
        r"<(script|style|noscript).*?>.*?</\1>",
        " ",
        text,
        flags=re.IGNORECASE | re.DOTALL
    )

    text = re.sub(
        r"<[^>]+>",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


def normalize_text(text):

    text = clean_html_text(text)

    text = text.lower()

    text = text.replace(
        "\xa0",
        " "
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# ============================================================
# URL
# ============================================================

def normalize_url(url):

    if not url:
        return ""

    url = str(url).strip()

    url = url.split("#")[0]

    return url


# ============================================================
# TANGGAL INDONESIA
# ============================================================

def parse_indonesian_date(text):

    if not text:
        return None

    bulan = {

        "januari": 1,
        "februari": 2,
        "maret": 3,
        "april": 4,
        "mei": 5,
        "juni": 6,
        "juli": 7,
        "agustus": 8,
        "september": 9,
        "oktober": 10,
        "november": 11,
        "desember": 12,

        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "jun": 6,
        "jul": 7,
        "agu": 8,
        "sep": 9,
        "okt": 10,
        "nov": 11,
        "des": 12,
    }

    text = normalize_text(text)

    match = re.search(
        r"(\d{1,2})\s+([a-z]+)\s+(\d{4})",
        text
    )

    if not match:
        return None

    day = int(match.group(1))
    month_name = match.group(2)
    year = int(match.group(3))

    if month_name not in bulan:
        return None

    try:

        return datetime.datetime(
            year,
            bulan[month_name],
            day
        )

    except Exception:

        return None


# ============================================================
# PARSE DATE
# ============================================================

def parse_date_safe(value):

    if not value:
        return None

    try:

        dt = parser.parse(
            str(value),
            fuzzy=True,
            dayfirst=True
        )

        if dt.tzinfo:

            dt = dt.astimezone(
                datetime.timezone.utc
            ).replace(
                tzinfo=None
            )

        return dt

    except Exception:

        return parse_indonesian_date(
            str(value)
        )


# ============================================================
# EXTRACT PUBLISHED DATE
# ============================================================

def extract_published_date(soup):

    candidates = []

    # JSON-LD
    for script in soup.find_all(
        "script",
        attrs={
            "type": re.compile(
                r"application/ld\+json",
                re.I
            )
        }
    ):

        try:

            raw = (
                script.string
                or script.get_text()
            )

            if not raw:
                continue

            data = json.loads(raw)

            objects = []

            if isinstance(data, list):
                objects.extend(data)

            elif isinstance(data, dict):

                objects.append(data)

                if "@graph" in data:
                    graph = data["@graph"]

                    if isinstance(graph, list):
                        objects.extend(graph)

            for obj in objects:

                if not isinstance(obj, dict):
                    continue

                for key in [
                    "datePublished",
                    "dateCreated",
                    "dateModified"
                ]:

                    value = obj.get(key)

                    if value:
                        candidates.append(value)

        except Exception:
            continue

    # Meta tags
    selectors = [

        {
            "property":
            "article:published_time"
        },

        {
            "name":
            "article:published_time"
        },

        {
            "itemprop":
            "datePublished"
        },

        {
            "property":
            "og:updated_time"
        },
    ]

    for attrs in selectors:

        element = soup.find(
            "meta",
            attrs=attrs
        )

        if (
            element
            and element.get("content")
        ):

            candidates.append(
                element.get("content")
            )

    # time tag
    for tag in soup.find_all("time"):

        value = (
            tag.get("datetime")
            or tag.get_text()
        )

        if value:
            candidates.append(value)

    for value in candidates:

        dt = parse_date_safe(value)

        if dt:
            return dt

    return None


# ============================================================
# RSS DATE
# ============================================================

def get_rss_date(entry):

    for attr in [
        "published_parsed",
        "updated_parsed"
    ]:

        value = getattr(
            entry,
            attr,
            None
        )

        if value:

            try:

                return datetime.datetime(
                    value.tm_year,
                    value.tm_mon,
                    value.tm_mday,
                    value.tm_hour,
                    value.tm_min,
                    value.tm_sec
                )

            except Exception:
                pass

    for attr in [
        "published",
        "updated"
    ]:

        value = getattr(
            entry,
            attr,
            None
        )

        if value:

            dt = parse_date_safe(value)

            if dt:
                return dt

    return None


# ============================================================
# VALIDASI TANGGAL
# ============================================================

def validate_date(
    article_date,
    rss_date
):

    now = datetime.datetime.now()

    dt = article_date or rss_date

    if not dt:
        return False, None

    if dt.year != TAHUN_TARGET:
        return False, dt

    # Toleransi satu hari untuk perbedaan timezone
    if dt > now + datetime.timedelta(days=1):
        return False, dt

    return True, dt


# ============================================================
# HTTP HEADERS
# ============================================================

def get_headers():

    return {

        "User-Agent":
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/131.0 Safari/537.36",

        "Accept-Language":
            "id-ID,id;q=0.9,en;q=0.8",

        "Accept":
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,*/*;q=0.8",

    }


# ============================================================
# FETCH WEB
# ============================================================

def fetch_webpage(url):

    try:

        response = requests.get(
            url,
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True
        )

        if response.status_code == 200:

            return {
                "html": response.text,
                "final_url": response.url
            }

        print(
            f"[FETCH] HTTP "
            f"{response.status_code}: {url}"
        )

    except Exception as e:

        print(
            f"[FETCH ERROR] "
            f"{url}: {e}"
        )

    return None


# ============================================================
# RESOLVE URL
# ============================================================

def resolve_redirect_url(url):

    try:

        response = requests.get(
            url,
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
            stream=True
        )

        final_url = (
            response.url
            or url
        )

        response.close()

        return final_url

    except Exception:

        return url


# ============================================================
# EXTRACT ARTICLE TEXT
# ============================================================

def extract_article_text(soup):

    copy_soup = BeautifulSoup(
        str(soup),
        "html.parser"
    )

    for tag in copy_soup([
        "script",
        "style",
        "noscript",
        "svg",
        "nav",
        "footer",
        "header",
        "form",
        "aside",
        "iframe",
        "figure",
        "figcaption",
    ]):

        tag.decompose()

    article = (
        copy_soup.find("article")
        or copy_soup.find("main")
    )

    if article:

        text = article.get_text(
            " ",
            strip=True
        )

    else:

        text = copy_soup.get_text(
            " ",
            strip=True
        )

    return clean_html_text(text)


# ============================================================
# PARAGRAF PERTAMA
# ============================================================

def extract_first_paragraphs(
    soup,
    limit=FIRST_PARAGRAPH_LIMIT
):

    copy_soup = BeautifulSoup(
        str(soup),
        "html.parser"
    )

    for tag in copy_soup([
        "script",
        "style",
        "noscript",
        "svg",
        "nav",
        "footer",
        "header",
        "form",
        "aside",
        "iframe",
    ]):

        tag.decompose()

    article = (
        copy_soup.find("article")
        or copy_soup.find("main")
        or copy_soup
    )

    paragraphs = []

    for p in article.find_all("p"):

        text = clean_html_text(
            p.get_text(
                " ",
                strip=True
            )
        )

        normalized = normalize_text(text)

        if len(text) < 25:
            continue

        if normalized in [
            "baca juga",
            "iklan",
            "advertisement",
            "baca selengkapnya",
        ]:

            continue

        paragraphs.append(text)

        if len(paragraphs) >= limit:
            break

    return paragraphs


# ============================================================
# CEK RELEVANSI SATKER
# ============================================================

def satker_is_relevant(
    title,
    first_paragraphs
):

    title_n = normalize_text(title)

    first_text = normalize_text(
        " ".join(first_paragraphs)
    )

    title_matches = [
        keyword
        for keyword in TARGET_KEJARI_KEYWORDS
        if normalize_text(keyword)
        in title_n
    ]

    first_matches = [
        keyword
        for keyword in TARGET_KEJARI_KEYWORDS
        if normalize_text(keyword)
        in first_text
    ]

    locations = []

    if title_matches:
        locations.append("title")

    if first_matches:
        locations.append(
            "first_paragraphs"
        )

    return (
        bool(
            title_matches
            or first_matches
        ),
        title_matches,
        first_matches,
        ",".join(locations)
    )


# ============================================================
# SCORE RULE
# ============================================================

def calculate_rule_score(
    text,
    rules
):

    score = 0
    detected = []

    text_n = normalize_text(text)

    for keyword, weight in rules.items():

        if normalize_text(keyword) in text_n:

            score += weight

            detected.append(keyword)

    return score, detected


# ============================================================
# NEGASI
# ============================================================

def has_negation_near(
    text,
    keyword,
    window=100
):

    text_n = normalize_text(text)
    keyword_n = normalize_text(keyword)

    if not keyword_n:
        return False

    negations = [

        "tidak",
        "bukan",
        "tanpa",
        "belum terbukti",
        "tidak terbukti",
        "menepis",
        "membantah",
        "dibantah",
        "tidak benar",
        "hoaks",
        "hoax",
    ]

    start = text_n.find(keyword_n)

    while start != -1:

        before = text_n[
            max(
                0,
                start - window
            ):start
        ]

        if any(
            neg in before
            for neg in negations
        ):

            return True

        start = text_n.find(
            keyword_n,
            start + 1
        )

    return False


# ============================================================
# CEK KEBERHASILAN
# ============================================================

def detect_success_context(text):

    text_n = normalize_text(text)

    hits = []

    for term in SUCCESS_LAW_ENFORCEMENT_CONTEXT:

        if term in text_n:

            if not has_negation_near(
                text_n,
                term
            ):

                hits.append(term)

    return list(
        dict.fromkeys(hits)
    )


# ============================================================
# CEK KEGIATAN RESMI
# ============================================================

def detect_official_activity(text):

    text_n = normalize_text(text)

    hits = []

    for term in OFFICIAL_ACTIVITY_CONTEXT:

        if term in text_n:

            if not has_negation_near(
                text_n,
                term
            ):

                hits.append(term)

    return list(
        dict.fromkeys(hits)
    )


# ============================================================
# KLASIFIKASI ARTIKEL
# ============================================================

def classify_article(
    title,
    snippet,
    content,
    first_paragraphs=None
):

    first_paragraphs = (
        first_paragraphs
        or []
    )

    title_clean = clean_html_text(
        title
    )

    snippet_clean = clean_html_text(
        snippet
    )

    content_clean = clean_html_text(
        content
    )

    # --------------------------------------------------------
    # CEK SATKER
    # --------------------------------------------------------

    (
        satker_ok,
        title_matches,
        first_matches,
        match_location
    ) = satker_is_relevant(
        title_clean,
        first_paragraphs
    )

    if not satker_ok:

        return {

            "category": "Netral",
            "priority": "RENDAH",

            "negative_score": 0,
            "handling_score": 0,
            "positive_score": 0,

            "detected_keywords": [],

            "satker_matches": [],
            "satker_match_location": "",

        }

    # --------------------------------------------------------
    # GABUNGKAN TEKS
    # --------------------------------------------------------

    first_text = " ".join(
        first_paragraphs
    )

    full_text = (
        f"{title_clean} "
        f"{snippet_clean} "
        f"{first_text} "
        f"{content_clean}"
    )

    full_n = normalize_text(
        full_text
    )

    title_n = normalize_text(
        title_clean
    )

    # --------------------------------------------------------
    # SCORE DASAR
    # --------------------------------------------------------

    negative_score, negative_kw = (
        calculate_rule_score(
            full_text,
            NEGATIVE_STRONG_RULES
        )
    )

    handling_score, handling_kw = (
        calculate_rule_score(
            full_text,
            HANDLING_RULES
        )
    )

    positive_score, positive_kw = (
        calculate_rule_score(
            full_text,
            POSITIVE_RULES
        )
    )

    # --------------------------------------------------------
    # SCORE KHUSUS JUDUL
    # --------------------------------------------------------

    title_negative_score, title_negative_kw = (
        calculate_rule_score(
            title_clean,
            NEGATIVE_STRONG_RULES
        )
    )

    title_handling_score, title_handling_kw = (
        calculate_rule_score(
            title_clean,
            HANDLING_RULES
        )
    )

    title_positive_score, title_positive_kw = (
        calculate_rule_score(
            title_clean,
            POSITIVE_RULES
        )
    )

    # --------------------------------------------------------
    # KONTEKS
    # --------------------------------------------------------

    success_hits = detect_success_context(
        full_text
    )

    official_hits = detect_official_activity(
        full_text
    )

    danger_hits = [

        term

        for term in DANGER_TITLE_TERMS

        if term in title_n

        and not has_negation_near(
            title_n,
            term
        )
    ]

    cancellation_hits = [

        term

        for term in CANCELLATION_CONTEXT

        if term in full_n

        and not has_negation_near(
            full_n,
            term
        )
    ]

    strong_context_hits = [

        term

        for term in STRONG_NEGATIVE_CONTEXT

        if term in full_n

        and not has_negation_near(
            full_n,
            term
        )
    ]

    soft_negative_hits = [

        term

        for term in SOFT_NEGATIVE_CONTEXT

        if term in full_n

        and not has_negation_near(
            full_n,
            term
        )
    ]

    legal_hits = [

        term

        for term in LEGAL_RISK_TERMS

        if term in full_n

        and not has_negation_near(
            full_n,
            term
        )
    ]

    # --------------------------------------------------------
    # TAMBAHAN SCORE
    # --------------------------------------------------------

    negative_score += (
        title_negative_score * 2
    )

    handling_score += (
        title_handling_score * 2
    )

    positive_score += (
        title_positive_score * 2
    )

    # ========================================================
    # PRIORITAS 1
    # KEBERHASILAN PENEGAKAN HUKUM
    #
    # Contoh:
    # "Kejari berhasil menangkap tersangka..."
    #
    # Walaupun ada kata:
    # korupsi / tersangka / narkotika
    #
    # tetap POSITIF.
    # ========================================================

    if success_hits:

        positive_score += 25

    # ========================================================
    # PRIORITAS 2
    # KEGIATAN RESMI
    #
    # Apel, rapat, FGD, kunjungan,
    # penyuluhan, kerja sama, dll.
    # ========================================================

    if official_hits:

        positive_score += 20

    # ========================================================
    # PRIORITAS 3
    # NEGATIF KUAT
    #
    # Hanya jika benar-benar terdapat
    # indikasi masalah terhadap satker.
    # ========================================================

    strong_negative = False

    # Konteks negatif yang sangat kuat
    if strong_context_hits:
        strong_negative = True

    # Judul secara langsung menyatakan masalah
    if danger_hits:
        strong_negative = True

    # Pembatalan pelantikan
    if cancellation_hits:
        strong_negative = True

    # Score tinggi
    if negative_score >= 35:
        strong_negative = True

    # --------------------------------------------------------
    # PENGECUALIAN PENTING
    #
    # Jika artikel adalah keberhasilan penegakan hukum
    # atau kegiatan resmi, jangan jadikan negatif hanya
    # karena ada kata korupsi/tersangka/narkotika.
    # --------------------------------------------------------

    if (
        success_hits
        or official_hits
    ):

        # Negatif hanya boleh menang jika
        # konteks negatifnya sangat eksplisit
        # dan lebih kuat dari konteks positif.

        if (
            strong_negative
            and negative_score
            > positive_score + 15
        ):

            category = "Negatif Kuat"
            priority = "TINGGI"

        else:

            category = "Positif"
            priority = "RENDAH"

    else:

        # ----------------------------------------------------
        # NEGATIF
        # ----------------------------------------------------

        if strong_negative:

            category = "Negatif Kuat"
            priority = "TINGGI"

        # ----------------------------------------------------
        # PERLU PENANGANAN
        # ----------------------------------------------------

        elif (
            handling_score >= 9
            or title_handling_score >= 6
            or len(legal_hits) >= 2
            or len(soft_negative_hits) >= 2
        ):

            category = "Perlu Penanganan"
            priority = "SEDANG"

        # ----------------------------------------------------
        # POSITIF
        # ----------------------------------------------------

        elif positive_score >= 8:

            category = "Positif"
            priority = "RENDAH"

        # ----------------------------------------------------
        # NETRAL
        # ----------------------------------------------------

        else:

            category = "Netral"
            priority = "RENDAH"

    # ========================================================
    # KEYWORDS
    # ========================================================

    all_detected = []

    all_detected.extend(
        negative_kw
    )

    all_detected.extend(
        handling_kw
    )

    all_detected.extend(
        positive_kw
    )

    all_detected.extend(
        title_negative_kw
    )

    all_detected.extend(
        title_handling_kw
    )

    all_detected.extend(
        title_positive_kw
    )

    all_detected.extend(
        danger_hits
    )

    all_detected.extend(
        cancellation_hits
    )

    all_detected.extend(
        strong_context_hits
    )

    all_detected.extend(
        soft_negative_hits
    )

    all_detected.extend(
        legal_hits
    )

    all_detected.extend(
        success_hits
    )

    all_detected.extend(
        official_hits
    )

    all_detected = list(
        dict.fromkeys(
            all_detected
        )
    )

    return {

        "category": category,
        "priority": priority,

        "negative_score": negative_score,
        "handling_score": handling_score,
        "positive_score": positive_score,

        "detected_keywords": all_detected,

        "satker_matches": list(
            dict.fromkeys(
                title_matches
                + first_matches
            )
        ),

        "satker_match_location":
            match_location,

    }


# ============================================================
# RSS GOOGLE NEWS
# ============================================================

def fetch_rss_feed(query):

    encoded_query = (
        urllib.parse.quote(query)
    )

    rss_url = (
        "https://news.google.com/rss/search?"
        f"q={encoded_query}"
        "&hl=id"
        "&gl=ID"
        "&ceid=ID:id"
    )

    try:

        feed = feedparser.parse(
            rss_url
        )

    except Exception as e:

        print(
            f"[RSS ERROR] {query}: {e}"
        )

        return []

    entries = []

    for entry in feed.entries:

        link = entry.get(
            "link",
            ""
        )

        if not link:
            continue

        entries.append({

            "title":
                clean_html_text(
                    entry.get(
                        "title",
                        ""
                    )
                ),

            "link":
                link,

            "rss_date":
                get_rss_date(entry),

        })

    return entries


# ============================================================
# PROCESS SINGLE ARTICLE
# ============================================================

def process_single_article(entry):

    try:

        resolved_url = (
            resolve_redirect_url(
                entry["link"]
            )
        )

        norm_url = normalize_url(
            resolved_url
        )

        if not norm_url:
            return None

        web_data = fetch_webpage(
            norm_url
        )

        if not web_data:
            return None

        final_url = normalize_url(
            web_data.get(
                "final_url",
                norm_url
            )
        )

        soup = BeautifulSoup(
            web_data["html"],
            "html.parser"
        )

        article_text = (
            extract_article_text(
                soup
            )
        )

        if len(article_text) < MIN_ARTICLE_TEXT:
            return None

        first_paragraphs = (
            extract_first_paragraphs(
                soup
            )
        )

        extracted_dt = (
            extract_published_date(
                soup
            )
        )

        is_valid, final_dt = (
            validate_date(
                extracted_dt,
                entry.get(
                    "rss_date"
                )
            )
        )

        if not is_valid:
            return None

        analysis = classify_article(

            entry.get(
                "title",
                ""
            ),

            "",

            article_text,

            first_paragraphs
        )

        # Hanya simpan jika relevan dengan satker
        satker_matches = (
            analysis.get(
                "satker_matches",
                []
            )
        )

        if not satker_matches:
            return None

        return {

            "title":
                clean_html_text(
                    entry.get(
                        "title",
                        ""
                    )
                ),

            "url":
                final_url,

            "content":
                article_text,

            "published_date":
                (
                    final_dt.isoformat()
                    if final_dt
                    else None
                ),

            "category":
                analysis["category"],

            "priority":
                analysis["priority"],

            "satker":
                NAMA_SATKER,

            "keywords":
                analysis[
                    "detected_keywords"
                ],

        }

    except Exception as e:

        print(
            f"[PROCESS ERROR] "
            f"{entry.get('link')}: {e}"
        )

        return None


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram_alert(article):

    if (
        not TELEGRAM_TOKEN
        or not CHAT_ID
    ):

        return False

    category = article.get(
        "category",
        "Netral"
    )

    if category == "Negatif Kuat":

        emoji = "🔴"

    elif category == "Perlu Penanganan":

        emoji = "🟡"

    elif category == "Positif":

        emoji = "🟢"

    else:

        emoji = "⚪"

    title = html.escape(
        str(
            article.get(
                "title",
                "Tanpa Judul"
            )
        )
    )

    category_safe = html.escape(
        category
    )

    priority = html.escape(
        str(
            article.get(
                "priority",
                "RENDAH"
            )
        )
    )

    satker = html.escape(
        str(
            article.get(
                "satker",
                NAMA_SATKER
            )
        )
    )

    url = html.escape(
        str(
            article.get(
                "url",
                ""
            )
        ),
        quote=True
    )

    message = (

        f"{emoji} "
        f"<b>PATROLI SIBER "
        f"- BERITA BARU</b>\n\n"

        f"<b>Judul:</b> "
        f"{title}\n"

        f"<b>Kategori:</b> "
        f"{category_safe}\n"

        f"<b>Prioritas:</b> "
        f"{priority}\n"

        f"<b>Satker:</b> "
        f"{satker}\n"

        f"<b>Link:</b> "
        f"<a href='{url}'>"
        f"Baca Artikel"
        f"</a>"
    )

    try:

        response = requests.post(

            f"https://api.telegram.org/"
            f"bot{TELEGRAM_TOKEN}/sendMessage",

            json={

                "chat_id":
                    CHAT_ID,

                "text":
                    message,

                "parse_mode":
                    "HTML",

                "disable_web_page_preview":
                    False,

            },

            timeout=10
        )

        if response.status_code == 200:

            return True

        print(
            "[TELEGRAM ERROR] "
            f"HTTP {response.status_code}: "
            f"{response.text[:300]}"
        )

    except Exception as e:

        print(
            f"[TELEGRAM ERROR] {e}"
        )

    return False


# ============================================================
# RECLASSIFY SEMUA ARTIKEL
# ============================================================

def reclassify_all_existing_articles():

    print()
    print(
        "=========================================="
    )
    print(
        "MEMULAI REKLASIFIKASI DATABASE"
    )
    print(
        "=========================================="
    )

    articles = get_all_articles()

    counts = {

        "Negatif Kuat": 0,
        "Perlu Penanganan": 0,
        "Netral": 0,
        "Positif": 0,

    }

    updated_count = 0
    failed_count = 0

    for art in articles:

        try:

            article_id = art.get(
                "id"
            )

            if not article_id:
                failed_count += 1
                continue

            clean_title = (
                clean_html_text(
                    art.get(
                        "title",
                        ""
                    )
                )
            )

            clean_content = (
                clean_html_text(
                    art.get(
                        "content",
                        ""
                    )
                )
            )

            # Ambil paragraf dengan lebih aman
            paragraphs = re.split(
                r"(?<=[.!?])\s+",
                clean_content
            )

            first_p = [

                p.strip()

                for p in paragraphs

                if len(
                    p.strip()
                ) >= 25

            ][:FIRST_PARAGRAPH_LIMIT]

            analysis = classify_article(

                clean_title,

                "",

                clean_content,

                first_p
            )

            result = update_article(

                article_id,

                {

                    "title":
                        clean_title,

                    "content":
                        clean_content,

                    "category":
                        analysis[
                            "category"
                        ],

                    "priority":
                        analysis[
                            "priority"
                        ],

                    "keywords":
                        analysis[
                            "detected_keywords"
                        ],

                }
            )

            if result is not None:

                updated_count += 1

                category = (
                    analysis[
                        "category"
                    ]
                )

                counts[
                    category
                ] = (
                    counts.get(
                        category,
                        0
                    ) + 1
                )

            else:

                failed_count += 1

        except Exception as e:

            failed_count += 1

            print(
                f"[RECLASSIFY ERROR] "
                f"{art.get('id')}: {e}"
            )

    print()
    print(
        "=========================================="
    )
    print(
        "REKLASIFIKASI SELESAI"
    )
    print(
        "=========================================="
    )

    print(
        json.dumps(
            counts,
            indent=2,
            ensure_ascii=False
        )
    )

    print(
        f"Total artikel : "
        f"{len(articles)}"
    )

    print(
        f"Berhasil      : "
        f"{updated_count}"
    )

    print(
        f"Gagal         : "
        f"{failed_count}"
    )

    return counts, updated_count, failed_count


# ============================================================
# RUN PATROL
# ============================================================

def run_patrol():

    start_time = time.time()

    print()
    print(
        "=========================================="
    )
    print(
        "MENJALANKAN PATROLI SIBER"
    )
    print(
        "=========================================="
    )

    print(
        f"Satker : {NAMA_SATKER}"
    )

    print(
        f"Tahun  : {TAHUN_TARGET}"
    )

    print()

    # --------------------------------------------------------
    # AMBIL RSS
    # --------------------------------------------------------

    raw_entries = []

    for query in SEARCH_TARGETS:

        print(
            f"[RSS] Mencari: {query}"
        )

        entries = fetch_rss_feed(
            query
        )

        raw_entries.extend(
            entries
        )

    # --------------------------------------------------------
    # DEDUP RSS
    # --------------------------------------------------------

    unique_entries = {}

    for entry in raw_entries:

        link = entry.get(
            "link"
        )

        if not link:
            continue

        unique_entries[
            link
        ] = entry

    unique_entries = list(
        unique_entries.values()
    )

    print()
    print(
        f"[INFO] Kandidat RSS : "
        f"{len(unique_entries)}"
    )

    # --------------------------------------------------------
    # PROCESS
    # --------------------------------------------------------

    processed_count = 0
    valid_count = 0
    saved_count = 0
    failed_save_count = 0
    new_articles_count = 0
    telegram_count = 0

    results = []

    with ThreadPoolExecutor(
        max_workers=MAX_WORKERS
    ) as executor:

        futures = {

            executor.submit(
                process_single_article,
                entry
            ): entry

            for entry in unique_entries

        }

        for future in as_completed(
            futures
        ):

            processed_count += 1

            try:

                result = (
                    future.result()
                )

                if result:

                    valid_count += 1

                    results.append(
                        result
                    )

            except Exception as e:

                print(
                    f"[FUTURE ERROR] {e}"
                )

    print()
    print(
        f"[INFO] Artikel valid : "
        f"{valid_count}"
    )

    # --------------------------------------------------------
    # SIMPAN
    # --------------------------------------------------------

    for article in results:

        try:

            existing = (
                get_article_by_link(
                    article["url"]
                )
            )

            saved = upsert_article(
                article
            )

            if saved:

                saved_count += 1

                if not existing:

                    new_articles_count += 1

                    if send_telegram_alert(
                        article
                    ):

                        telegram_count += 1

            else:

                failed_save_count += 1

        except Exception as e:

            failed_save_count += 1

            print(
                f"[SAVE ERROR] "
                f"{article.get('url')}: "
                f"{e}"
            )

    # --------------------------------------------------------
    # RECLASSIFY
    # --------------------------------------------------------

    (
        counts,
        reclassified_count,
        reclass_failed
    ) = reclassify_all_existing_articles()

    # --------------------------------------------------------
    # LOG
    # --------------------------------------------------------

    execution_time = round(
        time.time()
        - start_time,
        2
    )

    log_data = {

        "satker":
            NAMA_SATKER,

        "processed_urls":
            processed_count,

        "new_articles":
            new_articles_count,

        "execution_time_seconds":
            execution_time,

        "status":
            "SUCCESS",

    }

    log_saved = save_run_log(
        log_data
    )

    if log_saved:

        print(
            "[DB LOG] "
            "Run log berhasil disimpan."
        )

    else:

        print(
            "[DB LOG] "
            "Run log gagal disimpan."
        )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    print()
    print(
        "=========================================="
    )
    print(
        "PATROLI SELESAI"
    )
    print(
        "=========================================="
    )

    print(
        f"Durasi              : "
        f"{execution_time} detik"
    )

    print(
        f"Kandidat            : "
        f"{len(unique_entries)}"
    )

    print(
        f"Artikel valid       : "
        f"{valid_count}"
    )

    print(
        f"Berhasil disimpan   : "
        f"{saved_count}"
    )

    print(
        f"Gagal disimpan      : "
        f"{failed_save_count}"
    )

    print(
        f"Direklasifikasi     : "
        f"{reclassified_count}"
    )

    print(
        f"Reclass gagal       : "
        f"{reclass_failed}"
    )

    print(
        f"Negatif Kuat        : "
        f"{counts.get('Negatif Kuat', 0)}"
    )

    print(
        f"Perlu Penanganan    : "
        f"{counts.get('Perlu Penanganan', 0)}"
    )

    print(
        f"Netral              : "
        f"{counts.get('Netral', 0)}"
    )

    print(
        f"Positif             : "
        f"{counts.get('Positif', 0)}"
    )

    print(
        f"Telegram terkirim   : "
        f"{telegram_count}"
    )

    print(
        "=========================================="
    )

    print()
    print(
        "PROGRAM SELESAI NORMAL"
    )
    print(
        "=========================================="
    )

    return {

        "processed":
            processed_count,

        "valid":
            valid_count,

        "saved":
            saved_count,

        "save_failed":
            failed_save_count,

        "reclassified":
            reclassified_count,

        "reclass_failed":
            reclass_failed,

        "counts":
            counts,

        "telegram":
            telegram_count,

        "execution_time":
            execution_time,

    }


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    try:

        run_patrol()

    except KeyboardInterrupt:

        print()
        print(
            "PROGRAM DIHENTIKAN USER."
        )

        sys.exit(1)

    except Exception as e:

        print()
        print(
            "=========================================="
        )

        print(
            "PROGRAM ERROR"
        )

        print(
            "=========================================="
        )

        print(
            f"{type(e).__name__}: {e}"
        )

        sys.exit(1)


HANDLING_RULES = {
    "korupsi": 7, "dugaan korupsi": 9, "kasus korupsi": 8, "penyelidikan": 5, "penyidikan": 5,
    "diperiksa": 7, "diperiksa kejagung": 11, "dipanggil": 6, "dipanggil kejagung": 10, "dilaporkan": 7,
    "laporan masyarakat": 7, "pengaduan": 6, "pengaduan masyarakat": 7, "tersangka": 7, "terlapor": 7,
    "tuntutan": 5, "dituntut": 5, "narkotika": 6, "kasus narkotika": 8, "keluhan pelayanan": 8,
}

POSITIVE_RULES = {
    "berhasil mengungkap": 10, "berhasil menangkap": 10, "berhasil mengamankan": 9, "mengungkap korupsi": 9,
    "menangkap tersangka": 8, "menyita barang bukti": 8, "penghargaan": 9, "prestasi": 9, "capaian kinerja": 9,
    "pelayanan prima": 9, "penyuluhan hukum": 8, "sosialisasi hukum": 8, "jaksa masuk sekolah": 9,
    "jaksa menyapa": 7, "upacara": 5, "apel": 5, "kunjungan kerja": 7, "rapat koordinasi": 7,
    "penandatanganan mou": 8, "kerja sama": 8, "peresmian": 8, "pelantikan": 6, "bakti sosial": 8,
}

OFFICIAL_ACTIVITY_CONTEXT = ["upacara", "apel", "kunjungan kerja", "rapat koordinasi", "penandatanganan mou", "peresmian", "pelantikan", "bakti sosial"]
SUCCESS_LAW_ENFORCEMENT_CONTEXT = ["berhasil mengungkap", "berhasil menangkap", "mengungkap korupsi", "menangkap tersangka", "menyita barang bukti"]
HANDLING_CONTEXT = ["diperiksa kejagung", "dipanggil kejagung", "penyelidikan", "penyidikan", "menangani kasus", "kasus korupsi"]
DANGER_TITLE_TERMS = ["dicopot", "dipanggil kejagung", "diperiksa kejagung", "skandal", "perselingkuhan", "pelakor", "didesak", "batal dilantik"]
LEGAL_RISK_TERMS = ["korupsi", "narkotika", "tersangka", "terlapor", "diperiksa", "dipanggil", "penyelidikan", "penyidikan", "pengaduan", "dicopot"]
CANCELLATION_CONTEXT = ["pelantikan dibatalkan", "pelantikan cpns dibatalkan", "pelantikan ditunda", "batal dilantik"]

def clean_html_text(text):
    if not text:
        return ""
    text = html.unescape(str(text))
    text = re.sub(r'<[^>]+>', '', text)
    return re.sub(r"\s+", " ", text).strip()

def normalize_text(text):
    return clean_html_text(text).lower()

def normalize_url(url):
    return str(url).strip().split("#")[0] if url else ""

def parse_indonesian_date(text):
    if not text: return None
    bulan = {
        "januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5, "juni": 6,
        "juli": 7, "agustus": 8, "september": 9, "oktober": 10, "november": 11, "desember": 12,
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "agu": 8, "sep": 9, "okt": 10, "nov": 11, "des": 12
    }
    match = re.search(r"(\d{1,2})\s+([a-z]+)\s+(\d{4})", normalize_text(text))
    if not match or match.group(2) not in bulan: return None
    try:
        return datetime.datetime(int(match.group(3)), bulan[match.group(2)], int(match.group(1)))
    except Exception:
        return None

def parse_date_safe(value):
    if not value: return None
    try:
        dt = parser.parse(str(value), fuzzy=True, dayfirst=True)
        if dt.tzinfo:
            dt = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        return parse_indonesian_date(str(value))

def extract_published_date(soup):
    candidates = []
    for script in soup.find_all("script", attrs={"type": re.compile(r"application/ld\+json", re.I)}):
        try:
            raw = script.string or script.get_text()
            if not raw: continue
            data = json.loads(raw)
            objects = data if isinstance(data, list) else [data]
            if isinstance(data, dict) and "@graph" in data:
                objects.extend(data["@graph"])
            for obj in objects:
                if isinstance(obj, dict):
                    for key in ["datePublished", "dateCreated", "dateModified"]:
                        if obj.get(key): candidates.append(obj[key])
        except Exception: continue

    selectors = [{"property": "article:published_time"}, {"name": "article:published_time"}, {"itemprop": "datePublished"}]
    for attrs in selectors:
        element = soup.find("meta", attrs=attrs)
        if element and element.get("content"):
            candidates.append(element.get("content"))

    for tag in soup.find_all("time"):
        if tag.get("datetime") or tag.get_text():
            candidates.append(tag.get("datetime") or tag.get_text())

    for val in candidates:
        dt = parse_date_safe(val)
        if dt: return dt
    return None

def get_rss_date(entry):
    for attr in ["published_parsed", "updated_parsed"]:
        val = getattr(entry, attr, None)
        if val:
            try: return datetime.datetime(val.tm_year, val.tm_mon, val.tm_mday, val.tm_hour, val.tm_min, val.tm_sec)
            except Exception: pass
    for attr in ["published", "updated"]:
        val = getattr(entry, attr, None)
        if val:
            dt = parse_date_safe(val)
            if dt: return dt
    return None

def validate_date(article_date, rss_date):
    now = datetime.datetime.now()
    dt = article_date or rss_date
    if not dt or dt.year != TAHUN_TARGET or dt > (now + datetime.timedelta(days=1)):
        return False, dt
    return True, dt

def get_headers():
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0 Safari/537.36",
        "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
    }

def fetch_webpage(url):
    try:
        res = requests.get(url, headers=get_headers(), timeout=REQUEST_TIMEOUT, allow_redirects=True)
        if res.status_code == 200:
            return {"html": res.text, "final_url": res.url}
    except Exception as e:
        print(f"[FETCH ERROR] {url}: {e}")
    return None

def resolve_redirect_url(url):
    try:
        res = requests.get(url, headers=get_headers(), timeout=REQUEST_TIMEOUT, allow_redirects=True, stream=True)
        final_url = res.url or url
        res.close()
        return final_url
    except Exception:
        return url

def extract_article_text(soup):
    copy_soup = BeautifulSoup(str(soup), "html.parser")
    for tag in copy_soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "form", "aside", "iframe"]):
        tag.decompose()
    article = copy_soup.find("article") or copy_soup.find("main")
    text = article.get_text(" ", strip=True) if article else copy_soup.get_text(" ", strip=True)
    return clean_html_text(text)

def extract_first_paragraphs(soup, limit=FIRST_PARAGRAPH_LIMIT):
    copy_soup = BeautifulSoup(str(soup), "html.parser")
    for tag in copy_soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "form", "aside", "iframe"]):
        tag.decompose()
    article = copy_soup.find("article") or copy_soup.find("main") or copy_soup
    paragraphs = []
    for p in article.find_all("p"):
        text = clean_html_text(p.get_text(" ", strip=True))
        if len(text) >= 25 and normalize_text(text) not in ["baca juga", "iklan", "advertisement"]:
            paragraphs.append(text)
            if len(paragraphs) >= limit: break
    return paragraphs

def satker_is_relevant(title, first_paragraphs):
    title_n = normalize_text(title)
    first_text = normalize_text(" ".join(first_paragraphs))
    title_matches = [k for k in TARGET_KEJARI_KEYWORDS if normalize_text(k) in title_n]
    first_matches = [k for k in TARGET_KEJARI_KEYWORDS if normalize_text(k) in first_text]
    locs = []
    if title_matches: locs.append("title")
    if first_matches: locs.append("first_paragraphs")
    return bool(title_matches or first_matches), title_matches, first_matches, ",".join(locs)

def calculate_rule_score(text, rules):
    score, detected = 0, []
    text_n = normalize_text(text)
    for kw, weight in rules.items():
        if kw in text_n:
            score += weight
            detected.append(kw)
    return score, detected

def has_negation_near(text, keyword, window=60):
    text_n = normalize_text(text)
    start = text_n.find(keyword)
    negations = ["tidak", "bukan", "tanpa", "belum terbukti", "tidak terbukti", "menepis", "membantah"]
    while start != -1:
        before = text_n[max(0, start - window):start]
        if any(neg in before for neg in negations): return True
        start = text_n.find(keyword, start + 1)
    return False

def classify_article(title, snippet, content, first_paragraphs=None):
    first_paragraphs = first_paragraphs or []
    title_clean = clean_html_text(title)
    content_clean = clean_html_text(content)

    satker_ok, t_matches, f_matches, loc = satker_is_relevant(title_clean, first_paragraphs)
    if not satker_ok:
        return {
            "category": "Netral", "priority": "RENDAH", "negative_score": 0, "handling_score": 0,
            "positive_score": 0, "detected_keywords": [], "satker_matches": [], "satker_match_location": ""
        }

    full_text = f"{title_clean} {clean_html_text(snippet)} {' '.join(first_paragraphs)} {content_clean}"
    strong_score, strong_kw = calculate_rule_score(full_text, NEGATIVE_STRONG_RULES)
    handling_score, handling_kw = calculate_rule_score(full_text, HANDLING_RULES)
    positive_score, positive_kw = calculate_rule_score(full_text, POSITIVE_RULES)

    t_strong_s, t_strong_kw = calculate_rule_score(title_clean, NEGATIVE_STRONG_RULES)
    t_hand_s, _ = calculate_rule_score(title_clean, HANDLING_RULES)
    t_pos_s, _ = calculate_rule_score(title_clean, POSITIVE_RULES)

    danger_hits = [term for term in DANGER_TITLE_TERMS if term in normalize_text(title_clean) and not has_negation_near(title_clean, term)]
    legal_hits = [term for term in LEGAL_RISK_TERMS if term in normalize_text(full_text) and not has_negation_near(full_text, term)]

    cancellation_matches = [x for x in CANCELLATION_CONTEXT if x in normalize_text(full_text) and not has_negation_near(full_text, x)]
    strong_context_matches = [x for x in STRONG_NEGATIVE_CONTEXT if x in normalize_text(full_text) and not has_negation_near(full_text, x)]

    strong_score += (t_strong_s * 2) + (len(strong_context_matches) * 10)
    handling_score += (t_hand_s * 2)
    positive_score += (t_pos_s * 2)

    hard_negative = bool(strong_context_matches or danger_hits or t_strong_s >= 8 or strong_score >= 22 or cancellation_matches)

    if hard_negative:
        category, priority = "Negatif Kuat", "TINGGI"
    elif handling_score >= 8 or t_hand_s >= 5 or len(legal_hits) >= 2:
        category, priority = "Perlu Penanganan", "SEDANG"
    elif positive_score >= 6 or t_pos_s >= 4:
        category, priority = "Positif", "RENDAH"
    else:
        category, priority = "Netral", "RENDAH"

    all_detected = list(dict.fromkeys(strong_kw + handling_kw + positive_kw + danger_hits + legal_hits))

    return {
        "category": category, "priority": priority, "negative_score": strong_score,
        "handling_score": handling_score, "positive_score": positive_score,
        "detected_keywords": all_detected, "satker_matches": list(set(t_matches + f_matches)),
        "satker_match_location": loc,
    }

def fetch_rss_feed(query):
    encoded_query = urllib.parse.quote(query)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=id&gl=ID&ceid=ID:id"
    feed = feedparser.parse(rss_url)
    entries = []
    for entry in feed.entries:
        entries.append({
            "title": clean_html_text(entry.get("title", "")),
            "link": entry.get("link", ""),
            "rss_date": get_rss_date(entry),
        })
    return entries

def process_single_article(entry):
    resolved_url = resolve_redirect_url(entry["link"])
    norm_url = normalize_url(resolved_url)
    web_data = fetch_webpage(norm_url)
    if not web_data: return None

    soup = BeautifulSoup(web_data["html"], "html.parser")
    article_text = extract_article_text(soup)
    if len(article_text) < MIN_ARTICLE_TEXT: return None

    first_paragraphs = extract_first_paragraphs(soup)
    extracted_dt = extract_published_date(soup)
    is_valid, final_dt = validate_date(extracted_dt, entry["rss_date"])
    if not is_valid: return None

    analysis = classify_article(entry["title"], "", article_text, first_paragraphs)
    return {
        "title": clean_html_text(entry["title"]),
        "url": norm_url,
        "content": article_text,
        "published_date": final_dt.isoformat() if final_dt else None,
        "category": analysis["category"],
        "priority": analysis["priority"],
        "satker": NAMA_SATKER,
        "keywords": analysis["detected_keywords"],
    }

def send_telegram_alert(article):
    if not TELEGRAM_TOKEN or not CHAT_ID: return
    category = article.get("category", "Netral")
    emoji = "🔴" if category == "Negatif Kuat" else "🟡" if category == "Perlu Penanganan" else "🟢"
    msg = (
        f"{emoji} <b>PATROLI SIBER - BERITA BARU</b>\n\n"
        f"<b>Judul:</b> {html.escape(article['title'])}\n"
        f"<b>Kategori:</b> {category}\n"
        f"<b>Prioritas:</b> {article.get('priority', 'RENDAH')}\n"
        f"<b>Satker:</b> {article.get('satker', NAMA_SATKER)}\n"
        f"<b>Link:</b> <a href='{article['url']}'>Baca Artikel</a>"
    )
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=10)
    except Exception as e:
        print(f"[TELEGRAM ERROR] {e}")

def reclassify_all_existing_articles():
    print("[INFO] Memulai pembersihan tag HTML dan reklasifikasi database...")
    articles = get_all_articles()
    updated_count = 0
    for art in articles:
        clean_title = clean_html_text(art.get("title", ""))
        clean_content = clean_html_text(art.get("content", ""))
        first_p = [p.strip() for p in clean_content.split(".") if len(p.strip()) > 25][:3]
        analysis = classify_article(clean_title, "", clean_content, first_p)

        update_article(art["id"], {
            "title": clean_title,
            "content": clean_content,
            "category": analysis["category"],
            "priority": analysis["priority"],
            "keywords": analysis["detected_keywords"]
        })
        updated_count += 1
    print(f"[INFO] Pembersihan dan reklasifikasi selesai: {updated_count} artikel.")

def run_patrol():
    start_time = time.time()
    print(f"=== MENJALANKAN PATROLI SIBER ({NAMA_SATKER}) ===")
    raw_entries = []
    for query in SEARCH_TARGETS:
        raw_entries.extend(fetch_rss_feed(query))

    unique_entries = {e["link"]: e for e in raw_entries}.values()
    processed_count, new_articles_count = 0, 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_single_article, entry): entry for entry in unique_entries}
        for future in as_completed(futures):
            processed_count += 1
            res = future.result()
            if res:
                existing = get_article_by_link(res["url"])
                upsert_article(res)
                if not existing:
                    new_articles_count += 1
                    send_telegram_alert(res)

    reclassify_all_existing_articles()
    exec_time = round(time.time() - start_time, 2)
    save_run_log({"satker": NAMA_SATKER, "processed_urls": processed_count, "new_articles": new_articles_count, "execution_time_seconds": exec_time, "status": "SUCCESS"})

if __name__ == "__main__":
    run_patrol()
