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
# PATROLI SIBER 2026
# ============================================================
# FUNGSI UTAMA:
#
# 1. Mencari berita tahun 2026 melalui Google News RSS.
# 2. Memastikan berita relevan dengan Kejaksaan Negeri
#    Deli Serdang / Cabjari terkait.
# 3. Mengklasifikasikan artikel.
# 4. Menyimpan / memperbarui artikel di Supabase.
# 5. Telegram HANYA dikirim untuk LINK YANG BELUM ADA
#    DI DATABASE sebelum workflow berjalan.
# 6. Setelah pencarian selesai, SELURUH DATABASE
#    tetap direklasifikasi setiap workflow.
#
# ============================================================


TAHUN_TARGET = 2026
MAX_WORKERS = 10
REQUEST_TIMEOUT = 15
FIRST_PARAGRAPH_LIMIT = 3
MIN_ARTICLE_TEXT = 100


NAMA_SATKER = (
    os.getenv("NAMA_SATKER", "Kejaksaan Negeri Deli Serdang")
    .strip()
)

TELEGRAM_TOKEN = (
    os.getenv("TELEGRAM_TOKEN") or ""
).strip()

CHAT_ID = (
    os.getenv("CHAT_ID") or ""
).strip()


# ============================================================
# SATKER
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

    "nama viral": 8,
    "mendadak viral": 10,
    "viral": 5,
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

    "batal dilantik": 18,
    "pelantikan batal": 18,
    "pelantikan dibatalkan": 22,
    "pelantikan ditunda": 18,

    "pelantikan cpns dibatalkan": 24,
    "pelantikan cpns ditunda": 22,
    "pelantikan cpns kejari dibatalkan": 26,

    "gagal dilantik": 15,
    "pelantikan mendadak ditunda": 20,

    "bongkar dugaan skandal": 18,

    "kabur": 7,
    "melarikan diri": 9,
}


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

    "pelantikan dibatalkan",
    "pelantikan cpns dibatalkan",
    "pelantikan cpns kejari dibatalkan",
    "pelantikan ditunda",
    "pelantikan cpns ditunda",

    "batal dilantik",
    "pelantikan batal",
    "gagal dilantik",
]


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
# HANDLING
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
    "rapat",

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

    "papan bunga",
    "karangan bunga",

    "batal dilantik",
    "gagal dilantik",

    "pelantikan dibatalkan",
    "pelantikan ditunda",
    "pelantikan batal",

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


CANCELLATION_CONTEXT = [

    "pelantikan dibatalkan",
    "pelantikan cpns dibatalkan",
    "pelantikan cpns kejari dibatalkan",

    "pelantikan ditunda",
    "pelantikan cpns ditunda",

    "batal dilantik",
    "pelantikan batal",
    "gagal dilantik",

    "pengangkatan dibatalkan",
    "pengangkatan ditunda",

    "sertijab dibatalkan",
    "sertijab ditunda",

    "peresmian dibatalkan",

    "kegiatan dibatalkan",
    "acara dibatalkan",
]


# ============================================================
# UTILITAS
# ============================================================

def normalize_text(text):

    if not text:
        return ""

    text = html.unescape(str(text)).lower()

    text = re.sub(r"\s+", " ", text)

    return text.strip()


# ============================================================
# NORMALISASI LINK
# ============================================================

def normalize_url(url):

    if not url:
        return ""

    url = str(url).strip()

    url = url.split("#")[0]

    return url


# ============================================================
# TANGGAL
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

    try:

        month_name = match.group(2)

        if month_name not in bulan:
            return None

        return datetime.datetime(
            int(match.group(3)),
            bulan[month_name],
            int(match.group(1))
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
                dt
                .astimezone(datetime.timezone.utc)
                .replace(tzinfo=None)
            )

        return dt

    except Exception:

        return parse_indonesian_date(
            str(value)
        )


# ============================================================
# EKSTRAK TANGGAL ARTIKEL
# ============================================================

def extract_published_date(soup):

    candidates = []

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
                    "dateCreated",
                    "dateModified"
                ]:

                    if obj.get(key):
                        candidates.append(
                            obj[key]
                        )

        except Exception:
            continue


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


def validate_date(article_date, rss_date):

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
# HTTP
# ============================================================

def get_headers():

    return {

        "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
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
            allow_redirects=True
        )

        if response.status_code == 200:

            return {

                "html": response.text,

                "final_url":
                    response.url
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
# EKSTRAK ARTIKEL
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


    return re.sub(
        r"\s+",
        " ",
        text
    ).strip()


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
        "iframe"
    ]):

        tag.decompose()


    article = copy_soup.find("article")

    if not article:
        article = copy_soup.find("main")

    if not article:
        return []


    paragraphs = []


    for p in article.find_all("p"):

        text = re.sub(
            r"\s+",
            " ",
            p.get_text(
                " ",
                strip=True
            )
        ).strip()

        if not text:
            continue

        if len(text) < 25:
            continue

        low = normalize_text(text)

        if low in [
            "baca juga",
            "simak juga",
            "advertisement",
            "iklan"
        ]:
            continue

        paragraphs.append(text)

        if len(paragraphs) >= limit:
            break


    return paragraphs


# ============================================================
# SATKER MATCHING
# ============================================================

def find_satker_matches(
    title,
    first_paragraphs
):

    title_n = normalize_text(title)

    first_text = normalize_text(
        " ".join(first_paragraphs)
    )

    title_matches = []
    first_matches = []


    for keyword in TARGET_KEJARI_KEYWORDS:

        k = normalize_text(keyword)

        if k in title_n:
            title_matches.append(keyword)

        if k in first_text:
            first_matches.append(keyword)


    title_matches = list(
        dict.fromkeys(title_matches)
    )

    first_matches = list(
        dict.fromkeys(first_matches)
    )


    locations = []

    if title_matches:
        locations.append("title")

    if first_matches:
        locations.append(
            "first_paragraphs"
        )


    return (
        title_matches,
        first_matches,
        ",".join(locations)
    )


def satker_is_relevant(
    title,
    first_paragraphs
):

    (
        title_matches,
        first_matches,
        location
    ) = find_satker_matches(
        title,
        first_paragraphs
    )

    return (
        bool(
            title_matches
            or first_matches
        ),
        title_matches,
        first_matches,
        location
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

    text = normalize_text(text)


    for keyword, weight in rules.items():

        if keyword in text:

            score += weight

            detected.append(
                keyword
            )


    return score, detected


def find_context_matches(
    text,
    context_list
):

    text = normalize_text(text)

    return [
        phrase
        for phrase in context_list
        if phrase in text
    ]


def has_negation_near(
    text,
    keyword,
    window=60
):

    text = normalize_text(text)

    start = text.find(keyword)

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


    while start != -1:

        before = text[
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


        start = text.find(
            keyword,
            start + 1
        )


    return False


def filter_negative_keywords(
    text,
    keywords
):

    return [
        k
        for k in keywords
        if not has_negation_near(
            text,
            k
        )
    ]


# ============================================================
# CLASSIFIER
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


    title_n = normalize_text(title)

    snippet_n = normalize_text(
        snippet
    )

    first_n = normalize_text(
        " ".join(first_paragraphs)
    )

    content_n = normalize_text(
        content
    )


    # --------------------------------------------------------
    # RELEVANSI SATKER
    # --------------------------------------------------------

    (
        satker_ok,
        satker_title_matches,
        satker_first_matches,
        satker_match_location
    ) = satker_is_relevant(
        title,
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

            "satker_title_matches": [],

            "satker_first_paragraph_matches": [],

            "strong_context": [],
            "positive_context": [],
            "handling_context": [],
        }


    # --------------------------------------------------------
    # FULL TEXT
    # --------------------------------------------------------

    full_text = (
        f"{title_n} "
        f"{snippet_n} "
        f"{first_n} "
        f"{content_n}"
    )


    # --------------------------------------------------------
    # SCORE DASAR
    # --------------------------------------------------------

    (
        strong_score,
        strong_keywords
    ) = calculate_rule_score(
        full_text,
        NEGATIVE_STRONG_RULES
    )


    (
        handling_score,
        handling_keywords
    ) = calculate_rule_score(
        full_text,
        HANDLING_RULES
    )


    (
        positive_score,
        positive_keywords
    ) = calculate_rule_score(
        full_text,
        POSITIVE_RULES
    )


    # --------------------------------------------------------
    # SCORE JUDUL
    # --------------------------------------------------------

    (
        title_strong_score,
        title_strong_keywords
    ) = calculate_rule_score(
        title_n,
        NEGATIVE_STRONG_RULES
    )


    (
        title_handling_score,
        title_handling_keywords
    ) = calculate_rule_score(
        title_n,
        HANDLING_RULES
    )


    (
        title_positive_score,
        title_positive_keywords
    ) = calculate_rule_score(
        title_n,
        POSITIVE_RULES
    )


    # --------------------------------------------------------
    # CONTEXT
    # --------------------------------------------------------

    strong_context_matches = (
        find_context_matches(
            full_text,
            STRONG_NEGATIVE_CONTEXT
        )
    )


    soft_negative_matches = (
        find_context_matches(
            full_text,
            SOFT_NEGATIVE_CONTEXT
        )
    )


    official_activity_matches = (
        find_context_matches(
            full_text,
            OFFICIAL_ACTIVITY_CONTEXT
        )
    )


    positive_action_matches = (
        find_context_matches(
            full_text,
            SUCCESS_LAW_ENFORCEMENT_CONTEXT
        )
    )


    handling_context_matches = (
        find_context_matches(
            full_text,
            HANDLING_CONTEXT
        )
    )


    cancellation_matches = (
        find_context_matches(
            full_text,
            CANCELLATION_CONTEXT
        )
    )


    # --------------------------------------------------------
    # NEGATION
    # --------------------------------------------------------

    strong_keywords = (
        filter_negative_keywords(
            full_text,
            strong_keywords
        )
    )


    strong_context_matches = [

        x
        for x in strong_context_matches

        if not has_negation_near(
            full_text,
            x
        )
    ]


    cancellation_matches = [

        x
        for x in cancellation_matches

        if not has_negation_near(
            full_text,
            x
        )
    ]


    # --------------------------------------------------------
    # TITLE WEIGHT
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


    # --------------------------------------------------------
    # CONTEXT WEIGHT
    # --------------------------------------------------------

    strong_score += (
        len(strong_context_matches)
        * 10
    )

    handling_score += (
        len(handling_context_matches)
        * 3
    )

    positive_score += (
        len(positive_action_matches)
        * 5
    )

    positive_score += (
        len(official_activity_matches)
        * 3
    )


    # --------------------------------------------------------
    # DANGER TITLE
    # --------------------------------------------------------

    danger_hits = [

        term

        for term in DANGER_TITLE_TERMS

        if (
            term in title_n
            and not has_negation_near(
                title_n,
                term
            )
        )
    ]


    # --------------------------------------------------------
    # LEGAL RISK
    # --------------------------------------------------------

    legal_hits = [

        term

        for term in LEGAL_RISK_TERMS

        if (
            term in full_text
            and not has_negation_near(
                full_text,
                term
            )
        )
    ]


    # --------------------------------------------------------
    # NEGATIVE OVERRIDE
    # --------------------------------------------------------

    cancellation_negative = bool(
        cancellation_matches
    )


    hard_negative = bool(

        strong_context_matches

        or danger_hits

        or title_strong_score >= 8

        or strong_score >= 22

        or cancellation_negative
    )


    title_negative_explicit = bool(

        title_strong_keywords

        or danger_hits

        or any(
            x in title_n
            for x in cancellation_matches
        )
    )


    # --------------------------------------------------------
    # POSITIF
    # --------------------------------------------------------

    positive_success = bool(
        positive_action_matches
    )


    positive_official = bool(

        official_activity_matches

        and (
            title_positive_score >= 3
            or positive_score >= 5
        )
    )


    category = "Netral"
    priority = "RENDAH"


    # --------------------------------------------------------
    # KLASIFIKASI
    # --------------------------------------------------------

    if (
        hard_negative
        or title_negative_explicit
    ):

        category = "Negatif Kuat"
        priority = "KRITIS"


    elif (
        positive_success
        or positive_official
    ):

        category = "Positif"
        priority = "RENDAH"


    elif title_handling_score >= 8:

        category = "Perlu Penanganan"
        priority = "TINGGI"


    elif handling_score >= 14:

        category = "Perlu Penanganan"
        priority = "TINGGI"


    elif handling_score >= 7:

        category = "Perlu Penanganan"
        priority = "SEDANG"


    elif soft_negative_matches:

        category = "Perlu Penanganan"
        priority = "SEDANG"


    elif len(legal_hits) >= 2:

        category = "Perlu Penanganan"
        priority = "SEDANG"


    # --------------------------------------------------------
    # FINAL SAFETY
    # --------------------------------------------------------

    if (
        hard_negative
        or title_negative_explicit
    ):

        category = "Negatif Kuat"
        priority = "KRITIS"


    if category == "Perlu Penanganan":

        if (
            title_handling_score >= 10
            or danger_hits
        ):

            priority = "TINGGI"

        elif handling_score >= 15:

            priority = "TINGGI"


    # --------------------------------------------------------
    # DETECTED KEYWORDS
    # --------------------------------------------------------

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
            + cancellation_matches

            + title_strong_keywords
            + title_handling_keywords
            + title_positive_keywords

            + danger_hits
            + legal_hits
        )
    )


    return {

        "category": category,

        "priority": priority,

        "negative_score":
            int(strong_score),

        "handling_score":
            int(handling_score),

        "positive_score":
            int(positive_score),

        "detected_keywords":
            detected[:50],

        "satker_matches":
            list(
                dict.fromkeys(
                    satker_title_matches
                    + satker_first_matches
                )
            ),

        "satker_match_location":
            satker_match_location,

        "satker_title_matches":
            satker_title_matches,

        "satker_first_paragraph_matches":
            satker_first_matches,

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


            summary = (
                BeautifulSoup(
                    summary,
                    "html.parser"
                )
                .get_text(
                    " ",
                    strip=True
                )
            )


            rss_date = get_rss_date(
                entry
            )


            if link:

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


def generate_queries():

    return list(
        dict.fromkeys(

            f"{target} "
            f"after:2025-12-31 "
            f"before:2027-01-01"

            for target in SEARCH_TARGETS
        )
    )


def collect_candidates():

    all_candidates = []


    for query in generate_queries():

        print(
            f"[SEARCH] {query}"
        )

        all_candidates.extend(
            search_google_news(
                query
            )
        )


    unique = {}


    for item in all_candidates:

        link = normalize_url(
            item.get("link") or ""
        )

        if (
            link
            and link not in unique
        ):

            item["link"] = link

            unique[link] = item


    return list(
        unique.values()
    )


# ============================================================
# PROCESS CANDIDATE
# ============================================================

def process_candidate(item):

    original_url = normalize_url(
        item.get("link", "")
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
    # REDIRECT GOOGLE NEWS
    # --------------------------------------------------------

    final_url = (
        resolve_redirect_url(
            original_url
        )
    )


    result = fetch_webpage(
        final_url
    )


    if not result:
        return None


    html_content = result.get(
        "html",
        ""
    )

    real_url = normalize_url(
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

    article_date = (
        extract_published_date(
            soup
        )
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
    # FIRST 3 PARAGRAPHS
    # --------------------------------------------------------

    first_paragraphs = (
        extract_first_paragraphs(
            soup,
            FIRST_PARAGRAPH_LIMIT
        )
    )


    # --------------------------------------------------------
    # SATKER FILTER
    # --------------------------------------------------------

    (
        satker_ok,
        title_matches,
        first_matches,
        match_location
    ) = satker_is_relevant(
        title,
        first_paragraphs
    )


    if not satker_ok:

        print(
            f"[FILTER SATKER] "
            f"Ditolak: {title[:100]}"
        )

        return None


    # --------------------------------------------------------
    # CONTENT
    # --------------------------------------------------------

    content = extract_article_text(
        soup
    )


    if len(content) < MIN_ARTICLE_TEXT:

        content = (
            f"{snippet} {content}"
        ).strip()


    # --------------------------------------------------------
    # CLASSIFY
    # --------------------------------------------------------

    classification = classify_article(

        title,
        snippet,
        content,
        first_paragraphs
    )


    # --------------------------------------------------------
    # GUARD
    # --------------------------------------------------------

    if not classification.get(
        "satker_matches"
    ):

        return None


    # --------------------------------------------------------
    # RETURN ARTICLE
    # --------------------------------------------------------

    return {

        "title": title,

        "link": real_url,

        "google_news_url":
            original_url,

        "snippet": snippet,

        "content":
            content[:10000],

        "first_paragraphs":
            first_paragraphs,

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
# REKLASIFIKASI SELURUH DATABASE
# ============================================================

def rekategorisasi_semua_database():

    print()
    print("==========================================")
    print("REKLASIFIKASI SELURUH DATABASE")
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
            f"Gagal mengambil database: {e}"
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
        start=1
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

            link = normalize_url(
                article.get("link")
                or ""
            )


            # ------------------------------------------------
            # FIRST PARAGRAPHS
            # ------------------------------------------------

            first_paragraphs = (
                article.get(
                    "first_paragraphs"
                )
                or []
            )


            if isinstance(
                first_paragraphs,
                str
            ):

                try:

                    parsed = json.loads(
                        first_paragraphs
                    )

                    first_paragraphs = (
                        parsed
                        if isinstance(
                            parsed,
                            list
                        )
                        else []
                    )

                except Exception:

                    first_paragraphs = [

                        first_paragraphs

                    ] if first_paragraphs else []


            if not isinstance(
                first_paragraphs,
                list
            ):

                first_paragraphs = []


            # ------------------------------------------------
            # ARTIKEL LAMA
            # SCRAPE ULANG PARAGRAF AWAL
            # ------------------------------------------------

            if (
                not first_paragraphs
                and link
            ):

                try:

                    fetched = (
                        fetch_webpage(
                            link
                        )
                    )


                    if fetched:

                        soup = BeautifulSoup(

                            fetched.get(
                                "html",
                                ""
                            ),

                            "html.parser"
                        )


                        first_paragraphs = (
                            extract_first_paragraphs(
                                soup,
                                FIRST_PARAGRAPH_LIMIT
                            )
                        )

                except Exception as scrape_error:

                    print(

                        "[RECLASSIFY SCRAPE] "
                        f"{index}/{total}: "
                        f"{scrape_error}"
                    )


            if not link:

                failed += 1

                continue


            # ------------------------------------------------
            # CLASSIFY ULANG
            # ------------------------------------------------

            classification = (
                classify_article(

                    title,
                    snippet,
                    content,
                    first_paragraphs
                )
            )


            # ------------------------------------------------
            # UPDATE DATABASE
            # ------------------------------------------------

            updates = {

                "category":
                    classification.get(
                        "category",
                        "Netral"
                    ),

                "priority":
                    classification.get(
                        "priority",
                        "RENDAH"
                    ),

                "negative_score":
                    int(
                        classification.get(
                            "negative_score",
                            0
                        )
                    ),

                "handling_score":
                    int(
                        classification.get(
                            "handling_score",
                            0
                        )
                    ),

                "positive_score":
                    int(
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

                "satker_match_location":
                    classification.get(
                        "satker_match_location",
                        ""
                    ),

                "satker_title_matches":
                    classification.get(
                        "satker_title_matches",
                        []
                    ),

                "satker_first_paragraph_matches":
                    classification.get(
                        "satker_first_paragraph_matches",
                        []
                    ),

                "first_paragraphs":
                    first_paragraphs[
                        :FIRST_PARAGRAPH_LIMIT
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
            }


            update_article(
                link,
                updates
            )


            category = updates[
                "category"
            ]


            if category not in counter:

                category = "Netral"


            counter[category] += 1

            updated += 1


        except Exception as e:

            failed += 1

            print(

                "[RECLASSIFY ERROR] "
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
            ensure_ascii=False
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

    elif category == "Positif":

        emoji = "🟢"

    else:

        emoji = "🟡"


    keywords = finding.get(
        "detected_keywords",
        []
    )


    link = html.escape(
        normalize_url(
            finding.get(
                "link",
                ""
            )
        ),
        quote=True
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

        f"<b>Lokasi SATKER:</b> "
        f"{html.escape(finding.get('satker_match_location', '-'))}\n\n"

        f"<b>Indikator:</b>\n"
        f"{html.escape(', '.join(keywords[:20]) or '-')}\n\n"

        f"<b>Link:</b>\n"
        f'<a href="{link}">Buka Artikel</a>\n\n'

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

    print(
        "SATKER: JUDUL ATAU "
        "1-3 PARAGRAF PERTAMA"
    )

    print(
        "TELEGRAM: HANYA LINK BARU"
    )

    print(
        "REKLASIFIKASI: SELURUH DATABASE"
    )

    print("==========================================")
    print()


    # ========================================================
    # 1. AMBIL DATABASE TERLEBIH DAHULU
    # ========================================================

    print(
        "[DB] Mengambil link artikel "
        "yang sudah ada..."
    )


    try:

        existing_articles = (
            get_all_articles()
        )

    except Exception as e:

        print(
            "[DB ERROR] "
            f"Gagal membaca database: {e}"
        )

        raise


    existing_links = set()


    for article in existing_articles:

        link = normalize_url(
            article.get("link")
            or ""
        )

        if link:

            existing_links.add(
                link
            )


    print(
        f"[DB] Link sudah ada: "
        f"{len(existing_links)}"
    )


    # ========================================================
    # 2. SEARCH
    # ========================================================

    candidates = (
        collect_candidates()
    )


    print(
        f"[PATROLI] Kandidat ditemukan: "
        f"{len(candidates)}"
    )


    # ========================================================
    # 3. PROCESS
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
    # 4. FILTER LINK BARU
    # ========================================================

    new_articles = []

    duplicate_articles = []


    run_seen_links = set()


    for article in results:

        link = normalize_url(
            article.get("link")
            or ""
        )


        if not link:
            continue


        # -----------------------------------------------
        # Hindari duplikat dalam run yang sama
        # -----------------------------------------------

        if link in run_seen_links:

            continue


        run_seen_links.add(
            link
        )


        # -----------------------------------------------
        # LINK SUDAH ADA SEBELUM RUN
        # -----------------------------------------------

        if link in existing_links:

            duplicate_articles.append(
                article
            )

        else:

            new_articles.append(
                article
            )


    print()
    print(
        f"[LINK] Artikel baru      : "
        f"{len(new_articles)}"
    )

    print(
        f"[LINK] Artikel lama       : "
        f"{len(duplicate_articles)}"
    )


    # ========================================================
    # 5. SIMPAN / UPDATE ARTIKEL
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


    print()
    print(
        f"[SUPABASE] "
        f"Berhasil disimpan/update: "
        f"{save_success}"
    )

    print(
        f"[SUPABASE] Gagal: "
        f"{save_failed}"
    )


    # ========================================================
    # 6. TELEGRAM HANYA ARTIKEL BARU
    # ========================================================

    print()
    print(
        "[TELEGRAM] "
        "Memeriksa artikel BARU..."
    )


    telegram_count = 0
    telegram_skipped = 0


    telegram_seen = set()


    for article in new_articles:

        link = normalize_url(
            article.get("link")
            or ""
        )


        if not link:
            continue


        if link in telegram_seen:

            continue


        telegram_seen.add(
            link
        )


        category = article.get(
            "category",
            "Netral"
        )


        priority = article.get(
            "priority",
            "RENDAH"
        )


        # ------------------------------------------------
        # Telegram hanya untuk:
        #
        # Negatif Kuat + KRITIS
        # Negatif Kuat + TINGGI
        # Perlu Penanganan + TINGGI
        #
        # ------------------------------------------------

        if category not in [
            "Negatif Kuat",
            "Perlu Penanganan"
        ]:

            telegram_skipped += 1

            continue


        if priority not in [
            "KRITIS",
            "TINGGI"
        ]:

            telegram_skipped += 1

            continue


        try:

            if send_telegram(
                article
            ):

                telegram_count += 1

                print(
                    "[TELEGRAM] Terkirim: "
                    f"{article.get('title', '')[:80]}"
                )

        except Exception as e:

            print(
                f"[TELEGRAM ERROR] {e}"
            )


    print()
    print(
        f"[TELEGRAM] Terkirim : "
        f"{telegram_count}"
    )

    print(
        f"[TELEGRAM] Dilewati : "
        f"{telegram_skipped}"
    )


    # ========================================================
    # 7. REKLASIFIKASI SELURUH DATABASE
    #
    # PENTING:
    # Bagian ini TETAP dijalankan setiap workflow.
    #
    # ========================================================

    print()
    print(
        "[PATROLI] "
        "Memulai reklasifikasi "
        "SELURUH DATABASE..."
    )


    reclass_result = (
        rekategorisasi_semua_database()
    )


    # ========================================================
    # 8. RUN LOG
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


    log_data = {

        "duration_seconds":
            round(
                elapsed,
                2
            ),

        "candidate_count":
            len(candidates),

        "valid_count":
            len(results),

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
    # 9. SUMMARY
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
        f"Artikel baru        : "
        f"{len(new_articles)}"
    )

    print(
        f"Artikel lama        : "
        f"{len(duplicate_articles)}"
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
                "--rekategorisasi"
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

        print(
            str(e)
        )

        print("==========================================")

        sys.exit(1)
