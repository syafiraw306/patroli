import argparse
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

def fetch_webpage_content(
    url: str,
) -> Tuple[str, str]:

    if not url:
        return "", ""

    try:

        response = SESSION.get(
            url,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )

        response.raise_for_status()

        final_url = normalize_url(
            response.url
        )

        return (
            final_url,
            response.text,
        )

    except Exception as exc:

        print(
            f"[FETCH ERROR] "
            f"{url} -> "
            f"{type(exc).__name__}: {exc}"
        )

        return (
            url,
            "",
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

    encoded = (
        urllib.parse.quote_plus(
            query
        )
    )

    url = (
        "https://news.google.com/rss/search?"
        f"q={encoded}"
        "&hl=id"
        "&gl=ID"
        "&ceid=ID:id"
    )

    try:

        response = SESSION.get(
            url,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )

        response.raise_for_status()

        feed = feedparser.parse(
            response.content
        )

        print(
            f"[RSS DEBUG] "
            f"query={query} | "
            f"status={response.status_code} | "
            f"bytes={len(response.content)} | "
            f"entries={len(feed.entries)} | "
            f"bozo={getattr(feed, 'bozo', False)}"
        )

        if getattr(
            feed,
            "bozo",
            False,
        ):

            bozo_exception = (
                getattr(
                    feed,
                    "bozo_exception",
                    None,
                )
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
                f"Tidak ada entry untuk: "
                f"{query}"
            )

            return []

        rows = []

        for entry in feed.entries[
            :MAX_ARTICLES_PER_FEED
        ]:

            link = normalize_url(
                entry.get("link")
            )

            if not link:
                continue

            published = (
                extract_feed_date(
                    entry
                )
            )

            source_value = (
                entry.get("source")
            )

            if isinstance(
                source_value,
                dict,
            ):

                source = (
                    source_value.get(
                        "title",
                        "",
                    )
                )

            else:

                source = (
                    source_value
                    or ""
                )

            rows.append(
                {
                    "title": normalize_text(
                        entry.get(
                            "title"
                        )
                    ),

                    "link": link,

                    "published_date": (
                        published.isoformat()
                        if published
                        else None
                    ),

                    "source": normalize_text(
                        source
                    ),

                    "rss_description": (
                        normalize_text(
                            entry.get(
                                "summary"
                            )
                        )
                    ),
                }
            )

        print(
            f"[RSS OK] "
            f"{query} -> "
            f"{len(rows)} kandidat"
        )

        return rows

    except Exception as exc:

        print(
            f"[RSS ERROR] "
            f"{query} -> "
            f"{type(exc).__name__}: {exc}"
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

    for query in SEARCH_TARGETS:

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

    # --------------------------------------------------------
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
    
        final_url, raw_html = (
            fetch_webpage_content(
                rss_link
            )
        )
    
    except Exception as exc:
    
        print(
            "[FETCH WARNING] "
            f"{rss_link} -> "
            f"{type(exc).__name__}: "
            f"{exc}"
        )
    
        final_url = rss_link
        raw_html = ""
    
    final_url = normalize_url(
        final_url or rss_link
    )
    
    if not final_url:
    
        final_url = rss_link
    
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
        f"<b>Satker:</b> "
        f"{html.escape(NAMA_SATKER)}\n\n"
        f"<b>{title}</b>\n"
        f"{link}"
    )


def send_alert_if_needed(
    article: Dict[str, Any],
) -> bool:

    if (
        article.get(
            "category"
        )
        not in {
            "Negatif Kuat",
            "Perlu Penanganan",
        }
    ):

        return False

    return send_telegram_message(
        telegram_text(
            article
        )
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

    for article in valid_articles:

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

    
    # ========================================================
    
    # DEDUPE SUMMARY COUNTERS
    
    # ========================================================
    
    duplicate_url_count = 0
    
    duplicate_title_count = 0
    
    duplicate_content_count = 0
    
    other_skip_count = 0
    
    passed_dedupe_count = 0
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
    
    
        
        # ====================================================
        # DEDUPE SUMMARY COUNTER
        # ====================================================
        reason_text = normalize_text(reason)

        if should_save:
            passed_dedupe_count += 1

        elif reason_text == "DUPLICATE_URL":
            duplicate_url_count += 1

        elif reason_text.startswith(
            "DUPLICATE_TITLE_SAME_MEDIA"
        ):
            duplicate_title_count += 1

        elif reason_text.startswith(
            "DUPLICATE_CONTENT_SAME_MEDIA"
        ):
            duplicate_content_count += 1

        else:
            other_skip_count += 1

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
    # TELEGRAM
    # ========================================================

    telegram_count = 0
    telegram_skip_count = 0
    telegram_skip_categories = Counter()

    if telegram_enabled():

        for article in new_articles:

            category = normalize_text(
                article.get("category")
            ) or "Tidak diketahui"

            if category not in {
                "Negatif Kuat",
                "Perlu Penanganan",
            }:

                telegram_skip_count += 1
                telegram_skip_categories[category] += 1

                print(
                    "[TELEGRAM SKIP] "
                    f"Kategori tidak dikirim: "
                    f"{category}"
                )

                continue

            try:

                if not send_alert_if_needed(
                    article
                ):

                    telegram_skip_count += 1

                    print(
                        "[TELEGRAM SKIP] "
                        f"Tidak terkirim: "
                        f"{article.get('title', '')[:100]}"
                    )

                    continue

                telegram_count += 1

                print(
                    "[TELEGRAM] Terkirim: "
                    f"{article.get('title', '')[:100]}"
                )

            except Exception as exc:

                telegram_skip_count += 1

                print(
                    f"[TELEGRAM ERROR] "
                    f"{type(exc).__name__}: "
                    f"{exc}"
                )

    else:

        telegram_skip_count = len(new_articles)

        print(
            "[TELEGRAM] Tidak aktif. "
            "Periksa TELEGRAM_BOT_TOKEN "
            "dan TELEGRAM_CHAT_ID."
        )

    # ========================================================
    # DATABASE SUMMARY
    # ========================================================

    print()
    print(
        f"[DATABASE] Berhasil disimpan: "
        f"{saved_count}"
    )

    print()
    print(
        f"[DATABASE] Gagal simpan: "
        f"{save_failed}"
    )

    print()
    print(
        f"[DATABASE] Artikel baru: "
        f"{len(new_articles)}"
    )

    # ========================================================
    # DEDUPE SUMMARY
    # ========================================================

    print()
    print("=" * 70)
    print("DEDUPE SUMMARY")
    print("=" * 70)

    print(
        f"[DEDUPE] Duplicate URL      : "
        f"{duplicate_url_count}"
    )

    print(
        f"[DEDUPE] Duplicate Title    : "
        f"{duplicate_title_count}"
    )

    print(
        f"[DEDUPE] Duplicate Content  : "
        f"{duplicate_content_count}"
    )

    print(
        f"[DEDUPE] Other Skip Reason  : "
        f"{other_skip_count}"
    )

    print(
        f"[DEDUPE] Lolos Dedupe       : "
        f"{passed_dedupe_count}"
    )

    print(
        f"[DEDUPE] Artikel Baru Saved : "
        f"{saved_count}"
    )

    print("=" * 70)

    print(
        f"[TELEGRAM] Total artikel baru: "
        f"{len(new_articles)}"
    )

    for category, count in sorted(
        telegram_skip_categories.items()
    ):

        suffix = f" ({count})" if count > 1 else ""

        print(
            "[TELEGRAM SKIP] "
            f"Kategori tidak dikirim: "
            f"{category}{suffix}"
        )

    print(
        f"[TELEGRAM] Berhasil dikirim: "
        f"{telegram_count}"
    )

    print(
        f"[TELEGRAM] Tidak dikirim/skipped: "
        f"{telegram_skip_count}"
    )

    print()
    print("=" * 70)
    print("REKLASIFIKASI SELESAI")
    print("=" * 70)

    # ========================================================
    # RECLASSIFICATION
    # ========================================================

    counts = reclassify_all()

    # ========================================================
    # FINAL DATABASE
    # ========================================================

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

        "reclassified_count": len(
            final_articles
        ),

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

    print("[DB LOG] Run log berhasil disimpan.")

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
