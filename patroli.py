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
#
# ATURAN PENTING:
#
# SATKER HARUS ADA:
# 1. DI JUDUL
# ATAU
# 2. DI 1-3 PARAGRAF PERTAMA
#
# Kemunculan SATKER di bagian lain halaman TIDAK CUKUP.
# ============================================================

TARGET_KEJARI_KEYWORDS = [

    # Kejari Deli Serdang
    "kejaksaan negeri deli serdang",
    "kejari deli serdang",
    "kajari deli serdang",
    "kejari deliserdang",
    "kejaksaan deliserdang",
    "kejaksaan deli serdang",

    # Cabjari Pancur Batu
    "cabang kejaksaan negeri pancur batu",
    "cabjari pancur batu",
    "kacabjari pancur batu",

    # Cabjari Labuhan Deli
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
    "copot kajari": 16,
    "kajari dicopot": 18,

    "kejagung copot kajari": 20,
    "kajari dicopot kejagung": 20,

    "pelanggaran etik": 16,
    "pelanggaran etika": 15,
    "pelanggaran kode etik": 18,
    "melanggar etik": 15,

    "didesak mundur": 17,
    "didesak dicopot": 18,
    "kejari didesak": 16,

    "maladministrasi": 15,
    "arogan": 11,

    "pemerasan": 14,
    "dugaan pemerasan": 17,

    "suap": 13,
    "dugaan suap": 16,

    "gratifikasi": 13,
    "dugaan gratifikasi": 16,

    "pungli": 13,
    "dugaan pungli": 16,

    "mafia hukum": 18,

    "kolusi": 14,
    "nepotisme": 13,

    "penyalahgunaan wewenang": 17,
    "penyelewengan": 15,

    "cacat hukum": 13,

    "tidak transparan": 12,
    "tidak profesional": 12,

    "batal dilantik": 11,
    "gagal dilantik": 11,
    "pelantikan ditunda": 11,

    "pelantikan mendadak ditunda": 14,

    "bongkar dugaan skandal": 18,

    "kabur": 7,
    "melarikan diri": 9,
}


# ============================================================
# NEGATIF KONTEKS
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

    "kejari didesak",

    "dugaan pemerasan",
    "dugaan suap",
    "dugaan gratifikasi",
    "dugaan pungli",

    "mafia hukum",
    "penyalahgunaan wewenang",
    "maladministrasi",

    "tidak transparan",
    "tidak profesional",

    "penyelewengan wewenang",

    "protes terhadap kejari",
    "demo terhadap kejari",
    "demonstrasi terhadap kejari",
]


# ============================================================
# NEGATIF LUNAK
# ============================================================

SOFT_NEGATIVE_CONTEXT = [

    "menuai sorotan",
    "disorot",
    "menuai kritik",
    "kritik keras",
    "diprotes",
    "protes",
    "demonstrasi",
    "demo",
    "dipertanyakan",
    "kejanggalan",
    "janggal",
]


# ============================================================
# PERLU PENANGANAN
# ============================================================

HANDLING_RULES = {

    "korupsi": 7,
    "dugaan korupsi": 9,
    "kasus korupsi": 8,

    "penyelidikan": 5,
    "penyidikan": 5,

    "diperiksa": 7,
    "diperiksa kejagung": 11,
    "diperiksa kejaksaan agung": 11,

    "dipanggil": 6,
    "dipanggil kejagung": 10,
    "dipanggil ke kejagung": 10,

    "dilaporkan": 7,
    "laporan masyarakat": 7,
    "pengaduan": 6,
    "pengaduan masyarakat": 7,

    "tersangka": 7,
    "terlapor": 7,

    "tuntutan": 5,
    "dituntut": 5,

    "narkotika": 6,
    "kasus narkotika": 8,

    "narapidana kabur": 10,
    "terpidana kabur": 10,

    "guru honorer": 5,
    "dibebaskan": 5,

    "keluhan pelayanan": 8,
    "pelayanan buruk": 10,

    "masalah": 3,
    "bermasalah": 6,

    "dugaan": 4,
    "indikasi": 4,
    "terindikasi": 5,

    "kasus": 3,

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

    "berhasil mengungkap": 10,
    "berhasil menangkap": 10,
    "berhasil mengamankan": 9,
    "berhasil mengusut": 9,
    "berhasil menyita": 9,
    "berhasil menindak": 9,

    "mengungkap kasus": 8,
    "mengungkap perkara": 8,
    "mengungkap korupsi": 9,
    "mengungkap kasus korupsi": 10,
    "mengungkap kasus narkotika": 10,

    "menangkap tersangka": 8,
    "menangkap pelaku": 9,
    "mengamankan tersangka": 8,
    "mengamankan pelaku": 8,

    "menyita barang bukti": 8,
    "mengamankan barang bukti": 8,
    "berhasil mengamankan barang bukti": 10,

    "menetapkan tersangka": 6,
    "menindak pelaku": 7,

    "mengusut dugaan korupsi": 8,
    "usut dugaan korupsi": 8,
    "mengusut kasus korupsi": 8,

    "menangani kasus korupsi": 7,
    "menangani dugaan korupsi": 7,

    "melakukan penyelidikan": 6,
    "melakukan penyidikan": 6,

    "penyelidikan dugaan korupsi": 7,
    "penyidikan kasus korupsi": 7,

    "menuntut terdakwa": 7,
    "mengajukan tuntutan": 7,

    "penghargaan": 9,
    "prestasi": 9,
    "capaian kinerja": 9,
    "kinerja terbaik": 8,
    "peringkat terbaik": 8,
    "juara": 8,
    "terbaik": 7,

    "pelayanan prima": 9,
    "pelayanan publik": 7,
    "pelayanan terbaik": 9,
    "peningkatan pelayanan": 8,
    "peningkatan kualitas pelayanan": 8,
    "inovasi pelayanan": 9,

    "penyuluhan hukum": 8,
    "sosialisasi hukum": 8,
    "penerangan hukum": 8,
    "jaksa masuk sekolah": 9,
    "jaksa menyapa": 7,
    "program jaksa masuk sekolah": 9,

    "upacara": 5,
    "apel": 5,
    "apel pagi": 6,

    "kunjungan kerja": 7,
    "kunjungan": 5,

    "silaturahmi": 6,

    "rapat koordinasi": 7,
    "rapat": 4,
    "koordinasi": 6,
    "konsolidasi": 7,

    "fgd": 8,
    "focus group discussion": 8,

    "forum diskusi": 7,
    "diskusi": 4,

    "penandatanganan mou": 8,
    "penandatanganan": 6,
    "kerja sama": 8,
    "kerjasama": 8,

    "peresmian": 8,
    "peresmian gedung": 8,

    "pelantikan": 6,
    "pengambilan sumpah": 7,

    "bimbingan teknis": 7,
    "bimtek": 7,

    "pendampingan": 6,
    "monitoring": 5,
    "evaluasi": 5,

    "pemusnahan barang bukti": 8,
    "penyerahan barang bukti": 8,
    "penyerahan barang rampasan": 8,

    "program unggulan": 8,
    "program kerja": 5,
    "inovasi": 7,
    "transformasi": 6,
    "digitalisasi pelayanan": 8,
    "peningkatan kinerja": 8,

    "rapat pimpinan": 6,
    "rapat internal": 6,
    "briefing": 5,
    "evaluasi kinerja": 7,
    "monitoring dan evaluasi": 7,
    "monev": 6,

    "serah terima jabatan": 7,
    "sertijab": 7,

    "kunjungan kejaksaan": 6,
    "kunjungan kajari": 7,

    "bakti sosial": 8,
    "bantuan sosial": 8,
    "donor darah": 7,
    "kegiatan sosial": 7,
    "gotong royong": 6,

    "peringatan hari": 5,
    "hari bhakti": 7,
}


# ============================================================
# KONTEKS KEGIATAN RESMI
# ============================================================

OFFICIAL_ACTIVITY_CONTEXT = [

    "upacara",
    "apel",
    "apel pagi",
    "kunjungan kerja",
    "kunjungan",
    "silaturahmi",
    "rapat koordinasi",
    "rapat pimpinan",
    "rapat internal",
    "koordinasi",
    "konsolidasi",
    "fgd",
    "focus group discussion",
    "forum diskusi",
    "penandatanganan mou",
    "penandatanganan kerja sama",
    "kerja sama",
    "kerjasama",
    "peresmian",
    "pelantikan",
    "pengambilan sumpah",
    "bimbingan teknis",
    "bimtek",
    "pendampingan",
    "monitoring",
    "evaluasi kinerja",
    "monitoring dan evaluasi",
    "monev",
    "serah terima jabatan",
    "sertijab",
    "penyuluhan hukum",
    "sosialisasi hukum",
    "penerangan hukum",
    "jaksa masuk sekolah",
    "jaksa menyapa",
    "pelayanan publik",
    "pelayanan prima",
    "penghargaan",
    "prestasi",
    "capaian kinerja",
    "program unggulan",
    "inovasi pelayanan",
    "peningkatan pelayanan",
    "peningkatan kinerja",
    "bakti sosial",
    "bantuan sosial",
    "donor darah",
    "kegiatan sosial",
]


# ============================================================
# KONTEKS KEBERHASILAN
# ============================================================

SUCCESS_LAW_ENFORCEMENT_CONTEXT = [

    "berhasil mengungkap",
    "berhasil menangkap",
    "berhasil mengamankan",
    "berhasil mengusut",
    "berhasil menyita",
    "berhasil menindak",

    "mengungkap kasus",
    "mengungkap perkara",
    "mengungkap korupsi",
    "mengungkap kasus korupsi",
    "mengungkap kasus narkotika",

    "menangkap tersangka",
    "menangkap pelaku",

    "mengamankan tersangka",
    "mengamankan pelaku",

    "menyita barang bukti",
    "mengamankan barang bukti",
    "berhasil mengamankan barang bukti",

    "menetapkan tersangka",
    "menindak pelaku",

    "menuntut terdakwa",
    "mengajukan tuntutan",

    "pemusnahan barang bukti",
    "penyerahan barang bukti",
    "penyerahan barang rampasan",
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

    "dugaan pelanggaran",
    "dugaan penyalahgunaan",
    "dugaan penyelewengan",

    "perkara hukum",
    "sengketa hukum",
    "konflik hukum",
]


# ============================================================
# DANGER TITLE
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


# ============================================================
# LEGAL RISK
# ============================================================

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

    if not text:
        return ""

    text = html.unescape(str(text))
    text = text.lower()

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


# ============================================================
# NORMALISASI SATKER
# ============================================================

def normalize_satker_text(text):

    text = normalize_text(text)

    # Hilangkan variasi tanda baca
    text = re.sub(
        r"[^a-z0-9\s]",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


# ============================================================
# PARSE TANGGAL INDONESIA
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


# ============================================================
# PARSE DATE SAFE
# ============================================================

def parse_date_safe(value):

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

                    objects.extend(
                        graph
                    )

            elif isinstance(data, list):

                objects = data

            for obj in objects:

                if not isinstance(
                    obj,
                    dict,
                ):
                    continue

                for key in [
                    "datePublished",
                    "dateCreated",
                    "dateModified",
                ]:

                    value = obj.get(key)

                    if value:

                        candidates.append(
                            value
                        )

        except Exception:

            continue

    # META
    selectors = [

        {
            "property":
                "article:published_time"
        },

        {
            "property":
                "og:article:published_time"
        },

        {
            "name":
                "article:published_time"
        },

        {
            "name":
                "publishdate"
        },

        {
            "name":
                "pubdate"
        },

        {
            "name":
                "datePublished"
        },

        {
            "itemprop":
                "datePublished"
        },
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

                candidates.append(
                    value
                )

    # TIME
    for tag in soup.find_all("time"):

        value = (
            tag.get("datetime")
            or tag.get_text(
                " ",
                strip=True,
            )
        )

        if value:

            candidates.append(
                value
            )

    for value in candidates:

        dt = parse_date_safe(
            value
        )

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

            dt = parse_date_safe(
                value
            )

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

    if date_value > (
        now + datetime.timedelta(days=1)
    ):

        return False, date_value

    return True, date_value


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
# FETCH WEBPAGE
# ============================================================

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


# ============================================================
# RESOLVE GOOGLE NEWS REDIRECT
# ============================================================

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
# EXTRACT ARTICLE TEXT
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
# EXTRACT PARAGRAPHS
#
# HANYA mengambil paragraf yang benar-benar berasal dari
# area artikel.
# ============================================================

def extract_article_paragraphs(soup):

    copy_soup = BeautifulSoup(
        str(soup),
        "html.parser",
    )

    # Buang elemen yang bukan isi artikel
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

    if not article:

        return []

    paragraphs = []

    for p in article.find_all("p"):

        text = p.get_text(
            " ",
            strip=True,
        )

        text = re.sub(
            r"\s+",
            " ",
            text,
        ).strip()

        # Buang paragraf terlalu pendek
        if len(text) < 30:
            continue

        # Hindari paragraf navigasi
        bad_patterns = [
            "baca juga",
            "simak juga",
            "ikuti kami",
            "subscribe",
            "newsletter",
            "advertisement",
            "iklan",
        ]

        normalized = normalize_text(
            text
        )

        if any(
            x in normalized
            for x in bad_patterns
        ):

            continue

        paragraphs.append(
            text
        )

    return paragraphs


# ============================================================
# FIRST 3 PARAGRAPHS
# ============================================================

def extract_first_paragraphs(soup):

    paragraphs = extract_article_paragraphs(
        soup
    )

    first_three = paragraphs[:3]

    return first_three


# ============================================================
# SATKER MATCHING KETAT
#
# SATKER HANYA VALID JIKA ADA DI:
#
# 1. JUDUL
# ATAU
# 2. FIRST 3 PARAGRAPHS
#
# BUKAN seluruh halaman.
# ============================================================

def find_satker_matches_strict(
    title,
    first_paragraphs,
):

    title_n = normalize_satker_text(
        title
    )

    first_text = normalize_satker_text(
        " ".join(first_paragraphs)
    )

    title_matches = []
    first_paragraph_matches = []

    for keyword in TARGET_KEJARI_KEYWORDS:

        keyword_n = normalize_satker_text(
            keyword
        )

        if not keyword_n:
            continue

        if keyword_n in title_n:

            title_matches.append(
                keyword
            )

        if keyword_n in first_text:

            first_paragraph_matches.append(
                keyword
            )

    title_matches = list(
        dict.fromkeys(
            title_matches
        )
    )

    first_paragraph_matches = list(
        dict.fromkeys(
            first_paragraph_matches
        )
    )

    all_matches = list(
        dict.fromkeys(
            title_matches
            + first_paragraph_matches
        )
    )

    if title_matches:

        location = "title"

    elif first_paragraph_matches:

        location = "first_paragraphs"

    else:

        location = None

    return {

        "matched":
            bool(all_matches),

        "matches":
            all_matches,

        "title_matches":
            title_matches,

        "first_paragraph_matches":
            first_paragraph_matches,

        "location":
            location,
    }


# ============================================================
# SCORE ENGINE
# ============================================================

def calculate_rule_score(
    text,
    rules,
):

    score = 0
    detected = []

    text = normalize_text(
        text
    )

    for keyword, weight in rules.items():

        if keyword in text:

            score += weight

            detected.append(
                keyword
            )

    return score, detected


# ============================================================
# CONTEXT MATCH
# ============================================================

def find_context_matches(
    text,
    context_list,
):

    text = normalize_text(
        text
    )

    return [

        phrase

        for phrase in context_list

        if phrase in text

    ]


# ============================================================
# NEGATION CHECK
# ============================================================

def has_negation_near(
    text,
    keyword,
    window=60,
):

    text = normalize_text(
        text
    )

    start = text.find(
        keyword
    )

    while start != -1:

        before = text[
            max(
                0,
                start - window,
            ):
            start
        ]

        negations = [

            "tidak",
            "bukan",
            "tanpa",
            "belum terbukti",
            "tidak terbukti",
            "tidak ditemukan",
            "menepis",
            "membantah",
            "bantah",

        ]

        if any(
            neg in before
            for neg in negations
        ):

            return True

        start = text.find(
            keyword,
            start + 1,
        )

    return False


# ============================================================
# FILTER NEGATIVE
# ============================================================

def filter_negative_keywords(
    text,
    keywords,
):

    valid = []

    for keyword in keywords:

        if not has_negation_near(
            text,
            keyword,
        ):

            valid.append(
                keyword
            )

    return valid


# ============================================================
# CLASSIFIER FINAL
#
# RULE UTAMA:
# SATKER WAJIB DI JUDUL ATAU FIRST 3 PARAGRAPHS.
# ============================================================

def classify_article(
    title,
    snippet,
    content,
    first_paragraphs=None,
):

    title_n = normalize_text(
        title
    )

    snippet_n = normalize_text(
        snippet
    )

    content_n = normalize_text(
        content
    )

    if first_paragraphs is None:

        first_paragraphs = []

    if not isinstance(
        first_paragraphs,
        list,
    ):

        first_paragraphs = [
            str(first_paragraphs)
        ]

    first_paragraphs = [
        str(x).strip()
        for x in first_paragraphs
        if str(x).strip()
    ][:3]

    first_text = normalize_text(
        " ".join(first_paragraphs)
    )

    # --------------------------------------------------------
    # VALIDASI SATKER KETAT
    # --------------------------------------------------------

    satker_result = (
        find_satker_matches_strict(
            title,
            first_paragraphs,
        )
    )

    satker_matches = (
        satker_result["matches"]
    )

    satker_location = (
        satker_result["location"]
    )

    # --------------------------------------------------------
    # JIKA SATKER TIDAK ADA DI JUDUL / 3 PARAGRAF PERTAMA
    #
    # LANGSUNG NETRAL DAN DITOLAK.
    # --------------------------------------------------------

    if not satker_result["matched"]:

        return {

            "category": "Netral",
            "priority": "RENDAH",

            "negative_score": 0,
            "handling_score": 0,
            "positive_score": 0,

            "detected_keywords": [],

            "satker_matches": [],

            "satker_match_location":
                None,

            "satker_title_matches": [],

            "satker_first_paragraph_matches":
                [],

            "strong_context": [],

            "positive_context": [],

            "handling_context": [],

        }

    # --------------------------------------------------------
    # FULL TEXT
    #
    # Digunakan untuk klasifikasi setelah artikel terbukti
    # relevan dengan SATKER.
    # --------------------------------------------------------

    full_text = (
        f"{title_n} "
        f"{snippet_n} "
        f"{first_text} "
        f"{content_n}"
    )

    # --------------------------------------------------------
    # SCORE
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
    # TITLE SCORE
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
    # FIRST 3 PARAGRAPHS SCORE
    # --------------------------------------------------------

    first_strong_score, first_strong_keywords = (
        calculate_rule_score(
            first_text,
            NEGATIVE_STRONG_RULES,
        )
    )

    first_handling_score, first_handling_keywords = (
        calculate_rule_score(
            first_text,
            HANDLING_RULES,
        )
    )

    first_positive_score, first_positive_keywords = (
        calculate_rule_score(
            first_text,
            POSITIVE_RULES,
        )
    )

    # --------------------------------------------------------
    # CONTEXT
    # --------------------------------------------------------

    strong_context_matches = (
        find_context_matches(
            full_text,
            STRONG_NEGATIVE_CONTEXT,
        )
    )

    soft_negative_matches = (
        find_context_matches(
            full_text,
            SOFT_NEGATIVE_CONTEXT,
        )
    )

    official_activity_matches = (
        find_context_matches(
            full_text,
            OFFICIAL_ACTIVITY_CONTEXT,
        )
    )

    positive_action_matches = (
        find_context_matches(
            full_text,
            SUCCESS_LAW_ENFORCEMENT_CONTEXT,
        )
    )

    handling_context_matches = (
        find_context_matches(
            full_text,
            HANDLING_CONTEXT,
        )
    )

    # --------------------------------------------------------
    # NEGATION FILTER
    # --------------------------------------------------------

    strong_keywords = (
        filter_negative_keywords(
            full_text,
            strong_keywords,
        )
    )

    strong_context_matches = [

        x

        for x in strong_context_matches

        if not has_negation_near(
            full_text,
            x,
        )

    ]

    # --------------------------------------------------------
    # SCORE BOOST
    # --------------------------------------------------------

    strong_score += (
        title_strong_score * 2
    )

    handling_score += (
        title_handling_score * 2
    )

    positive_score += (
        title_positive_score * 2
    )

    # First paragraph boost
    strong_score += (
        first_strong_score
    )

    handling_score += (
        first_handling_score
    )

    positive_score += (
        first_positive_score
    )

    # Context boost
    strong_score += (
        len(
            strong_context_matches
        ) * 10
    )

    handling_score += (
        len(
            handling_context_matches
        ) * 3
    )

    positive_score += (
        len(
            positive_action_matches
        ) * 5
    )

    positive_score += (
        len(
            official_activity_matches
        ) * 3
    )

    # --------------------------------------------------------
    # TITLE DANGER
    # --------------------------------------------------------

    danger_hits = [

        term

        for term in DANGER_TITLE_TERMS

        if term in title_n

        and not has_negation_near(
            title_n,
            term,
        )

    ]

    # --------------------------------------------------------
    # LEGAL RISK
    # --------------------------------------------------------

    legal_hits = [

        term

        for term in LEGAL_RISK_TERMS

        if term in full_text

        and not has_negation_near(
            full_text,
            term,
        )

    ]

    # --------------------------------------------------------
    # RISK INDICATOR
    # --------------------------------------------------------

    risk_indicators = (

        len(strong_keywords)

        + len(handling_keywords)

        + len(strong_context_matches)

        + len(handling_context_matches)

    )

    # ========================================================
    # DEFAULT
    # ========================================================

    category = "Netral"
    priority = "RENDAH"

    # ========================================================
    # NEGATIF KUAT
    # ========================================================

    hard_negative = False

    if strong_context_matches:

        hard_negative = True

    elif danger_hits:

        hard_negative = True

    elif title_strong_score >= 8:

        hard_negative = True

    elif strong_score >= 22:

        hard_negative = True

    if hard_negative:

        category = "Negatif Kuat"
        priority = "KRITIS"

    # ========================================================
    # POSITIF
    # ========================================================

    positive_success = (
        len(
            positive_action_matches
        ) > 0
    )

    positive_official = (

        len(
            official_activity_matches
        ) > 0

        and (

            title_positive_score >= 3

            or positive_score >= 5

        )

    )

    # --------------------------------------------------------
    # Keberhasilan penegakan hukum
    # --------------------------------------------------------

    if positive_success:

        if (
            not strong_context_matches
            and not danger_hits
        ):

            category = "Positif"
            priority = "RENDAH"

    # --------------------------------------------------------
    # Kegiatan resmi
    # --------------------------------------------------------

    elif positive_official:

        if (
            not strong_context_matches
            and not danger_hits
        ):

            category = "Positif"
            priority = "RENDAH"

    # ========================================================
    # NEGATIF FINAL
    # ========================================================

    if (

        hard_negative

        and not positive_success

        and not positive_official

    ):

        category = "Negatif Kuat"
        priority = "KRITIS"

    # ========================================================
    # PERLU PENANGANAN
    # ========================================================

    if category != "Positif":

        if (

            title_handling_score >= 8

            and not hard_negative

        ):

            category = "Perlu Penanganan"
            priority = "TINGGI"

        elif (

            handling_score >= 14

            and not hard_negative

        ):

            category = "Perlu Penanganan"
            priority = "TINGGI"

        elif (

            handling_score >= 7

            and not hard_negative

        ):

            category = "Perlu Penanganan"
            priority = "SEDANG"

    # ========================================================
    # SUCCESS OVERRIDE
    # ========================================================

    if (

        positive_success

        and not strong_context_matches

        and not danger_hits

    ):

        category = "Positif"
        priority = "RENDAH"

    # ========================================================
    # OFFICIAL OVERRIDE
    # ========================================================

    if (

        positive_official

        and not strong_context_matches

        and not danger_hits

    ):

        category = "Positif"
        priority = "RENDAH"

    # ========================================================
    # SOFT NEGATIVE
    # ========================================================

    if (

        category == "Netral"

        and soft_negative_matches

        and not positive_success

        and not positive_official

    ):

        category = "Perlu Penanganan"
        priority = "SEDANG"

    # ========================================================
    # FALLBACK ANTI NETRAL
    # ========================================================

    if (

        category == "Netral"

        and risk_indicators >= 2

        and not positive_success

        and not positive_official

    ):

        category = "Perlu Penanganan"
        priority = "SEDANG"

    # ========================================================
    # ISU HUKUM
    # ========================================================

    if (

        category == "Netral"

        and len(legal_hits) >= 2

        and not positive_success

        and not positive_official

    ):

        category = "Perlu Penanganan"
        priority = "SEDANG"

    # ========================================================
    # PRIORITAS
    # ========================================================

    if category == "Perlu Penanganan":

        if (

            title_handling_score >= 10

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

            + soft_negative_matches

            + handling_context_matches

            + official_activity_matches

            + positive_action_matches

            + title_strong_keywords

            + title_handling_keywords

            + title_positive_keywords

            + first_strong_keywords

            + first_handling_keywords

            + first_positive_keywords

            + danger_hits

            + legal_hits

        )
    )

    # ========================================================
    # RETURN
    # ========================================================

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

        "satker_match_location":
            satker_location,

        "satker_title_matches":
            satker_result[
                "title_matches"
            ],

        "satker_first_paragraph_matches":
            satker_result[
                "first_paragraph_matches"
            ],

        "strong_context":
            strong_context_matches,

        "positive_context":
            list(
                dict.fromkeys(
                    official_activity_matches
                    + positive_action_matches
                )
            ),

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

                "title":
                    title,

                "link":
                    link,

                "snippet":
                    summary,

                "rss_date":
                    rss_date,

            })

        return results

    except Exception as e:

        print(
            f"[RSS ERROR] {e}"
        )

        return []


# ============================================================
# QUERY GENERATOR
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
# COLLECT CANDIDATES
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
#
# DI SINI first_paragraphs DIAMBIL DARI WEBSITE.
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
    # Resolve Google News
    # --------------------------------------------------------

    final_url = resolve_redirect_url(
        original_url
    )

    # --------------------------------------------------------
    # Fetch Website
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

    try:

        soup = BeautifulSoup(
            html_content,
            "html.parser",
        )

    except Exception:

        return None

    # --------------------------------------------------------
    # DATE
    # --------------------------------------------------------

    article_date = (
        extract_published_date(
            soup
        )
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
    # FIRST 3 PARAGRAPHS
    # --------------------------------------------------------

    first_paragraphs = (
        extract_first_paragraphs(
            soup
        )
    )

    # --------------------------------------------------------
    # CONTENT
    # --------------------------------------------------------

    content = extract_article_text(
        soup
    )

    if len(content) < 100:

        content = (
            f"{snippet} {content}"
        ).strip()

    # --------------------------------------------------------
    # VALIDASI SATKER SEBELUM CLASSIFICATION
    #
    # SATKER HARUS ADA DI TITLE ATAU FIRST 3 PARAGRAPHS.
    # --------------------------------------------------------

    satker_check = (
        find_satker_matches_strict(
            title,
            first_paragraphs,
        )
    )

    if not satker_check["matched"]:

        print(
            "[FILTER] DITOLAK - SATKER "
            "tidak ditemukan di judul / "
            "3 paragraf pertama:"
        )

        print(
            f"         {title}"
        )

        return None

    # --------------------------------------------------------
    # CLASSIFICATION
    # --------------------------------------------------------

    classification = classify_article(

        title=title,

        snippet=snippet,

        content=content,

        first_paragraphs=
            first_paragraphs,

    )

    # --------------------------------------------------------
    # DOUBLE CHECK
    # --------------------------------------------------------

    if not classification.get(
        "satker_matches"
    ):

        return None

    # --------------------------------------------------------
    # OUTPUT
    # --------------------------------------------------------

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

        "first_paragraphs":
            first_paragraphs,

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

        "satker_match_location":
            classification[
                "satker_match_location"
            ],

        "satker_title_matches":
            classification[
                "satker_title_matches"
            ],

        "satker_first_paragraph_matches":
            classification[
                "satker_first_paragraph_matches"
            ],

        "strong_context":
            classification[
                "strong_context"
            ],

        "positive_context":
            classification[
                "positive_context"
            ],

        "handling_context":
            classification[
                "handling_context"
            ],

        "detected_time":
            datetime.datetime.now().isoformat(),

        "source":
            "Google News RSS",

    }


# ============================================================
# REKATEGORISASI DATABASE
#
# ATURAN:
# Artikel yang sudah ada di database akan diperiksa ulang.
# first_paragraphs dipakai kembali.
#
# Jika first_paragraphs belum tersedia pada artikel lama,
# akan dicoba mengambil dari content.
# ============================================================

def rekategorisasi_semua_database():

    print()
    print(
        "=========================================="
    )
    print(
        "REKLASIFIKASI DATABASE SUPABASE"
    )
    print(
        "=========================================="
    )

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

    total = len(
        articles
    )

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
                article.get(
                    "title"
                )
                or ""
            )

            snippet = (
                article.get(
                    "snippet"
                )
                or ""
            )

            content = (
                article.get(
                    "content"
                )
                or ""
            )

            link = (
                article.get(
                    "link"
                )
                or ""
            )

            first_paragraphs = (
                article.get(
                    "first_paragraphs"
                )
                or []
            )

            # ------------------------------------------------
            # NORMALISASI first_paragraphs
            # ------------------------------------------------

            if isinstance(
                first_paragraphs,
                str,
            ):

                try:

                    parsed = json.loads(
                        first_paragraphs
                    )

                    if isinstance(
                        parsed,
                        list,
                    ):

                        first_paragraphs = (
                            parsed
                        )

                    else:

                        first_paragraphs = [
                            first_paragraphs
                        ]

                except Exception:

                    first_paragraphs = [
                        first_paragraphs
                    ]

            if not isinstance(
                first_paragraphs,
                list,
            ):

                first_paragraphs = []

            # ------------------------------------------------
            # Artikel lama mungkin belum punya
            # first_paragraphs.
            #
            # Untuk database lama, kita tidak boleh otomatis
            # menganggap seluruh content sebagai first 3
            # paragraf karena itu dapat menyebabkan false
            # positive.
            #
            # Jika kosong -> artikel akan menjadi Netral.
            # ------------------------------------------------

            if not first_paragraphs:

                print(
                    f"[RECLASSIFY] "
                    f"{index}/{total} "
                    f"first_paragraphs kosong -> "
                    f"validasi ketat."
                )

            if not link:

                failed += 1

                continue

            # ------------------------------------------------
            # CLASSIFY
            # ------------------------------------------------

            classification = classify_article(

                title=title,

                snippet=snippet,

                content=content,

                first_paragraphs=
                    first_paragraphs,

            )

            # ------------------------------------------------
            # UPDATE
            # ------------------------------------------------

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

                "satker_match_location":
                    classification.get(
                        "satker_match_location",
                    ),

                "satker_title_matches":
                    classification.get(
                        "satker_title_matches",
                        [],
                    ),

                "satker_first_paragraph_matches":
                    classification.get(
                        "satker_first_paragraph_matches",
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

            category = updates[
                "category"
            ]

            if category not in counter:

                category = "Netral"

            counter[
                category
            ] += 1

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

        "total":
            total,

        "updated":
            updated,

        "failed":
            failed,

        "counts":
            counter,

    }


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(finding):

    if (
        not TELEGRAM_TOKEN
        or not CHAT_ID
    ):

        print(
            "[TELEGRAM] "
            "Token/Chat ID belum dikonfigurasi."
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

    match_location = (
        finding.get(
            "satker_match_location"
        )
        or "-"
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

        f"<b>Lokasi Match SATKER:</b>\n"
        f"{html.escape(match_location)}\n\n"

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

                "chat_id":
                    CHAT_ID,

                "text":
                    message,

                "parse_mode":
                    "HTML",

                "disable_web_page_preview":
                    False,

            },

            timeout=15,

        )

        response.raise_for_status()

        result = response.json()

        if not result.get(
            "ok"
        ):

            print(
                f"[TELEGRAM ERROR] "
                f"{result}"
            )

        return bool(
            result.get(
                "ok"
            )
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
    print(
        "=========================================="
    )
    print(
        "MEMULAI PATROLI SIBER 2026"
    )
    print(
        "=========================================="
    )

    print(
        f"TARGET: {NAMA_SATKER}"
    )

    print(
        "FILTER SATKER:"
    )

    print(
        "  - Judul"
    )

    print(
        "  - 1-3 paragraf pertama"
    )

    print(
        "  - Tidak menerima match dari seluruh halaman"
    )

    print(
        "=========================================="
    )
    print()

    # --------------------------------------------------------
    # 1. GOOGLE NEWS
    # --------------------------------------------------------

    candidates = collect_candidates()

    print(
        f"[PATROLI] Kandidat ditemukan: "
        f"{len(candidates)}"
    )

    # --------------------------------------------------------
    # 2. PROCESS
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # 3. SIMPAN
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # 4. REKLASIFIKASI
    # --------------------------------------------------------

    print()

    print(
        "[PATROLI] Memulai reklasifikasi "
        "seluruh database..."
    )

    reclass_result = (
        rekategorisasi_semua_database()
    )

    # --------------------------------------------------------
    # 5. TELEGRAM
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # 6. STATISTIK
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # 7. RUN LOG
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # 8. OUTPUT
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

    print(
        "=========================================="
    )

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

        print(
            "=========================================="
        )

        print(
            "PROGRAM SELESAI NORMAL"
        )

        print(
            "=========================================="
        )

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

        print(
            "=========================================="
        )

        print(
            "FATAL ERROR"
        )

        print(
            "=========================================="
        )

        print(
            str(e)
        )

        print(
            "=========================================="
        )

        sys.exit(1)
