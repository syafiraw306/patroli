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
    save_run_log
)


# ============================================================
# KONFIGURASI
# ============================================================

TAHUN_TARGET = 2026

MAX_WORKERS = 10

REQUEST_TIMEOUT = 15

NAMA_SATKER = os.getenv(
    "NAMA_SATKER",
    "Kejaksaan Negeri Deli Serdang"
).strip()

TELEGRAM_TOKEN = (
    os.getenv("TELEGRAM_TOKEN") or ""
).strip()

CHAT_ID = (
    os.getenv("CHAT_ID") or ""
).strip()


# ============================================================
# TARGET
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
    "kacabjari labuhan deli"
]


SEARCH_TARGETS = [

    '"Kejaksaan Negeri Deli Serdang"',
    '"Kejari Deli Serdang"',
    '"Kajari Deli Serdang"',
    '"Kejari Deliserdang"',
    '"Kejaksaan Deli Serdang"',
    '"Cabjari Pancur Batu"',
    '"Cabjari Labuhan Deli"'

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
    "melarikan diri": 9
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

    "dipanggil": 7,
    "dipanggil kejagung": 11,

    "diperiksa kejaksaan agung": 12,

    "dilaporkan": 8,
    "laporan masyarakat": 8,
    "pengaduan": 7,

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
    "dicopot": 8
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

    "penyuluhan hukum": 5,
    "sosialisasi hukum": 5,

    "jaksa masuk sekolah": 5,

    "peresmian": 5,
    "program unggulan": 6,

    "pemusnahan barang bukti": 6
}


# ============================================================
# KONTEKS NEGATIF
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
    "batal dilantik imbas"
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

    "didesak bebaskan"
]


# ============================================================
# POSITIVE ACTION
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
    "menangkap pelaku"
]


# ============================================================
# UTIL
# ============================================================

def normalize_text(text):

    if not text:
        return ""

    text = html.unescape(
        str(text)
    )

    text = text.lower()

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


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
        "des": 12
    }

    text = normalize_text(text)

    match = re.search(
        r"(\d{1,2})\s+([a-z]+)\s+(\d{4})",
        text
    )

    if not match:
        return None

    try:

        day = int(
            match.group(1)
        )

        month_name = match.group(2)

        year = int(
            match.group(3)
        )

        if month_name not in bulan:
            return None

        return datetime.datetime(
            year,
            bulan[month_name],
            day
        )

    except Exception:

        return None


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


    # JSON LD
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
                    "dateCreated"
                ]:

                    value = obj.get(key)

                    if value:
                        candidates.append(value)

        except Exception:
            continue


    # META
    selectors = [

        {"property": "article:published_time"},
        {"property": "og:article:published_time"},
        {"name": "article:published_time"},
        {"name": "publishdate"},
        {"name": "pubdate"},
        {"name": "datePublished"},
        {"itemprop": "datePublished"}

    ]

    for attrs in selectors:

        element = soup.find(
            "meta",
            attrs=attrs
        )

        if element:

            value = (
                element.get("content")
                or element.get("datetime")
                or element.get_text(
                    " ",
                    strip=True
                )
            )

            if value:
                candidates.append(value)


    # TIME
    for tag in soup.find_all("time"):

        value = (
            tag.get("datetime")
            or tag.get_text(
                " ",
                strip=True
            )
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
        "updated",
        "created"
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
# VALIDASI DATE
# ============================================================

def validate_date(
    article_date,
    rss_date
):

    now = datetime.datetime.now()

    # Artikel date prioritas
    if article_date:

        if article_date.year != TAHUN_TARGET:
            return False, article_date

        if article_date > now + datetime.timedelta(
            days=1
        ):
            return False, article_date

        return True, article_date


    # RSS fallback
    if rss_date:

        if rss_date.year != TAHUN_TARGET:
            return False, rss_date

        if rss_date > now + datetime.timedelta(
            days=1
        ):
            return False, rss_date

        return True, rss_date


    return False, None


# ============================================================
# FETCH
# ============================================================

def fetch_webpage(url):

    headers = {

        "User-Agent":
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/131.0 Safari/537.36",

        "Accept-Language":
            "id-ID,id;q=0.9,en;q=0.8"

    }

    try:

        response = requests.get(
            url,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True
        )

        if response.status_code == 200:

            return {

                "html": response.text,

                "final_url":
                    response.url

            }

    except Exception:
        pass

    return None


# ============================================================
# REDIRECT
# ============================================================

def resolve_redirect_url(url):

    if not url:
        return ""

    try:

        response = requests.get(
            url,
            headers={
                "User-Agent":
                    "Mozilla/5.0"
            },
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
# ARTICLE TEXT
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
        "iframe"
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


    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# ============================================================
# SATKER
# ============================================================

def find_satker_matches(
    title,
    snippet,
    content
):

    text = normalize_text(
        f"{title} {snippet} {content}"
    )

    matches = []

    for keyword in TARGET_KEJARI_KEYWORDS:

        if keyword in text:

            matches.append(keyword)

    return list(
        dict.fromkeys(matches)
    )


# ============================================================
# SCORE
# ============================================================

def calculate_rule_score(
    text,
    rules
):

    score = 0

    detected = []

    for keyword, weight in rules.items():

        if keyword in text:

            score += weight

            detected.append(keyword)

    return score, detected


# ============================================================
# CLASSIFIER
# ============================================================

def classify_article(
    title,
    snippet,
    content
):

    title_n = normalize_text(title)

    snippet_n = normalize_text(snippet)

    content_n = normalize_text(content)

    full_text = (
        f"{title_n} "
        f"{snippet_n} "
        f"{content_n}"
    )


    satker_matches = find_satker_matches(
        title,
        snippet,
        content
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
            "positive_context": []

        }


    # --------------------------------------------------------
    # SCORE DASAR
    # --------------------------------------------------------

    strong_score, strong_keywords = (
        calculate_rule_score(
            full_text,
            NEGATIVE_STRONG_RULES
        )
    )

    handling_score, handling_keywords = (
        calculate_rule_score(
            full_text,
            HANDLING_RULES
        )
    )

    positive_score, positive_keywords = (
        calculate_rule_score(
            full_text,
            POSITIVE_RULES
        )
    )


    # --------------------------------------------------------
    # TITLE SCORE
    # --------------------------------------------------------

    title_strong_score, title_strong_keywords = (
        calculate_rule_score(
            title_n,
            NEGATIVE_STRONG_RULES
        )
    )

    title_handling_score, title_handling_keywords = (
        calculate_rule_score(
            title_n,
            HANDLING_RULES
        )
    )


    # --------------------------------------------------------
    # STRONG CONTEXT
    # --------------------------------------------------------

    strong_context_matches = []

    for phrase in STRONG_NEGATIVE_CONTEXT:

        if phrase in full_text:

            strong_context_matches.append(
                phrase
            )


    # --------------------------------------------------------
    # HANDLING CONTEXT
    # --------------------------------------------------------

    handling_context_matches = []

    for phrase in HANDLING_CONTEXT:

        if phrase in full_text:

            handling_context_matches.append(
                phrase
            )


    # --------------------------------------------------------
    # POSITIVE ACTION
    # --------------------------------------------------------

    positive_action_matches = []

    for phrase in POSITIVE_ACTION_CONTEXT:

        if phrase in full_text:

            positive_action_matches.append(
                phrase
            )


    # ========================================================
    # CONTEXTUAL BOOST
    # ========================================================

    # Judul sangat penting.
    if title_strong_score > 0:

        strong_score += (
            title_strong_score * 2
        )


    if title_handling_score > 0:

        handling_score += (
            title_handling_score
        )


    # Frasa eksplisit negatif sangat kuat.
    if strong_context_matches:

        strong_score += (
            len(strong_context_matches) * 8
        )


    # Pemeriksaan / pemanggilan / perkara
    # minimal perlu perhatian.
    if handling_context_matches:

        handling_score += (
            len(handling_context_matches) * 4
        )


    # ========================================================
    # PRIORITAS
    # ========================================================

    category = "Netral"

    priority = "RENDAH"


    # ========================================================
    # NEGATIF KUAT
    # ========================================================

    if strong_context_matches:

        category = "Negatif Kuat"

        priority = "KRITIS"


    elif title_strong_score >= 8:

        category = "Negatif Kuat"

        priority = "KRITIS"


    elif strong_score >= 14:

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
    # NETRAL
    # ========================================================

    else:

        category = "Netral"

        priority = "RENDAH"


    # ========================================================
    # KOREKSI:
    #
    # Artikel penegakan hukum jangan otomatis menjadi
    # negatif kuat hanya karena kata "korupsi".
    # ========================================================

    if (
        category == "Negatif Kuat"
        and positive_action_matches
        and not strong_context_matches
        and title_strong_score < 8
    ):

        category = "Perlu Penanganan"

        priority = "TINGGI"


    # ========================================================
    # KOREKSI EKSTRA UNTUK BERITA YANG BERISIKO
    # ========================================================

    title_lower = title_n


    danger_title_terms = [

        "dicopot",
        "dipanggil kejagung",
        "diperiksa kejagung",
        "skandal",
        "perselingkuhan",
        "pelakor",
        "didesak",
        "bongkar",
        "sorotan",
        "kasus narkotika",
        "papan bunga",
        "karangan bunga",
        "batal dilantik",
        "gagal dilantik"

    ]


    danger_hits = [

        term
        for term in danger_title_terms
        if term in title_lower

    ]


    if danger_hits:

        if (
            "dicopot" in title_lower
            or "skandal" in title_lower
            or "perselingkuhan" in title_lower
            or "pelakor" in title_lower
            or "didesak" in title_lower
            or "papan bunga" in title_lower
            or "karangan bunga" in title_lower
            or "batal dilantik" in title_lower
            or "gagal dilantik" in title_lower
        ):

            category = "Negatif Kuat"

            priority = "KRITIS"

        elif category == "Netral":

            category = "Perlu Penanganan"

            priority = "TINGGI"


    # ========================================================
    # FALLBACK ANTI-NETRAL
    #
    # Artikel yang mengandung minimal dua indikator risiko
    # tidak boleh terlalu mudah masuk Netral.
    # ========================================================

    risk_indicators = 0

    risk_indicators += len(
        strong_keywords
    )

    risk_indicators += len(
        handling_keywords
    )

    risk_indicators += len(
        strong_context_matches
    )

    risk_indicators += len(
        handling_context_matches
    )


    if (
        category == "Netral"
        and risk_indicators >= 2
    ):

        category = "Perlu Penanganan"

        priority = "SEDANG"


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

        )
    )


    return {

        "category":
            category,

        "priority":
            priority,

        "negative_score":
            int(strong_score),

        "handling_score":
            int(handling_score),

        "positive_score":
            int(positive_score),

        "detected_keywords":
            detected[:50],

        "satker_matches":
            satker_matches,

        "strong_context":
            strong_context_matches,

        "positive_context":
            positive_action_matches,

        "handling_context":
            handling_context_matches

    }


# ============================================================
# GOOGLE NEWS
# ============================================================

def search_google_news(
    query
):

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
                ""
            )

            link = getattr(
                entry,
                "link",
                ""
            )

            summary = getattr(
                entry,
                "summary",
                ""
            )


            summary = BeautifulSoup(
                summary,
                "html.parser"
            ).get_text(
                " ",
                strip=True
            )


            rss_date = get_rss_date(
                entry
            )


            if not link:
                continue


            results.append({

                "title":
                    title,

                "link":
                    link,

                "snippet":
                    summary,

                "rss_date":
                    rss_date

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


    # URL dedup
    unique = {}

    for item in all_candidates:

        link = item.get(
            "link",
            ""
        ).strip()

        if not link:
            continue

        if link not in unique:

            unique[link] = item


    return list(
        unique.values()
    )


# ============================================================
# PROCESS ARTICLE
# ============================================================

def process_candidate(item):

    original_url = item.get(
        "link",
        ""
    )

    title = item.get(
        "title",
        "Tanpa Judul"
    )

    snippet = item.get(
        "snippet",
        ""
    )

    rss_date = item.get(
        "rss_date"
    )


    if not original_url:
        return None


    # --------------------------------------------------------
    # REDIRECT
    # --------------------------------------------------------

    final_url = resolve_redirect_url(
        original_url
    )


    # --------------------------------------------------------
    # FETCH
    # --------------------------------------------------------

    result = fetch_webpage(
        final_url
    )


    if not result:
        return None


    html_content = result.get(
        "html",
        ""
    )

    real_url = (
        result.get(
            "final_url"
        )
        or final_url
    )


    try:

        soup = BeautifulSoup(
            html_content,
            "html.parser"
        )

    except Exception:

        return None


    # --------------------------------------------------------
    # DATE
    # --------------------------------------------------------

    article_date = extract_published_date(
        soup
    )


    valid_date, published_date = (
        validate_date(
            article_date,
            rss_date
        )
    )


    if not valid_date:

        return None


    # --------------------------------------------------------
    # CONTENT
    # --------------------------------------------------------

    content = extract_article_text(
        soup
    )


    if len(content) < 100:

        content = (
            f"{snippet} {content}"
        )


    # --------------------------------------------------------
    # CLASSIFY
    # --------------------------------------------------------

    classification = classify_article(
        title,
        snippet,
        content
    )


    return {

        "title":
            title,

        "link":
            real_url,

        "google_news_url":
            original_url,

        "snippet":
            snippet,

        "content":
            content[:10000],

        "published_date":
            published_date.isoformat(),

        "category":
            classification[
                "category"
            ],

        "priority":
            classification[
                "priority"
            ],

        "negative_score":
            classification[
                "negative_score"
            ],

        "handling_score":
            classification[
                "handling_score"
            ],

        "positive_score":
            classification[
                "positive_score"
            ],

        "detected_keywords":
            classification[
                "detected_keywords"
            ],

        "satker_matches":
            classification[
                "satker_matches"
            ],

        "strong_context":
            classification.get(
                "strong_context",
                []
            ),

        "positive_context":
            classification.get(
                "positive_context",
                []
            ),

        "handling_context":
            classification.get(
                "handling_context",
                []
            ),

        "detected_time":
            datetime.datetime.now().isoformat(),

        "source":
            "Google News RSS"

    }

# ============================================================
# REKLASIFIKASI SELURUH DATABASE
# ============================================================

def rekategorisasi_semua_database():
    """
    Membaca SELURUH artikel yang ada di Supabase,
    kemudian menjalankan classifier terbaru terhadap
    setiap artikel.

    Artikel tidak dihapus.
    Hanya field klasifikasi yang diperbarui.
    """

    print()
    print("==========================================")
    print("REKLASIFIKASI SELURUH DATABASE")
    print("==========================================")

    try:
        articles = get_all_articles()
    except Exception as e:
        print(f"[RECLASSIFY ERROR] Gagal membaca database: {e}")
        return {
            "total": 0,
            "updated": 0,
            "failed": 0,
            "counts": {
                "Negatif Kuat": 0,
                "Perlu Penanganan": 0,
                "Netral": 0,
                "Positif": 0
            }
        }

    total = len(articles)

    print(f"Total artikel di Supabase: {total}")

    counter = {
        "Negatif Kuat": 0,
        "Perlu Penanganan": 0,
        "Netral": 0,
        "Positif": 0
    }

    updated = 0
    failed = 0

    for index, article in enumerate(articles, start=1):

        title = article.get("title", "") or ""
        snippet = article.get("snippet", "") or ""
        content = article.get("content", "") or ""

        try:

            classification = classify_article(
                title,
                snippet,
                content
            )

            updates = {
                "category": classification.get(
                    "category",
                    "Netral"
                ),

                "priority": classification.get(
                    "priority",
                    "RENDAH"
                ),

                "negative_score": int(
                    classification.get(
                        "negative_score",
                        0
                    )
                ),

                "handling_score": int(
                    classification.get(
                        "handling_score",
                        0
                    )
                ),

                "positive_score": int(
                    classification.get(
                        "positive_score",
                        0
                    )
                ),

                "detected_keywords":
                    classification.get(
                        "detected_keywords",
                        []
                    ),

                "satker_matches":
                    classification.get(
                        "satker_matches",
                        []
                    ),

                "strong_context":
                    classification.get(
                        "strong_context",
                        []
                    ),

                "positive_context":
                    classification.get(
                        "positive_context",
                        []
                    ),

                "handling_context":
                    classification.get(
                        "handling_context",
                        []
                    )
            }

            link = article.get("link", "")

            if not link:
                print(
                    f"[SKIP] Artikel #{index} "
                    f"tidak memiliki link."
                )
                failed += 1
                continue

            update_article(
                link,
                updates
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

        # Progress setiap 25 artikel
        if (
            index % 25 == 0
            or index == total
        ):

            print(
                f"[RECLASSIFY] "
                f"{index}/{total} "
                f" | Updated: {updated} "
                f"| Failed: {failed}"
            )

    print()
    print("==========================================")
    print("REKLASIFIKASI SELESAI")
    print("==========================================")

    print(
        f"Total database : {total}"
    )

    print(
        f"Berhasil       : {updated}"
    )

    print(
        f"Gagal          : {failed}"
    )

    print(
        f"Negatif Kuat   : "
        f"{counter['Negatif Kuat']}"
    )

    print(
        f"Perlu Penanganan: "
        f"{counter['Perlu Penanganan']}"
    )

    print(
        f"Netral         : "
        f"{counter['Netral']}"
    )

    print(
        f"Positif        : "
        f"{counter['Positif']}"
    )

    print("==========================================")
    print()

    return {
        "total": total,
        "updated": updated,
        "failed": failed,
        "counts": counter
    } 
# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(
    finding
):

    if not TELEGRAM_TOKEN or not CHAT_ID:

        return False


    category = finding.get(
        "category",
        "Netral"
    )

    priority = finding.get(
        "priority",
        "RENDAH"
    )


    if category == "Negatif Kuat":

        emoji = "🔴"

    elif category == "Perlu Penanganan":

        emoji = "🟠"

    else:

        emoji = "🟡"


    keywords = finding.get(
        "detected_keywords",
        []
    )


    message = (

        f"{emoji} <b>PATROLI SIBER 2026</b>\n\n"

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
        f"<a href=\"{html.escape(finding.get('link', ''), quote=True)}\">"
        f"Buka Artikel"
        f"</a>\n\n"

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

                "chat_id":
                    CHAT_ID,

                "text":
                    message,

                "parse_mode":
                    "HTML",

                "disable_web_page_preview":
                    False

            },
            timeout=15
        )


        result = response.json()

        return bool(
            result.get("ok")
        )


    except Exception:

        return False


# ============================================================
# PATROLI
# ============================================================

# ============================================================
# PATROLI UTAMA
# ============================================================

def jalankan_patroli():

    start = time.time()

    print()
    print("==========================================")
    print("MEMULAI PATROLI SIBER 2026")
    print("==========================================")
    print(f"TARGET: {NAMA_SATKER}")
    print("==========================================")
    print()

    # ========================================================
    # 1. AMBIL KANDIDAT DARI GOOGLE NEWS
    # ========================================================

    candidates = collect_candidates()

    print(
        f"[PATROLI] Kandidat ditemukan: "
        f"{len(candidates)}"
    )

    # ========================================================
    # 2. PROSES ARTIKEL
    # ========================================================

    results = []

    with ThreadPoolExecutor(
        max_workers=MAX_WORKERS
    ) as executor:

        futures = [
            executor.submit(
                process_candidate,
                item
            )
            for item in candidates
        ]

        for future in as_completed(futures):

            try:

                result = future.result()

                if result:
                    results.append(result)

            except Exception as e:

                print(
                    f"[WORKER ERROR] {e}"
                )

    print(
        f"[PATROLI] Artikel valid: "
        f"{len(results)}"
    )

    # ========================================================
    # 3. SIMPAN / UPDATE ARTIKEL BARU
    # ========================================================

    save_success = 0
    save_failed = 0

    for article in results:

        try:

            upsert_article(article)

            save_success += 1

        except Exception as e:

            save_failed += 1

            print(
                f"[SUPABASE ERROR] {e}"
            )

    print(
        f"[SUPABASE] Berhasil disimpan/update: "
        f"{save_success}"
    )

    print(
        f"[SUPABASE] Gagal: "
        f"{save_failed}"
    )

    # ========================================================
    # 4. REKLASIFIKASI SELURUH DATABASE
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
    #
    # Telegram tetap menggunakan hasil artikel yang
    # ditemukan pada patroli ini.
    #
    # Tujuannya agar artikel lama tidak mengirim
    # notifikasi Telegram berulang-ulang setiap patroli.
    # ========================================================

    telegram_count = 0

    for article in results:

        category = article.get(
            "category",
            "Netral"
        )

        if category not in [
            "Negatif Kuat",
            "Perlu Penanganan"
        ]:

            continue

        priority = article.get(
            "priority",
            "RENDAH"
        )

        if priority not in [
            "KRITIS",
            "TINGGI"
        ]:

            continue

        try:

            if send_telegram(article):

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

    counts = (
        reclass_result.get(
            "counts",
            {
                "Negatif Kuat": 0,
                "Perlu Penanganan": 0,
                "Netral": 0,
                "Positif": 0
            }
        )
    )

    # ========================================================
    # 7. LOG
    # ========================================================

    log_data = {

        "duration_seconds":
            round(elapsed, 2),

        "candidate_count":
            len(candidates),

        "valid_count":
            len(results),

        "saved_count":
            save_success,

        "save_failed":
            save_failed,

        "database_total":
            reclass_result.get(
                "total",
                0
            ),

        "reclassified_count":
            reclass_result.get(
                "updated",
                0
            ),

        "reclassify_failed":
            reclass_result.get(
                "failed",
                0
            ),

        "negative_count":
            counts.get(
                "Negatif Kuat",
                0
            ),

        "handling_count":
            counts.get(
                "Perlu Penanganan",
                0
            ),

        "neutral_count":
            counts.get(
                "Netral",
                0
            ),

        "positive_count":
            counts.get(
                "Positif",
                0
            ),

        "telegram_count":
            telegram_count,

        "status":
            "SELESAI"

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
    # 8. OUTPUT AKHIR
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
        f"Database             : "
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
        f"Negatif Kuat       : "
        f"{counts.get('Negatif Kuat', 0)}"
    )

    print(
        f"Perlu Penanganan   : "
        f"{counts.get('Perlu Penanganan', 0)}"
    )

    print(
        f"Netral             : "
        f"{counts.get('Netral', 0)}"
    )

    print(
        f"Positif            : "
        f"{counts.get('Positif', 0)}"
    )

    print(
        f"Telegram terkirim  : "
        f"{telegram_count}"
    )

    print("==========================================")
    print()

    return log_data

# ============================================================
# REKLASIFIKASI DATABASE LAMA
# ============================================================

def rekategorisasi_semua_database():

    print(
        "=========================================="
    )

    print(
        "REKLASIFIKASI DATABASE SUPABASE"
    )

    print(
        "=========================================="
    )


    articles = get_all_articles()


    print(
        f"Total artikel: {len(articles)}"
    )


    counter = {

        "Negatif Kuat": 0,
        "Perlu Penanganan": 0,
        "Netral": 0,
        "Positif": 0

    }


    for index, article in enumerate(
        articles,
        start=1
    ):


        title = article.get(
            "title",
            ""
        )

        snippet = article.get(
            "snippet",
            ""
        )

        content = article.get(
            "content",
            ""
        )


        classification = classify_article(
            title,
            snippet,
            content
        )


        updates = {

            "category":
                classification[
                    "category"
                ],

            "priority":
                classification[
                    "priority"
                ],

            "negative_score":
                classification[
                    "negative_score"
                ],

            "handling_score":
                classification[
                    "handling_score"
                ],

            "positive_score":
                classification[
                    "positive_score"
                ],

            "detected_keywords":
                classification[
                    "detected_keywords"
                ],

            "satker_matches":
                classification[
                    "satker_matches"
                ],

            "strong_context":
                classification.get(
                    "strong_context",
                    []
                ),

            "positive_context":
                classification.get(
                    "positive_context",
                    []
                ),

            "handling_context":
                classification.get(
                    "handling_context",
                    []
                )

        }


        try:

            from database import update_article

            update_article(
                article.get(
                    "link"
                ),
                updates
            )


            category = updates[
                "category"
            ]

            counter[
                category
            ] += 1


        except Exception as e:

            print(
                f"[ERROR] {e}"
            )


        if index % 25 == 0:

            print(
                f"Progress: "
                f"{index}/{len(articles)}"
            )


    print(
        "=========================================="
    )

    print(
        "REKLASIFIKASI SELESAI"
    )

    print(
        json.dumps(
            counter,
            indent=2,
            ensure_ascii=False
        )
    )

    print(
        "=========================================="
    )


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":

    if (
        len(sys.argv) > 1
        and sys.argv[1].lower()
        in [
            "--reclassify",
            "--rekategorisasi"
        ]
    ):

        rekategorisasi_semua_database()

    else:

        jalankan_patroli()
