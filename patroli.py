import argparse
import base64
import csv
import html
import json
import os
import re
import time
import urllib.parse
from itertools import combinations
from difflib import SequenceMatcher
from collections import defaultdict, Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from audit_event_duplicates import (
    audit_event_duplicates,
    cluster_events,
    generate_event_name,
    extract_event_keywords,
    get_tokens,
    normalize_text,
    jaccard_similarity
)


import feedparser
import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from dotenv import load_dotenv

from risk_engine import calculate_risk_score

from database import (
    normalize_url,
    get_all_articles,
    get_supabase,
    get_article_by_link,
    upsert_article,
    save_run_log,
    update_article_classification_by_id,
    delete_article_by_id,
)


PATROLI_DIAGNOSTIC_VERSION = "V5.1"

# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()

TAHUN_TARGET = int(
    os.getenv("TAHUN_TARGET") or "2026"
)

MAX_WORKERS = int(
    os.getenv("MAX_WORKERS") or "10"
)

REQUEST_TIMEOUT = int(
    os.getenv("REQUEST_TIMEOUT") or "15"
)

MAX_ARTICLES_PER_FEED = int(
    os.getenv("MAX_ARTICLES_PER_FEED") or "40"
)

RSS_MAX_RETRIES = int(
    os.getenv("RSS_MAX_RETRIES") or "4"
)

RSS_BACKOFF_BASE = float(
    os.getenv("RSS_BACKOFF_BASE") or "2"
)

RSS_QUERY_DELAY = float(
    os.getenv("RSS_QUERY_DELAY") or "1.5"
)

MIN_CONTENT_LENGTH = int(
    os.getenv("MIN_CONTENT_LENGTH") or "180"
)

NAMA_SATKER = os.getenv(
    "NAMA_SATKER",
    "Kejaksaan Negeri Deli Serdang",
).strip()

TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN",
    "",
).strip()

TELEGRAM_CHAT_ID = os.getenv(
    "TELEGRAM_CHAT_ID",
    "",
).strip()

# ============================================================
# DUPLICATE & EVENT SIMILARITY CONFIGURATION
# ============================================================

# Artikel dianggap duplicate content jika similarity sangat tinggi
CONTENT_DUPLICATE_THRESHOLD = 0.95

# Artikel kemungkinan membahas event yang sama
# tetapi tetap boleh disimpan jika medianya berbeda
EVENT_CONTENT_SIMILARITY_THRESHOLD = 0.75


# ============================================================
# TARGET SATKER
# ============================================================

TARGET_KEJARI_KEYWORDS = [
    "kejaksaan negeri deli serdang",
    "kejari deli serdang",
    "kejari deliserdang",
    "kejaksaan deli serdang",
    "kajari deli serdang",
    "kajari deliserdang",
    "kepala kejaksaan negeri deli serdang",

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
# ISTILAH HUKUM
#
# Istilah hukum TIDAK otomatis negatif.
# ============================================================

LEGAL_EVENT_TERMS = {
    "kasus",
    "korupsi",
    "narkotika",
    "narkoba",
    "tersangka",
    "terdakwa",
    "penyidikan",
    "penyelidikan",
    "penuntutan",
    "perkara",
    "pidana",
    "pengadilan",
    "sidang",
    "vonis",
    "dakwaan",
    "suap",
    "gratifikasi",
    "penggeledahan",
    "penyitaan",
    "penangkapan",
    "ditangkap",
    "menangkap",
    "eksekusi",
}


# ============================================================
# IDENTITAS PIHAK INTERNAL SATKER
#
# Digunakan untuk membedakan:
#
# "Kajari ditetapkan tersangka"
#
# dengan:
#
# "Kajari menetapkan tersangka"
#
# ============================================================

INTERNAL_ACTOR_PATTERNS = [
    r"\bkajari\b",
    r"\bkepala kejaksaan\b",
    r"\bjaksa\b",
    r"\bjaksa penuntut umum\b",
    r"\bpegawai kejaksaan\b",
    r"\bpejabat kejaksaan\b",
    r"\bpetugas kejaksaan\b",
    r"\banggota kejaksaan\b",
    r"\bpenyidik kejaksaan\b",
    r"\bpenuntut umum\b",
]


SATKER_INSTITUTION_PATTERNS = [
    r"\bkejari\b",
    r"\bkejaksaan negeri\b",
    r"\bkejaksaan deli serdang\b",
    r"\bcabjari\b",
    r"\bcabang kejaksaan negeri\b",
]


# ============================================================
# POSITIVE ACTION
#
# Aksi penegakan hukum yang dilakukan oleh Kejari/Jaksa.
# ============================================================

POSITIVE_ACTION_PATTERNS = [

    # ========================================================
    # KEBERHASILAN
    # ========================================================

    r"\bberhasil\s+(?:mengungkap|mengamankan|menangkap|menyita|membongkar)",
    r"\bberhasil\s+.*?\bmenangkap\b",
    r"\bberhasil\s+.*?\bmengamankan\b",
    r"\bberhasil\s+.*?\bmenyita\b",
    r"\bberhasil\s+.*?\bmengungkap\b",


    # ========================================================
    # PENGUNGKAPAN KASUS
    # ========================================================

    r"\bmengungkap\s+(?:kasus|perkara)\b",
    r"\bungkap\s+(?:kasus|perkara)\b",
    r"\bmengungkap\s+.*?\bkasus\b",
    r"\bmembongkar\s+.*?\bkasus\b",


    # ========================================================
    # PENANGKAPAN
    # ========================================================

    r"\bmenangkap\s+(?:tersangka|pelaku)\b",
    r"\bmenangkap\s+.*?\btersangka\b",
    r"\bmengamankan\s+(?:tersangka|pelaku)\b",
    r"\bmengamankan\s+.*?\btersangka\b",


    # ========================================================
    # PENYITAAN
    # ========================================================

    r"\bmenyita\s+(?:barang bukti|aset)\b",
    r"\bmenyita\s+.*?\bbarang bukti\b",
    r"\bmenyita\s+.*?\baset\b",
    r"\bsita\s+(?:barang bukti|aset)\b",


    # ========================================================
    # PENETAPAN TERSANGKA
    # ========================================================

    r"\bmenetapkan\s+.*?\bsebagai\s+tersangka\b",
    r"\bditetapkan\s+.*?\bsebagai\s+tersangka\b",


    # ========================================================
    # PENYIDIKAN / PENYELIDIKAN
    # ========================================================
    #
    # TIDAK DIMASUKKAN SEBAGAI POSITIF.
    #
    # "melakukan penyidikan"
    # "melakukan penyelidikan"
    #
    # → NETRAL


    # ========================================================
    # PENUNTUTAN
    # ========================================================

    r"\bmenuntut\s+.*?\bdi\s+persidangan\b",
    r"\bmembacakan\s+tuntutan\b",


    # ========================================================
    # EKSEKUSI
    # ========================================================

    r"\bmelaksanakan\s+eksekusi\b",
    r"\bmelakukan\s+eksekusi\b",
    r"\beksekusi\s+.*?\bputusan\b",
    r"\beksekusi\s+.*?\bterpidana\b",
]
# ============================================================
# KEGIATAN RESMI
# ============================================================

OFFICIAL_ACTIVITY_PATTERNS = [

    # ========================================================
    # APEL / UPACARA
    # ========================================================

    r"\bapel pagi\b",
    r"\bapel gabungan\b",
    r"\bapel\b",
    r"\bupacara\b",
    r"\bupacara peringatan\b",

    # ========================================================
    # RAPAT / KOORDINASI / KONSOLIDASI
    # ========================================================

    r"\brapat\b",
    r"\brapat koordinasi\b",
    r"\brapat kerja\b",
    r"\bfgd\b",
    r"\bfocus group discussion\b",
    r"\bkonsolidasi\b",
    r"\bkoordinasi\b",
    r"\bmonitoring\b",
    r"\bevaluasi\b",

    # ========================================================
    # KUNJUNGAN / SILATURAHMI
    # ========================================================

    r"\bkunjungan kerja\b",
    r"\bkunjungan\b",
    r"\bsilaturahmi\b",

    # ========================================================
    # PENERANGAN / PENYULUHAN HUKUM
    # ========================================================

    r"\bpenyuluhan hukum\b",
    r"\bpenerangan hukum\b",
    r"\bsosialisasi hukum\b",
    r"\bsosialisasi\b",

    # ========================================================
    # ========================================================
    # KEGIATAN KEDINASAN
    # ========================================================
    
    r"\bpelantikan\b",
    r"\bpengambilan sumpah\b",
    r"\bserah terima\b",
    r"\bserah terima jabatan\b",
    r"\bsertijab\b",
    r"\bpenandatanganan\b",
    r"\bkerja sama\b",
    r"\bmoa\b",
    r"\bmou\b",
    r"\blaunching\b",
    r"\bperesmian\b",

    # ========================================================
    # SERAH TERIMA JABATAN
    # ========================================================
    
    r"\bsertijab\b",
    r"\bserah\s+terima\s+jabatan\b",
    r"\bserah\s+terima\b",

    # ========================================================
    # KEGIATAN SOSIAL / KEMASYARAKATAN
    # ========================================================

    r"\bziarah\b",
    r"\bbakti sosial\b",
    r"\bgotong royong\b",

    # ========================================================
    # PARTISIPASI KEGIATAN RESMI
    # ========================================================

    r"\bmengikuti zoom\b",
    r"\bmengikuti rapat\b",
    r"\bmengikuti kegiatan\b",
    r"\bmenghadiri rapat\b",
    r"\bmenghadiri kegiatan\b",
    r"\bmenghadiri acara\b",

    # ========================================================
    # MEMIMPIN KEGIATAN
    # ========================================================
    
    r"\bpimpin\b",
    r"\bpimpin sertijab\b",
    r"\bmemimpin kegiatan\b",
    r"\bmemimpin rapat\b",
    r"\bmemimpin apel\b",
    r"\bmemimpin upacara\b",

    # MEMIMPIN KEGIATAN
    r"\bpimpin\b",
    r"\bmemimpin\b",
]



# ============================================================
# NEGATIVE STRONG
#
# MASALAH HARUS DIARAHKAN KEPADA SATKER / INTERNAL SATKER.
#
# Sangat penting:
#
# "Kejari menetapkan tersangka"
# bukan negatif.
#
# "Kajari ditetapkan sebagai tersangka"
# negatif.
# ============================================================

NEGATIVE_STRONG_PATTERNS = [

    # ========================================================
    # KAJARI / KEPALA KEJAKSAAN SEBAGAI PIHAK BERMASALAH
    # ========================================================
    
    r"\b(?:kajari|kepala kejaksaan)\b.{0,180}"
    r"\b(?:ditangkap|diamankan|ditetapkan\s+sebagai\s+tersangka|"
    r"menjadi\s+tersangka|dijadikan\s+tersangka|terdakwa|terpidana)\b",
    
    r"\b(?:kajari|kepala kejaksaan)\b.{0,100}"
    r"\b(?:diduga\s+terlibat|terlibat\s+dalam|"
    r"diduga\s+menerima|menerima|"
    r"terjerat|tersangkut)\b.{0,80}"
    r"\b(?:suap|gratifikasi|korupsi|pungli|pemerasan|penggelapan)\b",
    
    r"\b(?:kajari|kepala kejaksaan)\b.{0,180}"
    r"\b(?:diperiksa|dipanggil|dilaporkan|diadukan|"
    r"disidang|diadili)\b",
    
    r"\b(?:kajari|kepala kejaksaan)\b.{0,180}"
    r"\b(?:dicopot|diberhentikan|dimutasi\s+karena)\b",
    
    
    # ========================================================
    # JAKSA / PEGAWAI INTERNAL SEBAGAI PIHAK BERMASALAH
    # ========================================================
    
    r"\b(?:jaksa|jaksa penuntut umum|pegawai kejaksaan|"
    r"pejabat kejaksaan|petugas kejaksaan|anggota kejaksaan)\b"
    r".{0,180}"
    r"\b(?:ditangkap|diamankan|ditetapkan\s+sebagai\s+tersangka|"
    r"menjadi\s+tersangka|dijadikan\s+tersangka|terdakwa|terpidana)\b",
    
    r"\b(?:jaksa|pegawai kejaksaan|pejabat kejaksaan|"
    r"petugas kejaksaan)\b.{0,100}"
    r"\b(?:diduga\s+terlibat|terlibat\s+dalam|"
    r"diduga\s+menerima|menerima|"
    r"terjerat|tersangkut)\b.{0,80}"
    r"\b(?:suap|gratifikasi|korupsi|pungli|pemerasan|"
    r"penggelapan)\b",
    
    r"\b(?:jaksa|pegawai kejaksaan|pejabat kejaksaan|"
    r"petugas kejaksaan)\b.{0,180}"
    r"\b(?:dilaporkan|diadukan|diperiksa|dipanggil|"
    r"disidang|diadili)\b",
    
    # ========================================================
    # KEJARI SEBAGAI INSTITUSI YANG DITUDUH
    # ========================================================

    r"\b(?:kejari|kejaksaan negeri|kejaksaan deli serdang|"
    r"cabjari|cabang kejaksaan negeri)\b.{0,180}"
    r"\b(?:diduga|terindikasi|dituding|dituduh)\b.{0,100}"
    r"\b(?:melakukan|terlibat|menerima|meminta|memeras)\b",

    r"\b(?:kejari|kejaksaan negeri|kejaksaan deli serdang|"
    r"cabjari|cabang kejaksaan negeri)\b.{0,180}"
    r"\b(?:pelanggaran etik|pelanggaran hukum|"
    r"maladministrasi)\b",


    # ========================================================
    # PENGADUAN LANGSUNG TERHADAP KEJARI
    # ========================================================

    r"\b(?:kejari|kejaksaan negeri|kejaksaan deli serdang|"
    r"cabjari|cabang kejaksaan negeri)\b.{0,180}"
    r"\b(?:dilaporkan|diadukan)\b",

    r"\b(?:dilaporkan|diadukan)\b.{0,180}"
    r"\b(?:kejari|kejaksaan negeri|kejaksaan deli serdang|"
    r"cabjari|cabang kejaksaan negeri)\b",

    r"\b(?:laporan pengaduan|aduan masyarakat)\b.{0,180}"
    r"\b(?:kejari|kejaksaan negeri|kajari|kepala kejaksaan)\b",


    # ========================================================
    # KANTOR SATKER SEBAGAI OBJEK
    # ========================================================

    r"\b(?:kantor|gedung)\b.{0,100}"
    r"\b(?:kejari|kejaksaan negeri)\b.{0,120}"
    r"\b(?:digeledah|disita|diperiksa)\b",

    r"\b(?:kejari|kejaksaan negeri)\b.{0,120}"
    r"\b(?:digeledah|disita)\b.{0,120}"
    r"\b(?:terkait|dugaan|kasus)\b",
]
# ============================================================
# HANDLING
#
# Tidak otomatis negatif.
# Harus ada hubungan dengan satker.
# ============================================================

HANDLING_PATTERNS = [
    r"\bdilaporkan\b",
    r"\bdiadukan\b",
    r"\bpengaduan\b",
    r"\blaporan masyarakat\b",
    r"\bdiperiksa\b",
    r"\bdimintai keterangan\b",
    r"\bklarifikasi\b",
    r"\bdipanggil\b",
    r"\bprotes\b",
    r"\bsoroti\b",
    r"\bdisorot\b",
    r"\bkritik\b",
    r"\bkritikan\b",
    r"\bdugaan\b",
    r"\bdiduga\b",
    r"\bdituding\b",
    r"\bdituduh\b",
    r"\bpolemik\b",
    r"\bsengketa\b",
    r"\bkeberatan\b",
    r"\bsomasi\b",
    r"\bdemonstrasi\b",
    r"\bunjuk rasa\b",
    r"\bviral\b",
    r"\bkontroversi\b",
    r"\bpermintaan transparansi\b",
]


# ============================================================
# NEGATION
# ============================================================

NEGATION_PATTERNS = [
    r"\btidak\s+(?:terbukti|benar|ada|melakukan|"
    r"terlibat|menerima|terlibat)\b",

    r"\bbelum\s+(?:terbukti|ada|ditemukan)\b",

    r"\bbantah\b",
    r"\bmembantah\b",
    r"\bdibantah\b",
    r"\bklarifikasi\b",
    r"\bhoaks\b",
    r"\btidak benar\b",
    r"\bfitnah\b",
    r"\bkeliru\b",
    r"\btidak terbukti\b",
]


# ============================================================
# DANGER TITLE
# ============================================================

DANGER_TITLE_TERMS = {
    "ditangkap",
    "tersangka",
    "suap",
    "gratifikasi",
    "korupsi",
    "dicopot",
    "dilaporkan",
    "diadukan",
    "pungli",
    "pemerasan",
    "pelanggaran etik",
}


# ============================================================
# PRIORITY
# ============================================================

PRIORITY_BY_CATEGORY = {
    "Negatif Kuat": "Tinggi",
    "Perlu Penanganan": "Sedang",
    "Netral": "Rendah",
    "Positif": "Rendah",
}


# ============================================================
# SESSION HTTP
# ============================================================

SESSION = requests.Session()

SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/151.0 Safari/537.36"
        ),
        "Accept-Language": (
            "id-ID,id;q=0.9,en;q=0.8"
        ),
    }
)


# ============================================================
# TEXT UTILITIES
# ============================================================

def normalize_text(
    value: Any,
) -> str:

    text = html.unescape(
        str(value or "")
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()

def sanitize_html_text(value: Any) -> Any:
    """
    Membersihkan HTML dari nilai teks database.

    Contoh:
        <a href="...">Judul</a>
        <font color="#6f6f6f">Media</font>

    menjadi:
        Judul Media

    Tidak mengubah None menjadi string kosong.
    """

    if value is None:
        return None

    if not isinstance(value, str):
        return value

    text = value.strip()

    if not text:
        return ""

    # --------------------------------------------------------
    # Hapus script/style beserta isinya
    # --------------------------------------------------------

    text = re.sub(
        r"<\s*(script|style|noscript)\b[^>]*>.*?</\s*\1\s*>",
        " ",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # --------------------------------------------------------
    # Gunakan BeautifulSoup untuk menghapus HTML
    # --------------------------------------------------------

    try:
        soup = BeautifulSoup(
            text,
            "html.parser",
        )

        # Tag yang biasanya hanya pembungkus visual.
        for tag in soup.find_all(
            [
                "br",
                "p",
                "div",
                "li",
                "tr",
            ]
        ):
            tag.insert_before(" ")
            tag.insert_after(" ")

        text = soup.get_text(
            " ",
            strip=True,
        )

    except Exception:
        # Fallback jika parser bermasalah
        text = re.sub(
            r"<[^>]+>",
            " ",
            text,
        )

    # --------------------------------------------------------
    # Decode HTML entity
    #
    # &amp;  -> &
    # &quot; -> "
    # &#39;  -> '
    # --------------------------------------------------------

    text = html.unescape(
        text
    )

    # --------------------------------------------------------
    # Hapus sisa tag HTML
    # --------------------------------------------------------

    text = re.sub(
        r"<[^>]+>",
        " ",
        text,
    )

    # --------------------------------------------------------
    # Normalisasi whitespace
    # --------------------------------------------------------

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    return text

SANITIZE_FIELDS = [
    "title",
    "snippet",
    "content",
    "summary",
    "source",

    "strong_context",
    "handling_context",
    "positive_context",
    "satker_context",

    "detected_keywords",
    "satker_matches",

    "positive_hits",
    "negative_hits",
    "handling_hits",
]

def sanitize_article(
    article: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Membersihkan field teks/list teks dari HTML.

    Field yang tidak termasuk SANITIZE_FIELDS
    tidak disentuh.
    """

    cleaned = {}

    for field in SANITIZE_FIELDS:

        if field not in article:
            continue

        value = article.get(field)

        if value is None:
            continue

        # ----------------------------------------------------
        # List
        # ----------------------------------------------------

        if isinstance(value, list):

            new_list = []

            for item in value:

                if isinstance(item, str):

                    cleaned_item = (
                        sanitize_html_text(
                            item
                        )
                    )

                    if cleaned_item:
                        new_list.append(
                            cleaned_item
                        )

                else:

                    # Jangan merusak tipe data non-string
                    new_list.append(
                        item
                    )

            cleaned[field] = new_list

        # ----------------------------------------------------
        # String
        # ----------------------------------------------------

        elif isinstance(value, str):

            cleaned[field] = (
                sanitize_html_text(
                    value
                )
            )

        # ----------------------------------------------------
        # Tipe lainnya
        # ----------------------------------------------------

        else:

            cleaned[field] = value

    return cleaned
    

def load_existing_normalized_links():
    """
    Mengambil seluruh link artikel dari database
    dan menyimpannya dalam bentuk normalized URL.

    Digunakan untuk mencegah artikel yang sama
    masuk kembali ke database.
    """

    try:

        supabase = get_supabase()

        print(
            "[DEDUPE] Mengambil link artikel "
            "yang sudah ada di database..."
        )

        all_links = set()

        offset = 0
        batch_size = 1000

        while True:

            response = (
                supabase
                .table("articles")
                .select("link")
                .range(
                    offset,
                    offset + batch_size - 1
                )
                .execute()
            )

            rows = response.data or []

            if not rows:
                break

            for row in rows:

                link = row.get("link")

                normalized = normalize_url(
                    link
                )

                if normalized:
                    all_links.add(
                        normalized
                    )

            if len(rows) < batch_size:
                break

            offset += batch_size

        print(
            f"[DEDUPE] Link unik yang sudah ada: "
            f"{len(all_links)}"
        )

        return all_links

    except Exception as e:

        print(
            f"[DEDUPE ERROR] "
            f"Gagal mengambil link database: {e}"
        )

        return set()



def article_link_exists(
    link: Any,
    existing_links: set,
) -> bool:
    """
    Mengecek apakah link artikel sudah ada.

    Link dibandingkan menggunakan URL yang sudah
    dinormalisasi sehingga variasi seperti:

        https://www.example.com/artikel/
        http://example.com/artikel
        https://example.com/artikel?utm_source=google

    dapat dianggap sebagai artikel yang sama.
    """

    normalized = normalize_url(link)

    if not normalized:
        return False

    return normalized in existing_links



def is_duplicate_link(link, existing_link_index):
    """
    Mengecek apakah link sudah ada di database/index.

    Return:
        True  -> duplicate
        False -> bukan duplicate
    """

    normalized = normalize_url(link)

    if not normalized:
        return False

    return normalized in existing_link_index


def register_new_link(link, existing_link_index):
    """
    Mendaftarkan link baru ke index.
    Dipanggil setelah artikel berhasil disimpan.
    """
    normalized = normalize_url(link)

    if not normalized:
        return False

    existing_link_index.add(normalized)
    return True
    
    
def build_existing_link_index():
    """
    Membuat index:
        normalized_link -> article

    Semua artikel lama di database dimasukkan ke memory
    sehingga kandidat baru dapat dicek sebelum disimpan.
    """

    print("[DEDUPE] Membuat index link dari database...")

    try:
        articles = get_all_articles()

        existing = {}

        for article in articles:
            link = article.get("link")

            if not link:
                continue

            normalized = normalize_url(link)

            if not normalized:
                continue

            # Pertahankan record pertama
            if normalized not in existing:
                existing[normalized] = article

        print(
            f"[DEDUPE] Index selesai: "
            f"{len(existing)} link unik."
        )

        return existing

    except Exception as e:
        print(f"[DEDUPE] Gagal membuat index link: {e}")
        return {}
        

# ============================================================
# DATE
# ============================================================

def parse_date_safe(
    value: Any,
) -> Optional[datetime]:

    if value is None or value == "":
        return None

    try:

        dt = date_parser.parse(
            str(value)
        )

        if dt.tzinfo is None:

            dt = dt.replace(
                tzinfo=timezone.utc
            )

        return dt.astimezone(
            timezone.utc
        )

    except Exception:

        return None


def extract_published_date(
    entry: Any,
    fallback: Optional[datetime] = None,
) -> Optional[datetime]:

    for key in (
        "published",
        "updated",
        "created",
    ):

        dt = parse_date_safe(
            entry.get(key)
        )

        if dt:
            return dt

    for key in (
        "published_parsed",
        "updated_parsed",
        "created_parsed",
    ):

        value = entry.get(
            key
        )

        if value:

            try:

                return datetime(
                    *value[:6],
                    tzinfo=timezone.utc,
                )

            except Exception:

                pass

    return fallback


def is_article_2026(
    dt: Optional[datetime],
) -> bool:

    return bool(
        dt
        and dt.year == TAHUN_TARGET
    )


def is_url_old(
    dt: Optional[datetime],
) -> bool:

    return not is_article_2026(
        dt
    )


# ============================================================
# FETCH WEB
# ============================================================

def _is_google_news_url(url: Any) -> bool:
    """True jika URL berasal dari domain Google News."""
    if not url:
        return False
    try:
        host = urllib.parse.urlparse(str(url).strip()).netloc.lower().split(":", 1)[0]
        return host == "news.google.com"
    except Exception:
        return False


def _clean_candidate_url(url: Any, base_url: str = "") -> str:
    """Validasi dan normalisasi URL HTTP(S), termasuk URL relatif."""
    if not url:
        return ""
    value = html.unescape(str(url)).strip().strip('"\'')
    if not value:
        return ""
    if base_url:
        value = urllib.parse.urljoin(base_url, value)
    try:
        parsed = urllib.parse.urlparse(value)
    except Exception:
        return ""
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return ""
    return normalize_url(value)


def extract_canonical_article_url(raw_html: str, response_url: str = "") -> str:
    """Ambil canonical/og:url artikel asli dari HTML."""
    if not raw_html:
        return ""

    try:
        soup = BeautifulSoup(raw_html, "html.parser")
    except Exception:
        return ""

    candidates = []
    for tag in soup.find_all("link"):
        rel = tag.get("rel") or []
        if isinstance(rel, str):
            rel = [rel]
        if "canonical" in {str(item).lower().strip() for item in rel}:
            candidates.append(tag.get("href"))

    for tag in soup.find_all("meta"):
        prop = str(tag.get("property") or tag.get("name") or "").lower().strip()
        if prop == "og:url":
            candidates.append(tag.get("content"))

    for candidate in candidates:
        cleaned = _clean_candidate_url(candidate, response_url)
        if cleaned and not _is_google_news_url(cleaned):
            return cleaned
    return ""


def _url_source_domain(url: str) -> str:
    try:
        host = urllib.parse.urlparse(str(url)).netloc.lower().split(":", 1)[0]
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def _looks_like_media_url(url: str) -> bool:
    """Menolak URL navigasi umum agar ekstraksi Google News tetap konservatif."""
    if not url or _is_google_news_url(url):
        return False
    host = _url_source_domain(url)
    if not host:
        return False
    blocked_hosts = {
        "google.com", "google.co.id", "youtube.com", "youtu.be",
        "facebook.com", "instagram.com", "twitter.com", "x.com",
        "t.me", "linkedin.com",
    }
    if host in blocked_hosts or any(host.endswith("." + h) for h in blocked_hosts):
        return False
    return True


def _decode_embedded_url(value: Any) -> str:
    """Decode URL yang disimpan escaped/HTML-encoded di HTML Google News."""
    if not value:
        return ""
    text = html.unescape(str(value)).strip()
    text = text.replace(r"\/", "/")
    text = text.replace(r"\u002F", "/").replace(r"\u003A", ":")
    text = text.replace(r"\u0026", "&").replace(r"\u003F", "?")
    text = text.replace(r"\u003D", "=").replace(r"\u0025", "%")
    return text


def _extract_url_like_strings(raw_html: str) -> List[str]:
    """Mengambil URL absolut dari HTML termasuk JSON/JS escaped URLs."""
    if not raw_html:
        return []

    decoded = _decode_embedded_url(raw_html)
    patterns = [
        r'https?://[^\s"\'<>\\]+',
        r'https?:\\/\\/[^\s"\'<>]+',
    ]

    found = []
    seen = set()
    for pattern in patterns:
        for match in re.finditer(pattern, decoded, flags=re.I):
            value = _decode_embedded_url(match.group(0)).rstrip(".,;)]}\"")
            if value and value not in seen:
                seen.add(value)
                found.append(value)
    return found


def _title_token_set(value: Any) -> set:
    stopwords = {
        "yang", "dengan", "dari", "untuk", "dalam", "pada", "oleh", "dan", "atau",
        "ini", "itu", "telah", "akan", "jadi", "saat", "setelah", "sebagai", "karena",
        "kepada", "hingga", "dalam", "news", "berita",
    }
    return {
        token.lower()
        for token in re.findall(r"[\w]{4,}", normalize_text(value))
        if token.lower() not in stopwords
    }


def _domain_related(host: str, source_domain: str) -> bool:
    if not host or not source_domain:
        return False
    return (
        host == source_domain
        or host.endswith("." + source_domain)
        or source_domain.endswith("." + host)
    )



def decode_google_news_base64_url(url: str, raw_html: str = "") -> str:
    """
    Resolve Google News RSS article URLs to publisher URLs.

    Google News currently uses an internal `garturl` RPC for many
    /rss/articles/CBMi... links.  The most reliable flow is:

    1. GET the Google News article/RSS URL.
    2. Read c-wiz[data-p] from the returned HTML.
    3. Build the Fbv4je/garturlreq request from that payload.
    4. Parse garturlres from Google's response.

    A legacy direct base64 URL extraction is retained as a fallback.
    """
    if not _is_google_news_url(url):
        return ""

    try:
        parsed = urllib.parse.urlparse(str(url))
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) < 3 or parts[-2] not in {"articles", "read"}:
            return ""
        token = parts[-1]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", token):
            return ""

        # --------------------------------------------------------
        # 1. Legacy offline format
        # --------------------------------------------------------
        padded = token + "=" * ((4 - len(token) % 4) % 4)
        try:
            decoded = base64.urlsafe_b64decode(padded)
            matches = re.findall(
                rb"https?://[^\x00\x0a\x0d\x22\x27<>]+",
                decoded,
            )
            for raw in matches:
                candidate = raw.decode("utf-8", errors="ignore").rstrip(".,;)]}")
                candidate = _clean_candidate_url(candidate, url)
                if candidate and _looks_like_media_url(candidate):
                    return candidate
        except Exception:
            pass

        # --------------------------------------------------------
        # 2. Preferred current Google News garturl flow.
        # --------------------------------------------------------
        # The Google News article page exposes a c-wiz[data-p] payload.
        # Community-tested implementations use that payload to construct
        # the Fbv4je request rather than guessing the protobuf structure.
        html_text = raw_html or ""
        if not html_text:
            response = SESSION.get(
                str(url),
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True,
            )
            response.raise_for_status()
            html_text = response.text

        try:
            soup = BeautifulSoup(html_text, "html.parser")
            data_p = ""
            node = soup.select_one("c-wiz[data-p]")
            if node is not None:
                data_p = node.get("data-p") or ""
            if not data_p:
                node = soup.select_one("c-wiz > div[data-p]")
                if node is not None:
                    data_p = node.get("data-p") or ""
        except Exception:
            data_p = ""

        if data_p:
            try:
                decoded_data = html.unescape(data_p)
                obj = json.loads(
                    decoded_data.replace("%.@.", '["garturlreq",', 1)
                )

                # Google currently expects the garturl request object with
                # the last six metadata elements reduced to the final two.
                if isinstance(obj, list) and len(obj) >= 6:
                    garturl_obj = obj[:-6] + obj[-2:]
                else:
                    garturl_obj = obj

                rpc_payload = json.dumps(
                    [[
                        [
                            "Fbv4je",
                            json.dumps(garturl_obj, separators=(",", ":")),
                            "null",
                            "generic",
                        ]
                    ]],
                    separators=(",", ":"),
                )

                response = SESSION.post(
                    "https://news.google.com/_/DotsSplashUi/data/batchexecute",
                    params={"rpcids": "Fbv4je"},
                    data={"f.req": rpc_payload},
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                        "Referer": "https://news.google.com/",
                        "User-Agent": SESSION.headers.get("User-Agent", "Mozilla/5.0"),
                    },
                    timeout=REQUEST_TIMEOUT,
                )
                response.raise_for_status()
                text = response.text

                # Primary parser used by known working Python implementations.
                try:
                    outer = json.loads(text.replace(")]}'", "", 1))
                    array_string = outer[0][2]
                    inner = json.loads(array_string)
                    if isinstance(inner, list) and len(inner) > 1:
                        candidate = inner[1]
                        candidate = _clean_candidate_url(candidate, url)
                        if candidate and _looks_like_media_url(candidate):
                            return candidate
                except Exception:
                    pass

                # Secondary parser for escaped garturlres responses.
                marker = r'[\\"garturlres\\",\\"'
                pos = text.find('garturlres')
                if pos >= 0:
                    tail = text[pos:pos + 20000]
                    for match in re.finditer(
                        r'https?://[^\\"\'<>\\s]+',
                        tail,
                        flags=re.I,
                    ):
                        candidate = match.group(0)
                        candidate = candidate.replace(r'\\u0026', '&')
                        candidate = candidate.replace(r'\\/', '/')
                        candidate = html.unescape(candidate)
                        candidate = _clean_candidate_url(candidate, url)
                        if candidate and _looks_like_media_url(candidate):
                            return candidate
            except Exception as exc:
                print(
                    "[GOOGLE NEWS GARTURL WARNING] "
                    f"{type(exc).__name__}: {exc}"
                )

        # --------------------------------------------------------
        # 3. Alternative current format using data-n-a-sg / data-n-a-ts.
        # --------------------------------------------------------
        try:
            soup = BeautifulSoup(html_text, "html.parser")
            node = soup.select_one("c-wiz > div[data-n-a-sg][data-n-a-ts]")
            if node is not None:
                signature = node.get("data-n-a-sg")
                timestamp = node.get("data-n-a-ts")
                if signature and timestamp:
                    req = [
                        "Fbv4je",
                        (
                            '["garturlreq",[["en-US","US",'
                            '["FINANCE_TOP_INDICES","WEB_TEST_1_0_0"],'
                            'null,null,1,1,"US:en",null,180,null,null,null,null,null,0,null,null,'
                            '[1608992183,723341000]],"en-US","US",1,[2,3,4,8],1,0,"655000234",0,0,null,0],'
                            f'"{token}",{timestamp},"{signature}"]'
                        ),
                        "null",
                        "generic",
                    ]
                    rpc_payload = json.dumps([[req]], separators=(",", ":"))
                    response = SESSION.post(
                        "https://news.google.com/_/DotsSplashUi/data/batchexecute",
                        params={"rpcids": "Fbv4je"},
                        data={"f.req": rpc_payload},
                        headers={
                            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                            "Referer": "https://news.google.com/",
                            "User-Agent": SESSION.headers.get("User-Agent", "Mozilla/5.0"),
                        },
                        timeout=REQUEST_TIMEOUT,
                    )
                    response.raise_for_status()
                    text = response.text
                    pos = text.find("garturlres")
                    if pos >= 0:
                        tail = text[pos:pos + 20000]
                        for match in re.finditer(r'https?://[^\\"\'<>\\s]+', tail, flags=re.I):
                            candidate = match.group(0)
                            candidate = candidate.replace(r'\\u0026', '&').replace(r'\\/', '/')
                            candidate = html.unescape(candidate)
                            candidate = _clean_candidate_url(candidate, url)
                            if candidate and _looks_like_media_url(candidate):
                                return candidate
        except Exception as exc:
            print(
                "[GOOGLE NEWS DECODER WARNING] "
                f"{type(exc).__name__}: {exc}"
            )

    except Exception as exc:
        print(
            "[GOOGLE NEWS DECODER WARNING] "
            f"{type(exc).__name__}: {exc}"
        )

    return ""

def extract_google_news_original_url(
    raw_html: str,
    response_url: str = "",
    source_url: str = "",
    title: str = "",
) -> str:
    """
    Mencari URL media asli ketika URL Google News tidak melakukan redirect.

    V5.2 memperluas pencarian ke:
    - anchor href
    - meta refresh
    - URL absolut yang tertanam di JSON/JavaScript
    - field JSON/JS yang bernama url/targetUrl/originalUrl/articleUrl/canonicalUrl

    Pemilihan tetap konservatif: domain source RSS menjadi sinyal terkuat,
    kemudian kemiripan anchor/judul dan bentuk path artikel. URL navigasi umum
    tidak dipilih sebagai media asli.
    """
    if not raw_html:
        return ""

    try:
        soup = BeautifulSoup(raw_html, "html.parser")
    except Exception:
        soup = None

    source_domain = _url_source_domain(source_url)
    title_tokens = _title_token_set(title)
    scored: Dict[str, float] = {}
    candidate_reasons: Dict[str, List[str]] = defaultdict(list)

    def add_candidate(value: Any, anchor_text: str = "", context: str = "") -> None:
        cleaned = _clean_candidate_url(_decode_embedded_url(value), response_url)
        if not _looks_like_media_url(cleaned):
            return

        parsed = urllib.parse.urlparse(cleaned)
        host = _url_source_domain(cleaned)
        path = parsed.path or "/"
        path_lower = path.lower()
        score = 0.0

        if _domain_related(host, source_domain):
            score += 100
            candidate_reasons[cleaned].append("source-domain")

        if anchor_text and title_tokens:
            overlap = len(title_tokens & _title_token_set(anchor_text))
            score += min(overlap, 12) * 6
            if overlap:
                candidate_reasons[cleaned].append(f"title-overlap:{overlap}")

        # URL yang terlihat seperti halaman artikel mendapat bonus kecil.
        article_markers = (
            "/berita/", "/news/", "/artikel/", "/read/", "/story/",
            "/detail/", "/2026/", "/2025/", "/amp/", "/post/",
        )
        if any(marker in path_lower for marker in article_markers):
            score += 12
            candidate_reasons[cleaned].append("article-path")
        elif path not in {"", "/"}:
            score += 3

        # URL media yang terlalu panjang/aneh cenderung berupa tracking payload.
        if len(cleaned) <= 350:
            score += 2
        if len(cleaned) > 900:
            score -= 8

        # URL yang muncul dalam field yang jelas-jelas menunjuk target artikel.
        context_lower = context.lower()
        if any(key in context_lower for key in (
            "originalurl", "targeturl", "articleurl", "canonicalurl", "article_url",
        )):
            score += 30
            candidate_reasons[cleaned].append("article-url-field")
        elif re.search(r'(?i)(?:["\']url["\']\s*:|["\']url["\']\s*=)', context):
            score += 10
            candidate_reasons[cleaned].append("url-field")

        scored[cleaned] = max(scored.get(cleaned, -999.0), score)

    if soup is not None:
        for tag in soup.find_all("a", href=True):
            add_candidate(tag.get("href"), tag.get_text(" ", strip=True), "anchor")

        for tag in soup.find_all("meta"):
            if str(tag.get("http-equiv") or "").lower().strip() == "refresh":
                content = str(tag.get("content") or "")
                match = re.search(r"url\s*=\s*(.+)$", content, flags=re.I)
                if match:
                    add_candidate(match.group(1).strip(" \\\"'"), "", "meta-refresh")

    # Field-oriented extraction sebelum fallback seluruh HTML.
    field_pattern = re.compile(
        r'(?is)["\'](?P<key>originalUrl|targetUrl|articleUrl|canonicalUrl|article_url|url)["\']\s*[:=]\s*["\'](?P<url>https?:(?:\\/\\/|//)[^"\']+)["\']'
    )
    for match in field_pattern.finditer(raw_html):
        add_candidate(match.group("url"), title, match.group("key"))

    # URL absolut tertanam di JSON/JS. Gunakan hanya jika ada sinyal domain/title.
    for embedded_url in _extract_url_like_strings(raw_html):
        add_candidate(embedded_url, "", "embedded-url")

    if not scored:
        return ""

    ranked = sorted(scored.items(), key=lambda item: item[1], reverse=True)
    best_url, best_score = ranked[0]
    best_domain = _url_source_domain(best_url)

    # Domain source adalah bukti utama. Jika source domain tidak tersedia,
    # wajib ada skor kuat dari konteks/title agar tidak mengambil URL acak.
    if source_domain and _domain_related(best_domain, source_domain):
        return best_url

    if best_score >= 45:
        return best_url

    return ""


def resolve_article_url_details(
    rss_url: str,
    response_url: str = "",
    raw_html: str = "",
    source_url: str = "",
    title: str = "",
) -> Tuple[str, str]:
    """Resolve URL sekaligus mengembalikan metode resolusinya."""
    # ------------------------------------------------------------
    # 0. Offline Google News token decoding
    # ------------------------------------------------------------
    # Untuk URL /rss/articles/CBMi..., token sering memuat URL publisher
    # secara langsung. Ini lebih stabil daripada mengandalkan HTML Google.
    decoded = decode_google_news_base64_url(rss_url, raw_html=raw_html)
    if decoded and not _is_google_news_url(decoded):
        return decoded, "base64_embedded"

    canonical = extract_canonical_article_url(raw_html, response_url)
    if canonical:
        return canonical, "canonical"

    resolved = _clean_candidate_url(response_url)
    if resolved and not _is_google_news_url(resolved):
        return resolved, "redirect"

    decoded = decode_google_news_base64_url(rss_url, raw_html=raw_html)
    if decoded:
        print(f"[URL GOOGLE NEWS] Media asli via garturl: {decoded}")
        return decoded, "base64_embedded"

    original = extract_google_news_original_url(
        raw_html=raw_html,
        response_url=response_url,
        source_url=source_url,
        title=title,
    )
    if original:
        print(f"[URL GOOGLE NEWS] Media asli ditemukan: {original}")
        return original, "embedded_original"

    return normalize_url(rss_url) or _clean_candidate_url(rss_url), "google_fallback"


def resolve_article_url(
    rss_url: str,
    response_url: str = "",
    raw_html: str = "",
    source_url: str = "",
    title: str = "",
) -> str:
    """Backward-compatible wrapper; mengembalikan URL saja."""
    resolved, _method = resolve_article_url_details(
        rss_url=rss_url,
        response_url=response_url,
        raw_html=raw_html,
        source_url=source_url,
        title=title,
    )
    return resolved

def fetch_webpage_content(
    url: str,
) -> Tuple[str, str]:
    """Fetch halaman dengan redirect dan mengembalikan URL akhir + HTML."""
    if not url:
        return "", ""

    response = SESSION.get(
        url,
        timeout=REQUEST_TIMEOUT,
        allow_redirects=True,
    )
    response.raise_for_status()

    return (
        normalize_url(response.url),
        response.text,
    )


# ============================================================
# ARTICLE TEXT
# ============================================================

def extract_article_text(
    raw_html: str,
) -> str:

    if not raw_html:
        return ""

    soup = BeautifulSoup(
        raw_html,
        "html.parser",
    )

    for tag in soup(
        [
            "script",
            "style",
            "noscript",
            "svg",
            "nav",
            "footer",
            "header",
            "form",
            "aside",
        ]
    ):

        tag.decompose()

    candidates = []

    selectors = [
        "article",
        "main",
        "[itemprop='articleBody']",
        ".article-body",
        ".article-content",
        ".post-content",
        ".entry-content",
        ".content-article",
        ".detail-content",
        ".read-content",
        ".news-content",
    ]

    for selector in selectors:

        for node in soup.select(
            selector
        ):

            txt = normalize_text(
                node.get_text(
                    " ",
                    strip=True,
                )
            )

            if len(txt) > 100:

                candidates.append(
                    txt
                )

    if candidates:

        return max(
            candidates,
            key=len,
        )

    paragraphs = [
        normalize_text(
            paragraph.get_text(
                " ",
                strip=True,
            )
        )
        for paragraph
        in soup.find_all("p")
    ]

    paragraphs = [
        paragraph
        for paragraph in paragraphs
        if len(paragraph) >= 35
    ]

    return normalize_text(
        " ".join(
            paragraphs
        )
    )


# ============================================================
# SATKER MATCH
# ============================================================


def find_satker_matches(
    title: str,
    content: str,
) -> List[str]:
    """
    Mencari kecocokan nama/keyword satker
    pada judul dan isi artikel.

    Pencocokan menggunakan word boundary agar
    tidak mudah menghasilkan false positive akibat
    substring yang kebetulan sama.

    Mengembalikan daftar keyword satker yang ditemukan.
    """

    text = normalize_text(
        f"{title}. {content}"
    ).lower()

    matches = []

    for keyword in TARGET_KEJARI_KEYWORDS:

        keyword_clean = normalize_text(
            keyword
        ).lower()

        if not keyword_clean:
            continue

        # Escape agar keyword aman digunakan sebagai regex.
        pattern = (
            r"(?<!\w)"
            + re.escape(keyword_clean)
            + r"(?!\w)"
        )

        if re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        ):
            matches.append(
                keyword
            )

    return list(
        dict.fromkeys(
            matches
        )
    )



def find_satker_match_location(
    title: str,
    content: str,
) -> str:

    title_lower = normalize_text(
        title
    ).lower()

    content_lower = normalize_text(
        content
    ).lower()

    for keyword in TARGET_KEJARI_KEYWORDS:

        key = keyword.lower()

        if key in title_lower:

            return "judul"

        if key in content_lower:

            return "isi"

    return ""


def check_satker_relevance(
    title: str,
    content: str,
) -> bool:

    return bool(
        find_satker_matches(
            title,
            content,
        )
    )


# ============================================================
# REGEX
# ============================================================

def regex_hits(
    text: str,
    patterns: List[str],
) -> List[str]:

    hits = []

    for pattern in patterns:

        try:

            if re.search(
                pattern,
                text,
                flags=re.I,
            ):

                hits.append(
                    pattern
                )

        except re.error:

            continue

    return hits


# ============================================================
# SENTENCE SPLITTER
# ============================================================

def split_sentences(
    text: str,
) -> List[str]:

    text = normalize_text(
        text
    )

    if not text:
        return []

    sentences = re.split(
        r"(?<=[.!?])\s+",
        text,
    )

    return [
        normalize_text(
            sentence
        )
        for sentence in sentences
        if normalize_text(
            sentence
        )
    ]


# ============================================================
# SATKER CONTEXT
# ============================================================

def sentence_contains_internal_actor(sentence: str) -> bool:
    """
    Mengembalikan True jika kalimat menyebut aktor
    internal Kejari Deli Serdang.

    Aktor dapat berupa:
    - Person: Kajari / Jaksa
    - Institution: Kejari / Kejaksaan Negeri

    Tetapi wajib terkait dengan satker target.
    """

    text = normalize_text(sentence).lower()

    if not text:
        return False

    # ==========================================
    # 1. WAJIB TERKAIT SATKER TARGET
    # ==========================================

    if not sentence_contains_satker(text):
        return False

    # ==========================================
    # 2. PERSON ACTOR
    # ==========================================

    has_person_actor = any(
        re.search(pattern, text, re.I)
        for pattern in INTERNAL_ACTOR_PATTERNS
        if pattern
    )

    # ==========================================
    # 3. INSTITUTION ACTOR
    # ==========================================

    has_institution_actor = any(
        keyword.lower() in text
        for keyword in [
            "kejari",
            "kejaksaan negeri",
            "kejaksaan",
        ]
    )

    return has_person_actor or has_institution_actor

def sentence_contains_satker(
    sentence: str,
) -> bool:
    """
    Mengecek apakah kalimat menyebut satker target
    menggunakan word boundary.
    """

    text = normalize_text(
        sentence
    ).lower()

    if not text:
        return False

    for keyword in TARGET_KEJARI_KEYWORDS:

        keyword_clean = normalize_text(
            keyword
        ).lower()

        if not keyword_clean:
            continue

        pattern = (
            r"(?<!\w)"
            + re.escape(keyword_clean)
            + r"(?!\w)"
        )

        if re.search(
            pattern,
            text,
            flags=re.I,
        ):
            return True

    return False


def get_satker_context_sentences(
    title: str,
    content: str,
) -> List[str]:

    sentences = split_sentences(
        f"{title}. {content}"
    )

    contexts = []

    for sentence in sentences:

        if sentence_contains_satker(
            sentence
        ):

            contexts.append(
                sentence
            )

    return contexts[:20]


# ============================================================
# NEGATION
# ============================================================

def has_negation_near(
    text: str,
    term: str,
    window: int = 120,
) -> bool:

    text = text.lower()

    for match in re.finditer(
        re.escape(
            term.lower()
        ),
        text,
    ):

        before = text[
            max(
                0,
                match.start()
                - window,
            ):
            match.start()
        ]

        if any(
            re.search(
                pattern,
                before,
                re.I,
            )
            for pattern
            in NEGATION_PATTERNS
        ):

            return True

    return False


def sentence_has_negation(
    sentence: str,
) -> bool:

    text = sentence.lower()

    return any(
        re.search(
            pattern,
            text,
            re.I,
        )
        for pattern
        in NEGATION_PATTERNS
    )


# ============================================================
# POSITIVE CONTEXT
# ============================================================


def find_positive_context(
    title: str,
    content: str,
) -> List[str]:
    """
    Mencari konteks positif yang benar-benar berkaitan
    dengan satker target atau aktor internal target.

    Positif mencakup:

    1. Keberhasilan nyata
       - berhasil mengungkap kasus
       - berhasil menangkap tersangka
       - berhasil menyita barang bukti/aset
       - membongkar kasus

    2. Kegiatan resmi satker
       - apel
       - rapat
       - FGD
       - kunjungan
       - penyuluhan
       - pelantikan
       - sertijab
       - silaturahmi

    Catatan:
    - Penyidikan/penyelidikan tidak otomatis positif.
    - Kalimat dengan negasi tidak dianggap positif.
    - Kalimat yang menunjukkan aktor target sebagai
      pihak bermasalah tidak dianggap positif.
    """

    sentences = split_sentences(
        f"{title}. {content}"
    )

    contexts = []

    for sentence in sentences:

        # ----------------------------------------------------
        # 1. ABAIKAN NEGASI
        # ----------------------------------------------------

        if sentence_has_negation(sentence):
            continue

        # ----------------------------------------------------
        # 2. HARUS TERKAIT SATKER / AKTOR INTERNAL TARGET
        # ----------------------------------------------------

        has_satker = sentence_contains_satker(
            sentence
        )

        has_internal_actor = (
            sentence_contains_internal_actor(
                sentence
            )
        )

        if not (
            has_satker
            or has_internal_actor
        ):
            continue

        # ----------------------------------------------------
        # 3. CEK APAKAH ADA AKSI POSITIF
        # ----------------------------------------------------

        positive_hits = regex_hits(
            sentence,
            POSITIVE_ACTION_PATTERNS,
        )

        # ----------------------------------------------------
        # 4. CEK APAKAH ADA KEGIATAN RESMI
        # ----------------------------------------------------

        official_hits = regex_hits(
            sentence,
            OFFICIAL_ACTIVITY_PATTERNS,
        )

        # Tidak ada indikator positif.
        if not (
            positive_hits
            or official_hits
        ):
            continue

        # ----------------------------------------------------
        # 5. CEK NEGATIF KUAT
        #
        # Jika aktor target adalah pihak bermasalah,
        # jangan masukkan sebagai positif.
        # ----------------------------------------------------

        negative_hits = regex_hits(
            sentence,
            NEGATIVE_STRONG_PATTERNS,
        )

        if negative_hits:
            continue

        # ----------------------------------------------------
        # 6. SIMPAN KONTEXT POSITIF
        # ----------------------------------------------------

        contexts.append(sentence)

    # Hilangkan context duplikat
    unique_contexts = []
    seen = set()
    
    for context in contexts:
        normalized = context.strip().lower()
    
        if normalized in seen:
            continue
    
        seen.add(normalized)
        unique_contexts.append(context)
    
    return unique_contexts[:20]


def find_official_activity_context(
    title: str,
    content: str,
) -> List[str]:

    sentences = split_sentences(
        f"{title}. {content}"
    )

    contexts = []

    for sentence in sentences:

        if sentence_has_negation(sentence):
            continue

        activity_hits = regex_hits(
            sentence,
            OFFICIAL_ACTIVITY_PATTERNS,
        )

        if not activity_hits:
            continue

        if not (
            sentence_contains_satker(sentence)
            or sentence_contains_internal_actor(sentence)
        ):
            continue

        contexts.append(sentence)

    # Hilangkan context duplikat
    unique_contexts = []
    seen = set()
    
    for context in contexts:
        normalized = context.strip().lower()
    
        if normalized in seen:
            continue
    
        seen.add(normalized)
        unique_contexts.append(context)
    
    return unique_contexts[:20]


# ============================================================
# NEGATIVE CONTEXT
# ============================================================


def find_negative_context(
    title: str,
    content: str,
) -> List[str]:

    """
    Mencari kalimat yang benar-benar menunjukkan
    masalah negatif langsung terhadap satker atau
    aktor internal kejaksaan.

    Prinsip:
    1. Kalimat yang dinegasikan tidak dianggap negatif.
    2. Kalimat keberhasilan penegakan hukum tidak dianggap negatif.
    3. Kalimat kegiatan resmi tidak dianggap negatif.
    4. Harus ada hubungan langsung dengan satker
       atau aktor internal kejaksaan.
    5. Hanya kalimat yang memenuhi NEGATIVE_STRONG_PATTERNS
       yang dikembalikan.
    """

    sentences = split_sentences(
        f"{title}. {content}"
    )

    contexts = []

    for sentence in sentences:

        sentence = normalize_text(
            sentence
        )

        if not sentence:
            continue

        # ====================================================
        # NEGASI / BANTAHAN
        # ====================================================

        if sentence_has_negation(
            sentence
        ):
            continue

        # ====================================================
        # KEBERHASILAN PENEGAKAN HUKUM
        #
        # Contoh:
        # "Kejari berhasil menangkap tersangka."
        # "Kejari mengungkap kasus korupsi."
        #
        # Jangan dianggap negatif hanya karena ada
        # kata "tersangka", "korupsi", "kasus", dll.
        # ====================================================

        positive_hits = regex_hits(
            sentence,
            POSITIVE_ACTION_PATTERNS,
        )

        if positive_hits:
            continue

        # ====================================================
        # KEGIATAN RESMI
        #
        # Contoh:
        # apel, rapat, FGD, kunjungan, koordinasi,
        # monitoring, evaluasi, sosialisasi, dll.
        # ====================================================

        official_hits = regex_hits(
            sentence,
            OFFICIAL_ACTIVITY_PATTERNS,
        )

        if official_hits:
            continue

        # ====================================================
        # NEGATIVE STRONG PATTERN
        # ====================================================

        hits = regex_hits(
            sentence,
            NEGATIVE_STRONG_PATTERNS,
        )

        if not hits:
            continue

        # ====================================================
        # HUBUNGAN LANGSUNG DENGAN SATKER / INTERNAL
        # ====================================================

        if not (
            sentence_contains_satker(
                sentence
            )
            or sentence_contains_internal_actor(
                sentence
            )
        ):
            continue

        # ====================================================
        # SIMPAN KONTEKS
        # ====================================================

        contexts.append(
            sentence
        )

    return contexts[:20]

 
# ============================================================
# HANDLING CONTEXT
# ============================================================


def find_handling_context(
    title: str,
    content: str,
) -> List[str]:
    """
    Mencari konteks yang perlu ditangani/dipantau.

    Syarat:
    1. Kalimat tidak mengandung negasi.
    2. Kalimat mengandung pola HANDLING_PATTERNS.
    3. Kalimat berkaitan dengan satker atau aktor internal.

    Handling tidak otomatis berarti masalah berat terhadap satker.
    Konteks ini digunakan untuk berita hukum/isu yang perlu dipantau.
    """

    sentences = split_sentences(
        f"{title}. {content}"
    )

    contexts = []

    for sentence in sentences:

        # ----------------------------------------------------
        # NEGASI
        # ----------------------------------------------------

        if sentence_has_negation(
            sentence
        ):
            continue

        # ----------------------------------------------------
        # HANDLING PATTERN
        # ----------------------------------------------------

        if not regex_hits(
            sentence,
            HANDLING_PATTERNS,
        ):
            continue

        # ----------------------------------------------------
        # HARUS BERKAITAN DENGAN SATKER
        # ATAU AKTOR INTERNAL
        # ----------------------------------------------------

        if not (
            sentence_contains_satker(
                sentence
            )
            or sentence_contains_internal_actor(
                sentence
            )
        ):
            continue

        contexts.append(
            sentence
        )

    return contexts[:20]



    
# ============================================================
# POSITIVE SCORE
# ============================================================


def calculate_positive_score(
    title: str,
    content: str,
) -> int:
    """
    Menghitung skor positif berdasarkan konteks yang benar-benar
    berkaitan dengan satker.

    Prinsip:
    - Aksi keberhasilan penegakan hukum mendapat bobot tinggi.
    - Kegiatan resmi satker mendapat bobot positif.
    - Hubungan langsung dengan satker menjadi syarat utama.
    - Keyword hukum seperti kasus, tersangka, narkotika, penyidikan,
      dll. TIDAK otomatis menghasilkan skor positif.
    - Menghindari double counting berlebihan.
    """

    title = normalize_text(title)
    content = normalize_text(content)

    score = 0

    # ========================================================
    # CONTEXT
    # ========================================================

    positive_context = find_positive_context(
        title,
        content,
    ) or []

    official_context = (
        find_official_activity_context(
            title,
            content,
        )
    )

    # ========================================================
    # POSITIVE CONTEXT YANG BENAR-BENAR TERKAIT SATKER
    # ========================================================

    positive_satker_context = [
        sentence
        for sentence in positive_context
        if (
            sentence_contains_satker(sentence)
            or sentence_contains_internal_actor(sentence)
        )
    ]

    official_satker_context = [
        sentence
        for sentence in official_context
        if (
            sentence_contains_satker(sentence)
            or sentence_contains_internal_actor(sentence)
        )
    ]

    # ========================================================
    # 1. KEBERHASILAN PENEGAKAN HUKUM
    # ========================================================

    if positive_satker_context:

        # Ada konteks keberhasilan yang secara langsung
        # berkaitan dengan satker/aktor internal.
        score += 12

        # Tambahan jika ada lebih dari satu konteks positif.
        if len(positive_satker_context) >= 2:
            score += 4

        if len(positive_satker_context) >= 3:
            score += 3

    # ========================================================
    # 2. KEGIATAN RESMI SATKER
    # ========================================================

    if official_satker_context:

        # Kegiatan resmi satker merupakan indikator positif.
        score += 8

        if len(official_satker_context) >= 2:
            score += 3

        if len(official_satker_context) >= 3:
            score += 2

    # ========================================================
    # 3. AKSI POSITIF DI JUDUL
    # ========================================================

    title_positive_hits = regex_hits(
        title.lower(),
        POSITIVE_ACTION_PATTERNS,
    )

    if title_positive_hits:

        # Jangan beri bonus judul apabila judul positif
        # tidak menyebut/berhubungan dengan satker.
        if (
            sentence_contains_satker(title)
            or sentence_contains_internal_actor(title)
        ):
            score += 7

    # ========================================================
    # 4. KEGIATAN RESMI DI JUDUL
    # ========================================================

    title_official_hits = regex_hits(
        title.lower(),
        OFFICIAL_ACTIVITY_PATTERNS,
    )

    if title_official_hits:

        if (
            sentence_contains_satker(title)
            or sentence_contains_internal_actor(title)
        ):
            score += 5

    # ========================================================
    # 5. BONUS HUBUNGAN LANGSUNG DENGAN SATKER
    # ========================================================

    if (
        positive_satker_context
        or official_satker_context
    ):

        score += 4

    # ========================================================
    # BATAS MAKSIMUM
    # ========================================================

    return min(
        score,
        40,
    )


# ============================================================
# NEGATIVE SCORE
# ============================================================

def calculate_negative_score(
    title: str,
    content: str,
) -> int:
    """
    Menghitung skor negatif berdasarkan konteks.

    Prinsip:
    - Kata hukum seperti kasus, tersangka, penyidikan,
      narkotika, korupsi, dll. TIDAK otomatis negatif.
    - Negatif hanya dihitung jika masalah benar-benar
      berkaitan dengan satker atau aktor internal.
    - Keberhasilan penegakan hukum tidak dianggap negatif.
    - Kalimat negasi/bantahan tidak dianggap negatif.
    - Konteks negatif yang sama tidak dihitung berulang kali.
    """

    title = normalize_text(title)
    content = normalize_text(content)

    # ========================================================
    # NEGATIVE CONTEXT
    # ========================================================

    contexts = find_negative_context(
        title,
        content,
    )

    if not contexts:
        return 0

    score = 0

    # Mencegah kalimat yang sama dihitung berulang
    seen_contexts = set()

    for context in contexts:

        context = normalize_text(context)

        if not context:
            continue

        context_key = context.lower()

        if context_key in seen_contexts:
            continue

        seen_contexts.add(
            context_key
        )

        # ====================================================
        # NEGASI / BANTAHAN
        # ====================================================

        if sentence_has_negation(
            context
        ):
            continue

        # ====================================================
        # POSITIVE OVERRIDE
        #
        # Contoh:
        # "Kejari berhasil menangkap tersangka..."
        #
        # Jangan dianggap negatif hanya karena terdapat
        # kata "tersangka", "kasus", "narkotika", dll.
        # ====================================================

        if regex_hits(
            context,
            POSITIVE_ACTION_PATTERNS,
        ):
            continue

        if regex_hits(
            context,
            OFFICIAL_ACTIVITY_PATTERNS,
        ):
            continue

        # ====================================================
        # HARUS ADA HUBUNGAN DENGAN SATKER / INTERNAL ACTOR
        # ====================================================

        has_satker = (
            sentence_contains_satker(
                context
            )
        )

        has_internal_actor = (
            sentence_contains_internal_actor(
                context
            )
        )

        if not (
            has_satker
            or has_internal_actor
        ):
            continue

        # ====================================================
        # NEGATIVE SCORE
        # ====================================================

        # Konteks negatif yang benar-benar menyebut
        # satker/internal actor = dasar negatif kuat.
        score += 12

        # Aktor internal membuat konteks lebih sensitif.
        if has_internal_actor:
            score += 4

        # Batasi agar satu konteks tidak terlalu dominan.
        score = min(
            score,
            32,
        )

    # ========================================================
    # NEGATIVE TITLE CONTEXT
    # ========================================================

    title_contexts = []

    for sentence in split_sentences(
        title
    ):

        sentence = normalize_text(
            sentence
        )

        if not sentence:
            continue

        if not (
            sentence_contains_satker(
                sentence
            )
            or sentence_contains_internal_actor(
                sentence
            )
        ):
            continue

        if not regex_hits(
            sentence,
            NEGATIVE_STRONG_PATTERNS,
        ):
            continue

        if sentence_has_negation(
            sentence
        ):
            continue

        if regex_hits(
            sentence,
            POSITIVE_ACTION_PATTERNS,
        ):
            continue

        if regex_hits(
            sentence,
            OFFICIAL_ACTIVITY_PATTERNS,
        ):
            continue

        title_contexts.append(
            sentence
        )

    # ========================================================
    # TITLE SCORE
    #
    # Judul negatif merupakan sinyal tambahan,
    # bukan pengganti konteks isi.
    # ========================================================

    if title_contexts:

        score += 8

    # ========================================================
    # FINAL
    # ========================================================

    return min(
        score,
        40,
    )
    
# ============================================================
# HANDLING SCORE
# ============================================================

def calculate_handling_score(
    title: str,
    content: str,
) -> int:

    contexts = find_handling_context(
        title,
        content,
    )

    if not contexts:
        return 0

    score = 0

    for context in contexts:

        score += 3

        if sentence_contains_satker(
            context
        ):

            score += 2

        if sentence_contains_internal_actor(
            context
        ):

            score += 2

    return min(
        score,
        30,
    )


# ============================================================
# CLASSIFIER
# ============================================================


def classify_article(
    title: str,
    content: str,
) -> Dict[str, Any]:

    title = normalize_text(
        title
    )

    content = normalize_text(
        content
    )

    full = (
        f"{title}. {content}"
    ).lower()

    # ========================================================
    # SATKER
    # ========================================================

    satker_matches = (
        find_satker_matches(
            title,
            content,
        )
    )

    satker_location = (
        find_satker_match_location(
            title,
            content,
        )
    )

    satker_context = (
        get_satker_context_sentences(
            title,
            content,
        )
    )

    # ========================================================
    # CONTEXT
    # ========================================================

    positive_context = (
        find_positive_context(
            title,
            content,
        )
    )

    official_context = (
        find_official_activity_context(
            title,
            content,
        )
        or []
    )

    negative_context = (
        find_negative_context(
            title,
            content,
        )
    )

    handling_context = (
        find_handling_context(
            title,
            content,
        )
    )

    # ========================================================
    # SCORE
    # ========================================================

    negative_score = (
        calculate_negative_score(
            title,
            content,
        )
    )

    handling_score = (
        calculate_handling_score(
            title,
            content,
        )
    )

    positive_score = (
        calculate_positive_score(
            title,
            content,
        )
    )

    # ========================================================
    # HITS
    # ========================================================

    positive_hits = (
        regex_hits(
            full,
            POSITIVE_ACTION_PATTERNS,
        )
        + regex_hits(
            full,
            OFFICIAL_ACTIVITY_PATTERNS,
        )
    )

    negative_hits = regex_hits(
        full,
        NEGATIVE_STRONG_PATTERNS,
    )

    handling_hits = regex_hits(
        full,
        HANDLING_PATTERNS,
    )

    # ========================================================
    # NEGATION
    # ========================================================

    negated_danger = any(
        has_negation_near(
            full,
            term,
        )
        for term
        in DANGER_TITLE_TERMS
    )

    # ========================================================
    # POSITIVE SATKER CONTEXT
    # ========================================================

    positive_satker_context = [
        sentence
        for sentence
        in (
            positive_context
            + official_context
        )
        if sentence_contains_satker(
            sentence
        )
    ]

    # ========================================================
    # NEGATIVE DIRECTNESS
    # ========================================================

    direct_negative = bool(
        negative_context
    )

    # ========================================================
    # CLASSIFICATION
    # ========================================================

    category = "Netral"

    # ========================================================
    # RULE 1
    #
    # NEGATIF KUAT
    #
    # Ini memiliki prioritas tertinggi.
    #
    # Hanya berlaku apabila:
    # - ada konteks negatif langsung
    # - score cukup kuat
    # - bukan kalimat yang dinegasikan
    # ========================================================

    if (
        direct_negative
        and negative_score >= 12
        and not negated_danger
    ):

        category = "Negatif Kuat"

    # ========================================================
    # RULE 2
    #
    # KEGIATAN RESMI SATKER
    #
    # Keyword hukum seperti:
    # kasus, perkara, tersangka, korupsi,
    # narkotika, penyidikan, dll.
    #
    # TIDAK BOLEH otomatis membatalkan
    # kegiatan resmi.
    # ========================================================

    elif (
        official_context
        and check_satker_relevance(
            title,
            content,
        )
    ):

        category = "Positif"

    # ========================================================
    # RULE 3
    #
    # KEBERHASILAN PENEGAKAN HUKUM
    #
    # Misalnya:
    # - berhasil menangkap
    # - berhasil mengungkap
    # - menyita
    # - memusnahkan
    # - menghentikan penuntutan
    # - menetapkan tersangka dalam proses resmi
    #
    # Selama bukan negative direct context.
    # ========================================================

    elif (
        positive_context
        and check_satker_relevance(
            title,
            content,
        )
    ):

        category = "Positif"

    # ========================================================
    # RULE 4
    #
    # PERLU PENANGANAN
    #
    # Isu perlu dipantau tetapi belum memenuhi
    # kriteria negatif kuat.
    # ========================================================

    elif (
        handling_score >= 3
        and handling_context
    ):

        category = "Perlu Penanganan"

    # ========================================================
    # RULE 5
    #
    # POSITIVE SCORE
    # ========================================================

    elif positive_score >= 3:

        category = "Positif"

    # ========================================================
    # RULE 6
    #
    # DEFAULT
    # ========================================================

    else:

        category = "Netral"

    # ========================================================
    # NEGATION OVERRIDE
    # ========================================================

    if (
        negated_danger
        and category == "Negatif Kuat"
    ):

        if (
            handling_score >= 3
            and handling_context
        ):

            category = (
                "Perlu Penanganan"
            )

        elif (
            positive_context
            or official_context
        ):

            category = "Positif"

        else:

            category = "Netral"

    # ========================================================
    # POSITIVE DOMINANCE
    #
    # Hanya berlaku jika tidak ada negative direct.
    # ========================================================

    if (
        positive_satker_context
        and not direct_negative
        and category == "Perlu Penanganan"
    ):

        category = "Positif"

    # ========================================================
    # PRIORITY
    # ========================================================

    priority = (
        PRIORITY_BY_CATEGORY[
            category
        ]
    )

    # ========================================================
    # LEGAL KEYWORDS
    # ========================================================

    detected_keywords = sorted(
        {
            word
            for word
            in LEGAL_EVENT_TERMS
            if re.search(
                r"\b"
                + re.escape(word)
                + r"\b",
                full,
                re.I,
            )
        }
    )

    # ========================================================
    # RESULT
    # ========================================================

    return {

        "category": category,

        "priority": priority,

        "negative_score": int(
            negative_score
        ),

        "handling_score": int(
            handling_score
        ),

        "positive_score": int(
            positive_score
        ),

        "positive_hits": (
            positive_hits[:15]
        ),

        "negative_hits": (
            negative_hits[:15]
        ),

        "handling_hits": (
            handling_hits[:15]
        ),

        "keywords": (
            detected_keywords
        ),

        "satker_matches": (
            satker_matches[:20]
        ),

        "satker_match_location": (
            satker_location
        ),

        "satker_context": (
            satker_context[:20]
        ),

        "strong_context": (
            negative_context[:20]
        ),

        "positive_context": (
            (
                positive_context
                + official_context
            )[:20]
        ),

        "handling_context": (
            handling_context[:20]
        ),
    }


# ============================================================
# GOOGLE NEWS RSS
# ============================================================

def extract_feed_date(
    entry: Any,
) -> Optional[datetime]:

    for key in (
        "published_parsed",
        "updated_parsed",
        "created_parsed",
    ):

        value = entry.get(
            key
        )

        if value:

            try:

                return datetime(
                    value.tm_year,
                    value.tm_mon,
                    value.tm_mday,
                    value.tm_hour,
                    value.tm_min,
                    value.tm_sec,
                    tzinfo=timezone.utc,
                )

            except Exception:

                pass

    for key in (
        "published",
        "updated",
        "created",
    ):

        value = entry.get(
            key
        )

        if value:

            parsed = parse_date_safe(
                value
            )

            if parsed:

                return parsed

    return None


def parse_google_news_feed(
    query: str,
) -> List[Dict[str, Any]]:

    encoded = urllib.parse.quote_plus(query)

    url = (
        "https://news.google.com/rss/search?"
        f"q={encoded}"
        "&hl=id"
        "&gl=ID"
        "&ceid=ID:id"
    )

    last_error = None

    for attempt in range(1, RSS_MAX_RETRIES + 1):

        try:

            response = SESSION.get(
                url,
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True,
            )

            status = response.status_code

            # Retry khusus rate-limit / transient server errors.
            if status in {429, 502, 503, 504}:

                retry_after = response.headers.get(
                    "Retry-After"
                )

                if retry_after:
                    try:
                        delay = max(0.0, float(retry_after))
                    except (TypeError, ValueError):
                        delay = RSS_BACKOFF_BASE * (2 ** (attempt - 1))
                else:
                    delay = RSS_BACKOFF_BASE * (2 ** (attempt - 1))

                if attempt < RSS_MAX_RETRIES:

                    print(
                        f"[RSS RETRY] query={query} | "
                        f"status={status} | "
                        f"attempt={attempt}/{RSS_MAX_RETRIES} | "
                        f"sleep={delay:.1f}s"
                    )

                    time.sleep(delay)
                    continue

                response.raise_for_status()

            response.raise_for_status()

            feed = feedparser.parse(response.content)

            print(
                f"[RSS DEBUG] query={query} | "
                f"status={response.status_code} | "
                f"bytes={len(response.content)} | "
                f"entries={len(feed.entries)} | "
                f"bozo={getattr(feed, 'bozo', False)}"
            )

            if getattr(feed, "bozo", False):

                bozo_exception = getattr(
                    feed,
                    "bozo_exception",
                    None,
                )

                if bozo_exception:

                    print(
                        f"[RSS BOZO ERROR] "
                        f"{query} -> "
                        f"{type(bozo_exception).__name__}: "
                        f"{bozo_exception}"
                    )

            if not feed.entries:

                print(
                    f"[RSS EMPTY] "
                    f"Tidak ada entry untuk: {query}"
                )

                return []

            rows = []

            for entry in feed.entries[:MAX_ARTICLES_PER_FEED]:

                link = normalize_url(
                    entry.get("link")
                )

                if not link:
                    continue

                published = extract_feed_date(entry)

                source_value = entry.get("source")
                source_url = ""

                if isinstance(source_value, dict):
                    source = source_value.get("title", "")
                    source_url = source_value.get("href", "") or source_value.get("url", "")
                else:
                    source = source_value or ""

                rows.append(
                    {
                        "title": normalize_text(
                            entry.get("title")
                        ),
                        "link": link,
                        "published_date": (
                            published.isoformat()
                            if published
                            else None
                        ),
                        "source": normalize_text(source),
                        "source_url": _clean_candidate_url(source_url),
                        "rss_description": normalize_text(
                            entry.get("summary")
                        ),
                    }
                )

            print(
                f"[RSS OK] "
                f"{query} -> {len(rows)} kandidat"
            )

            return rows

        except requests.RequestException as exc:

            last_error = exc

            if attempt < RSS_MAX_RETRIES:

                delay = RSS_BACKOFF_BASE * (
                    2 ** (attempt - 1)
                )

                print(
                    f"[RSS RETRY] query={query} | "
                    f"error={type(exc).__name__}: {exc} | "
                    f"attempt={attempt}/{RSS_MAX_RETRIES} | "
                    f"sleep={delay:.1f}s"
                )

                time.sleep(delay)
                continue

            break

        except Exception as exc:

            last_error = exc
            break

    print(
        f"[RSS ERROR] "
        f"{query} -> "
        f"{type(last_error).__name__ if last_error else 'UnknownError'}: "
        f"{last_error}"
    )

    return []


# ============================================================
# COLLECT
# ============================================================


def collect_candidates() -> List[Dict[str, Any]]:
    """
    Mengumpulkan kandidat artikel dari seluruh SEARCH_TARGETS.

    Fungsi ini hanya bertugas:
    - mengambil hasil RSS
    - normalisasi URL
    - dedupe kandidat berdasarkan URL RSS
    - mempertahankan kandidat dengan metadata/deskripsi paling lengkap

    Filter tahun, relevansi satker, konten, dan klasifikasi
    dilakukan di process_candidate().
    """

    all_rows: Dict[str, Dict[str, Any]] = {}

    total_raw = 0
    skipped_empty_link = 0
    replaced_with_better = 0

    for query_index, query in enumerate(SEARCH_TARGETS):

        # Jeda sebelum query berikutnya untuk mengurangi risiko 429/503.
        # Diterapkan walaupun query sebelumnya gagal atau mengembalikan 0 hasil.
        if query_index > 0 and RSS_QUERY_DELAY > 0:
            time.sleep(RSS_QUERY_DELAY)

        print(
            f"[RSS] Mencari: {query}"
        )

        try:
            rows = parse_google_news_feed(query)

        except Exception as exc:

            print(
                f"[RSS ERROR] "
                f"{query} -> "
                f"{type(exc).__name__}: "
                f"{exc}"
            )

            continue

        if not rows:
            continue

        total_raw += len(rows)

        for row in rows:

            if not isinstance(row, dict):
                continue

            # ------------------------------------------------
            # NORMALISASI LINK
            # ------------------------------------------------

            raw_link = row.get("link")

            link = normalize_url(
                raw_link
            )

            if not link:

                skipped_empty_link += 1

                continue

            # Simpan URL yang sudah dinormalisasi.
            row["link"] = link

            # ------------------------------------------------
            # NORMALISASI DATA DASAR
            # ------------------------------------------------

            row["title"] = normalize_text(
                row.get("title")
            )

            row["rss_description"] = normalize_text(
                row.get("rss_description")
            )

            row["source"] = (
                normalize_text(
                    row.get("source")
                )
                or "Google News"
            )

            # ------------------------------------------------
            # HITUNG KELENGKAPAN KANDIDAT
            # ------------------------------------------------
            #
            # Kandidat yang mempunyai:
            # - title
            # - description
            # - published_date
            # - source
            #
            # dianggap lebih lengkap.
            # ------------------------------------------------

            current_score = (
                bool(row.get("title"))
                + bool(row.get("rss_description"))
                + bool(row.get("published_date"))
                + bool(row.get("source"))
            )

            current_description_length = len(
                row.get(
                    "rss_description",
                    ""
                )
            )

            # ------------------------------------------------
            # DEDUPE DALAM HASIL RSS
            # ------------------------------------------------

            if link not in all_rows:

                row["_candidate_score"] = (
                    current_score
                )

                row["_description_length"] = (
                    current_description_length
                )

                all_rows[link] = row

                continue

            existing = all_rows[link]

            existing_score = (
                existing.get(
                    "_candidate_score",
                    0
                )
            )

            existing_description_length = (
                existing.get(
                    "_description_length",
                    0
                )
            )

            # ------------------------------------------------
            # PILIH DATA YANG LEBIH LENGKAP
            # ------------------------------------------------

            replace = False

            if current_score > existing_score:

                replace = True

            elif (
                current_score == existing_score
                and current_description_length
                > existing_description_length
            ):

                replace = True

            if replace:

                row["_candidate_score"] = (
                    current_score
                )

                row["_description_length"] = (
                    current_description_length
                )

                all_rows[link] = row

                replaced_with_better += 1

    # HAPUS FIELD INTERNAL
    # --------------------------------------------------------

    candidates = []

    for row in all_rows.values():

        row.pop(
            "_candidate_score",
            None
        )

        row.pop(
            "_description_length",
            None
        )

        candidates.append(
            row
        )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    print(
        f"[RSS] Total hasil mentah     : "
        f"{total_raw}"
    )

    print(
        f"[RSS] Link kosong dilewati   : "
        f"{skipped_empty_link}"
    )

    print(
        f"[RSS] Kandidat setelah dedupe: "
        f"{len(candidates)}"
    )

    print(
        f"[RSS] Kandidat diganti data "
        f"lebih lengkap               : "
        f"{replaced_with_better}"
    )

    return candidates



# ============================================================
# PROCESS CANDIDATE
# ============================================================

def process_candidate(
candidate: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Memproses satu kandidat artikel.
    

    Alur:
    1. Normalisasi link
    2. Validasi tanggal RSS
    3. Fetch halaman
    4. Ekstraksi konten
    5. Fallback ke RSS description
    6. Validasi relevansi satker
    7. Validasi tanggal final
    8. Klasifikasi
    9. Membentuk record artikel
    
    Fetch halaman yang gagal tidak langsung menggagalkan
    artikel jika RSS description masih cukup untuk diproses.
    """
    
    result = {
        "ok": False,
        "article": None,
        "reason": "",
    }

    # ========================================================
    # BASIC DATA
    # ========================================================
    
    title = normalize_text(
        candidate.get("title")
    )
    
    rss_link = normalize_url(
        candidate.get("link")
    )
    
    rss_date = parse_date_safe(
        candidate.get("published_date")
    )
    
    rss_description = normalize_text(
        candidate.get("rss_description")
    )
    
    # ========================================================
    # LINK
    # ========================================================
    
    if not rss_link:
    
        result["reason"] = "link kosong"
    
        return result
    
    # ========================================================
    # TITLE
    # ========================================================
    
    if not title:
    
        result["reason"] = "judul kosong"
    
        return result
    
    # ========================================================
    # FILTER TANGGAL RSS
    # ========================================================
    
    if (
        rss_date
        and not is_article_2026(
            rss_date
        )
    ):
    
        result["reason"] = (
            "bukan tahun target"
        )
    
        return result
    
    # ========================================================
    # FETCH
    # ========================================================
    
    final_url = rss_link
    raw_html = ""
    
    try:
        fetched_url, raw_html = fetch_webpage_content(rss_link)
        final_url, url_resolution_method = resolve_article_url_details(
            rss_url=rss_link,
            response_url=fetched_url,
            raw_html=raw_html,
            source_url=candidate.get("source_url", ""),
            title=title,
        )
        print(
            f"[URL] RSS={rss_link} -> RESOLVED={final_url}"
        )
        if _is_google_news_url(final_url):
            print(
                "[URL WARNING] URL masih Google News; "
                "canonical media URL tidak ditemukan."
            )
    
    except Exception as exc:
        print(
            "[FETCH WARNING] "
            f"{rss_link} -> "
            f"{type(exc).__name__}: "
            f"{exc}"
        )
        final_url = normalize_url(rss_link)
        url_resolution_method = "fetch_failed_google_fallback"
        raw_html = ""
    
    if not final_url:
        final_url = rss_link
        url_resolution_method = "google_fallback"
    
    # ========================================================
    # CONTENT
    # ========================================================
    
    content = ""
    
    if raw_html:
    
        try:
    
            content = (
                extract_article_text(
                    raw_html
                )
            )
    
        except Exception as exc:
    
            print(
                "[EXTRACT WARNING] "
                f"{rss_link} -> "
                f"{type(exc).__name__}: "
                f"{exc}"
            )
    
    # ========================================================
    # FALLBACK RSS DESCRIPTION
    #
    # Penting:
    # Jika website tidak bisa di-fetch tetapi RSS description
    # cukup panjang, artikel tetap dapat diproses.
    # ========================================================
    
    if (
        len(content)
        < MIN_CONTENT_LENGTH
    ):
    
        if (
            len(rss_description)
            >= MIN_CONTENT_LENGTH
        ):
    
            content = rss_description
    
    # ========================================================
    # KONTEN TERLALU PENDEK
    # ========================================================
    
    if (
        len(content)
        < MIN_CONTENT_LENGTH
    ):
    
        if not raw_html:
    
            result["reason"] = (
                "fetch gagal / halaman kosong "
                "dan RSS description terlalu pendek"
            )
    
        else:
    
            result["reason"] = (
                "konten terlalu pendek"
            )
    
        return result
    
    # ========================================================
    # RELEVANCE SATKER
    # ========================================================
    
    if not check_satker_relevance(
        title,
        content,
    ):
    
        result["reason"] = (
            "tidak relevan dengan satker"
        )
    
        return result
    
    # ========================================================
    # TANGGAL FINAL
    #
    # Jangan menggunakan datetime.now().
    # Artikel tanpa tanggal tidak boleh otomatis
    # dianggap sebagai artikel tahun 2026.
    # ========================================================
    
    published = rss_date
    
    if not published:
    
        try:
    
            published = (
                extract_published_date(
                    candidate
                )
            )
    
        except Exception as exc:
    
            print(
                "[DATE WARNING] "
                f"{rss_link} -> "
                f"{type(exc).__name__}: "
                f"{exc}"
            )
    
    # ========================================================
    # TANGGAL TIDAK DITEMUKAN
    # ========================================================
    
    if not published:
    
        result["reason"] = (
            "tanggal artikel tidak ditemukan"
        )
    
        return result
    
    # ========================================================
    # VALIDASI TAHUN FINAL
    # ========================================================
    
    if not is_article_2026(
        published
    ):
    
        result["reason"] = (
            "tanggal artikel bukan 2026"
        )
    
        return result
    
    # ========================================================
    # CLASSIFICATION
    # ========================================================
    
    try:
    
        classification = (
            classify_article(
                title,
                content,
            )
        )
    
    except Exception as exc:
    
        result["reason"] = (
            f"classification gagal: "
            f"{type(exc).__name__}"
        )
    
        return result
    
    # ========================================================
    # ARTICLE
    # ========================================================
    
    article = {
    
        "title": title,
    
        "link": final_url,

        # Internal observability field. Dihapus sebelum upsert ke database.py.
        "_url_resolution_method": url_resolution_method,
    
        "content": content[
            :15000
        ],
    
        "published_date": (
            published.isoformat()
        ),
    
        "source": (
            normalize_text(
                candidate.get(
                    "source"
                )
            )
            or "Google News"
        ),

        "publisher": (
            get_publisher_from_title(title)
            or (urllib.parse.urlparse(final_url).netloc.lower().replace("www.", "")
                if final_url and "news.google.com" not in str(final_url) else "")
        ),
    
        "category": (
            classification.get(
                "category",
                "Netral",
            )
        ),
    
        "priority": (
            classification.get(
                "priority",
                "Rendah",
            )
        ),
    
        "negative_score": int(
            classification.get(
                "negative_score",
                0,
            )
        ),
    
        "handling_score": int(
            classification.get(
                "handling_score",
                0,
            )
        ),
    
        "positive_score": int(
            classification.get(
                "positive_score",
                0,
            )
        ),
    
        "detected_keywords": (
            classification.get(
                "keywords",
                [],
            )
        ),
    
        "satker_matches": (
            classification.get(
                "satker_matches",
                [],
            )
        ),
    
        "satker_match_location": (
            classification.get(
                "satker_match_location",
                "",
            )
        ),
    
        "strong_context": (
            classification.get(
                "strong_context",
                [],
            )
        ),
    
        "positive_context": (
            classification.get(
                "positive_context",
                [],
            )
        ),
    
        "handling_context": (
            classification.get(
                "handling_context",
                [],
            )
        ),
    }
    
    # ========================================================
    # SUCCESS
    # ========================================================
    
    result["ok"] = True
    
    result["article"] = article
    
    result["reason"] = "valid"
    
    return result
   



# ============================================================
# RISK CONTEXT ENGINE
# ============================================================
# Mengaktifkan seluruh 5 faktor Risk Engine tanpa mengubah database.py.
# Konteks dihitung READ-ONLY dari artikel yang sudah ada + artikel baru.
# ============================================================

RISK_EVENT_SIMILARITY_THRESHOLD = 0.62
RISK_STRONG_TITLE_SIMILARITY = 0.82
RISK_MAX_RELATED_ARTICLES = 100
RISK_RECENT_DAYS = 7

# Kata yang terlalu umum untuk menjadi penentu utama event.
RISK_GENERIC_EVENT_TOKENS = {
    "deli", "serdang", "kejari", "kejaksaan", "negeri", "kajari",
    "cabang", "cabjari", "sumut", "sumatera", "utara", "terkait",
    "dengan", "setelah", "resmi", "terhadap", "ungkap", "dalam",
    "untuk", "yang", "dan", "atau", "ini", "itu", "jadi", "jadi",
    "kini", "saat", "sebut", "kata", "menurut", "berikut", "diperiksa",
}

# Anchor event: kata yang biasanya menjelaskan kejadian inti.
RISK_EVENT_ANCHOR_TOKENS = {
    # Penegakan hukum / masalah
    "korupsi", "narkotika", "narkoba", "tersangka", "terdakwa", "pidana",
    "penyidikan", "penyelidikan", "penuntutan", "perkara", "pengadilan",
    "sidang", "vonis", "dakwaan", "suap", "gratifikasi", "penggeledahan",
    "penyitaan", "penangkapan", "ditangkap", "ditangkapnya", "diamankan",
    "dicopot", "pencopotan", "dipanggil", "pelanggaran", "kode", "etik",
    "diganti", "penggantinya", "pelantikan", "dilantik", "lantik", "plh",
    # Kegiatan/kebijakan yang cukup spesifik
    "sertifikasi", "wakaf", "tanah", "bunga", "pelakor", "bos", "dana",
    "desa", "lubuk", "pakam", "batu", "lokong", "revanda", "sitepu",
    "padang", "lawas", "sapta", "putra", "jamintel", "integritas",
}

# V3: proteksi context untuk kategori non-prioritas.
# Netral/Positif tetap dapat context untuk observability, tetapi context
# tidak boleh sendirian menaikkan risk ke MEDIUM/HIGH/CRITICAL.
RISK_NONPRIORITY_MAX_SCORE = 30


def _risk_article_fingerprint(article: Dict[str, Any]) -> str:
    """Fingerprint ringan untuk menghindari duplicate internal saat context dihitung."""
    url = normalize_url(article.get("link") or "")
    if url:
        return f"url:{url}"
    title = normalize_text(article.get("title") or "").lower()
    media = normalize_text(get_media_source(article)).lower()
    return f"title_media:{title}|{media}"


def _risk_unique_articles(all_articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deduplicate context tanpa menggabungkan artikel berbeda media."""
    unique = []
    seen = set()
    for item in all_articles:
        marker = _risk_article_fingerprint(item)
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(item)
    return unique


_RISK_BLOCK_CACHE = {}


def _risk_tokens(value: Any) -> set:
    text = normalize_text(value).lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return {token for token in text.split() if len(token) >= 4}


def _risk_event_tokens(article: Dict[str, Any]) -> set:
    """Token judul yang relevan untuk identitas event, tanpa kata institusi umum."""
    title_tokens = _risk_tokens(article.get("title"))
    return title_tokens - RISK_GENERIC_EVENT_TOKENS


def _risk_event_anchors(article: Dict[str, Any]) -> set:
    """Anchor event dari judul; fallback ke token judul non-generik yang cukup informatif."""
    tokens = _risk_event_tokens(article)
    anchors = tokens & RISK_EVENT_ANCHOR_TOKENS
    if anchors:
        return anchors
    # Untuk event non-hukum, token non-generik tetap dapat menjadi anchor.
    return {token for token in tokens if len(token) >= 6}


def _risk_event_similarity(article_a: Dict[str, Any], article_b: Dict[str, Any]) -> float:
    title_a = normalize_text(article_a.get("title"))
    title_b = normalize_text(article_b.get("title"))
    if not title_a or not title_b:
        return 0.0

    title_ratio = SequenceMatcher(None, title_a.lower(), title_b.lower()).ratio()
    title_tokens_a = _risk_event_tokens(article_a)
    title_tokens_b = _risk_event_tokens(article_b)
    title_token_ratio = (
        len(title_tokens_a & title_tokens_b) / len(title_tokens_a | title_tokens_b)
        if (title_tokens_a and title_tokens_b)
        else 0.0
    )

    content_a = normalize_text(article_a.get("content") or article_a.get("summary"))[:2000]
    content_b = normalize_text(article_b.get("content") or article_b.get("summary"))[:2000]
    content_tokens_a = _risk_tokens(content_a) - RISK_GENERIC_EVENT_TOKENS
    content_tokens_b = _risk_tokens(content_b) - RISK_GENERIC_EVENT_TOKENS
    content_ratio = (
        len(content_tokens_a & content_tokens_b) / len(content_tokens_a | content_tokens_b)
        if (content_tokens_a and content_tokens_b)
        else 0.0
    )

    return round(
        (title_ratio * 0.55)
        + (title_token_ratio * 0.30)
        + (content_ratio * 0.15),
        4,
    )


def _risk_same_url(article_a: Dict[str, Any], article_b: Dict[str, Any]) -> bool:
    url_a = normalize_url(article_a.get("link") or "")
    url_b = normalize_url(article_b.get("link") or "")
    return bool(url_a and url_b and url_a == url_b)


def _risk_same_title_media(article_a: Dict[str, Any], article_b: Dict[str, Any]) -> bool:
    title_a = normalize_text(article_a.get("title")).lower()
    title_b = normalize_text(article_b.get("title")).lower()
    if not title_a or not title_b or title_a != title_b:
        return False
    media_a = normalize_text(get_media_source(article_a)).lower()
    media_b = normalize_text(get_media_source(article_b)).lower()
    return bool(media_a and media_b and media_a == media_b)


def _risk_is_related_event(article: Dict[str, Any], other: Dict[str, Any]) -> Tuple[bool, float]:
    """Validasi dua tahap agar institusi/lokasi umum tidak membuat false cluster."""
    similarity = _risk_event_similarity(article, other)
    if similarity < RISK_EVENT_SIMILARITY_THRESHOLD:
        return False, similarity

    anchors_a = _risk_event_anchors(article)
    anchors_b = _risk_event_anchors(other)
    anchor_overlap = anchors_a & anchors_b

    # Judul yang sangat kuat boleh lolos tanpa anchor eksplisit.
    title_a = normalize_text(article.get("title"))
    title_b = normalize_text(other.get("title"))
    title_ratio = SequenceMatcher(None, title_a.lower(), title_b.lower()).ratio()

    if title_ratio >= RISK_STRONG_TITLE_SIMILARITY:
        return True, similarity

    # Untuk similarity normal, wajib ada anchor event yang sama.
    if not anchor_overlap:
        return False, similarity

    # Minimal dua anchor yang sama untuk mencegah event berbeda yang hanya
    # berbagi satu istilah umum seperti "dana", "desa", atau "korupsi".
    # Satu anchor tetap boleh jika judul sudah cukup dekat.
    if len(anchor_overlap) >= 2:
        return True, similarity
    if title_ratio >= 0.72:
        return True, similarity
    return False, similarity


def _build_risk_block_index(all_articles: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Membuat inverted index setelah dedup internal untuk mencegah recurrence palsu."""
    index = defaultdict(list)
    for item in _risk_unique_articles(all_articles):
        anchors = _risk_event_anchors(item)
        for anchor in anchors:
            index[anchor].append(item)
    return index


def _risk_candidate_articles(article: Dict[str, Any], all_articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Ambil kandidat berdasarkan anchor event; fallback terbatas untuk judul sangat kuat."""
    cache_key = (id(all_articles), len(all_articles), "v3")
    index = _RISK_BLOCK_CACHE.get(cache_key)
    if index is None:
        index = _build_risk_block_index(all_articles)
        _RISK_BLOCK_CACHE.clear()
        _RISK_BLOCK_CACHE[cache_key] = index

    candidates = []
    seen = set()
    for anchor in _risk_event_anchors(article):
        for item in index.get(anchor, []):
            marker = id(item)
            if marker not in seen:
                seen.add(marker)
                candidates.append(item)

    # Bila tidak ada anchor, jangan melakukan O(N) similarity scan.
    return candidates


def _risk_published_datetime(article: Dict[str, Any]) -> Optional[datetime]:
    value = article.get("published_date")
    if not value:
        return None
    try:
        parsed = date_parser.parse(str(value))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def build_risk_context(article: Dict[str, Any], all_articles: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Hitung media spread, recurrence, dan trend secara READ-ONLY."""
    article_date = _risk_published_datetime(article)
    related = []

    candidates = _risk_candidate_articles(article, all_articles)
    for other in candidates:
        if other is article:
            continue
        if _risk_same_url(article, other):
            continue
        is_related, similarity = _risk_is_related_event(article, other)
        if is_related:
            related.append((similarity, other))

    related.sort(key=lambda item: item[0], reverse=True)
    related = related[:RISK_MAX_RELATED_ARTICLES]
    event_articles = [article] + [item[1] for item in related]

    media_sources = set()
    for item in event_articles:
        source = normalize_text(get_media_source(item))
        if source:
            media_sources.add(source.lower())

    recurrence_count = 0
    recent_count = 0
    previous_count = 0
    seen_recurrence = set()

    if article_date is not None:
        current_ts = article_date.timestamp()
        recent_start = current_ts - (RISK_RECENT_DAYS * 86400)
        previous_start = current_ts - (RISK_RECENT_DAYS * 2 * 86400)

        for _, other in related:
            # Copy artikel dari media yang sama dengan judul sama tidak boleh
            # dihitung sebagai recurrence kedua kali.
            if _risk_same_title_media(article, other):
                continue

            other_link = normalize_url(other.get("link") or "")
            marker = other_link or normalize_text(other.get("title")).lower()
            if marker in seen_recurrence:
                continue
            seen_recurrence.add(marker)

            other_date = _risk_published_datetime(other)
            if other_date is None:
                continue
            ts = other_date.timestamp()
            if ts < current_ts:
                recurrence_count += 1
            if recent_start <= ts <= current_ts:
                recent_count += 1
            elif previous_start <= ts < recent_start:
                previous_count += 1

    if recent_count <= 0:
        trend_score = 0
    elif previous_count <= 0:
        trend_score = 15 if recent_count >= 3 else 10
    else:
        ratio = recent_count / previous_count
        if ratio >= 3:
            trend_score = 15
        elif ratio >= 2:
            trend_score = 12
        elif ratio >= 1.5:
            trend_score = 8
        elif ratio > 1:
            trend_score = 5
        else:
            trend_score = 0

    return {
        "media_count": max(1, len(media_sources)),
        "media_sources": media_sources,
        "recurrence_count": recurrence_count,
        "trend_score": trend_score,
        "related_count": len(related),
        "related_titles": [item.get("title", "") for _, item in related[:20]],
        "recent_count": recent_count,
        "previous_count": previous_count,
    }


def calculate_article_risk(article: Dict[str, Any], all_articles: List[Dict[str, Any]]) -> Dict[str, Any]:
    context = build_risk_context(article, all_articles)
    result = calculate_risk_score(
        article,
        media_count=context["media_count"],
        media_sources=context["media_sources"],
        recurrence_count=context["recurrence_count"],
        trend_score=context["trend_score"],
    )

    # V3 business guard: Netral/Positif tidak menjadi MEDIUM hanya karena
    # context amplification. Scoring engine tetap unchanged; guard berada
    # di application layer.
    category = str(article.get("category") or "Netral").strip()
    if category in {"Netral", "Positif"} and result["risk_score"] > RISK_NONPRIORITY_MAX_SCORE:
        result["risk_score"] = RISK_NONPRIORITY_MAX_SCORE
        result["risk_level"] = "LOW"
        result["reasons"] = list(result.get("reasons") or [])
        result["reasons"].append(
            "Proteksi V3: kategori Netral/Positif dibatasi LOW; context tidak boleh menjadi satu-satunya dasar prioritas."
        )

    result["context"] = context
    result["context"]["v3_nonpriority_guard"] = category in {"Netral", "Positif"}
    return result


# ============================================================
# TELEGRAM
# ============================================================

def telegram_enabled() -> bool:

    return bool(
        TELEGRAM_BOT_TOKEN
        and TELEGRAM_CHAT_ID
    )


def send_telegram_message(
    text: str,
) -> bool:

    if not telegram_enabled():

        return False

    url = (
        "https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:

        response = SESSION.post(
            url,
            data=payload,
            timeout=REQUEST_TIMEOUT,
        )

        response.raise_for_status()

        return True

    except Exception as exc:

        print(
            f"[TELEGRAM ERROR] "
            f"{type(exc).__name__}: {exc}"
        )

        return False


def telegram_text(
    article: Dict[str, Any],
) -> str:

    title = html.escape(
        normalize_text(
            article.get(
                "title"
            )
        )
    )

    category = html.escape(
        str(
            article.get(
                "category",
                "Netral",
            )
        )
    )

    priority = html.escape(
        str(
            article.get(
                "priority",
                "Rendah",
            )
        )
    )

    link = html.escape(
        normalize_url(
            article.get(
                "link"
            )
        )
    )

    return (
        f"<b>Patroli Siber "
        f"{TAHUN_TARGET}</b>\n"
        f"<b>Kategori:</b> "
        f"{category}\n"
        f"<b>Prioritas:</b> "
        f"{priority}\n"
        f"<b>Risk:</b> "
        f"{html.escape(str(article.get('risk_score', 'N/A')))} / 100 "
        f"({html.escape(str(article.get('risk_level', 'N/A')))})\n"
        f"<b>Satker:</b> "
        f"{html.escape(NAMA_SATKER)}\n\n"
        f"<b>{title}</b>\n"
        f"{link}"
    )


def is_current_month_year_article(
    article: Dict[str, Any],
) -> bool:
    """
    Telegram hanya untuk artikel pada bulan dan tahun berjalan.
    Waktu pembanding menggunakan UTC agar konsisten di GitHub Actions.
    """

    published = _risk_published_datetime(article)

    if published is None:
        return False

    now = datetime.now(timezone.utc)

    return (
        published.year == now.year
        and published.month == now.month
    )


def send_alert_if_needed(
    article: Dict[str, Any],
) -> bool:

    category = normalize_text(
        article.get("category")
    ) or "Netral"

    if category not in {
        "Negatif Kuat",
        "Perlu Penanganan",
    }:
        return False

    if not is_current_month_year_article(article):

        print(
            "[TELEGRAM SKIP] "
            "Artikel bukan bulan/tahun berjalan: "
            f"{article.get('title', '')[:100]}"
        )

        return False

    return send_telegram_message(
        telegram_text(article)
    )


# ============================================================
# RECLASSIFY ALL
# ============================================================

def reclassify_all() -> Dict[str, int]:
    """Klasifikasi ulang seluruh artikel yang sudah ada di Supabase."""
    print("=" * 70)
    print("MEMULAI REKLASIFIKASI SELURUH DATABASE")
    print("=" * 70)

    try:
        articles = get_all_articles()
    except Exception as exc:
        print(f"[REKLASIFIKASI ERROR] Gagal mengambil database: {exc}")
        return {"Negatif Kuat": 0, "Perlu Penanganan": 0, "Netral": 0, "Positif": 0}

    total = len(articles)
    counts = {"Negatif Kuat": 0, "Perlu Penanganan": 0, "Netral": 0, "Positif": 0}
    updated = 0
    failed = 0

    print(f"[REKLASIFIKASI] Total artikel: {total}")

    for index, article in enumerate(articles, start=1):
        try:
            title = normalize_text(article.get("title"))
            content = normalize_text(article.get("content") or article.get("summary") or "")
            classification = classify_article(title, content) if (title or content) else {"category": "Netral", "priority": "Rendah"}
            category = classification.get("category", "Netral")
            priority = classification.get("priority", PRIORITY_BY_CATEGORY.get(category, "Rendah"))
            if category not in counts:
                category = "Netral"
                priority = "Rendah"
            counts[category] += 1

            article_id = article.get("id")
            if article_id is None:
                failed += 1
                print(f"[REKLASIFIKASI ERROR] {index}/{total} -> ID artikel tidak ditemukan")
                continue

            result = update_article_classification_by_id(article_id, category, priority)
            if result is not None:
                updated += 1
            else:
                failed += 1
                print(f"[REKLASIFIKASI ERROR] {index}/{total} -> gagal update ID={article_id}")
        except Exception as exc:
            failed += 1
            print(f"[REKLASIFIKASI ERROR] {index}/{total} -> {type(exc).__name__}: {exc}")

        if index % 25 == 0 or index == total:
            print(f"[REKLASIFIKASI] Progress {index}/{total}")

    print("\n" + "=" * 70)
    print("REKLASIFIKASI SELESAI")
    print("=" * 70)
    print(f"Negatif Kuat      : {counts['Negatif Kuat']}")
    print(f"Perlu Penanganan  : {counts['Perlu Penanganan']}")
    print(f"Netral            : {counts['Netral']}")
    print(f"Positif           : {counts['Positif']}")
    print(f"Total             : {total}")
    print(f"Berhasil update   : {updated}")
    print(f"Gagal update      : {failed}")
    print("=" * 70)
    return counts


# ============================================================
# RUN ONCE
# ============================================================

def run_once() -> Dict[str, Any]:

    started = time.perf_counter()

    print("=" * 70)
    print("MEMULAI PATROLI SIBER")
    print("=" * 70)

    # ========================================================
    # DATABASE AWAL
    # ========================================================

    try:
        existing_articles = get_all_articles()

        # ========================================================
        # BUILD DUPLICATE INDEXES
        # ========================================================
        
        existing_link_index = {
        
            normalize_url(
                article.get("link")
            )
        
            for article in existing_articles
        
            if normalize_url(
                article.get("link")
            )
        }
        
        
        # Diagnostic-only lookup: normalized URL -> full DB article.
        # This does NOT change the duplicate decision rule.
        existing_article_by_link = {}
        for existing_article in existing_articles:
            existing_link = normalize_url(
                existing_article.get("link")
            )
            if existing_link:
                existing_article_by_link.setdefault(
                    existing_link,
                    existing_article,
                )

        existing_title_index = (
            build_existing_title_index(
                existing_articles
            )
        )
        
        
        existing_content_index = (
            build_existing_content_index(
                existing_articles
            )
        )
        
        
        print(
            f"[DATABASE] "
            f"Total artikel sebelum run: "
            f"{len(existing_articles)}"
        )
        
        print(
            f"[DEDUPE] "
            f"Unique URL index: "
            f"{len(existing_link_index)}"
        )
        
        print(
            f"[DEDUPE] "
            f"Title + media index: "
            f"{len(existing_title_index)}"
        )
        
        print(
            f"[DEDUPE] "
            f"Content index: "
            f"{len(existing_content_index)}"
        )

    except Exception as exc:

        print(
            f"[DATABASE ERROR] "
            f"Gagal mengambil database: "
            f"{type(exc).__name__}: {exc}"
        )

        return {
            "status": "Gagal",
            "error": str(exc),
        }

    # ========================================================
    # COLLECT CANDIDATES
    # ========================================================

    try:
        candidates = collect_candidates()

    except Exception as exc:

        print(
            f"[COLLECT ERROR] "
            f"{type(exc).__name__}: {exc}"
        )

        return {
            "status": "Gagal",
            "error": str(exc),
        }

    # ========================================================
    # PROCESS CANDIDATES
    # ========================================================

    valid_articles = []

    filtered_count = 0

    worker_errors = 0

    filter_reasons: Dict[str, int] = {}

    with ThreadPoolExecutor(
        max_workers=max(
            1,
            MAX_WORKERS,
        )
    ) as executor:

        futures = [
            executor.submit(
                process_candidate,
                candidate,
            )
            for candidate in candidates
        ]

        for future in as_completed(futures):

            try:

                result = future.result()

                if result.get("ok"):

                    article = result.get("article")

                    if article:
                        valid_articles.append(article)

                else:

                    filtered_count += 1

                    reason = normalize_text(
                        result.get(
                            "reason",
                            "",
                        )
                    )

                    if reason:

                        filter_reasons[reason] = (
                            filter_reasons.get(
                                reason,
                                0,
                            )
                            + 1
                        )

                        print(
                            f"[FILTER] "
                            f"{reason}"
                        )

            except Exception as exc:

                worker_errors += 1

                print(
                    f"[WORKER ERROR] "
                    f"{type(exc).__name__}: "
                    f"{exc}"
                )

    print()
    print(
        f"[PATROLI] "
        f"Kandidat: "
        f"{len(candidates)}"
    )

    print(
        f"[PATROLI] "
        f"Artikel valid: "
        f"{len(valid_articles)}"
    )

    print(
        f"[PATROLI] "
        f"Tidak lolos filter: "
        f"{filtered_count}"
    )

    print(
        f"[PATROLI] "
        f"Worker error: "
        f"{worker_errors}"
    )

    # ========================================================
    # FILTER SUMMARY
    # ========================================================

    if filter_reasons:

        print()
        print(
            "[PATROLI] RINGKASAN FILTER"
        )
        print("-" * 70)

        for reason, count in sorted(
            filter_reasons.items(),
            key=lambda item: item[1],
            reverse=True,
        ):

            print(
                f"{reason}: {count}"
            )

    # ========================================================
    # DEDUPE HASIL RUN
    # ========================================================

    unique_articles: Dict[
        str,
        Dict[str, Any],
    ] = {}

    print(
        f"[DEBUG SAVE] Memasuki SAVE LOOP | "
        f"total={len(valid_articles)}"
    )
    
    for article in valid_articles:

        print(
            f"[DEBUG SAVE] Memproses artikel: "
            f"{article.get('title', '')[:120]}"
        )
    
        # ====================================================
        # VALIDATE LINK
        # ====================================================
        
        link = normalize_url(
            article.get("link")
        )

        if not link:
            continue

        if link not in unique_articles:

            unique_articles[link] = article

        else:

            existing = unique_articles[link]

            current_content_length = len(
                normalize_text(
                    article.get("content")
                )
            )

            existing_content_length = len(
                normalize_text(
                    existing.get("content")
                )
            )

            if (
                current_content_length
                > existing_content_length
            ):

                unique_articles[link] = article

    valid_articles = list(
        unique_articles.values()
    )
    
    print(
        f"[PATROLI] "
        f"Artikel valid setelah dedupe: "
        f"{len(valid_articles)}"
    )
    
    print(
        f"[DEBUG SAVE] valid_articles sebelum SAVE = "
        f"{len(valid_articles)}"
    )

    # ========================================================
    # V5.2 URL RESOLUTION SUMMARY
    # ========================================================

    url_resolution_counts = Counter()
    for item in valid_articles:
        method = normalize_text(
            item.get("_url_resolution_method")
        ) or "unknown"
        url_resolution_counts[method] += 1

    print()
    print("[URL RESOLUTION SUMMARY]")
    print(
        f"RSS candidates             : {len(candidates)}"
    )
    print(
        f"Valid articles processed   : {len(valid_articles)}"
    )
    print(
        f"Resolved to media URL      : "
        f"{sum(url_resolution_counts[k] for k in ('base64_embedded', 'canonical', 'redirect', 'embedded_original'))}"
    )
    print(
        f"Base64 embedded URL        : {url_resolution_counts.get('base64_embedded', 0)}"
    )
    print(
        f"Canonical URL              : {url_resolution_counts.get('canonical', 0)}"
    )
    print(
        f"Redirect URL               : {url_resolution_counts.get('redirect', 0)}"
    )
    print(
        f"Embedded original URL      : {url_resolution_counts.get('embedded_original', 0)}"
    )
    print(
        f"Still Google News URL      : "
        f"{url_resolution_counts.get('google_fallback', 0) + url_resolution_counts.get('fetch_failed_google_fallback', 0)}"
    )
    print(
        f"Fetch failed fallback      : {url_resolution_counts.get('fetch_failed_google_fallback', 0)}"
    )

    # ========================================================
    # SAVE
    # ========================================================
    # ========================================================
    # SAVE
    #
    # Semua keputusan duplicate hanya melalui:
    #
    # should_save_article()
    #
    # Tidak ada lagi:
    #
    # - is_duplicate_article()
    # - existing_links tambahan
    # - was_existing
    # - get_article_by_link()
    #
    # ========================================================
    
    saved_count = 0
    save_failed = 0
    duplicate_reason_counts = Counter()
    
    new_articles = []
    
    
    for article in valid_articles:
    
        # ====================================================
        # VALIDATE LINK
        # ====================================================
    
        link = normalize_url(
            article.get("link")
        )
    
        if not link:
    
            print(
                "[SKIP] INVALID_LINK"
            )
    
            continue
    
    
        # ====================================================
        # CENTRAL DUPLICATE DECISION
        #
        # Hanya fungsi ini yang menentukan:
        #
        # - Duplicate URL
        # - Duplicate Title + Media
        # - Duplicate Content + Media
        #
        # Event sama dari media berbeda
        # TETAP BOLEH DISIMPAN.
        # ====================================================
    
        (
            should_save,
            reason,
            similarity,
            matched_article,
        ) = should_save_article(
    
            article,
    
            existing_link_index,
    
            existing_title_index,
    
            existing_content_index,
        )

        if not should_save and reason.startswith("DUPLICATE_"):
            duplicate_reason_counts[reason] += 1
    
    
        # Diagnostic-only: identify the existing DB row for URL duplicates.
        matched_url_article = None
        if reason == "DUPLICATE_URL":
            matched_url_article = existing_article_by_link.get(link)


        # ====================================================
        # SKIP DUPLICATE
        # ====================================================
    
        if not should_save:
    
            print()
            print(
                f"[SKIP] {reason}"
            )
    
            print(
                f"TITLE: "
                f"{article.get('title', '')}"
            )
    
            print(
                f"LINK: "
                f"{article.get('link', '')}"
            )
    
            print(
                f"MEDIA: "
                f"{get_media_source(article)}"
            )

            if reason == "DUPLICATE_URL":
                print("[DUPLICATE URL DIAGNOSTIC]")

                if matched_url_article:
                    print(
                        f"MATCHED DB ID: "
                        f"{matched_url_article.get('id', 'Unknown')}"
                    )
                    print(
                        f"MATCHED DB TITLE: "
                        f"{matched_url_article.get('title', '')}"
                    )
                    print(
                        f"MATCHED DB MEDIA: "
                        f"{get_media_source(matched_url_article)}"
                    )
                    print(
                        f"MATCHED DB SOURCE: "
                        f"{normalize_text(matched_url_article.get('source', ''))}"
                    )
                    print(
                        f"MATCHED DB PUBLISHER: "
                        f"{normalize_text(matched_url_article.get('publisher', ''))}"
                    )
                    print(
                        f"MATCHED DB LINK: "
                        f"{matched_url_article.get('link', '')}"
                    )
                    print(
                        f"CANDIDATE LINK NORMALIZED: {link}"
                    )
                    print(
                        "MATCHED DB LINK NORMALIZED: "
                        f"{normalize_url(matched_url_article.get('link'))}"
                    )
                    print(
                        "TITLE+MEDIA MATCH: "
                        f"{build_title_key(article) == build_title_key(matched_url_article)}"
                    )
                    print(
                        "MEDIA MATCH: "
                        f"{get_media_source(article).lower().strip() == get_media_source(matched_url_article).lower().strip()}"
                    )

                    candidate_content = normalize_content_for_duplicate(
                        get_article_content(article)
                    )
                    matched_content = normalize_content_for_duplicate(
                        get_article_content(matched_url_article)
                    )

                    if candidate_content and matched_content:
                        try:
                            similarity_url = calculate_content_similarity(
                                candidate_content,
                                matched_content,
                            )
                            print(
                                f"CONTENT SIMILARITY: {similarity_url:.2%}"
                            )
                        except Exception as exc:
                            print(
                                "CONTENT SIMILARITY: ERROR "
                                f"{type(exc).__name__}: {exc}"
                            )
                    else:
                        print(
                            "CONTENT SIMILARITY: "
                            "Tidak dapat dihitung (content kosong)"
                        )
                else:
                    print(
                        "[DUPLICATE URL DIAGNOSTIC] "
                        "Matched database article tidak ditemukan "
                        "meskipun URL ada di index."
                    )

    
            if matched_article:
    
                print(
                    f"MATCHED ID: "
                    f"{matched_article.get('id', 'Unknown')}"
                )
    
                print(
                    f"MATCHED TITLE: "
                    f"{matched_article.get('title', '')}"
                )
    
                print(
                    f"MATCHED MEDIA: "
                    f"{get_media_source(matched_article)}"
                )
    
                print(
                    f"SIMILARITY: "
                    f"{similarity:.2%}"
                )
    
            continue
    
    
        # ====================================================
        # ARTICLE APPROVED
        # ====================================================
    
        print()
    
        print(
            "[SAVE] NEW_ARTICLE"
        )
    
        print(
            f"TITLE: "
            f"{article.get('title', '')}"
        )
    
        print(
            f"MEDIA: "
            f"{get_media_source(article)}"
        )
    
    
        # ====================================================
        # UPSERT ARTICLE
        # ====================================================
    
        try:
            # Jangan pernah mengirim field observability internal ke database.py.
            article.pop("_url_resolution_method", None)
    
            saved = upsert_article(
                article
            )
    
    
            # ====================================================
            # SAVE FAILED
            # ====================================================
    
            if saved is None:
    
                save_failed += 1
    
                print(
                    f"[SAVE ERROR] "
                    f"Gagal menyimpan: "
                    f"{link}"
                )
    
                continue
    
    
            # ====================================================
            # SAVE SUCCESS
            # ====================================================
    
            saved_count += 1
    
    
            # ====================================================
            # UPDATE DUPLICATE INDEX
            #
            # SANGAT PENTING.
            #
            # Artikel yang baru saja disimpan harus langsung
            # dimasukkan ke index.
            #
            # Dengan demikian artikel berikutnya dalam satu
            # GitHub Actions run juga bisa terdeteksi duplicate.
            # ====================================================
    
            register_saved_article(
    
                article,
    
                existing_link_index,
    
                existing_title_index,
    
                existing_content_index,
            )
    
    
            # ====================================================
            # RISK ANALYSIS — 5 FACTORS AKTIF
            # ====================================================
            # Tidak menulis risk fields ke database karena database.py
            # harus tetap tidak berubah.
            risk_pool = existing_articles + new_articles + [article]
            try:
                risk_result = calculate_article_risk(article, risk_pool)
                article["risk_score"] = risk_result["risk_score"]
                article["risk_level"] = risk_result["risk_level"]
                article["risk_factors"] = risk_result["factors"]
                article["risk_reasons"] = risk_result["reasons"]
                article["risk_context"] = risk_result["context"]
                print(
                    f"[RISK] {risk_result['risk_score']}/100 "
                    f"{risk_result['risk_level']} | "
                    f"media={risk_result['context']['media_count']} | "
                    f"recurrence={risk_result['context']['recurrence_count']} | "
                    f"trend={risk_result['context']['trend_score']}"
                )
            except Exception as exc:
                print(
                    f"[RISK WARNING] Gagal menghitung risk: "
                    f"{type(exc).__name__}: {exc}"
                )


            # ====================================================
            # NEW ARTICLE
            #
            # Artikel hanya masuk Telegram jika benar-benar
            # lolos duplicate prevention dan berhasil disimpan.
            # ====================================================
    
            new_articles.append(
                article
            )
    
    
            print(
                f"[SAVE SUCCESS] "
                f"{article.get('title', '')[:100]}"
            )
    
    
        except Exception as exc:
    
            save_failed += 1
    
            print(
                f"[SAVE ERROR] "
                f"{link}: "
                f"{type(exc).__name__}: "
                f"{exc}"
            )
    # ========================================================
    # V5.2 DUPLICATE SUMMARY
    # ========================================================

    print()
    print("[DUPLICATE SUMMARY]")
    print(
        f"DUPLICATE_URL               : {duplicate_reason_counts.get('DUPLICATE_URL', 0)}"
    )
    print(
        f"DUPLICATE_TITLE_SAME_MEDIA  : {duplicate_reason_counts.get('DUPLICATE_TITLE_SAME_MEDIA', 0)}"
    )
    print(
        f"DUPLICATE_CONTENT_SAME_MEDIA: {duplicate_reason_counts.get('DUPLICATE_CONTENT_SAME_MEDIA', 0)}"
    )
    print(
        f"NEW_ARTICLE                 : {saved_count}"
    )
    print(
        f"SAVE_FAILED                 : {save_failed}"
    )

    # ========================================================
    # RISK SUMMARY
    # ========================================================
    risk_level_counts = Counter()
    for item in new_articles:
        level = normalize_text(item.get("risk_level"))
        if level:
            risk_level_counts[level] += 1

    print()
    print("[RISK] RINGKASAN ARTIKEL BARU")
    print(
        f"[RISK] Scored: {sum(risk_level_counts.values())} | "
        f"CRITICAL={risk_level_counts.get('CRITICAL', 0)} | "
        f"HIGH={risk_level_counts.get('HIGH', 0)} | "
        f"MEDIUM={risk_level_counts.get('MEDIUM', 0)} | "
        f"LOW={risk_level_counts.get('LOW', 0)}"
    )

    # ========================================================
    # TELEGRAM
    # ========================================================

    telegram_count = 0
    telegram_skipped = 0

    print(
        f"[TELEGRAM] Total artikel baru: "
        f"{len(new_articles)}"
    )

    if telegram_enabled():

        for article in new_articles:

            try:

                category = normalize_text(
                    article.get("category")
                ) or "Netral"

                # Hanya Negatif Kuat dan Perlu Penanganan
                # yang boleh dikirim ke Telegram.
                if category not in {
                    "Negatif Kuat",
                    "Perlu Penanganan",
                }:
                    telegram_skipped += 1

                    print(
                        "[TELEGRAM SKIP] "
                        f"Kategori tidak dikirim: {category}"
                    )
                    continue

                if not send_alert_if_needed(
                    article
                ):
                    telegram_skipped += 1
                    continue

                telegram_count += 1

                print(
                    "[TELEGRAM] Terkirim: "
                    f"{article.get('title', '')[:100]}"
                )

            except Exception as exc:

                telegram_skipped += 1

                print(
                    f"[TELEGRAM ERROR] "
                    f"{type(exc).__name__}: "
                    f"{exc}"
                )

    else:

        telegram_skipped = len(new_articles)

        if new_articles:
            print(
                "[TELEGRAM] Tidak aktif. "
                "Periksa TELEGRAM_BOT_TOKEN "
                "dan TELEGRAM_CHAT_ID."
            )

    print(
        f"[TELEGRAM] Berhasil dikirim: "
        f"{telegram_count}"
    )

    print(
        f"[TELEGRAM] Tidak dikirim/skipped: "
        f"{telegram_skipped}"
    )

    # ========================================================
    # FINAL DATABASE
    # ========================================================
    # IMPORTANT:
    # run_once() TIDAK melakukan reclassify seluruh database.
    # Reklasifikasi hanya dijalankan oleh mode --reclassify
    # di main().

    try:

        final_articles = get_all_articles()

    except Exception as exc:

        print(
            f"[DATABASE ERROR] "
            f"Gagal mengambil database akhir: "
            f"{type(exc).__name__}: {exc}"
        )

        final_articles = []

    duration = round(
        time.perf_counter()
        - started,
        2,
    )

    # Hitung distribusi kategori secara READ-ONLY untuk summary/log.
    # Ini bukan reclassification dan tidak mengubah database.
    counts = Counter(
        normalize_text(
            article.get("category")
        ) or "Netral"
        for article in final_articles
    )

    # ========================================================
    # RUN LOG
    # ========================================================

    log = {

        "duration_seconds": duration,

        "candidate_count": len(
            candidates
        ),

        "valid_count": len(
            valid_articles
        ),

        "filtered_count": filtered_count,

        "worker_error_count": worker_errors,

        "saved_count": saved_count,

        "save_failed_count": save_failed,

        "new_article_count": len(
            new_articles
        ),

        # Mode --once tidak melakukan reclassification.
        "reclassified_count": 0,

        "negative_count": counts.get(
            "Negatif Kuat",
            0,
        ),

        "handling_count": counts.get(
            "Perlu Penanganan",
            0,
        ),

        "neutral_count": counts.get(
            "Netral",
            0,
        ),

        "positive_count": counts.get(
            "Positif",
            0,
        ),

        "telegram_count": telegram_count,

        "status": "Selesai",
    }

    save_run_log(log)

    # ========================================================
    # INTERNAL PRODUCTION-AUDIT PAYLOAD
    # Tidak disimpan ke database/run_logs. Hanya dikembalikan
    # ke caller --production-audit untuk validasi otomatis.
    # ========================================================
    log["_audit_new_articles"] = [
        {
            "id": item.get("id"),
            "title": item.get("title", ""),
            "link": item.get("link", ""),
            "category": item.get("category", ""),
            "published_date": item.get("published_date", ""),
            "risk_score": item.get("risk_score"),
            "risk_level": item.get("risk_level", ""),
        }
        for item in new_articles
    ]

    # ========================================================
    # SUMMARY
    # ========================================================

    print()
    print("=" * 70)
    print("PATROLI SELESAI")
    print("=" * 70)

    print(
        f"Durasi                 : "
        f"{duration} detik"
    )

    print(
        f"Kandidat               : "
        f"{len(candidates)}"
    )

    print(
        f"Artikel valid          : "
        f"{len(valid_articles)}"
    )

    print(
        f"Tidak lolos filter    : "
        f"{filtered_count}"
    )

    print(
        f"Worker error           : "
        f"{worker_errors}"
    )

    print(
        f"Berhasil disimpan      : "
        f"{saved_count}"
    )

    print(
        f"Gagal simpan           : "
        f"{save_failed}"
    )

    print(
        f"Artikel baru           : "
        f"{len(new_articles)}"
    )

    print(
        f"Database               : "
        f"{len(final_articles)}"
    )

    print(
        f"Negatif Kuat           : "
        f"{counts.get('Negatif Kuat', 0)}"
    )

    print(
        f"Perlu Penanganan       : "
        f"{counts.get('Perlu Penanganan', 0)}"
    )

    print(
        f"Netral                 : "
        f"{counts.get('Netral', 0)}"
    )

    print(
        f"Positif                : "
        f"{counts.get('Positif', 0)}"
    )

    print(
        f"Telegram terkirim      : "
        f"{telegram_count}"
    )

    print("=" * 70)

    return log





# ============================================================
# PRODUCTION AUDIT
# ============================================================

def production_audit() -> Dict[str, Any]:
    """Jalankan patroli normal lalu validasi invariant production."""
    print("=" * 70)
    print("PRODUCTION AUDIT")
    print("=" * 70)
    print("Menjalankan patroli normal + validasi invariant...")

    result = run_once()
    failures = []

    def check(condition: bool, name: str, detail: str) -> None:
        if condition:
            print(f"[AUDIT PASS] {name}: {detail}")
        else:
            print(f"[AUDIT FAIL] {name}: {detail}")
            failures.append(f"{name}: {detail}")

    check(result.get("status") == "Selesai", "RUN_STATUS", f"status={result.get('status')!r}")
    check(int(result.get("worker_error_count", 0) or 0) == 0, "WORKER_ERRORS", f"count={result.get('worker_error_count', 0)}")
    check(int(result.get("save_failed_count", 0) or 0) == 0, "SAVE_FAILURES", f"count={result.get('save_failed_count', 0)}")

    saved = int(result.get("saved_count", 0) or 0)
    new_count = int(result.get("new_article_count", 0) or 0)
    valid = int(result.get("valid_count", 0) or 0)
    telegram = int(result.get("telegram_count", 0) or 0)

    check(saved == new_count, "SAVE_NEW_ACCOUNTING", f"saved={saved}, new={new_count}")
    check(0 <= new_count <= valid, "NEW_COUNT_BOUND", f"new={new_count}, valid={valid}")
    check(0 <= telegram <= new_count, "TELEGRAM_BOUND", f"telegram={telegram}, new={new_count}")

    new_items = result.get("_audit_new_articles") or []
    check(len(new_items) == new_count, "NEW_ARTICLE_PAYLOAD", f"payload={len(new_items)}, reported={new_count}")

    allowed_categories = {"Negatif Kuat", "Perlu Penanganan", "Netral", "Positif"}
    telegram_categories = {"Negatif Kuat", "Perlu Penanganan"}
    normalized_new_links = []
    invalid_category = []
    google_links = []
    invalid_risk = []

    for item in new_items:
        link = normalize_url(item.get("link") or "")
        normalized_new_links.append(link)
        domain = urllib.parse.urlparse(link).netloc.lower().replace("www.", "") if link else ""
        if not link or domain == "news.google.com":
            google_links.append(link or "<EMPTY>")

        category = item.get("category") or ""
        if category not in allowed_categories:
            invalid_category.append(category)

        score = item.get("risk_score")
        level = item.get("risk_level")
        if score is None or not isinstance(score, (int, float)) or not 0 <= float(score) <= 100:
            invalid_risk.append({"title": item.get("title", ""), "risk_score": score})
        if level not in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
            invalid_risk.append({"title": item.get("title", ""), "risk_level": level})

    nonempty_links = [x for x in normalized_new_links if x]
    check(len(nonempty_links) == len(set(nonempty_links)), "NEW_ARTICLE_URL_UNIQUENESS", f"duplicates={len(nonempty_links) - len(set(nonempty_links))}")
    check(not google_links, "NEW_URLS_ARE_PUBLISHER_URLS", f"google_news_or_empty={len(google_links)}")
    check(not invalid_category, "CATEGORY_VALIDITY", f"invalid={invalid_category[:5]}")
    check(not invalid_risk, "RISK_FIELDS_VALID", f"invalid={invalid_risk[:5]}")

    try:
        final_articles = get_all_articles()
        final_link_counts = Counter(
            normalize_url(article.get("link") or "")
            for article in final_articles
            if normalize_url(article.get("link") or "")
        )
        missing_after_save = [
            link for link in normalized_new_links
            if link and final_link_counts.get(link, 0) != 1
        ]
        check(not missing_after_save, "DATABASE_READBACK_NEW_ARTICLES", f"missing_or_nonunique={len(missing_after_save)}")
    except Exception as exc:
        check(False, "DATABASE_READBACK", f"{type(exc).__name__}: {exc}")

    expected_telegram_upper_bound = sum(
        1 for item in new_items
        if item.get("category") in telegram_categories
        and is_current_month_year_article(item)
    )
    check(telegram <= expected_telegram_upper_bound, "TELEGRAM_CATEGORY_DATE_RULE", f"sent={telegram}, eligible={expected_telegram_upper_bound}")

    print("=" * 70)
    if failures:
        print("PRODUCTION AUDIT: FAILED")
        for failure in failures:
            print(f" - {failure}")
        print("=" * 70)
        raise RuntimeError(f"Production audit gagal pada {len(failures)} invariant(s).")

    print("PRODUCTION AUDIT: PASSED")
    print("Semua invariant production terpenuhi.")
    print("=" * 70)
    return result


# ============================================================
# DEDUPE DRY RUN
# ============================================================

def dedupe_dry_run() -> Dict[str, Any]:
    """
    Audit duplicate link tanpa mengubah database.

    Menghasilkan:
    - dedupe_report.csv
    - dedupe_report.json

    Tidak melakukan INSERT, UPDATE, DELETE.
    """

    print("=" * 70)
    print(
        "DEDUPE DRY RUN"
    )
    print(
        "CEK DUPLICATE LINK TANPA "
        "MENGUBAH DATABASE"
    )
    print("=" * 70)

    try:

        articles = (
            get_all_articles()
        )

    except Exception as exc:

        print(
            f"[DEDUPE ERROR] "
            f"Gagal mengambil database: "
            f"{type(exc).__name__}: "
            f"{exc}"
        )

        return {
            "total_articles": 0,
            "unique_links": 0,
            "duplicate_groups": 0,
            "duplicate_articles": 0,
            "empty_links": 0,
            "error": True,
        }

    total_articles = len(
        articles
    )

    print(
        f"[DATABASE] Total artikel: "
        f"{total_articles}"
    )

    groups: Dict[
        str,
        List[Dict[str, Any]],
    ] = {}

    empty_links = []

    for article in articles:

        raw_link = article.get(
            "link"
        )

        normalized_link = (
            normalize_url(
                raw_link
            )
        )

        if not normalized_link:

            empty_links.append(
                article
            )

            continue

        groups.setdefault(
            normalized_link,
            [],
        ).append(
            article
        )

    duplicate_groups = {
        link: rows
        for link, rows
        in groups.items()
        if len(rows) > 1
    }

    duplicate_articles = sum(
        len(rows) - 1
        for rows
        in duplicate_groups.values()
    )

    unique_links = len(
        groups
    )

    report_rows = []

    json_groups = []

    for group_number, (
        normalized_link,
        rows,
    ) in enumerate(
        duplicate_groups.items(),
        start=1,
    ):

        rows_sorted = sorted(
            rows,
            key=get_dedupe_record_score,
            reverse=True,
        )

        keep = rows_sorted[0]

        keep_id = keep.get(
            "id"
        )

        keep_title = normalize_text(
            keep.get(
                "title"
            )
        )

        keep_content_length = len(
            normalize_text(
                keep.get(
                    "content"
                )
                or keep.get(
                    "summary"
                )
                or ""
            )
        )

        json_group = {
            "group": group_number,

            "normalized_link": (
                normalized_link
            ),

            "total_records": (
                len(rows)
            ),

            "recommended_keep": {
                "id": keep_id,
                "title": keep_title,
                "content_length": (
                    keep_content_length
                ),
                "published_date": (
                    keep.get(
                        "published_date"
                    )
                ),
                "link": (
                    keep.get(
                        "link"
                    )
                ),
            },

            "delete_candidates": [],
        }

        for row in rows_sorted:

            article_id = row.get(
                "id"
            )

            title = normalize_text(
                row.get(
                    "title"
                )
            )

            content_length = len(
                normalize_text(
                    row.get(
                        "content"
                    )
                    or row.get(
                        "summary"
                    )
                    or ""
                )
            )

            is_keep = (
                article_id
                == keep_id
            )

            action = (
                "KEEP"
                if is_keep
                else "DELETE_CANDIDATE"
            )

            report_rows.append(
                {
                    "duplicate_group": (
                        group_number
                    ),

                    "normalized_link": (
                        normalized_link
                    ),

                    "record_count": (
                        len(rows)
                    ),

                    "recommended_action": (
                        action
                    ),

                    "article_id": (
                        article_id
                    ),

                    "title": title,

                    "content_length": (
                        content_length
                    ),

                    "published_date": (
                        row.get(
                            "published_date"
                        )
                    ),

                    "category": (
                        row.get(
                            "category",
                            "",
                        )
                    ),

                    "priority": (
                        row.get(
                            "priority",
                            "",
                        )
                    ),

                    "original_link": (
                        row.get(
                            "link",
                            "",
                        )
                    ),
                }
            )

            if not is_keep:

                json_group[
                    "delete_candidates"
                ].append(
                    {
                        "id": (
                            article_id
                        ),

                        "title": title,

                        "content_length": (
                            content_length
                        ),

                        "published_date": (
                            row.get(
                                "published_date"
                            )
                        ),

                        "link": (
                            row.get(
                                "link"
                            )
                        ),
                    }
                )

        json_groups.append(
            json_group
        )

    # ========================================================
    # CSV
    # ========================================================

    csv_path = (
        "dedupe_report.csv"
    )

    csv_fields = [
        "duplicate_group",
        "normalized_link",
        "record_count",
        "recommended_action",
        "article_id",
        "title",
        "content_length",
        "published_date",
        "category",
        "priority",
        "original_link",
    ]

    try:

        with open(
            csv_path,
            "w",
            newline="",
            encoding="utf-8",
        ) as csv_file:

            writer = (
                csv.DictWriter(
                    csv_file,
                    fieldnames=csv_fields,
                )
            )

            writer.writeheader()

            writer.writerows(
                report_rows
            )

        print(
            f"[REPORT] CSV berhasil dibuat: "
            f"{csv_path}"
        )

    except Exception as exc:

        print(
            f"[REPORT ERROR] CSV: "
            f"{type(exc).__name__}: "
            f"{exc}"
        )

    # ========================================================
    # JSON
    # ========================================================

    json_path = (
        "dedupe_report.json"
    )

    json_report = {
        "generated_at": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),

        "tahun_target": (
            TAHUN_TARGET
        ),

        "nama_satker": (
            NAMA_SATKER
        ),

        "total_articles": (
            total_articles
        ),

        "unique_links": (
            unique_links
        ),

        "duplicate_groups": (
            len(
                duplicate_groups
            )
        ),

        "duplicate_articles": (
            duplicate_articles
        ),

        "empty_links": (
            len(
                empty_links
            )
        ),

        "groups": json_groups,
    }

    try:

        with open(
            json_path,
            "w",
            encoding="utf-8",
        ) as json_file:

            json.dump(
                json_report,
                json_file,
                ensure_ascii=False,
                indent=2,
                default=str,
            )

        print(
            f"[REPORT] JSON berhasil dibuat: "
            f"{json_path}"
        )

    except Exception as exc:

        print(
            f"[REPORT ERROR] JSON: "
            f"{type(exc).__name__}: "
            f"{exc}"
        )

    # ========================================================
    # SUMMARY
    # ========================================================

    print()
    print("=" * 70)
    print(
        "HASIL DEDUPE DRY RUN"
    )
    print("=" * 70)

    print(
        f"Total artikel       : "
        f"{total_articles}"
    )

    print(
        f"Link unik           : "
        f"{unique_links}"
    )

    print(
        f"Kelompok duplicate  : "
        f"{len(duplicate_groups)}"
    )

    print(
        f"Artikel duplicate   : "
        f"{duplicate_articles}"
    )

    print(
        f"Link kosong         : "
        f"{len(empty_links)}"
    )

    print("=" * 70)

    if duplicate_groups:

        print()
        print(
            "REKOMENDASI DUPLICATE"
        )
        print("=" * 70)

        for group in json_groups:

            print()

            print(
                f"DUPLICATE #{group['group']}"
            )

            print(
                f"Jumlah record : "
                f"{group['total_records']}"
            )

            keep = group[
                "recommended_keep"
            ]

            print(
                f"PERTAHANKAN  : "
                f"ID={keep['id']} | "
                f"{keep['title'][:100]}"
            )

            print(
                f"Content      : "
                f"{keep['content_length']} karakter"
            )

            candidates = group[
                "delete_candidates"
            ]

            if candidates:

                print(
                    "HAPUS KANDIDAT:"
                )

                for candidate in (
                    candidates
                ):

                    print(
                        f"  - ID={candidate['id']} | "
                        f"{candidate['title'][:100]}"
                    )

    else:

        print()
        print(
            "[DEDUPE] Tidak ditemukan "
            "duplicate link."
        )

    # ========================================================
    # EMPTY LINK
    # ========================================================

    if empty_links:

        print()
        print("=" * 70)
        print(
            "ARTIKEL DENGAN LINK KOSONG"
        )
        print("=" * 70)

        for article in empty_links:

            print(
                f"ID={article.get('id', '-')}"
                f" | "
                f"{normalize_text(article.get('title'))[:100]}"
            )

    print()
    print("=" * 70)
    print(
        "DEDUPE DRY RUN SELESAI"
    )
    print(
        "TIDAK ADA DATA YANG DIUBAH"
    )
    print("=" * 70)

    return {
        "total_articles": (
            total_articles
        ),

        "unique_links": (
            unique_links
        ),

        "duplicate_groups": (
            len(
                duplicate_groups
            )
        ),

        "duplicate_articles": (
            duplicate_articles
        ),

        "empty_links": (
            len(
                empty_links
            )
        ),

        "error": False,

        "csv_report": (
            csv_path
        ),

        "json_report": (
            json_path
        ),
    }


# ============================================================
# DEDUPE REAL
# ============================================================

def dedupe() -> Dict[str, Any]:
    """Alias kompatibilitas untuk dedupe_database()."""
    return dedupe_database()

def get_dedupe_record_score(
    row: Dict[str, Any],
) -> tuple:
    """
    Menentukan kualitas record untuk deduplikasi.

    Prioritas:
    1. Content paling lengkap
    2. Memiliki title
    3. Memiliki published_date
    4. ID lebih kecil jika kualitas lainnya sama
    """

    content = normalize_text(
        row.get("content")
        or row.get("summary")
        or ""
    )

    title = normalize_text(
        row.get("title")
    )

    published = normalize_text(
        row.get("published_date")
    )

    try:
        article_id = int(
            row.get("id")
        )
    except Exception:
        article_id = 10**18

    return (
        len(content),
        bool(title),
        bool(published),
        -article_id,
    )

# ============================================================
# DEDUPE DATABASE
# ============================================================
# ============================================================
# DEDUPE DATABASE
# ============================================================

def dedupe_database() -> Dict[str, Any]:
    """Hapus duplicate berdasarkan normalized URL; record terbaik dipertahankan."""

    print("=" * 70)
    print("DEDUPE DATABASE - BERDASARKAN LINK")
    print("=" * 70)

    try:
        articles = get_all_articles()

    except Exception as exc:

        print(
            f"[DEDUPE ERROR] "
            f"Gagal mengambil database: "
            f"{type(exc).__name__}: {exc}"
        )

        return {
            "success": False,
            "deleted": 0,
            "failed": 0,
            "duplicate_groups": 0,
            "remaining": -1,
            "error": str(exc),
        }

    groups: Dict[
        str,
        List[Dict[str, Any]],
    ] = {}

    empty_links = 0

    # --------------------------------------------------------
    # KELOMPOKKAN BERDASARKAN NORMALIZED URL
    # --------------------------------------------------------

    for article in articles:

        normalized = normalize_url(
            article.get("link")
        )

        if not normalized:

            empty_links += 1

            continue

        groups.setdefault(
            normalized,
            [],
        ).append(article)

    duplicate_groups = {
        link: rows
        for link, rows
        in groups.items()
        if len(rows) > 1
    }

    delete_candidates: List[
        Dict[str, Any]
    ] = []

    # --------------------------------------------------------
    # SCORE RECORD
    #
    # Prioritas:
    # 1. Content paling lengkap
    # 2. Ada title
    # 3. Ada published_date
    # 4. ID lebih kecil
    # --------------------------------------------------------

    def record_score(
        row: Dict[str, Any],
    ):

        content = normalize_text(
            row.get("content")
            or row.get("summary")
            or ""
        )

        title = normalize_text(
            row.get("title")
        )

        published = normalize_text(
            row.get("published_date")
        )

        try:

            article_id = int(
                row.get("id")
            )

        except Exception:

            article_id = 10**18

        return (
            len(content),
            bool(title),
            bool(published),
            -article_id,
        )

    # --------------------------------------------------------
    # SUMMARY AWAL
    # --------------------------------------------------------

    print(
        f"[DATABASE] Total artikel: "
        f"{len(articles)}"
    )

    print(
        f"[DEDUPE] Link unik: "
        f"{len(groups)}"
    )

    print(
        f"[DEDUPE] Kelompok duplicate: "
        f"{len(duplicate_groups)}"
    )

    print(
        f"[DEDUPE] Artikel duplicate: "
        f"{sum(len(v) - 1 for v in duplicate_groups.values())}"
    )

    # --------------------------------------------------------
    # TENTUKAN RECORD YANG DIPERTAHANKAN
    # --------------------------------------------------------

    for number, (
        normalized_link,
        rows,
    ) in enumerate(
        duplicate_groups.items(),
        start=1,
    ):

        rows_sorted = sorted(
            rows,
            key=record_score,
            reverse=True,
        )

        keep = rows_sorted[0]

        duplicates = rows_sorted[1:]

        print()
        print(
            f"[DUPLICATE #{number}] "
            f"{normalized_link}"
        )

        print(
            "  KEEP   "
            f"ID={keep.get('id')} | "
            f"{normalize_text(keep.get('title'))[:100]}"
        )

        for row in duplicates:

            print(
                "  DELETE "
                f"ID={row.get('id')} | "
                f"{normalize_text(row.get('title'))[:100]}"
            )

        delete_candidates.extend(
            duplicates
        )

    # --------------------------------------------------------
    # DELETE
    # --------------------------------------------------------

    deleted = 0
    failed = 0

    for row in delete_candidates:

        article_id = row.get("id")

        if article_id is None:

            failed += 1

            print(
                "[DELETE ERROR] "
                "ID artikel tidak ditemukan"
            )

            continue

        try:

            result = delete_article_by_id(
                article_id
            )

            if result:

                deleted += 1

            else:

                failed += 1

                print(
                    "[DELETE ERROR] "
                    f"Gagal menghapus ID={article_id}"
                )

        except Exception as exc:

            failed += 1

            print(
                "[DELETE ERROR] "
                f"ID={article_id} -> "
                f"{type(exc).__name__}: {exc}"
            )

    # --------------------------------------------------------
    # CEK DATABASE SETELAH DEDUPE
    # --------------------------------------------------------

    try:

        remaining_articles = (
            get_all_articles()
        )

        remaining = len(
            remaining_articles
        )

    except Exception as exc:

        remaining = -1

        print(
            "[DEDUPE WARNING] "
            "Gagal menghitung database setelah "
            f"dedupe: {type(exc).__name__}: {exc}"
        )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("DEDUPE SELESAI")
    print("=" * 70)

    print(
        f"Record sebelum : "
        f"{len(articles)}"
    )

    print(
        f"Link unik      : "
        f"{len(groups)}"
    )

    print(
        f"Kelompok dup.  : "
        f"{len(duplicate_groups)}"
    )

    print(
        f"Berhasil hapus : "
        f"{deleted}"
    )

    print(
        f"Gagal hapus    : "
        f"{failed}"
    )

    print(
        f"Record sesudah : "
        f"{remaining}"
    )

    print(
        f"Link kosong    : "
        f"{empty_links}"
    )

    print("=" * 70)

    return {
        "success": failed == 0,
        "deleted": deleted,
        "failed": failed,
        "duplicate_groups": len(
            duplicate_groups
        ),
        "duplicate_articles": sum(
            len(v) - 1
            for v
            in duplicate_groups.values()
        ),
        "remaining": remaining,
        "empty_links": empty_links,
    }


# ============================================================
# SANITIZE DATABASE
# ============================================================


def sanitize_database() -> Dict[str, Any]:
    """
    Membersihkan HTML yang sudah tersimpan di database.

    Tidak:
    - INSERT artikel
    - DELETE artikel
    - mengubah link
    - mengubah klasifikasi
    - melakukan dedupe

    Hanya UPDATE field yang memang mengandung perubahan.
    """

    print("=" * 70)
    print("SANITASI DATABASE")
    print("MEMBERSIHKAN HTML DARI DATA ARTIKEL")
    print("=" * 70)

    try:

        articles = get_all_articles()

    except Exception as exc:

        print(
            "[SANITIZE ERROR] "
            "Gagal mengambil database: "
            f"{type(exc).__name__}: {exc}"
        )

        return {
            "success": False,
            "total": 0,
            "updated": 0,
            "unchanged": 0,
            "failed": 0,
        }

    total = len(articles)

    updated = 0
    unchanged = 0
    failed = 0

    print(
        f"[SANITIZE] Total artikel: {total}"
    )

    # --------------------------------------------------------
    # Proses satu per satu
    # --------------------------------------------------------

    for index, article in enumerate(
        articles,
        start=1,
    ):

        article_id = article.get(
            "id"
        )

        if article_id is None:

            failed += 1

            print(
                "[SANITIZE ERROR] "
                f"{index}/{total} -> "
                "ID artikel tidak ditemukan"
            )

            continue

        try:

            cleaned = sanitize_article(
                article
            )

            payload = {}

            # ------------------------------------------------
            # Hanya update field yang berubah
            # ------------------------------------------------

            for field in SANITIZE_FIELDS:

                if field not in cleaned:
                    continue

                old_value = article.get(
                    field
                )

                new_value = cleaned.get(
                    field
                )

                if new_value != old_value:

                    payload[field] = new_value

            # ------------------------------------------------
            # Tidak ada perubahan
            # ------------------------------------------------

            if not payload:

                unchanged += 1

            else:

                supabase = get_supabase()

                (
                    supabase
                    .table("articles")
                    .update(payload)
                    .eq("id", article_id)
                    .execute()
                )

                updated += 1

                print(
                    "[SANITIZE] UPDATE "
                    f"ID={article_id} | "
                    f"field={', '.join(payload.keys())}"
                )

        except Exception as exc:

            failed += 1

            print(
                "[SANITIZE ERROR] "
                f"{index}/{total} | "
                f"ID={article_id} | "
                f"{type(exc).__name__}: {exc}"
            )

        # ----------------------------------------------------
        # Progress
        # ----------------------------------------------------

        if (
            index % 25 == 0
            or index == total
        ):

            print(
                "[SANITIZE] Progress "
                f"{index}/{total}"
            )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("SANITASI SELESAI")
    print("=" * 70)

    print(
        f"Total artikel   : {total}"
    )

    print(
        f"Berhasil update : {updated}"
    )

    print(
        f"Tidak berubah   : {unchanged}"
    )

    print(
        f"Gagal           : {failed}"
    )

    print("=" * 70)

    return {
        "success": failed == 0,
        "total": total,
        "updated": updated,
        "unchanged": unchanged,
        "failed": failed,
    }
    
def audit_negative_articles() -> Dict[str, Any]:
    """
    Audit artikel yang saat ini diklasifikasikan sebagai Negatif Kuat.

    Fungsi ini TIDAK mengubah database.
    Hanya menampilkan artikel negatif beserta alasan/konteksnya.
    """

    print("=" * 70)
    print("AUDIT ARTIKEL NEGATIF")
    print("TIDAK ADA DATA YANG DIUBAH")
    print("=" * 70)

    try:
        articles = get_all_articles()

    except Exception as exc:

        print(
            "[AUDIT ERROR] "
            f"Gagal mengambil database: "
            f"{type(exc).__name__}: {exc}"
        )

        return {
            "success": False,
            "total": 0,
            "negative": 0,
            "error": str(exc),
        }

    negative_articles = [
        article
        for article in articles
        if normalize_text(
            article.get("category")
        ).lower()
        == "negatif kuat"
    ]

    print(
        f"[AUDIT] Total artikel    : {len(articles)}"
    )

    print(
        f"[AUDIT] Negatif Kuat     : "
        f"{len(negative_articles)}"
    )

    print()

    for index, article in enumerate(
        negative_articles,
        start=1,
    ):

        title = normalize_text(
            article.get("title")
        )

        content = normalize_text(
            article.get("content")
        )

        link = normalize_url(
            article.get("link")
        )

        classification = classify_article(
            title,
            content,
        )

        print("=" * 70)

        print(
            f"NEGATIF #{index}"
        )

        print(
            f"ID          : "
            f"{article.get('id')}"
        )

        print(
            f"Judul       : "
            f"{title}"
        )

        print(
            f"Link        : "
            f"{link}"
        )

        print(
            f"Kategori DB  : "
            f"{article.get('category')}"
        )

        print(
            f"Neg. Score  : "
            f"{classification.get('negative_score', 0)}"
        )

        print(
            f"Handling    : "
            f"{classification.get('handling_score', 0)}"
        )

        print(
            f"Pos. Score  : "
            f"{classification.get('positive_score', 0)}"
        )

        print(
            f"Satker      : "
            f"{classification.get('satker_matches', [])}"
        )

        print(
            f"Strong Ctx  : "
            f"{classification.get('strong_context', [])}"
        )

        print(
            f"Handling Ctx: "
            f"{classification.get('handling_context', [])}"
        )

        print(
            f"Positive Ctx: "
            f"{classification.get('positive_context', [])}"
        )

        print(
            f"Hasil ulang : "
            f"{classification.get('category', 'Netral')}"
        )

    print()
    print("=" * 70)
    print("AUDIT NEGATIF SELESAI")
    print("TIDAK ADA DATA YANG DIUBAH")
    print("=" * 70)

    return {
        "success": True,
        "total": len(articles),
        "negative": len(negative_articles),
    }

def audit_content_duplicates() -> None:
    """Audit duplicate sesuai aturan produksi; tidak mengubah database."""
    print("=" * 70)
    print("AUDIT CONTENT DUPLICATES")
    print("=" * 70)
    articles = get_all_articles()
    print(f"[AUDIT] Total artikel: {len(articles)}")

    title_groups = defaultdict(list)
    for article in articles:
        key = build_title_key(article)
        if key:
            title_groups[key].append(article)
    duplicate_titles = {k:v for k,v in title_groups.items() if len(v) > 1}

    content_items = []
    for article in articles:
        content = normalize_content_for_duplicate(get_article_content(article))
        if len(content) >= 100:
            content_items.append((article, content))

    content_groups = []
    seen = set()
    for i, (article_a, content_a) in enumerate(content_items):
        media_a = get_media_source(article_a).lower().strip()
        group = [article_a]
        for j in range(i + 1, len(content_items)):
            article_b, content_b = content_items[j]
            if get_media_source(article_b).lower().strip() != media_a:
                continue
            similarity = calculate_content_similarity(content_a, content_b)
            if similarity >= CONTENT_DUPLICATE_THRESHOLD:
                group.append(article_b)
        if len(group) > 1:
            ids = tuple(sorted(str(a.get("id", "")) for a in group))
            if ids not in seen:
                seen.add(ids)
                content_groups.append(group)

    print("\n" + "=" * 70)
    print(f"DUPLIKAT TITLE + MEDIA: {len(duplicate_titles)} KELOMPOK")
    print("=" * 70)
    for key, items in duplicate_titles.items():
        print("\n" + "-" * 70)
        print(f"KEY: {key}")
        for item in items:
            print(f"ID={item.get('id')} | {item.get('title')} | MEDIA={get_media_source(item)}")

    print("\n" + "=" * 70)
    print(f"DUPLIKAT CONTENT + MEDIA: {len(content_groups)} KELOMPOK")
    print("=" * 70)
    for number, items in enumerate(content_groups, 1):
        print(f"\nCONTENT DUPLICATE #{number} | MEDIA={get_media_source(items[0])}")
        for item in items:
            print(f"ID={item.get('id')} | {item.get('title')}")

    print("\n" + "=" * 70)
    print("AUDIT CONTENT DUPLICATES SELESAI")
    print("=" * 70)
    print(f"Total artikel              : {len(articles)}")
    print(f"Duplicate title + media    : {len(duplicate_titles)} kelompok")
    print(f"Duplicate content + media  : {len(content_groups)} kelompok")

def audit_exact_duplicates() -> None:
    """
    Audit artikel yang merupakan duplicate kuat.

    Syarat:
    - Title identik setelah normalisasi
    - Content identik setelah normalisasi

    Fungsi ini TIDAK menghapus data.
    """

    print("=" * 70)
    print("AUDIT EXACT DUPLICATES")
    print("=" * 70)

    try:
        articles = get_all_articles()

    except Exception as exc:

        print(
            f"[AUDIT ERROR] "
            f"Gagal mengambil artikel: {exc}"
        )

        return

    print(
        f"[AUDIT] Total artikel: "
        f"{len(articles)}"
    )

    # ========================================================
    # KELOMPOKKAN BERDASARKAN TITLE + CONTENT
    # ========================================================

    exact_groups = {}

    for article in articles:

        title = normalize_text(
            article.get("title") or ""
        )

        content = normalize_text(
            article.get("content")
            or article.get("summary")
            or ""
        )

        normalized_title = (
            title.lower().strip()
        )

        normalized_content = (
            content.lower().strip()
        )

        # ----------------------------------------------------
        # Abaikan artikel tanpa title
        # ----------------------------------------------------

        if not normalized_title:
            continue

        # ----------------------------------------------------
        # Abaikan artikel tanpa content
        # ----------------------------------------------------

        if not normalized_content:
            continue

        # ----------------------------------------------------
        # Hindari snippet terlalu pendek
        # ----------------------------------------------------

        if len(normalized_content) < 50:
            continue

        # ----------------------------------------------------
        # KEY = TITLE + CONTENT
        # ----------------------------------------------------

        key = (
            normalized_title,
            normalized_content,
        )

        if key not in exact_groups:

            exact_groups[key] = []

        exact_groups[key].append(
            article
        )

    # ========================================================
    # AMBIL YANG BENAR-BENAR DUPLICATE
    # ========================================================

    exact_duplicates = {

        key: items

        for key, items
        in exact_groups.items()

        if len(items) > 1
    }

    # ========================================================
    # TAMPILKAN HASIL
    # ========================================================

    print()
    print("=" * 70)

    print(
        f"EXACT DUPLICATES: "
        f"{len(exact_duplicates)} KELOMPOK"
    )

    print("=" * 70)

    total_duplicate_records = 0

    for index, (
        key,
        items,
    ) in enumerate(
        exact_duplicates.items(),
        start=1,
    ):

        title, content = key

        total_duplicate_records += len(
            items
        )

        print()
        print("-" * 70)

        print(
            f"EXACT DUPLICATE "
            f"#{index}"
        )

        print()

        print("TITLE:")

        print(title)

        print()

        print(
            f"CONTENT LENGTH: "
            f"{len(content)}"
        )

        print()

        print(
            f"JUMLAH RECORD: "
            f"{len(items)}"
        )

        print()

        print("CONTENT PREVIEW:")

        print(
            content[:300]
        )

        print()

        for item in items:

            print(
                f"ID     : "
                f"{item.get('id')}"
            )

            print(
                f"LINK   : "
                f"{item.get('link')}"
            )

            print(
                f"DATE   : "
                f"{item.get('published_date')}"
            )

            print(
                f"SOURCE : "
                f"{item.get('source')}"
            )

            print()

    # ========================================================
    # SUMMARY
    # ========================================================

    print()
    print("=" * 70)

    print(
        "AUDIT EXACT DUPLICATES SELESAI"
    )

    print("=" * 70)

    print(
        f"Total artikel            : "
        f"{len(articles)}"
    )

    print(
        f"Kelompok exact duplicate : "
        f"{len(exact_duplicates)}"
    )

    print(
        f"Total record duplicate   : "
        f"{total_duplicate_records}"
    )

    print("=" * 70)

def audit_title_duplicates() -> None:
    """
    Audit artikel yang memiliki judul sama.

    Fungsi ini TIDAK menghapus data.

    Menampilkan:
    - ID
    - Judul
    - Link
    - Domain/source
    - Tanggal
    - Panjang konten
    - Preview konten

    Tujuan:
    Membantu menentukan apakah artikel dengan judul
    sama benar-benar duplicate atau hanya memiliki
    judul yang kebetulan sama.
    """

    from urllib.parse import urlparse

    print("=" * 70)
    print("AUDIT TITLE DUPLICATES DETAIL")
    print("=" * 70)

    try:
        articles = get_all_articles()

    except Exception as exc:

        print(
            f"[AUDIT ERROR] "
            f"Gagal mengambil artikel: {exc}"
        )

        return

    print(
        f"[AUDIT] Total artikel: "
        f"{len(articles)}"
    )

    # ========================================================
    # GROUP BERDASARKAN NORMALIZED TITLE
    # ========================================================

    title_groups = {}

    for article in articles:

        title = normalize_text(
            article.get("title") or ""
        )

        normalized_title = (
            title.lower()
            .strip()
        )

        if not normalized_title:
            continue

        if normalized_title not in title_groups:

            title_groups[
                normalized_title
            ] = []

        title_groups[
            normalized_title
        ].append(article)

    # ========================================================
    # AMBIL HANYA TITLE DUPLICATE
    # ========================================================

    duplicate_titles = {

        title: items

        for title, items
        in title_groups.items()

        if len(items) > 1
    }

    print()
    print("=" * 70)
    print(
        f"DUPLIKAT JUDUL: "
        f"{len(duplicate_titles)} KELOMPOK"
    )
    print("=" * 70)

    # ========================================================
    # COUNTER
    # ========================================================

    total_duplicate_records = 0

    same_content_groups = 0
    different_content_groups = 0

    # ========================================================
    # LOOP DUPLICATE TITLE
    # ========================================================

    for group_number, (
        normalized_title,
        items,
    ) in enumerate(
        duplicate_titles.items(),
        start=1,
    ):

        total_duplicate_records += len(items)

        print()
        print("#" * 70)

        print(
            f"DUPLICATE TITLE GROUP "
            f"#{group_number}"
        )

        print("#" * 70)

        print()

        print("TITLE:")

        print(
            normalize_text(
                items[0].get("title") or ""
            )
        )

        print()

        print(
            f"JUMLAH ARTIKEL: "
            f"{len(items)}"
        )

        # ====================================================
        # CEK APAKAH CONTENT SAMA
        # ====================================================

        normalized_contents = set()

        for item in items:

            content = normalize_text(
                item.get("content")
                or item.get("summary")
                or ""
            )

            normalized_content = (
                content.lower()
                .strip()
            )

            if normalized_content:

                normalized_contents.add(
                    normalized_content
                )

        if len(normalized_contents) <= 1:

            content_status = (
                "⚠️ CONTENT IDENTIK / SANGAT MUNGKIN DUPLIKAT"
            )

            same_content_groups += 1

        else:

            content_status = (
                "ℹ️ CONTENT BERBEDA"
            )

            different_content_groups += 1

        print()

        print(
            f"STATUS CONTENT: "
            f"{content_status}"
        )

        print()

        print("-" * 70)

        # ====================================================
        # DETAIL SETIAP ARTIKEL
        # ====================================================

        for index, item in enumerate(
            items,
            start=1,
        ):

            article_id = item.get("id")

            title = normalize_text(
                item.get("title") or ""
            )

            link = (
                item.get("link")
                or ""
            )

            # ------------------------------------------------
            # DOMAIN
            # ------------------------------------------------

            domain = ""

            try:

                if link:

                    domain = (
                        urlparse(link)
                        .netloc
                    )

            except Exception:

                domain = ""

            # ------------------------------------------------
            # DATE
            # ------------------------------------------------

            published_date = (
                item.get("published_at")
                or item.get("published_date")
                or ""
            )

            # ------------------------------------------------
            # CONTENT
            # ------------------------------------------------

            content = normalize_text(
                item.get("content")
                or item.get("summary")
                or ""
            )

            content_length = len(content)

            content_preview = (
                content[:300]
                if content
                else "[CONTENT KOSONG]"
            )

            print()

            print(
                f"ARTIKEL #{index}"
            )

            print()

            print(
                f"ID            : "
                f"{article_id}"
            )

            print(
                f"DOMAIN        : "
                f"{domain}"
            )

            print(
                f"DATE          : "
                f"{published_date}"
            )

            print(
                f"CONTENT LENGTH: "
                f"{content_length}"
            )

            print(
                f"LINK:"
            )

            print(
                link
            )

            print()

            print(
                "CONTENT PREVIEW:"
            )

            print(
                content_preview
            )

            print()

            print("-" * 70)

    # ========================================================
    # SUMMARY
    # ========================================================

    print()

    print("=" * 70)
    print("AUDIT TITLE DUPLICATES SELESAI")
    print("=" * 70)

    print(
        f"Total artikel                  : "
        f"{len(articles)}"
    )

    print(
        f"Kelompok duplicate title       : "
        f"{len(duplicate_titles)}"
    )

    print(
        f"Total record dalam duplicate   : "
        f"{total_duplicate_records}"
    )

    print(
        f"Content identik                : "
        f"{same_content_groups} kelompok"
    )

    print(
        f"Content berbeda                : "
        f"{different_content_groups} kelompok"
    )

    print("=" * 70)

# ==============================================================
# AUDIT EVENT QUALITY
# ==============================================================


def normalize_event_text(text):
    """
    Normalisasi teks untuk perbandingan judul/event.
    """

    if not text:
        return ""

    text = text.lower()

    # Hilangkan nama media umum di akhir judul
    text = re.sub(
        r'\s*[-|:]\s*(detikcom|kompas\.com|inews\.id|tribunnews\.com|'
        r'tribun-medan\.com|antara news.*|tvonenews|waspada\.id|'
        r'harian mistar|harian sib\.com|google news|google berita).*',
        '',
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()

    return text


def title_similarity(title1, title2):
    """
    Menghitung similarity dua judul.
    """

    t1 = normalize_event_text(title1)
    t2 = normalize_event_text(title2)

    if not t1 or not t2:
        return 0

    return SequenceMatcher(None, t1, t2).ratio()


def detect_exact_duplicates(articles):
    """
    Mendeteksi artikel yang memiliki judul identik
    atau hampir identik.
    """

    duplicates = []

    for i in range(len(articles)):

        for j in range(i + 1, len(articles)):

            title1 = articles[i].get("title", "")
            title2 = articles[j].get("title", "")

            similarity = title_similarity(title1, title2)

            if similarity >= 0.97:

                duplicates.append({
                    "article_1": articles[i],
                    "article_2": articles[j],
                    "similarity": similarity
                })

    return duplicates


def detect_satker_from_articles(articles):
    """
    Mengambil SATKER dari artikel.
    """

    satkers = []

    for article in articles:

        article_satkers = (
            article.get("satker")
            or article.get("satkers")
            or []
        )

        if isinstance(article_satkers, str):
            article_satkers = [article_satkers]

        for satker in article_satkers:

            if satker:
                satkers.append(
                    str(satker).lower().strip()
                )

    if not satkers:
        return []

    counter = Counter(satkers)

    return [
        satker
        for satker, count in counter.most_common()
    ]


def evaluate_event_name(event_name):
    """
    Menilai apakah nama event cukup natural.
    """

    if not event_name:
        return {
            "score": 0,
            "status": "BURUK",
            "reason": "Nama event kosong"
        }

    words = event_name.split()

    score = 100
    problems = []

    # Nama terlalu pendek
    if len(words) < 3:
        score -= 40
        problems.append("Nama event terlalu pendek")

    # Nama terlalu panjang
    if len(words) > 12:
        score -= 15
        problems.append("Nama event terlalu panjang")

    generic_words = [
        "sumut",
        "news",
        "com",
        "online",
        "artikel",
        "berita"
    ]

    generic_count = sum(
        1 for word in words
        if word.lower() in generic_words
    )

    if generic_count >= 2:
        score -= 25
        problems.append(
            "Terlalu banyak kata generic"
        )

    if score >= 80:
        status = "BAIK"
    elif score >= 60:
        status = "CUKUP"
    else:
        status = "BURUK"

    return {
        "score": max(score, 0),
        "status": status,
        "reason": (
            ", ".join(problems)
            if problems
            else "Nama event cukup baik"
        )
    }


def evaluate_cluster_cohesion(articles):
    """
    Mengukur apakah artikel dalam cluster
    benar-benar membahas event yang sama.
    """

    if len(articles) <= 1:

        return {
            "average_similarity": 1.0,
            "score": 100,
            "status": "SINGLE"
        }

    similarities = []

    for i in range(len(articles)):

        for j in range(i + 1, len(articles)):

            title1 = articles[i].get("title", "")
            title2 = articles[j].get("title", "")

            similarity = title_similarity(
                title1,
                title2
            )

            similarities.append(similarity)

    if not similarities:
        avg_similarity = 0
    else:
        avg_similarity = (
            sum(similarities)
            / len(similarities)
        )

    score = int(avg_similarity * 100)

    if score >= 75:
        status = "SANGAT BAIK"
    elif score >= 60:
        status = "BAIK"
    elif score >= 45:
        status = "CUKUP"
    else:
        status = "LEMAH"

    return {
        "average_similarity": avg_similarity,
        "score": score,
        "status": status
    }


def calculate_event_quality(
    event_name,
    articles
):
    """
    Menghitung total quality score event.
    """

    name_result = evaluate_event_name(
        event_name
    )

    cohesion_result = (
        evaluate_cluster_cohesion(
            articles
        )
    )

    satkers = detect_satker_from_articles(
        articles
    )

    duplicates = detect_exact_duplicates(
        articles
    )

    # ==========================================================
    # SATKER SCORE
    # ==========================================================

    if satkers:
        satker_score = 100
    else:
        satker_score = 40

    # ==========================================================
    # DUPLICATE SCORE
    # ==========================================================

    article_count = len(articles)

    if article_count <= 1:

        duplicate_score = 100

    else:

        duplicate_ratio = (
            len(duplicates)
            / article_count
        )

        duplicate_score = int(
            max(
                0,
                100 - duplicate_ratio * 100
            )
        )

    # ==========================================================
    # TOTAL SCORE
    # ==========================================================

    total_score = int(

        name_result["score"] * 0.20

        + cohesion_result["score"] * 0.45

        + satker_score * 0.20

        + duplicate_score * 0.15
    )

    if total_score >= 85:
        quality = "EXCELLENT"

    elif total_score >= 70:
        quality = "GOOD"

    elif total_score >= 50:
        quality = "NEEDS REVIEW"

    else:
        quality = "POOR"

    return {

        "score": total_score,

        "quality": quality,

        "event_name": name_result,

        "cohesion": cohesion_result,

        "satkers": satkers,

        "duplicates": duplicates,

        "satker_score": satker_score,

        "duplicate_score": duplicate_score
    }


def calculate_title_similarity(title_a, title_b):

    if not title_a or not title_b:
        return 0.0

    title_a = title_a.lower().strip()
    title_b = title_b.lower().strip()

    return SequenceMatcher(
        None,
        title_a,
        title_b
    ).ratio()

def get_publisher_from_title(title):
    """Mengambil nama media dari bagian akhir judul, misalnya 'Judul - Kompas.com'."""
    if not title:
        return ""

    title = str(title).strip()

    for separator in (" - ", " | "):
        if separator in title:
            publisher = title.rsplit(separator, 1)[-1].strip()
            if publisher:
                return publisher

    return ""


# Backward-compatible alias.
def get_article_source(article):
    return get_media_source(article)


def normalize_title(title):
    if not title:
        return ""

    title = str(title).lower()
    title = re.sub(r"\s+", " ", title)
    return title.strip()

# ============================================================
# DUPLICATE PREVENTION
# ============================================================

CONTENT_DUPLICATE_THRESHOLD = 0.95


def normalize_content_for_duplicate(value):
    """
    Normalisasi content untuk perbandingan duplicate.
    """

    if not value:
        return ""

    text = normalize_text(value).lower()

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    return text


def get_article_content(article):
    """
    Mengambil content terbaik dari artikel.
    """

    if not isinstance(article, dict):
        return ""

    return (
        article.get("content")
        or article.get("summary")
        or article.get("snippet")
        or ""
    )


def calculate_content_similarity(
    content_a,
    content_b,
):
    """
    Menghitung similarity content.

    Return:
        0.0 - 1.0
    """

    text_a = normalize_content_for_duplicate(
        content_a
    )

    text_b = normalize_content_for_duplicate(
        content_b
    )

    if not text_a or not text_b:
        return 0.0

    return SequenceMatcher(
        None,
        text_a,
        text_b,
    ).ratio()


def get_media_source(article):
    """Mengembalikan identitas publisher yang stabil untuk dedupe."""
    if not isinstance(article, dict):
        return "unknown"

    for field in ("publisher", "media_name", "media", "source_name", "nama_media"):
        value = normalize_text(article.get(field))
        if value and value.lower() not in {"google news", "google news rss", "unknown"}:
            return value.strip()

    publisher = get_publisher_from_title(article.get("title", ""))
    if publisher:
        return publisher.strip()

    link = article.get("link") or article.get("url") or ""
    try:
        domain = urllib.parse.urlparse(str(link)).netloc.lower().replace("www.", "")
        if domain and domain != "news.google.com":
            return domain
    except Exception:
        pass

    source = normalize_text(article.get("source"))
    if source and source.lower() not in {"google news", "google news rss"}:
        return source.strip()

    return "unknown"

def build_title_key(article):
    """
    Duplicate title hanya dianggap duplicate
    jika berasal dari media yang sama.

    Format:
        normalized_title|media
    """

    if not isinstance(article, dict):
        return ""

    title = normalize_title(
        article.get("title", "")
    )

    media = get_media_source(
        article
    ).lower().strip()

    if not title:
        return ""

    return f"{title}|{media}"


def build_existing_title_index(
    articles,
):
    """
    Membuat index duplicate title.

    Duplicate title dicek berdasarkan:

        TITLE + MEDIA

    Jadi:

    Media A:
        "Kejari Deli Serdang Raih Penghargaan"

    Media B:
        "Kejari Deli Serdang Raih Penghargaan"

    Tetap boleh disimpan.

    Tetapi jika judul identik dari media yang sama,
    artikel dianggap duplicate.
    """

    title_index = set()

    for article in articles:

        key = build_title_key(
            article
        )

        if key:

            title_index.add(
                key
            )

    return title_index


def build_existing_content_index(
    articles,
):
    """
    Membuat list artikel existing untuk
    pengecekan duplicate content.

    Content tidak menggunakan dictionary/set karena
    perlu perhitungan similarity.
    """

    content_index = []

    for article in articles:

        content = get_article_content(
            article
        )

        normalized = normalize_content_for_duplicate(
            content
        )

        if not normalized:
            continue

        content_index.append(
            {
                "article": article,
                "content": normalized,
            }
        )

    return content_index


def is_duplicate_content(
    article,
    existing_content_index,
    threshold=CONTENT_DUPLICATE_THRESHOLD,
):
    """
    Mengecek apakah content artikel hampir sama.

    PENTING:

    Duplicate content hanya dianggap duplicate
    jika berasal dari MEDIA YANG SAMA.

    Artikel dari media berbeda yang membahas
    event yang sama TETAP BOLEH disimpan.

    Return:

        (
            is_duplicate,
            similarity,
            matched_article
        )
    """

    # ========================================================
    # VALIDASI ARTICLE
    # ========================================================

    if not isinstance(article, dict):

        return (
            False,
            0.0,
            None,
        )

    # ========================================================
    # CANDIDATE CONTENT
    # ========================================================

    candidate_content = get_article_content(
        article
    )

    candidate_content = (
        normalize_content_for_duplicate(
            candidate_content
        )
    )

    if not candidate_content:

        return (
            False,
            0.0,
            None,
        )

    # ========================================================
    # CANDIDATE MEDIA
    # ========================================================

    candidate_media = (
        get_media_source(
            article
        )
        .lower()
        .strip()
    )

    # ========================================================
    # BEST MATCH
    # ========================================================

    best_similarity = 0.0

    best_article = None

    # ========================================================
    # CHECK EXISTING CONTENT
    # ========================================================

    for item in existing_content_index:

        if not isinstance(item, dict):
            continue

        existing_article = item.get(
            "article"
        )

        if not isinstance(
            existing_article,
            dict,
        ):
            continue

        # ====================================================
        # GET EXISTING MEDIA
        # ====================================================

        existing_media = (
            get_media_source(
                existing_article
            )
            .lower()
            .strip()
        )

        # ====================================================
        # PENTING
        #
        # HANYA BANDINGKAN CONTENT
        # DARI MEDIA YANG SAMA
        # ====================================================

        if existing_media != candidate_media:
            continue

        # ====================================================
        # EXISTING CONTENT
        # ====================================================

        existing_content = item.get(
            "content",
            "",
        )

        if not existing_content:
            continue

        # ====================================================
        # CALCULATE SIMILARITY
        # ====================================================

        similarity = (
            calculate_content_similarity(
                candidate_content,
                existing_content,
            )
        )

        # ====================================================
        # BEST MATCH
        # ====================================================

        if similarity > best_similarity:

            best_similarity = similarity

            best_article = existing_article

    # ========================================================
    # DUPLICATE DECISION
    # ========================================================

    if best_similarity >= threshold:

        return (
            True,
            best_similarity,
            best_article,
        )

    return (
        False,
        best_similarity,
        best_article,
    )
    
def should_save_article(
    article,
    existing_link_index,
    existing_title_index,
    existing_content_index,
):
    """
    CENTRAL DECISION FUNCTION.

    Menentukan apakah artikel boleh disimpan.

    PRIORITAS:

    1. Duplicate URL
       -> JANGAN SIMPAN

    2. Duplicate Title + Media
       -> JANGAN SIMPAN

    3. Duplicate Content + Media Sama
       -> JANGAN SIMPAN

    4. Event sama + Media berbeda
       -> TETAP SIMPAN

    Return:

        (
            should_save,
            reason,
            similarity,
            matched_article
        )
    """

    # ========================================================
    # VALIDATE ARTICLE
    # ========================================================

    if not isinstance(article, dict):

        return (
            False,
            "INVALID_ARTICLE",
            0.0,
            None,
        )

    # ========================================================
    # VALIDATE LINK
    # ========================================================

    link = normalize_url(
        article.get("link")
    )

    if not link:

        return (
            False,
            "INVALID_LINK",
            0.0,
            None,
        )

    # ========================================================
    # 1. DUPLICATE URL
    # ========================================================

    if link in existing_link_index:

        return (
            False,
            "DUPLICATE_URL",
            1.0,
            None,
        )

    # ========================================================
    # 2. DUPLICATE TITLE + SAME MEDIA
    # ========================================================

    title_key = build_title_key(
        article
    )

    if (
        title_key
        and title_key in existing_title_index
    ):

        return (
            False,
            "DUPLICATE_TITLE_SAME_MEDIA",
            1.0,
            None,
        )

    # ========================================================
    # 3. DUPLICATE CONTENT
    #
    # Fungsi is_duplicate_content()
    # sekarang hanya membandingkan media yang sama.
    # ========================================================

    (
        content_duplicate,
        similarity,
        matched_article,
    ) = is_duplicate_content(

        article,

        existing_content_index,

    )

    if content_duplicate:

        matched_media = (
            get_media_source(
                matched_article
            )
            if matched_article
            else "Unknown"
        )

        candidate_media = (
            get_media_source(
                article
            )
        )

        return (
            False,

            (
                "DUPLICATE_CONTENT_SAME_MEDIA "
                f"({similarity:.2%}) "
                f"| media={candidate_media} "
                f"| matched={matched_media}"
            ),

            similarity,

            matched_article,
        )

    # ========================================================
    # 4. ARTICLE IS NEW
    #
    # Event sama dari media berbeda
    # TETAP BOLEH MASUK DATABASE.
    #
    # Event clustering hanya digunakan untuk:
    #
    # - audit
    # - intelligence
    # - analytics
    #
    # BUKAN untuk memblokir artikel.
    # ========================================================

    return (
        True,
        "NEW_ARTICLE",
        similarity,
        None,
    )

def register_saved_article(
    article,
    existing_link_index,
    existing_title_index,
    existing_content_index,
):
    """
    Update seluruh index setelah artikel
    berhasil disimpan ke database.

    PENTING:
    Fungsi ini hanya dipanggil SETELAH
    upsert_article berhasil.
    """

    if not isinstance(article, dict):
        return

    # ========================================================
    # REGISTER URL
    # ========================================================

    link = normalize_url(
        article.get("link")
    )

    if link:

        existing_link_index.add(
            link
        )

    # ========================================================
    # REGISTER TITLE + MEDIA
    # ========================================================

    title_key = build_title_key(
        article
    )

    if title_key:

        existing_title_index.add(
            title_key
        )

    # ========================================================
    # REGISTER CONTENT
    # ========================================================

    content = get_article_content(
        article
    )

    normalized_content = (
        normalize_content_for_duplicate(
            content
        )
    )

    if normalized_content:

        existing_content_index.append(
            {
                "article": article,
                "content": normalized_content,
            }
        )

def count_duplicate_titles(titles):
    normalized_titles = [normalize_title(title) for title in titles if title]
    return len(normalized_titles) - len(set(normalized_titles))


def detect_duplicate_sources(cluster):
    title_sources = defaultdict(set)

    for article in cluster:
        title = normalize_title(article.get("title", ""))
        if title:
            title_sources[title].add(get_media_source(article))

    return [
        {"title": title, "sources": sorted(sources)}
        for title, sources in title_sources.items()
        if len(sources) > 1
    ]


def _cluster_average_similarity(cluster):
    """Similarity judul antar semua pasangan artikel dalam skala 0..100."""
    similarities = []

    for article_a, article_b in combinations(cluster, 2):
        title_a = article_a.get("title", "")
        title_b = article_b.get("title", "")
        similarity = calculate_title_similarity(title_a, title_b)
        similarities.append(similarity * 100)

    return sum(similarities) / len(similarities) if similarities else 0.0


def audit_event_quality(articles):
    print("=" * 70)
    print("AUDIT EVENT QUALITY")
    print("=" * 70)
    print()
    print(f"[AUDIT] Total artikel: {len(articles)}")

    clusters = cluster_events(articles)

    print()
    print(f"[AUDIT] Total event cluster: {len(clusters)}")

    high_events = 0
    medium_events = 0
    low_events = 0
    clusters_with_duplicates = 0
    total_duplicate_titles = 0

    for cluster_index, cluster in enumerate(clusters, start=1):
        print()
        print("=" * 70)
        print(f"EVENT CLUSTER #{cluster_index}")
        print("=" * 70)
        print()
        print(f"Jumlah artikel: {len(cluster)}")

        event_name = generate_event_name(cluster)
        if event_name:
            print(f"EVENT: {event_name}")

        average_similarity = _cluster_average_similarity(cluster)

        sources = {
            get_media_source(article)
            for article in cluster
            if get_media_source(article)
        }
        unique_sources = len(sources)

        event_score = 0
        if average_similarity >= 85:
            event_score += 50
        elif average_similarity >= 70:
            event_score += 40
        elif average_similarity >= 50:
            event_score += 30
        else:
            event_score += 15

        if unique_sources >= 4:
            event_score += 30
        elif unique_sources >= 2:
            event_score += 25
        else:
            event_score += 15

        if len(cluster) >= 5:
            event_score += 20
        elif len(cluster) >= 3:
            event_score += 15
        else:
            event_score += 10

        event_score = min(event_score, 100)

        if event_score >= 80:
            event_level = "HIGH"
            high_events += 1
        elif event_score >= 60:
            event_level = "MEDIUM"
            medium_events += 1
        else:
            event_level = "LOW"
            low_events += 1

        # PENTING: counter ini di-reset untuk SETIAP cluster.
        title_counter = Counter(
            normalize_title(article.get("title", ""))
            for article in cluster
            if normalize_title(article.get("title", ""))
        )

        cluster_duplicate_titles = sum(
            count - 1
            for count in title_counter.values()
            if count > 1
        )

        if cluster_duplicate_titles > 0:
            database_status = "DUPLICATES DETECTED"
            clusters_with_duplicates += 1
        else:
            database_status = "CLEAN"

        total_duplicate_titles += cluster_duplicate_titles

        print()
        print("EVENT QUALITY")
        print(f"Event Score         : {event_score}/100")
        print(f"Event Level         : {event_level}")
        print(f"Average Similarity  : {average_similarity:.2f}%")
        print(f"Unique Media Sources: {unique_sources}")

        print()
        print("DATA QUALITY")
        print(f"Duplicate Titles    : {cluster_duplicate_titles}")
        print(f"Database Status     : {database_status}")

        print()
        print("MEDIA:")
        for source in sorted(sources) or ["Unknown"]:
            print(f"- {source}")

        print()
        print("ARTIKEL:")
        for index, article in enumerate(cluster, start=1):
            article_id = article.get("id", "Unknown")
            title = article.get("title", "No Title")
            media = get_media_source(article)
            print()
            print(f"[{index}] ID={article_id}")
            print(title)
            print(f"Media: {media}")

    print_event_quality_summary(
        total_articles=len(articles),
        total_clusters=len(clusters),
        high_events=high_events,
        medium_events=medium_events,
        low_events=low_events,
        clusters_with_duplicates=clusters_with_duplicates,
        total_duplicate_titles=total_duplicate_titles,
    )

    print()
    print("=" * 70)
    print("AUDIT EVENT QUALITY SELESAI")
    print("=" * 70)


def print_event_quality_summary(
    total_articles,
    total_clusters,
    high_events,
    medium_events,
    low_events,
    clusters_with_duplicates,
    total_duplicate_titles
):

    print()
    print("=" * 70)
    print("AUDIT EVENT QUALITY SUMMARY")
    print("=" * 70)

    print()
    print(f"Total Artikel              : {total_articles}")
    print(f"Total Event Cluster        : {total_clusters}")

    print()
    print(f"HIGH Quality Events        : {high_events}")
    print(f"MEDIUM Quality Events      : {medium_events}")
    print(f"LOW Quality Events         : {low_events}")

    print()
    print(f"Clusters With Duplicates   : {clusters_with_duplicates}")
    print(f"Total Duplicate Titles     : {total_duplicate_titles}")

    print()
    print("-" * 70)

    # DATABASE HEALTH

    if total_duplicate_titles == 0:

        database_health = "HEALTHY"

    elif total_duplicate_titles <= 5:

        database_health = "WARNING"

    else:

        database_health = "CRITICAL"

    print(f"Database Health            : {database_health}")

    print()
    print("=" * 70)
    print("RECOMMENDATION")
    print("=" * 70)

    if total_duplicate_titles > 0:

        print()
        print("1. Jalankan audit_exact_duplicates")
        print("2. Jalankan audit_title_duplicates")
        print("3. Periksa duplicate ingestion dari berbagai source")
        print("4. Gunakan duplicate prevention sebelum insert database")

    else:

        print()
        print("Tidak ditemukan duplicate title.")
        print("Database dalam kondisi baik.")

    print()
    
    
# ============================================================
# MAIN
# ============================================================

def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Patroli Siber berita "
            "Kejari Deli Serdang"
        )
    )
        
    parser.add_argument(
        "--once",
        action="store_true",
        help=(
            "jalankan patroli satu kali"
        ),
    )

    parser.add_argument(
        "--production-audit",
        action="store_true",
        help=(
            "jalankan patroli normal lalu validasi invariant production"
        ),
    )

    parser.add_argument(
        "--reclassify",
        action="store_true",
        help=(
            "klasifikasi ulang seluruh "
            "artikel di database"
        ),
    )

    parser.add_argument(
        "--dedupe-dry-run",
        action="store_true",
        help=(
            "cek duplicate link tanpa "
            "mengubah database"
        ),
    )

    parser.add_argument(
        "--dedupe",
        action="store_true",
        help=(
            "hapus duplicate link "
            "dari database"
        ),
    )

    parser.add_argument(
        "--sanitize-database",
        action="store_true",
        help=(
            "membersihkan HTML dari "
            "data artikel di database"
        ),
    )

    parser.add_argument(
        "--audit-negative-articles",
        action="store_true",
        help="Audit artikel yang diklasifikasikan sebagai Negatif Kuat",
    )

    parser.add_argument(
        "--audit-exact-duplicates",
        action="store_true",
        help=(
            "audit artikel dengan title dan "
            "content identik"
        ),
    )
    
    parser.add_argument(
        "--audit-content-duplicates",
        action="store_true",
        help=(
            "audit artikel dengan judul atau "
            "konten duplicate"
        ),
    )

    parser.add_argument(
        "--audit-title-duplicates",
        action="store_true",
        help=(
            "audit detail artikel dengan judul sama"
        ),
    )

    parser.add_argument(
        "--audit-event-duplicates",
        action="store_true",
        help=(
            "audit artikel dengan event yg sama"
        ),
    )

    parser.add_argument(
        "--audit-event-quality",
        action="store_true",
        help=(
            "audit kualitas event yg sama"
        ),
    )

    args = parser.parse_args()

    # --------------------------------------------------------
    # PRODUCTION AUDIT
    # --------------------------------------------------------

    if args.production_audit:

        production_audit()

        return

    # --------------------------------------------------------
    # SANITIZE DATABASE
    # --------------------------------------------------------

    if args.sanitize_database:

        sanitize_database()

        return

    # --------------------------------------------------------
    # DEDUPE DRY RUN
    # --------------------------------------------------------

    if args.dedupe_dry_run:

        dedupe_dry_run()

        return

    # --------------------------------------------------------
    # DEDUPE REAL
    # --------------------------------------------------------

    if args.dedupe:

        dedupe_database()

        return

    # --------------------------------------------------------
    # RECLASSIFY
    # --------------------------------------------------------

    if args.reclassify:

        reclassify_all()

        return

    if args.audit_negative_articles:

        audit_negative_articles()

        return

    if args.audit_event_duplicates:

        articles = get_all_articles()
        
        audit_event_duplicates(articles)

        return

    if args.audit_event_quality:

        articles = get_all_articles()
        
        audit_event_quality(articles)

        return


    # --------------------------------------------------------
    # AUDIT EXACT DUPLICATES
    # --------------------------------------------------------
    
    if args.audit_exact_duplicates:
    
        audit_exact_duplicates()
    
        return


    if args.audit_content_duplicates:

        audit_content_duplicates()

        return

    # --------------------------------------------------------
    # AUDIT TITLE DUPLICATES
    # --------------------------------------------------------
    
    if args.audit_title_duplicates:
    
        audit_title_duplicates()
    
        return

    # --------------------------------------------------------
    # DEFAULT
    #
    # Cocok untuk GitHub Actions,
    # cron, Task Scheduler, dll.
    # --------------------------------------------------------

    # --once maupun tanpa argumen menjalankan satu patroli.
    run_once()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
