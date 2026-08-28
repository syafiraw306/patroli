
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
    update_article,
    save_run_log,
)


# ============================================================
# KONFIGURASI
# ============================================================

TAHUN_TARGET = 2026
MAX_WORKERS = 10
REQUEST_TIMEOUT = 15

NAMA_SATKER = os.getenv(
    "NAMA_SATKER",
    "Kejaksaan Negeri Deli Serdang",
).strip()

TELEGRAM_TOKEN = (
    os.getenv("TELEGRAM_TOKEN") or ""
).strip()

CHAT_ID = (
    os.getenv("CHAT_ID") or ""
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
# NEGATIF KUAT
# ============================================================

NEGATIVE_STRONG_RULES = {

    "skandal": 12,
    "skandal perselingkuhan": 18,
    "perselingkuhan": 15,
    "selingkuh": 14,
    "pelakor": 15,

    "dugaan skandal": 14,
    "dugaan perselingkuhan": 16,

    "karangan bunga sindiran": 15,
    "papan bunga sindiran": 15,
    "papan bunga pelakor": 17,
    "karangan bunga pelakor": 17,

    "aib": 12,

    "dicopot": 13,
    "pencopotan": 13,
    "copot kajari": 15,
    "kajari dicopot": 17,

    "kejagung copot kajari": 18,
    "kajari dicopot kejagung": 18,

    "pelanggaran etik": 16,
    "pelanggaran etika": 15,
    "pelanggaran kode etik": 17,
    "melanggar etik": 15,

    "didesak": 12,
    "didesak mundur": 16,
    "didesak dicopot": 17,
    "kejari didesak": 15,

    "protes": 10,
    "demonstrasi": 10,
    "demo": 9,

    "kritik keras": 13,
    "menuai kritik": 11,
    "menuai sorotan": 11,
    "disorot": 10,

    "terjerat": 13,
    "tersandung": 12,
    "terlibat skandal": 17,

    "maladministrasi": 14,
    "arogan": 11,

    "pemerasan": 14,
    "dugaan pemerasan": 16,

    "suap": 13,
    "dugaan suap": 15,

    "gratifikasi": 13,
    "dugaan gratifikasi": 15,

    "pungli": 13,
    "dugaan pungli": 15,

    "mafia hukum": 17,
    "mafia": 13,

    "kolusi": 14,
    "nepotisme": 13,

    "penyalahgunaan wewenang": 15,
    "penyelewengan": 14,

    "cacat hukum": 13,

    "kejanggalan": 11,
    "janggal": 8,

    "tidak transparan": 11,
    "tidak profesional": 11,

    "batal dilantik": 11,
    "gagal dilantik": 11,
    "pelantikan ditunda": 11,

    "pelantikan mendadak ditunda": 14,

    "bongkar dugaan skandal": 17,

    "sorotan kasus narkotika": 14,

    "kabur": 7,
    "melarikan diri": 9,
}


# ============================================================
# PERLU PENANGANAN
# ============================================================

HANDLING_RULES = {

    "korupsi": 8,
    "dugaan korupsi": 10,
    "kasus korupsi": 9,

    "penyelidikan": 6,
    "penyidikan": 6,

    "diperiksa": 8,
    "diperiksa kejagung": 12,
    "diperiksa kejaksaan agung": 12,

    "dipanggil": 7,
    "dipanggil kejagung": 11,
    "dipanggil ke kejagung": 11,

    "dilaporkan": 8,
    "laporan masyarakat": 8,
    "pengaduan": 7,
    "pengaduan masyarakat": 8,

    "tersangka": 8,
    "terlapor": 8,

    "tuntutan": 5,
    "dituntut": 6,

    "narkotika": 7,
    "kasus narkotika": 10,

    "narapidana kabur": 10,
    "terpidana kabur": 10,

    "guru honorer": 5,
    "dibebaskan": 6,

    "keluhan pelayanan": 8,
    "pelayanan buruk": 9,

    "masalah": 3,
    "bermasalah": 6,

    "dipertanyakan": 7,

    "dugaan": 5,
    "indikasi": 5,
    "terindikasi": 6,

    "kasus": 4,

    "pencopotan": 8,
    "dicopot": 8,

    "perkara": 4,
    "konflik": 5,
    "sengketa": 5,
    "pelaporan": 6,
    "pengawasan": 4,
    "pemeriksaan": 5,
}


# ============================================================
# POSITIF
# ============================================================

POSITIVE_RULES = {

    "berhasil mengungkap": 8,
    "berhasil menangkap": 8,
    "berhasil mengamankan": 7,
    "berhasil mengusut": 7,

    "penghargaan": 7,
    "prestasi": 7,
    "capaian kinerja": 7,

    "pelayanan prima": 7,
    "pelayanan publik": 5,
    "pelayanan terbaik": 6,

    "penyuluhan hukum": 5,
    "sosialisasi hukum": 5,
    "penerangan hukum": 5,

    "jaksa masuk sekolah": 5,

    "peresmian": 5,
    "program unggulan": 6,
    "inovasi pelayanan": 6,

    "pemusnahan barang bukti": 6,
    "penyerahan barang bukti": 5,

    "upacara": 3,
    "apel": 3,
    "kunjungan kerja": 4,
    "silaturahmi": 4,
    "rapat koordinasi": 4,
    "koordinasi": 4,
    "konsolidasi": 4,
    "fgd": 4,
    "focus group discussion": 4,

    "penandatanganan mou": 5,
    "kerja sama": 5,

    "penyerahan penghargaan": 6,
    "peningkatan pelayanan": 6,
    "peningkatan kinerja": 6,
}


# ============================================================
# KONTEKS NEGATIF KUAT
# ============================================================

STRONG_NEGATIVE_CONTEXT = [

    "skandal perselingkuhan",
    "dugaan perselingkuhan",
    "perselingkuhan oknum",
    "oknum jaksa selingkuh",

    "papan bunga pelakor",
    "karangan bunga pelakor",

    "papan bunga sindiran",
    "karangan bunga sindiran",

    "kajari dicopot",
    "kajari dicopot kejagung",
    "kejagung copot kajari",

    "pencopotan kajari",

    "pelanggaran etik",
    "pelanggaran kode etik",

    "didesak mundur",
    "didesak dicopot",
    "didesak bebaskan",

    "kejari didesak",

    "menuai sorotan",
    "di tengah sorotan",

    "sorotan kasus narkotika",

    "bongkar dugaan skandal",

    "heboh karangan bunga",
    "heboh papan bunga",

    "28 cpns batal dilantik",
    "28 cpns gagal dilantik",

    "pelantikan 28 cpns ditunda",

    "gagal dilantik imbas",
    "batal dilantik imbas",

    "dugaan pemerasan",
    "dugaan suap",
    "dugaan gratifikasi",
    "dugaan pungli",

    "mafia hukum",
    "penyalahgunaan wewenang",
    "maladministrasi",
]


# ============================================================
# KONTEKS PENANGANAN
# ============================================================

HANDLING_CONTEXT = [

    "diperiksa kejagung",
    "dipanggil kejagung",
    "dipanggil ke kejagung",
    "diperiksa kejaksaan agung",

    "kejagung periksa",
    "kejagung memeriksa",

    "penyelidikan",
    "penyidikan",

    "mengusut kasus",
    "mengusut dugaan",

    "menangani kasus",
    "menangani dugaan",

    "menetapkan tersangka",

    "kasus narkotika",
    "kasus korupsi",

    "narapidana kabur",
    "terpidana kabur",

    "dilaporkan masyarakat",
    "pengaduan masyarakat",

    "didesak bebaskan",

    "dugaan pelanggaran",
    "dugaan penyalahgunaan",
    "dugaan penyelewengan",

    "perkara hukum",
    "sengketa hukum",
    "konflik hukum",
]


# ============================================================
# AKSI PENEGAKAN HUKUM POSITIF
# ============================================================

POSITIVE_ACTION_CONTEXT = [

    "mengusut dugaan korupsi",
    "usut dugaan korupsi",
    "mengusut kasus korupsi",

    "menangani kasus korupsi",
    "menangani dugaan korupsi",

    "melakukan penyelidikan",
    "melakukan penyidikan",

    "penyelidikan dugaan korupsi",
    "penyidikan kasus korupsi",

    "berhasil mengungkap kasus",
    "berhasil mengungkap korupsi",

    "berhasil menangkap tersangka",
    "berhasil mengamankan tersangka",

    "menetapkan tersangka",
    "menindak pelaku",

    "mengungkap kasus narkotika",
    "menangkap pelaku",

    "berhasil mengamankan barang bukti",
    "berhasil menyita barang bukti",

    "menuntut terdakwa",
    "mengajukan tuntutan",
]


# ============================================================
# AKTIVITAS NORMAL
# ============================================================

NORMAL_ACTIVITY_TERMS = [

    "upacara",
    "apel",
    "kunjungan kerja",
    "silaturahmi",
    "rapat koordinasi",
    "koordinasi",
    "konsolidasi",
    "fgd",
    "focus group discussion",
    "penandatanganan mou",
    "kerja sama",
    "peresmian",
    "penyuluhan hukum",
    "sosialisasi hukum",
    "penerangan hukum",
    "jaksa masuk sekolah",
    "pelayanan publik",
    "pelayanan prima",
    "penghargaan",
    "prestasi",
    "capaian kinerja",
    "program unggulan",
]


# ============================================================
# ISTILAH RISIKO JUDUL
# ============================================================

DANGER_TITLE_TERMS = [

    "dicopot",
    "dipanggil kejagung",
    "diperiksa kejagung",
    "diperiksa kejaksaan agung",

    "skandal",
    "perselingkuhan",
    "pelakor",

    "didesak",
    "bongkar",
    "sorotan",

    "kasus narkotika",
    "kasus korupsi",

    "papan bunga",
    "karangan bunga",

    "batal dilantik",
    "gagal dilantik",

    "pelanggaran etik",
    "pelanggaran kode etik",

    "dugaan suap",
    "dugaan gratifikasi",
    "dugaan pungli",
    "dugaan pemerasan",

    "mafia hukum",
    "penyalahgunaan wewenang",
]


LEGAL_RISK_TERMS = [

    "korupsi",
    "narkotika",
    "tersangka",
    "terlapor",
    "diperiksa",
    "dipanggil",
    "penyelidikan",
    "penyidikan",
    "pengaduan",
    "dilaporkan",
    "pencopotan",
    "dicopot",
    "pelanggaran",
    "pemerasan",
    "suap",
    "gratifikasi",
    "pungli",
    "penyelewengan",
    "mafia hukum",
    "penyalahgunaan wewenang",
    "sengketa",
    "konflik",
]


# ============================================================
# UTILITAS
# ============================================================

def normalize_text(text):
    """Normalisasi teks untuk pencarian keyword."""

    if not text:
        return ""

    text = html.unescape(str(text))
    text = text.lower()

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def parse_indonesian_date(text):
    """Parse tanggal Bahasa Indonesia."""

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
        text,
    )

    if not match:
        return None

    try:

        day = int(match.group(1))
        month_name = match.group(2)
        year = int(match.group(3))

        if month_name not in bulan:
            return None

        return datetime.datetime(
            year,
            bulan[month_name],
            day,
        )

    except Exception:

        return None


def parse_date_safe(value):
    """Parse tanggal dengan beberapa metode."""

    if not value:
        return None

    try:

        dt = parser.parse(
            str(value),
            fuzzy=True,
            dayfirst=True,
        )

        if dt.tzinfo:

            dt = (
                dt.astimezone(
                    datetime.timezone.utc
                )
                .replace(tzinfo=None)
            )

        return dt

    except Exception:

        return parse_indonesian_date(
            str(value)
        )


# ============================================================
# DATE EXTRACTION
# ============================================================

def extract_published_date(soup):

    candidates = []

    # --------------------------------------------------------
    # JSON-LD
    # --------------------------------------------------------

    for script in soup.find_all(
        "script",
        attrs={
            "type": re.compile(
                r"application/ld\+json",
                re.I,
            )
        },
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

            if isinstance(data, dict):

                objects.append(data)

                graph = data.get("@graph")

                if isinstance(graph, list):
                    objects.extend(graph)

            elif isinstance(data, list):

                objects = data

            for obj in objects:

                if not isinstance(obj, dict):
                    continue

                for key in [
                    "datePublished",
                    "dateCreated",
                    "dateModified",
                ]:

                    value = obj.get(key)

                    if value:
                        candidates.append(value)

        except Exception:

            continue

    # --------------------------------------------------------
    # META
    # --------------------------------------------------------

    selectors = [

        {"property": "article:published_time"},
        {"property": "og:article:published_time"},
        {"name": "article:published_time"},
        {"name": "publishdate"},
        {"name": "pubdate"},
        {"name": "datePublished"},
        {"itemprop": "datePublished"},
    ]

    for attrs in selectors:

        element = soup.find(
            "meta",
            attrs=attrs,
        )

        if element:

            value = (
                element.get("content")
                or element.get("datetime")
                or element.get_text(
                    " ",
                    strip=True,
                )
            )

            if value:
                candidates.append(value)

    # --------------------------------------------------------
    # TIME TAG
    # --------------------------------------------------------

    for tag in soup.find_all("time"):

        value = (
            tag.get("datetime")
            or tag.get_text(
                " ",
                strip=True,
            )
        )

        if value:
            candidates.append(value)

    # --------------------------------------------------------
    # PARSE
    # --------------------------------------------------------

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
        "updated_parsed",
    ]:

        value = getattr(
            entry,
            attr,
            None,
        )

        if value:

            try:

                return datetime.datetime(
                    value.tm_year,
                    value.tm_mon,
                    value.tm_mday,
                    value.tm_hour,
                    value.tm_min,
                    value.tm_sec,
                )

            except Exception:

                pass

    for attr in [
        "published",
        "updated",
        "created",
    ]:

        value = getattr(
            entry,
            attr,
            None,
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
    rss_date,
):

    now = datetime.datetime.now()

    date_value = (
        article_date
        or rss_date
    )

    if not date_value:
        return False, None

    if date_value.year != TAHUN_TARGET:
        return False, date_value

    # Tolak tanggal yang terlalu jauh di masa depan.
    if date_value > now + datetime.timedelta(days=1):
        return False, date_value

    return True, date_value


# ============================================================
# HTTP
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


def fetch_webpage(url):

    if not url:
        return None

    try:

        response = requests.get(
            url,
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )

        if response.status_code == 200:

            return {

                "html":
                    response.text,

                "final_url":
                    response.url,

            }

    except Exception as e:

        print(
            f"[FETCH ERROR] {url}: {e}"
        )

    return None


def resolve_redirect_url(url):

    if not url:
        return ""

    try:

        response = requests.get(
            url,
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
            stream=True,
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
# ARTICLE TEXT
# ============================================================

def extract_article_text(soup):

    copy_soup = BeautifulSoup(
        str(soup),
        "html.parser",
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
    )

    if article:

        text = article.get_text(
            " ",
            strip=True,
        )

    else:

        text = copy_soup.get_text(
            " ",
            strip=True,
        )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


# ============================================================
# SATKER MATCHING
# ============================================================

def find_satker_matches(
    title,
    snippet,
    content,
):

    title_text = normalize_text(title)
    snippet_text = normalize_text(snippet)
    content_text = normalize_text(content)

    matches = []

    for keyword in TARGET_KEJARI_KEYWORDS:

        keyword_n = normalize_text(keyword)

        if keyword_n in title_text:
            matches.append(keyword)

        elif keyword_n in snippet_text:
            matches.append(keyword)

        elif keyword_n in content_text:
            matches.append(keyword)

    return list(
        dict.fromkeys(matches)
    )


# ============================================================
# SCORE ENGINE
# ============================================================

def calculate_rule_score(
    text,
    rules,
):

    score = 0
    detected = []

    text = normalize_text(text)

    for keyword, weight in rules.items():

        if keyword in text:

            score += weight
            detected.append(keyword)

    return score, detected


def find_context_matches(
    text,
    context_list,
):

    text = normalize_text(text)

    return [
        phrase
        for phrase in context_list
        if phrase in text
    ]


# ============================================================
# CLASSIFIER
# ============================================================

def classify_article(
    title,
    snippet,
    content,
):

    title_n = normalize_text(title)
    snippet_n = normalize_text(snippet)
    content_n = normalize_text(content)

    full_text = (
        f"{title_n} "
        f"{snippet_n} "
        f"{content_n}"
    )

    # --------------------------------------------------------
    # SATKER
    # --------------------------------------------------------

    satker_matches = find_satker_matches(
        title,
        snippet,
        content,
    )

    if not satker_matches:

        return {

            "category": "Netral",
            "priority": "RENDAH",

            "negative_score": 0,
            "handling_score": 0,
            "positive_score": 0,

            "detected_keywords": [],
            "satker_matches": [],

            "strong_context": [],
            "positive_context": [],
            "handling_context": [],
        }

    # --------------------------------------------------------
    # SCORE FULL TEXT
    # --------------------------------------------------------

    strong_score, strong_keywords = (
        calculate_rule_score(
            full_text,
            NEGATIVE_STRONG_RULES,
        )
    )

    handling_score, handling_keywords = (
        calculate_rule_score(
            full_text,
            HANDLING_RULES,
        )
    )

    positive_score, positive_keywords = (
        calculate_rule_score(
            full_text,
            POSITIVE_RULES,
        )
    )

    # --------------------------------------------------------
    # SCORE TITLE
    # --------------------------------------------------------

    title_strong_score, title_strong_keywords = (
        calculate_rule_score(
            title_n,
            NEGATIVE_STRONG_RULES,
        )
    )

    title_handling_score, title_handling_keywords = (
        calculate_rule_score(
            title_n,
            HANDLING_RULES,
        )
    )

    title_positive_score, title_positive_keywords = (
        calculate_rule_score(
            title_n,
            POSITIVE_RULES,
        )
    )

    # --------------------------------------------------------
    # CONTEXT
    # --------------------------------------------------------

    strong_context_matches = find_context_matches(
        full_text,
        STRONG_NEGATIVE_CONTEXT,
    )

    handling_context_matches = find_context_matches(
        full_text,
        HANDLING_CONTEXT,
    )

    positive_action_matches = find_context_matches(
        full_text,
        POSITIVE_ACTION_CONTEXT,
    )

    # --------------------------------------------------------
    # TITLE BOOST
    # --------------------------------------------------------

    strong_score += title_strong_score * 2
    handling_score += title_handling_score * 2
    positive_score += title_positive_score * 2

    # --------------------------------------------------------
    # CONTEXT BOOST
    # --------------------------------------------------------

    strong_score += (
        len(strong_context_matches) * 8
    )

    handling_score += (
        len(handling_context_matches) * 4
    )

    positive_score += (
        len(positive_action_matches) * 3
    )

    # --------------------------------------------------------
    # DANGER TITLE
    # --------------------------------------------------------

    danger_hits = [

        term
        for term in DANGER_TITLE_TERMS
        if term in title_n
    ]

    # --------------------------------------------------------
    # LEGAL RISK
    # --------------------------------------------------------

    legal_hits = [

        term
        for term in LEGAL_RISK_TERMS
        if term in full_text
    ]

    # --------------------------------------------------------
    # RISK INDICATORS
    # --------------------------------------------------------

    risk_indicators = (
        len(strong_keywords)
        + len(handling_keywords)
        + len(strong_context_matches)
        + len(handling_context_matches)
    )

    # --------------------------------------------------------
    # DEFAULT
    # --------------------------------------------------------

    category = "Netral"
    priority = "RENDAH"

    # ========================================================
    # NEGATIF KUAT
    # ========================================================

    if strong_context_matches:

        category = "Negatif Kuat"
        priority = "KRITIS"

    elif danger_hits:

        category = "Negatif Kuat"
        priority = "KRITIS"

    elif title_strong_score >= 8:

        category = "Negatif Kuat"
        priority = "KRITIS"

    elif strong_score >= 20:

        category = "Negatif Kuat"
        priority = "KRITIS"

    # ========================================================
    # PERLU PENANGANAN
    # ========================================================

    elif title_handling_score >= 7:

        category = "Perlu Penanganan"
        priority = "TINGGI"

    elif handling_score >= 12:

        category = "Perlu Penanganan"
        priority = "TINGGI"

    elif handling_score >= 7:

        category = "Perlu Penanganan"
        priority = "SEDANG"

    # ========================================================
    # POSITIF
    # ========================================================

    elif positive_score >= 6:

        category = "Positif"
        priority = "RENDAH"

    # ========================================================
    # NORMAL ACTIVITY
    # ========================================================

    normal_activity_hits = [

        term
        for term in NORMAL_ACTIVITY_TERMS
        if term in title_n
    ]

    if (
        normal_activity_hits
        and not strong_context_matches
        and not danger_hits
        and not title_strong_score
    ):

        if positive_score >= 3:

            category = "Positif"
            priority = "RENDAH"

    # ========================================================
    # POSITIVE LAW ENFORCEMENT
    # ========================================================

    if (
        category == "Negatif Kuat"
        and positive_action_matches
        and not strong_context_matches
        and not danger_hits
        and title_strong_score < 8
    ):

        category = "Perlu Penanganan"
        priority = "TINGGI"

    # Jika berita jelas menunjukkan tindakan penegakan
    # hukum oleh Kejaksaan, jangan langsung dianggap negatif.
    if (
        positive_action_matches
        and not strong_context_matches
        and not danger_hits
        and title_strong_score == 0
    ):

        if handling_score >= 7:

            category = "Perlu Penanganan"
            priority = "TINGGI"

    # ========================================================
    # FALLBACK ANTI-NETRAL
    # ========================================================

    if (
        category == "Netral"
        and risk_indicators >= 2
    ):

        category = "Perlu Penanganan"
        priority = "SEDANG"

    # ========================================================
    # ISU HUKUM
    # ========================================================

    if (
        category == "Netral"
        and len(legal_hits) >= 2
    ):

        category = "Perlu Penanganan"
        priority = "SEDANG"

    # ========================================================
    # PRIORITAS TAMBAHAN
    # ========================================================

    if category == "Perlu Penanganan":

        if (
            title_strong_score >= 5
            or len(danger_hits) >= 1
        ):

            priority = "TINGGI"

        elif handling_score >= 15:

            priority = "TINGGI"

    # ========================================================
    # DETECTED KEYWORDS
    # ========================================================

    detected = list(
        dict.fromkeys(

            strong_keywords
            + handling_keywords
            + positive_keywords
            + strong_context_matches
            + handling_context_matches
            + positive_action_matches
            + title_strong_keywords
            + title_handling_keywords
            + title_positive_keywords
            + danger_hits
            + legal_hits

        )
    )

    # ========================================================
    # RETURN
    # ========================================================

    return {

        "category": category,

        "priority": priority,

        "negative_score": int(
            strong_score
        ),

        "handling_score": int(
            handling_score
        ),

        "positive_score": int(
            positive_score
        ),

        "detected_keywords": detected[:50],

        "satker_matches": satker_matches,

        "strong_context":
            strong_context_matches,

        "positive_context":
            positive_action_matches,

        "handling_context":
            handling_context_matches,
    }


# ============================================================
# GOOGLE NEWS RSS
# ============================================================

def search_google_news(query):

    encoded_query = urllib.parse.quote(
        query
    )

    rss_url = (
        "https://news.google.com/rss/search?"
        f"q={encoded_query}"
        "&hl=id-ID"
        "&gl=ID"
        "&ceid=ID:id"
    )

    try:

        feed = feedparser.parse(
            rss_url
        )

        results = []

        for entry in feed.entries:

            title = getattr(
                entry,
                "title",
                "",
            )

            link = getattr(
                entry,
                "link",
                "",
            )

            summary = getattr(
                entry,
                "summary",
                "",
            )

            summary = BeautifulSoup(
                summary,
                "html.parser",
            ).get_text(
                " ",
                strip=True,
            )

            rss_date = get_rss_date(
                entry
            )

            if not link:
                continue

            results.append({

                "title": title,

                "link": link,

                "snippet": summary,

                "rss_date": rss_date,
            })

        return results

    except Exception as e:

        print(
            f"[RSS ERROR] {e}"
        )

        return []


# ============================================================
# QUERY
# ============================================================

def generate_queries():

    queries = []

    for target in SEARCH_TARGETS:

        queries.append(
            f"{target} "
            f"after:2025-12-31 "
            f"before:2027-01-01"
        )

    return list(
        dict.fromkeys(
            queries
        )
    )


# ============================================================
# COLLECT
# ============================================================

def collect_candidates():

    all_candidates = []

    queries = generate_queries()

    for query in queries:

        print(
            f"[SEARCH] {query}"
        )

        results = search_google_news(
            query
        )

        all_candidates.extend(
            results
        )

    # --------------------------------------------------------
    # Deduplicate
    # --------------------------------------------------------

    unique = {}

    for item in all_candidates:

        link = item.get(
            "link",
            "",
        ).strip()

        if not link:
            continue

        if link not in unique:

            unique[link] = item

    return list(
        unique.values()
    )


# ============================================================
# PROCESS CANDIDATE
# ============================================================

def process_candidate(item):

    original_url = item.get(
        "link",
        "",
    )

    title = item.get(
        "title",
        "Tanpa Judul",
    )

    snippet = item.get(
        "snippet",
        "",
    )

    rss_date = item.get(
        "rss_date"
    )

    if not original_url:
        return None

    # --------------------------------------------------------
    # Resolve Google News URL
    # --------------------------------------------------------

    final_url = resolve_redirect_url(
        original_url
    )

    # --------------------------------------------------------
    # Fetch
    # --------------------------------------------------------

    result = fetch_webpage(
        final_url
    )

    if not result:
        return None

    html_content = result.get(
        "html",
        "",
    )

    real_url = (
        result.get(
            "final_url"
        )
        or final_url
    )

    # --------------------------------------------------------
    # Parse
    # --------------------------------------------------------

    try:

        soup = BeautifulSoup(
            html_content,
            "html.parser",
        )

    except Exception:

        return None

    # --------------------------------------------------------
    # Date
    # --------------------------------------------------------

    article_date = extract_published_date(
        soup
    )

    valid_date, published_date = (
        validate_date(
            article_date,
            rss_date,
        )
    )

    if not valid_date:
        return None

    # --------------------------------------------------------
    # Content
    # --------------------------------------------------------

    content = extract_article_text(
        soup
    )

    if len(content) < 100:

        content = (
            f"{snippet} {content}"
        ).strip()

    # --------------------------------------------------------
    # Classification
    # --------------------------------------------------------

    classification = classify_article(
        title,
        snippet,
        content,
    )

    # Jika tidak terkait satker, tidak perlu disimpan.
    if not classification.get(
        "satker_matches"
    ):

        return None

    # --------------------------------------------------------
    # Result
    # --------------------------------------------------------

    return {

        "title": title,

        "link": real_url,

        "google_news_url":
            original_url,

        "snippet": snippet,

        "content":
            content[:10000],

        "published_date":
            published_date.isoformat(),

        "category":
            classification["category"],

        "priority":
            classification["priority"],

        "negative_score":
            classification["negative_score"],

        "handling_score":
            classification["handling_score"],

        "positive_score":
            classification["positive_score"],

        "detected_keywords":
            classification["detected_keywords"],

        "satker_matches":
            classification["satker_matches"],

        "strong_context":
            classification["strong_context"],

        "positive_context":
            classification["positive_context"],

        "handling_context":
            classification["handling_context"],

        "detected_time":
            datetime.datetime.now().isoformat(),

        "source":
            "Google News RSS",
    }


# ============================================================
# REKLASIFIKASI DATABASE
# ============================================================

def rekategorisasi_semua_database():

    print()
    print("==========================================")
    print("REKLASIFIKASI DATABASE SUPABASE")
    print("==========================================")

    counter = {

        "Negatif Kuat": 0,
        "Perlu Penanganan": 0,
        "Netral": 0,
        "Positif": 0,
    }

    updated = 0
    failed = 0

    try:

        articles = get_all_articles()

    except Exception as e:

        print(
            "[RECLASSIFY ERROR] "
            f"Gagal mengambil artikel dari Supabase: {e}"
        )

        return {

            "total": 0,
            "updated": 0,
            "failed": 1,
            "counts": counter,
        }

    total = len(articles)

    print(
        f"[SUPABASE] Total artikel: {total}"
    )

    if total == 0:

        return {

            "total": 0,
            "updated": 0,
            "failed": 0,
            "counts": counter,
        }

    for index, article in enumerate(
        articles,
        start=1,
    ):

        try:

            title = (
                article.get("title")
                or ""
            )

            snippet = (
                article.get("snippet")
                or ""
            )

            content = (
                article.get("content")
                or ""
            )

            link = (
                article.get("link")
                or ""
            )

            if not link:

                failed += 1
                continue

            classification = classify_article(
                title,
                snippet,
                content,
            )

            updates = {

                "category":
                    classification.get(
                        "category",
                        "Netral",
                    ),

                "priority":
                    classification.get(
                        "priority",
                        "RENDAH",
                    ),

                "negative_score":
                    int(
                        classification.get(
                            "negative_score",
                            0,
                        )
                    ),

                "handling_score":
                    int(
                        classification.get(
                            "handling_score",
                            0,
                        )
                    ),

                "positive_score":
                    int(
                        classification.get(
                            "positive_score",
                            0,
                        )
                    ),

                "detected_keywords":
                    classification.get(
                        "detected_keywords",
                        [],
                    ),

                "satker_matches":
                    classification.get(
                        "satker_matches",
                        [],
                    ),

                "strong_context":
                    classification.get(
                        "strong_context",
                        [],
                    ),

                "positive_context":
                    classification.get(
                        "positive_context",
                        [],
                    ),

                "handling_context":
                    classification.get(
                        "handling_context",
                        [],
                    ),
            }

            update_article(
                link,
                updates,
            )

            category = updates["category"]

            if category not in counter:

                category = "Netral"

            counter[category] += 1
            updated += 1

        except Exception as e:

            failed += 1

            print(
                f"[RECLASSIFY ERROR] "
                f"{index}/{total}: {e}"
            )

        if (
            index % 25 == 0
            or index == total
        ):

            print(
                f"Progress: "
                f"{index}/{total}"
            )

    print()
    print("==========================================")
    print("REKLASIFIKASI SELESAI")
    print("==========================================")

    print(
        json.dumps(
            counter,
            indent=2,
            ensure_ascii=False,
        )
    )

    print(
        f"Total artikel : {total}"
    )

    print(
        f"Berhasil      : {updated}"
    )

    print(
        f"Gagal         : {failed}"
    )

    return {

        "total": total,

        "updated": updated,

        "failed": failed,

        "counts": counter,
    }


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(finding):

    if not TELEGRAM_TOKEN or not CHAT_ID:

        print(
            "[TELEGRAM] Token/Chat ID belum dikonfigurasi."
        )

        return False

    category = finding.get(
        "category",
        "Netral",
    )

    priority = finding.get(
        "priority",
        "RENDAH",
    )

    if category == "Negatif Kuat":

        emoji = "🔴"

    elif category == "Perlu Penanganan":

        emoji = "🟠"

    else:

        emoji = "🟡"

    keywords = finding.get(
        "detected_keywords",
        [],
    )

    link = finding.get(
        "link",
        "",
    )

    safe_link = html.escape(
        link,
        quote=True,
    )

    message = (

        f"{emoji} "
        f"<b>PATROLI SIBER 2026</b>\n\n"

        f"<b>Satker:</b> "
        f"{html.escape(NAMA_SATKER)}\n\n"

        f"<b>Kategori:</b> "
        f"{html.escape(category)}\n"

        f"<b>Prioritas:</b> "
        f"{html.escape(priority)}\n\n"

        f"<b>Judul:</b>\n"
        f"{html.escape(finding.get('title', '-'))}\n\n"

        f"<b>Tanggal:</b>\n"
        f"{html.escape(finding.get('published_date', '-'))}\n\n"

        f"<b>Indikator:</b>\n"
        f"{html.escape(', '.join(keywords[:20]) or '-')}\n\n"

        f"<b>Link:</b>\n"
        f"<a href=\"{safe_link}\">Buka Artikel</a>\n\n"

        f"<i>Verifikasi isi berita tetap diperlukan.</i>"
    )

    url = (
        "https://api.telegram.org/"
        f"bot{TELEGRAM_TOKEN}/sendMessage"
    )

    try:

        response = requests.post(
            url,
            json={

                "chat_id": CHAT_ID,

                "text": message,

                "parse_mode": "HTML",

                "disable_web_page_preview": False,
            },
            timeout=15,
        )

        response.raise_for_status()

        result = response.json()

        if not result.get("ok"):

            print(
                f"[TELEGRAM ERROR] {result}"
            )

        return bool(
            result.get("ok")
        )

    except Exception as e:

        print(
            f"[TELEGRAM ERROR] {e}"
        )

        return False


# ============================================================
# PATROLI UTAMA
# ============================================================

def jalankan_patroli():

    start = time.time()

    print()
    print("==========================================")
    print("MEMULAI PATROLI SIBER 2026")
    print("==========================================")
    print(
        f"TARGET: {NAMA_SATKER}"
    )
    print("==========================================")
    print()

    # ========================================================
    # 1. GOOGLE NEWS
    # ========================================================

    candidates = collect_candidates()

    print(
        f"[PATROLI] Kandidat ditemukan: "
        f"{len(candidates)}"
    )

    # ========================================================
    # 2. PROCESS
    # ========================================================

    results = []

    with ThreadPoolExecutor(
        max_workers=MAX_WORKERS
    ) as executor:

        futures = [

            executor.submit(
                process_candidate,
                item,
            )

            for item in candidates
        ]

        for future in as_completed(
            futures
        ):

            try:

                result = future.result()

                if result:

                    results.append(
                        result
                    )

            except Exception as e:

                print(
                    f"[WORKER ERROR] {e}"
                )

    print(
        f"[PATROLI] Artikel valid: "
        f"{len(results)}"
    )

    # ========================================================
    # 3. SIMPAN
    # ========================================================

    save_success = 0
    save_failed = 0

    for article in results:

        try:

            upsert_article(
                article
            )

            save_success += 1

        except Exception as e:

            save_failed += 1

            print(
                f"[SUPABASE ERROR] {e}"
            )

    print(
        "[SUPABASE] "
        f"Berhasil disimpan/update: "
        f"{save_success}"
    )

    print(
        f"[SUPABASE] Gagal: "
        f"{save_failed}"
    )

    # ========================================================
    # 4. REKLASIFIKASI
    # ========================================================

    print()
    print(
        "[PATROLI] Memulai reklasifikasi "
        "seluruh database..."
    )

    reclass_result = (
        rekategorisasi_semua_database()
    )

    # ========================================================
    # 5. TELEGRAM
    # ========================================================

    telegram_count = 0

    for article in results:

        category = article.get(
            "category",
            "Netral",
        )

        priority = article.get(
            "priority",
            "RENDAH",
        )

        if category not in [
            "Negatif Kuat",
            "Perlu Penanganan",
        ]:

            continue

        if priority not in [
            "KRITIS",
            "TINGGI",
        ]:

            continue

        try:

            if send_telegram(
                article
            ):

                telegram_count += 1

        except Exception as e:

            print(
                f"[TELEGRAM ERROR] {e}"
            )

    # ========================================================
    # 6. STATISTIK
    # ========================================================

    elapsed = (
        time.time()
        - start
    )

    counts = reclass_result.get(
        "counts",
        {

            "Negatif Kuat": 0,
            "Perlu Penanganan": 0,
            "Netral": 0,
            "Positif": 0,
        }
    )

    # ========================================================
    # 7. RUN LOG
    # ========================================================

    log_data = {

        "duration_seconds":
            round(
                elapsed,
                2,
            ),

        "candidate_count":
            len(candidates),

        "valid_count":
            len(results),

        "negative_count":
            counts.get(
                "Negatif Kuat",
                0,
            ),

        "handling_count":
            counts.get(
                "Perlu Penanganan",
                0,
            ),

        "neutral_count":
            counts.get(
                "Netral",
                0,
            ),

        "positive_count":
            counts.get(
                "Positif",
                0,
            ),

        "telegram_count":
            telegram_count,

        "status":
            "SELESAI",
    }

    try:

        save_run_log(
            log_data
        )

    except Exception as e:

        print(
            f"[LOG ERROR] {e}"
        )

    # ========================================================
    # 8. OUTPUT
    # ========================================================

    print()
    print("==========================================")
    print("PATROLI SELESAI")
    print("==========================================")

    print(
        f"Durasi              : "
        f"{elapsed:.1f} detik"
    )

    print(
        f"Kandidat            : "
        f"{len(candidates)}"
    )

    print(
        f"Artikel valid       : "
        f"{len(results)}"
    )

    print(
        f"Berhasil disimpan   : "
        f"{save_success}"
    )

    print(
        f"Gagal disimpan      : "
        f"{save_failed}"
    )

    print(
        f"Database            : "
        f"{reclass_result.get('total', 0)}"
    )

    print(
        f"Direklasifikasi     : "
        f"{reclass_result.get('updated', 0)}"
    )

    print(
        f"Reclass gagal       : "
        f"{reclass_result.get('failed', 0)}"
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

    print("==========================================")
    print()

    return log_data


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":

    try:

        if (
            len(sys.argv) > 1
            and sys.argv[1].lower()
            in [
                "--reclassify",
                "--rekategorisasi",
            ]
        ):

            result = (
                rekategorisasi_semua_database()
            )

        else:

            result = (
                jalankan_patroli()
            )

        print()
        print("==========================================")
        print("PROGRAM SELESAI NORMAL")
        print("==========================================")

        sys.exit(0)

    except KeyboardInterrupt:

        print()
        print(
            "[PATROLI] "
            "Dihentikan oleh pengguna."
        )

        sys.exit(0)

    except Exception as e:

        print()
        print("==========================================")
        print("FATAL ERROR")
        print("==========================================")
        print(str(e))
        print("==========================================")

        sys.exit(1)

