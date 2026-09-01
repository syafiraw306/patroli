import argparse
import csv
import html
import json
import os
import re
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import feedparser
import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from dotenv import load_dotenv

from database import (
    get_all_articles,
    get_supabase,
    get_article_by_link,
    save_run_log,
    upsert_article,
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
# TARGET SATKER
# ============================================================

TARGET_KEJARI_KEYWORDS = [
    "kejaksaan negeri deli serdang",
    "kejari deli serdang",
    "kejari deliserdang",
    "kejaksaan deli serdang",
    "kajari deli serdang",
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

    # keberhasilan
    r"\bberhasil\s+(?:mengungkap|mengamankan|menangkap|menyita|membongkar)",
    r"\bberhasil\s+.*?\bmenangkap\b",
    r"\bberhasil\s+.*?\bmengamankan\b",
    r"\bberhasil\s+.*?\bmenyita\b",
    r"\bberhasil\s+.*?\bmengungkap\b",

    # pengungkapan
    r"\bmengungkap\s+(?:kasus|perkara)\b",
    r"\bungkap\s+(?:kasus|perkara)\b",
    r"\bmengungkap\s+.*?\bkasus\b",
    r"\bmembongkar\s+.*?\bkasus\b",

    # penangkapan
    r"\bmenangkap\s+(?:tersangka|pelaku)\b",
    r"\bmenangkap\s+.*?\btersangka\b",
    r"\bmengamankan\s+(?:tersangka|pelaku)\b",
    r"\bmengamankan\s+.*?\btersangka\b",

    # penyitaan
    r"\bmenyita\s+(?:barang bukti|aset)\b",
    r"\bmenyita\s+.*?\bbarang bukti\b",
    r"\bmenyita\s+.*?\baset\b",
    r"\bsita\s+(?:barang bukti|aset)\b",

    # penetapan tersangka
    r"\bmenetapkan\s+.*?\bsebagai\s+tersangka\b",
    r"\bditetapkan\s+.*?\bsebagai\s+tersangka\b",

    # penyidikan
    r"\bmelakukan\s+penyidikan\b",
    r"\bmelaksanakan\s+penyidikan\b",
    r"\bmelakukan\s+penyelidikan\b",
    r"\bmelaksanakan\s+penyelidikan\b",
    r"\bberhasil\s+melakukan\s+penyidikan\b",
    r"\bberhasil\s+melakukan\s+penyelidikan\b",

    # penuntutan
    r"\bmelakukan\s+penuntutan\b",
    r"\bmelaksanakan\s+penuntutan\b",
    r"\bmenuntut\s+.*?\bdi\s+persidangan\b",
    r"\bmembacakan\s+tuntutan\b",

    # eksekusi
    r"\bmelaksanakan\s+eksekusi\b",
    r"\bmelakukan\s+eksekusi\b",
    r"\beksekusi\s+.*?\bputusan\b",
    r"\beksekusi\s+.*?\bterpidana\b",
]


# ============================================================
# KEGIATAN RESMI
# ============================================================

OFFICIAL_ACTIVITY_PATTERNS = [
    r"\bapel\b",
    r"\bupacara\b",
    r"\brapat\b",
    r"\bfgd\b",
    r"\bfocus group discussion\b",
    r"\bkunjungan\b",
    r"\bsilaturahmi\b",
    r"\bkonsolidasi\b",
    r"\bkoordinasi\b",
    r"\bmonitoring\b",
    r"\bevaluasi\b",
    r"\bpenyuluhan hukum\b",
    r"\bpenerangan hukum\b",
    r"\bsosialisasi\b",
    r"\bpelantikan\b",
    r"\bpengambilan sumpah\b",
    r"\bserah terima\b",
    r"\blaunching\b",
    r"\bperesmian\b",
    r"\bpenandatanganan\b",
    r"\bkerja sama\b",
    r"\bmoa\b",
    r"\bmou\b",
    r"\bziarah\b",
    r"\bbakti sosial\b",
    r"\bgotong royong\b",
    r"\bkunjungan kerja\b",
    r"\bmengikuti zoom\b",
    r"\bmenghadiri\b",
    r"\bhadiri\b",
    r"\bmemimpin rapat\b",
    r"\bmemimpin\b",
    r"\bmengikuti\b",
    r"\bupacara peringatan\b",
    r"\bapel pagi\b",
    r"\bapel gabungan\b",
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

    # --------------------------------------------------------
    # KAJARI / KEPALA KEJAKSAAN SEBAGAI PIHAK BERMASALAH
    # --------------------------------------------------------

    r"\b(?:kajari|kepala kejaksaan)\b.{0,180}"
    r"\b(?:ditangkap|diamankan|ditetapkan\s+sebagai\s+tersangka|"
    r"menjadi\s+tersangka|tersangka|terdakwa|terpidana)\b",

    r"\b(?:kajari|kepala kejaksaan)\b.{0,180}"
    r"\b(?:suap|gratifikasi|korupsi|pungli|pemerasan|penggelapan)\b",

    r"\b(?:kajari|kepala kejaksaan)\b.{0,180}"
    r"\b(?:diperiksa|dipanggil|dilaporkan|diadukan|"
    r"disidang|diadili)\b",

    r"\b(?:kajari|kepala kejaksaan)\b.{0,180}"
    r"\b(?:dicopot|diberhentikan|dimutasi\s+karena)\b",

    # --------------------------------------------------------
    # JAKSA / PEGAWAI INTERNAL
    # --------------------------------------------------------

    r"\b(?:jaksa|jaksa penuntut umum|pegawai kejaksaan|"
    r"pejabat kejaksaan|petugas kejaksaan)\b.{0,180}"
    r"\b(?:ditangkap|diamankan|ditetapkan\s+sebagai\s+tersangka|"
    r"menjadi\s+tersangka|tersangka|terdakwa)\b",

    r"\b(?:jaksa|pegawai kejaksaan|pejabat kejaksaan)\b.{0,180}"
    r"\b(?:suap|gratifikasi|korupsi|pungli|pemerasan|"
    r"penggelapan)\b",

    r"\b(?:jaksa|pegawai kejaksaan|pejabat kejaksaan)\b.{0,180}"
    r"\b(?:dilaporkan|diadukan|diperiksa|dipanggil|"
    r"disidang|diadili)\b",

    # --------------------------------------------------------
    # KEJARI SEBAGAI INSTITUSI YANG DITUDUH
    # --------------------------------------------------------

    r"\b(?:kejari|kejaksaan negeri|kejaksaan deli serdang|"
    r"cabjari|cabang kejaksaan negeri)\b.{0,180}"
    r"\b(?:diduga|terindikasi|dituding|dituduh)\b.{0,100}"
    r"\b(?:melakukan|terlibat|menerima|meminta|memeras)\b",

    r"\b(?:kejari|kejaksaan negeri|kejaksaan deli serdang|"
    r"cabjari|cabang kejaksaan negeri)\b.{0,180}"
    r"\b(?:pelanggaran etik|pelanggaran hukum|"
    r"maladministrasi)\b",

    # --------------------------------------------------------
    # PENGADUAN / LAPORAN LANGSUNG TERHADAP KEJARI
    # --------------------------------------------------------

    r"\b(?:kejari|kejaksaan negeri|kejaksaan deli serdang|"
    r"cabjari|cabang kejaksaan negeri)\b.{0,180}"
    r"\b(?:dilaporkan|diadukan)\b",

    r"\b(?:dilaporkan|diadukan)\b.{0,180}"
    r"\b(?:kejari|kejaksaan negeri|kejaksaan deli serdang|"
    r"cabjari|cabang kejaksaan negeri)\b",

    r"\b(?:laporan pengaduan|aduan masyarakat)\b.{0,180}"
    r"\b(?:kejari|kejaksaan negeri|kajari|kepala kejaksaan)\b",

    # --------------------------------------------------------
    # KANTOR SATKER SEBAGAI OBJEK
    # --------------------------------------------------------

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
# SANITASI TEKS
# ============================================================

def clean_html_text(value):
    """
    Membersihkan HTML dari teks yang berasal dari RSS,
    Google News, website berita, atau sumber eksternal.

    Contoh:

        <a href="https://...">Judul Berita</a>
        <font color="#6f6f6f">Media Online</font>

    menjadi:

        Judul Berita Media Online
    """

    if value is None:
        return ""

    if isinstance(value, (dict, list, tuple)):
        return str(value)

    text = str(value)

    if not text:
        return ""

    # --------------------------------------------------------
    # Decode HTML entities
    # --------------------------------------------------------

    text = html.unescape(text)

    # --------------------------------------------------------
    # Hapus script
    # --------------------------------------------------------

    text = re.sub(
        r"<script\b[^>]*>.*?</script>",
        " ",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # --------------------------------------------------------
    # Hapus style
    # --------------------------------------------------------

    text = re.sub(
        r"<style\b[^>]*>.*?</style>",
        " ",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # --------------------------------------------------------
    # Pertahankan isi anchor <a>...</a>
    # tetapi buang tag-nya.
    # --------------------------------------------------------

    text = re.sub(
        r"<a\b[^>]*>(.*?)</a>",
        r" \1 ",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # --------------------------------------------------------
    # Hapus seluruh tag HTML lainnya
    # --------------------------------------------------------

    text = re.sub(
        r"<[^>]+>",
        " ",
        text,
        flags=re.IGNORECASE,
    )

    # --------------------------------------------------------
    # Decode entity sekali lagi
    # --------------------------------------------------------

    text = html.unescape(text)

    # --------------------------------------------------------
    # Hapus URL Google News yang berdiri sendiri
    # --------------------------------------------------------

    text = re.sub(
        r"https?://news\.google\.com/\S+",
        " ",
        text,
        flags=re.IGNORECASE,
    )

    # --------------------------------------------------------
    # Hapus URL yang tersisa jika memang tidak diperlukan
    # --------------------------------------------------------

    text = re.sub(
        r"https?://\S+",
        " ",
        text,
        flags=re.IGNORECASE,
    )

    # --------------------------------------------------------
    # Hapus karakter kontrol
    # --------------------------------------------------------

    text = re.sub(
        r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]",
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
    )

    return text.strip()


def clean_text_list(value):
    """
    Membersihkan field yang dapat berupa list/string.

    Contoh:
        [
            '<a href="...">Judul</a>',
            '<font>Media</font>'
        ]

    menjadi:
        [
            'Judul',
            'Media'
        ]
    """

    if value is None:
        return []

    if isinstance(value, str):
        value = [value]

    if not isinstance(value, (list, tuple)):
        value = [value]

    result = []

    for item in value:

        cleaned = clean_html_text(item)

        if cleaned and cleaned not in result:
            result.append(cleaned)

    return result

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


def normalize_url(url: Any) -> str:
    """
    Canonical URL untuk deduplikasi:
    - http/https diperlakukan sama dan disimpan sebagai https
    - www. dihilangkan
    - fragment dihilangkan
    - tracking parameter umum dihilangkan
    - trailing slash dihilangkan (kecuali root)
    """
    value = str(url or "").strip()
    if not value:
        return ""
    try:
        if not re.match(r"^[a-z][a-z0-9+.-]*://", value, re.I):
            value = "https://" + value
        parsed = urllib.parse.urlsplit(value)
        scheme = "https" if parsed.scheme.lower() in {"http", "https"} else parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        path = parsed.path.rstrip("/") or "/"
        tracking_keys = {
            "utm_source", "utm_medium", "utm_campaign", "utm_term",
            "utm_content", "fbclid", "gclid", "dclid", "msclkid",
            "ref", "referrer", "source", "mc_cid", "mc_eid", "_ga", "_gl",
        }
        clean_query = [
            (k, v) for k, v in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
            if k.lower() not in tracking_keys
        ]
        query = urllib.parse.urlencode(clean_query, doseq=True)
        return urllib.parse.urlunsplit((scheme, netloc, path, query, ""))
    except Exception:
        return value.split("#", 1)[0].rstrip("/")


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

    text = normalize_text(
        f"{title}. {content}"
    ).lower()

    matches = []

    for keyword in TARGET_KEJARI_KEYWORDS:

        if (
            keyword.lower()
            in text
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

def sentence_contains_satker(
    sentence: str,
) -> bool:

    text = sentence.lower()

    return any(
        keyword.lower()
        in text
        for keyword
        in TARGET_KEJARI_KEYWORDS
    )


def sentence_contains_internal_actor(
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
        in INTERNAL_ACTOR_PATTERNS
    )


def sentence_contains_satker_institution(
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
        in SATKER_INSTITUTION_PATTERNS
    )


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

    sentences = split_sentences(
        f"{title}. {content}"
    )

    contexts = []

    for sentence in sentences:

        if sentence_has_negation(
            sentence
        ):

            continue

        if regex_hits(
            sentence,
            POSITIVE_ACTION_PATTERNS,
        ):

            contexts.append(
                sentence
            )

    return contexts[:20]


def find_official_activity_context(
    title: str,
    content: str,
) -> List[str]:

    sentences = split_sentences(
        f"{title}. {content}"
    )

    contexts = []

    for sentence in sentences:

        if sentence_has_negation(
            sentence
        ):

            continue

        if regex_hits(
            sentence,
            OFFICIAL_ACTIVITY_PATTERNS,
        ):

            contexts.append(
                sentence
            )

    return contexts[:20]


# ============================================================
# NEGATIVE CONTEXT
# ============================================================

def find_negative_context(
    title: str,
    content: str,
) -> List[str]:

    sentences = split_sentences(
        f"{title}. {content}"
    )

    contexts = []

    for sentence in sentences:

        if sentence_has_negation(
            sentence
        ):

            continue

        hits = regex_hits(
            sentence,
            NEGATIVE_STRONG_PATTERNS,
        )

        if not hits:
            continue

        # ----------------------------------------------------
        # PENTING:
        #
        # Pastikan kalimat memang menyebut satker/internal.
        # ----------------------------------------------------

        if (
            sentence_contains_satker(
                sentence
            )
            or sentence_contains_internal_actor(
                sentence
            )
        ):

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

    sentences = split_sentences(
        f"{title}. {content}"
    )

    contexts = []

    for sentence in sentences:

        if sentence_has_negation(
            sentence
        ):

            continue

        if not sentence_contains_satker(
            sentence
        ):

            continue

        if regex_hits(
            sentence,
            HANDLING_PATTERNS,
        ):

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

    title = normalize_text(
        title
    )

    content = normalize_text(
        content
    )

    full = (
        f"{title}. {content}"
    ).lower()

    positive_action_hits = (
        regex_hits(
            full,
            POSITIVE_ACTION_PATTERNS,
        )
    )

    official_hits = (
        regex_hits(
            full,
            OFFICIAL_ACTIVITY_PATTERNS,
        )
    )

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
    )

    score = 0

    # Aksi penegakan hukum
    score += (
        4 * len(
            positive_action_hits
        )
    )

    # Kegiatan resmi
    score += (
        3 * len(
            official_hits
        )
    )

    # Konteks positif
    score += (
        3 * len(
            positive_context
        )
    )

    # Konteks kegiatan
    score += (
        2 * len(
            official_context
        )
    )

    # Positive di judul
    title_positive = regex_hits(
        title.lower(),
        POSITIVE_ACTION_PATTERNS,
    )

    if title_positive:

        score += 5

    # Positive activity yang jelas menyebut satker
    if (
        official_context
        and check_satker_relevance(
            title,
            content,
        )
    ):

        score += 3

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

    title = normalize_text(
        title
    )

    content = normalize_text(
        content
    )

    contexts = find_negative_context(
        title,
        content,
    )

    if not contexts:
        return 0

    score = 0

    for context in contexts:

        if sentence_has_negation(
            context
        ):

            continue

        # Satu konteks negatif langsung = kuat.
        score += 12

        # Jika Kajari/internal actor disebut,
        # tambah bobot.
        if sentence_contains_internal_actor(
            context
        ):

            score += 4

    title_contexts = [
        sentence
        for sentence
        in split_sentences(
            title
        )
        if (
            sentence_contains_satker(
                sentence
            )
            or sentence_contains_internal_actor(
                sentence
            )
        )
        and regex_hits(
            sentence,
            NEGATIVE_STRONG_PATTERNS,
        )
    ]

    if title_contexts:

        score += 8

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
    # NEGASI / BANTAHAN
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

    # --------------------------------------------------------
    # RULE 1
    #
    # Kegiatan resmi satker.
    #
    # Negatif langsung harus mengalahkan ini.
    # --------------------------------------------------------

    if (
        official_context
        and check_satker_relevance(
            title,
            content,
        )
        and negative_score == 0
    ):

        category = "Positif"

    # --------------------------------------------------------
    # RULE 2
    #
    # Keberhasilan penegakan hukum.
    #
    # Misalnya:
    # "Kejari berhasil menangkap tersangka."
    # --------------------------------------------------------

    elif (
        positive_context
        and negative_score == 0
    ):

        category = "Positif"

    # --------------------------------------------------------
    # RULE 3
    #
    # NEGATIF KUAT.
    #
    # Harus ada konteks negatif langsung.
    # --------------------------------------------------------

    elif (
        direct_negative
        and negative_score >= 12
        and not negated_danger
    ):

        category = "Negatif Kuat"

    # --------------------------------------------------------
    # RULE 4
    #
    # PERLU PENANGANAN.
    #
    # Hanya jika konteks handling menyebut satker.
    # --------------------------------------------------------

    elif (
        handling_score >= 3
        and handling_context
    ):

        category = "Perlu Penanganan"

    # --------------------------------------------------------
    # RULE 5
    #
    # POSITIF SCORE.
    # --------------------------------------------------------

    elif positive_score >= 3:

        category = "Positif"

    else:

        category = "Netral"

    # ========================================================
    # SAFETY OVERRIDE
    #
    # Jika positif jauh lebih jelas daripada negatif,
    # pertahankan POSITIF.
    # ========================================================

    if (
        category == "Negatif Kuat"
        and positive_score > 0
        and positive_score >= negative_score
        and negative_score < 25
    ):

        category = "Positif"

    # ========================================================
    # POSITIVE DOMINANCE
    #
    # Jika ada aksi positif satker yang jelas dan
    # negatif tidak langsung, jangan jadikan negatif.
    # ========================================================

    if (
        positive_satker_context
        and not direct_negative
        and category in {
            "Perlu Penanganan",
            "Negatif Kuat",
        }
    ):

        category = "Positif"

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

        else:

            category = "Netral"

    # ========================================================
    # PRIORITY
    # ========================================================

    priority = PRIORITY_BY_CATEGORY[
        category
    ]

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

    all_rows: Dict[
        str,
        Dict[str, Any],
    ] = {}

    for query in SEARCH_TARGETS:

        print(
            f"[RSS] Mencari: "
            f"{query}"
        )

        rows = (
            parse_google_news_feed(
                query
            )
        )

        for row in rows:

            link = normalize_url(
                row.get("link")
            )

            if not link:
                continue

            # Dedupe sebelum proses.
            if link not in all_rows:

                all_rows[
                    link
                ] = row

            else:

                # Jika duplicate dari query berbeda,
                # ambil data yang lebih lengkap.
                existing = all_rows[
                    link
                ]

                if (
                    len(
                        normalize_text(
                            row.get(
                                "rss_description"
                            )
                        )
                    )
                    >
                    len(
                        normalize_text(
                            existing.get(
                                "rss_description"
                            )
                        )
                    )
                ):

                    all_rows[
                        link
                    ] = row

    print(
        f"[PATROLI] "
        f"Kandidat unik: "
        f"{len(all_rows)}"
    )

    return list(
        all_rows.values()
    )


# ============================================================
# PROCESS CANDIDATE
# ============================================================

def process_candidate(
    candidate: Dict[str, Any],
) -> Dict[str, Any]:

    title = normalize_text(
        candidate.get("title")
    )

    rss_link = normalize_url(
        candidate.get("link")
    )

    rss_date = parse_date_safe(
        candidate.get(
            "published_date"
        )
    )

    result = {
        "ok": False,
        "article": None,
        "reason": "",
    }

    if not rss_link:

        result["reason"] = (
            "link kosong"
        )

        return result

    # --------------------------------------------------------
    # FILTER RSS
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # FETCH
    # --------------------------------------------------------

    final_url, raw_html = (
        fetch_webpage_content(
            rss_link
        )
    )

    final_url = normalize_url(
        final_url or rss_link
    )

    if not final_url:

        final_url = rss_link

    # --------------------------------------------------------
    # CONTENT
    # --------------------------------------------------------

    content = (
        extract_article_text(
            raw_html
        )
    )

    if (
        len(content)
        < MIN_CONTENT_LENGTH
    ):

        content = normalize_text(
            candidate.get(
                "rss_description"
            )
        )

    if (
        len(content)
        < MIN_CONTENT_LENGTH
    ):

        result["reason"] = (
            "konten terlalu pendek"
        )

        return result

    # --------------------------------------------------------
    # RELEVANCE
    # --------------------------------------------------------

    if not check_satker_relevance(
        title,
        content,
    ):

        result["reason"] = (
            "tidak relevan dengan satker"
        )

        return result

    # --------------------------------------------------------
    # DATE
    # --------------------------------------------------------

    published = (
        rss_date
        or datetime.now(
            timezone.utc
        )
    )

    if not is_article_2026(
        published
    ):

        result["reason"] = (
            "tanggal artikel bukan 2026"
        )

        return result

    # --------------------------------------------------------
    # CLASSIFICATION
    # --------------------------------------------------------

    classification = (
        classify_article(
            title,
            content,
        )
    )

    # --------------------------------------------------------
    # ARTICLE
    # --------------------------------------------------------

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

    result["ok"] = True
    result["article"] = article

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

def run_once() -> Dict[str, Any]:

    started = time.perf_counter()

    print("=" * 70)
    print(
        "MEMULAI PATROLI SIBER"
    )
    print("=" * 70)

    existing_articles = (
        get_all_articles()
    )

    existing_links = {
        normalize_url(
            article.get(
                "link"
            )
        )
        for article
        in existing_articles
        if normalize_url(
            article.get(
                "link"
            )
        )
    }

    print(
        f"[DATABASE] "
        f"Link sebelum run: "
        f"{len(existing_links)}"
    )

    candidates = (
        collect_candidates()
    )

    valid_articles = []

    failed = 0

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
            for candidate
            in candidates
        ]

        for future in as_completed(
            futures
        ):

            try:

                result = (
                    future.result()
                )

                if result.get(
                    "ok"
                ):

                    article = (
                        result.get(
                            "article"
                        )
                    )

                    if article:

                        valid_articles.append(
                            article
                        )

                else:

                    failed += 1

                    reason = (
                        result.get(
                            "reason",
                            "",
                        )
                    )

                    if reason:

                        print(
                            f"[FILTER] "
                            f"{reason}"
                        )

            except Exception as exc:

                failed += 1

                print(
                    f"[WORKER ERROR] "
                    f"{type(exc).__name__}: "
                    f"{exc}"
                )

    print(
        f"[PATROLI] "
        f"Artikel valid: "
        f"{len(valid_articles)}"
    )

    # ========================================================
    # DEDUPE HASIL RUN
    # ========================================================

    unique_articles = {}

    for article in valid_articles:

        link = normalize_url(
            article.get(
                "link"
            )
        )

        if not link:
            continue

        if link not in unique_articles:

            unique_articles[
                link
            ] = article

        else:

            existing = (
                unique_articles[
                    link
                ]
            )

            # Pertahankan konten lebih panjang.
            if len(
                normalize_text(
                    article.get(
                        "content"
                    )
                )
            ) > len(
                normalize_text(
                    existing.get(
                        "content"
                    )
                )
            ):

                unique_articles[
                    link
                ] = article

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

    saved_count = 0
    save_failed = 0

    new_articles = []

    for article in valid_articles:

        link = normalize_url(
            article.get(
                "link"
            )
        )

        if not link:
            continue

        was_existing = (
            link
            in existing_links
        )

        print(
            f"[CHECK LINK] "
            f"{'LAMA' if was_existing else 'BARU'} | "
            f"{link}"
        )

        if not was_existing:

            try:

                existing_by_link = (
                    get_article_by_link(
                        link
                    )
                )

                if existing_by_link:

                    was_existing = True

            except Exception as exc:

                print(
                    f"[CHECK LINK WARNING] "
                    f"{link} -> "
                    f"{type(exc).__name__}: "
                    f"{exc}"
                )

        try:
    
            saved = (
                upsert_article(
                    article
                )
            )

            if saved is None:

                save_failed += 1

                print(
                    f"[SAVE ERROR] "
                    f"Gagal menyimpan: "
                    f"{link}"
                )

                continue

            saved_count += 1

            if not was_existing:

                new_articles.append(
                    article
                )

        except Exception as exc:

            save_failed += 1

            print(
                f"[SAVE ERROR] "
                f"{link}: "
                f"{type(exc).__name__}: "
                f"{exc}"
            )

    print(
        f"[DATABASE] "
        f"Berhasil disimpan/update: "
        f"{saved_count}"
    )

    print(
        f"[DATABASE] "
        f"Gagal: "
        f"{save_failed}"
    )

    print(
        f"[DATABASE] "
        f"Artikel baru: "
        f"{len(new_articles)}"
    )

    # ========================================================
    # TELEGRAM
    # ========================================================

    telegram_count = 0

    if telegram_enabled():

        print(
            f"[TELEGRAM] "
            f"Kandidat artikel baru: "
            f"{len(new_articles)}"
        )

        for article in (
            new_articles
        ):

            if not send_alert_if_needed(
                article
            ):

                continue

            telegram_count += 1

            print(
                "[TELEGRAM] Terkirim: "
                f"{article.get('title', '')[:100]}"
            )

    else:

        print(
            "[TELEGRAM] Tidak aktif. "
            "Periksa TELEGRAM_BOT_TOKEN "
            "dan TELEGRAM_CHAT_ID."
        )

    # ========================================================
    # RECLASSIFICATION
    # ========================================================

    counts = (
        reclassify_all()
    )

    final_articles = (
        get_all_articles()
    )

    duration = round(
        time.perf_counter()
        - started,
        2,
    )

    # ========================================================
    # RUN LOG
    # ========================================================

    log = {
        "duration_seconds": (
            duration
        ),

        "candidate_count": (
            len(candidates)
        ),

        "valid_count": (
            len(valid_articles)
        ),

        "saved_count": (
            saved_count
        ),

        "failed_count": (
            failed
            + save_failed
        ),

        "reclassified_count": (
            len(final_articles)
        ),

        "negative_count": (
            counts.get(
                "Negatif Kuat",
                0,
            )
        ),

        "handling_count": (
            counts.get(
                "Perlu Penanganan",
                0,
            )
        ),

        "neutral_count": (
            counts.get(
                "Netral",
                0,
            )
        ),

        "positive_count": (
            counts.get(
                "Positif",
                0,
            )
        ),

        "telegram_count": (
            telegram_count
        ),

        "status": "Selesai",
    }

    save_run_log(
        log
    )

    # ========================================================
    # SUMMARY
    # ========================================================

    print()
    print("=" * 70)
    print(
        "PATROLI SELESAI"
    )
    print("=" * 70)

    print(
        f"Durasi            : "
        f"{duration} detik"
    )

    print(
        f"Kandidat          : "
        f"{len(candidates)}"
    )

    print(
        f"Artikel valid     : "
        f"{len(valid_articles)}"
    )

    print(
        f"Berhasil disimpan : "
        f"{saved_count}"
    )

    print(
        f"Gagal             : "
        f"{failed + save_failed}"
    )

    print(
        f"Artikel baru      : "
        f"{len(new_articles)}"
    )

    print(
        f"Database          : "
        f"{len(final_articles)}"
    )

    print(
        f"Negatif Kuat      : "
        f"{counts.get('Negatif Kuat', 0)}"
    )

    print(
        f"Perlu Penanganan  : "
        f"{counts.get('Perlu Penanganan', 0)}"
    )

    print(
        f"Netral            : "
        f"{counts.get('Netral', 0)}"
    )

    print(
        f"Positif           : "
        f"{counts.get('Positif', 0)}"
    )

    print(
        f"Telegram terkirim : "
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

        def record_score(row):

            content = normalize_text(
                row.get(
                    "content"
                )
                or row.get(
                    "summary"
                )
                or ""
            )

            title = normalize_text(
                row.get(
                    "title"
                )
            )

            published = normalize_text(
                row.get(
                    "published_date"
                )
            )

            try:

                article_id = int(
                    row.get(
                        "id"
                    )
                )

            except Exception:

                article_id = (
                    999999999
                )

            return (
                len(content),
                bool(title),
                bool(published),
                -article_id,
            )

        rows_sorted = sorted(
            rows,
            key=record_score,
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
        print(f"[DEDUPE ERROR] Gagal mengambil database: {type(exc).__name__}: {exc}")
        return {"success": False, "deleted": 0, "failed": 0, "error": str(exc)}

    groups: Dict[str, List[Dict[str, Any]]] = {}
    empty_links = 0
    for article in articles:
        normalized = normalize_url(article.get("link"))
        if not normalized:
            empty_links += 1
            continue
        groups.setdefault(normalized, []).append(article)

    duplicate_groups = {k: v for k, v in groups.items() if len(v) > 1}
    delete_candidates: List[Dict[str, Any]] = []

    def record_score(row: Dict[str, Any]):
        content = normalize_text(row.get("content") or row.get("summary") or "")
        title = normalize_text(row.get("title"))
        published = normalize_text(row.get("published_date"))
        try:
            article_id = int(row.get("id"))
        except Exception:
            article_id = 10**18
        return (len(content), bool(title), bool(published), -article_id)

    print(f"[DATABASE] Total artikel: {len(articles)}")
    print(f"[DEDUPE] Link unik: {len(groups)}")
    print(f"[DEDUPE] Kelompok duplicate: {len(duplicate_groups)}")
    print(f"[DEDUPE] Artikel duplicate: {sum(len(v)-1 for v in duplicate_groups.values())}")

    for number, (normalized_link, rows) in enumerate(duplicate_groups.items(), start=1):
        rows_sorted = sorted(rows, key=record_score, reverse=True)
        keep = rows_sorted[0]
        duplicates = rows_sorted[1:]
        print(f"\n[DUPLICATE #{number}] {normalized_link}")
        print(f"  KEEP   ID={keep.get('id')} | {normalize_text(keep.get('title'))[:100]}")
        for row in duplicates:
            print(f"  DELETE ID={row.get('id')} | {normalize_text(row.get('title'))[:100]}")
        delete_candidates.extend(duplicates)

    deleted = 0
    failed = 0
    for row in delete_candidates:
        article_id = row.get("id")
        if article_id is None:
            failed += 1
            continue
        try:
            if delete_article_by_id(article_id):
                deleted += 1
            else:
                failed += 1
        except Exception as exc:
            failed += 1
            print(f"[DELETE ERROR] ID={article_id} -> {type(exc).__name__}: {exc}")

    try:
        remaining = len(get_all_articles())
    except Exception:
        remaining = -1

    print("\n" + "=" * 70)
    print("DEDUPE SELESAI")
    print("=" * 70)
    print(f"Record sebelum : {len(articles)}")
    print(f"Berhasil hapus : {deleted}")
    print(f"Gagal hapus    : {failed}")
    print(f"Record sesudah : {remaining}")
    print(f"Link kosong    : {empty_links}")
    print("=" * 70)
    return {"success": failed == 0, "deleted": deleted, "failed": failed, "duplicate_groups": len(duplicate_groups), "remaining": remaining}

# ============================================================
# DEDUPE REAL
# ============================================================

def dedupe() -> Dict[str, Any]:
    """Alias kompatibilitas untuk dedupe_database()."""
    return dedupe_database()

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

    args = parser.parse_args()

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
