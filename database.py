import os
import re
import html
import urllib.parse
from urllib.parse import (
    urlparse,
    parse_qsl,
    urlencode,
    urlunparse,
)
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from supabase import create_client, Client


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()

SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").strip()
SUPABASE_KEY = (os.getenv("SUPABASE_KEY") or "").strip()

_supabase: Optional[Client] = None


# ============================================================
# SUPABASE CLIENT
# ============================================================

def get_supabase() -> Client:
    """
    Membuat dan mengembalikan Supabase client.

    Client dibuat sekali saja kemudian digunakan kembali.
    """

    global _supabase

    if _supabase is not None:
        return _supabase

    if not SUPABASE_URL:
        raise RuntimeError("SUPABASE_URL belum dikonfigurasi.")

    if not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_KEY belum dikonfigurasi.")

    _supabase = create_client(
        SUPABASE_URL,
        SUPABASE_KEY,
    )

    print("[SUPABASE] Client berhasil dibuat.")

    return _supabase


# ============================================================
# TEXT / HTML CLEANING
# ============================================================

def clean_html(raw_html: Any) -> str:
    """
    Membersihkan HTML menjadi teks biasa.

    Digunakan untuk:
    - title
    - content
    - summary
    """

    if raw_html is None:
        return ""

    text = html.unescape(str(raw_html))

    # Hapus script dan style beserta isinya
    text = re.sub(
        r"<(script|style)[^>]*>.*?</\1>",
        " ",
        text,
        flags=re.I | re.S,
    )

    # Hapus tag HTML lainnya
    text = re.sub(
        r"<[^>]+>",
        " ",
        text,
    )

    # Normalisasi whitespace
    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


# ============================================================
# URL NORMALIZATION
# ============================================================

TRACKING_PARAMETERS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_name",
    "utm_id",
    "gclid",
    "fbclid",
    "dclid",
    "msclkid",
    "mc_cid",
    "mc_eid",
    "_ga",
    "ref",
    "ref_src",
    "source",
}

def normalize_url(
    url: str,
) -> str:
    """
    Normalisasi URL untuk deduplikasi.

    Khusus Google News:
    URL artikel yang sama dapat memiliki parameter berbeda
    seperti hl, gl, dan ceid.

    Contoh:

    hl=id&gl=ID&ceid=ID:id

    dan

    hl=en-US&gl=US&ceid=US:en

    Tetap dianggap sebagai artikel yang sama.
    """

    if not url:
        return ""

    url = url.strip()

    try:

        parsed = urlparse(url)

        domain = (
            parsed.netloc
            .lower()
            .replace("www.", "")
        )

        # ====================================================
        # GOOGLE NEWS
        # ====================================================

        if domain == "news.google.com":

            # Ambil hanya parameter penting.
            #
            # hl, gl, ceid adalah parameter regional
            # sehingga harus diabaikan.
            #
            # oc juga diabaikan karena tidak menentukan
            # identitas artikel.

            query_params = parse_qsl(
                parsed.query,
                keep_blank_values=True,
            )

            important_params = []

            for key, value in query_params:

                if key.lower() in {
                    "hl",
                    "gl",
                    "ceid",
                    "oc",
                }:
                    continue

                important_params.append(
                    (
                        key,
                        value,
                    )
                )

            normalized_query = urlencode(
                sorted(
                    important_params
                )
            )

            normalized_url = urlunparse(
                (
                    parsed.scheme.lower(),
                    domain,
                    parsed.path.rstrip("/"),
                    "",
                    normalized_query,
                    "",
                )
            )

            return normalized_url

        # ====================================================
        # DOMAIN NORMAL
        # ====================================================

        query_params = parse_qsl(
            parsed.query,
            keep_blank_values=True,
        )

        # Parameter tracking umum yang tidak penting
        tracking_params = {
            "utm_source",
            "utm_medium",
            "utm_campaign",
            "utm_term",
            "utm_content",
            "fbclid",
            "gclid",
        }

        clean_params = [
            (key, value)
            for key, value in query_params
            if key.lower()
            not in tracking_params
        ]

        normalized_query = urlencode(
            sorted(clean_params)
        )

        normalized_url = urlunparse(
            (
                parsed.scheme.lower(),
                domain,
                parsed.path.rstrip("/"),
                "",
                normalized_query,
                "",
            )
        )

        return normalized_url

    except Exception:

        # Jika parsing gagal,
        # gunakan URL asli yang sudah dibersihkan.
        return url.lower().strip()
        
# ============================================================
# ARTICLE PAYLOAD CLEANING
# ============================================================

def clean_article_payload(
    article: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Membersihkan payload artikel sebelum dikirim ke Supabase.

    Hanya data yang sesuai dengan kolom tabel articles
    yang dikirim ke Supabase.

    Field sementara dari RSS dibuang.
    """

    # ========================================================
    # COPY DATA
    # ========================================================

    data = dict(article or {})

    # ========================================================
    # CLEAN TEXT
    # ========================================================

    if "title" in data:

        data["title"] = clean_html(
            data.get("title")
        )

    if "content" in data:

        data["content"] = clean_html(
            data.get("content")
        )

    if "summary" in data:

        data["summary"] = clean_html(
            data.get("summary")
        )

    # ========================================================
    # NORMALIZE LINK
    # ========================================================

    if "link" in data:

        data["link"] = normalize_url(
            data.get("link")
        )

    # ========================================================
    # REMOVE TEMPORARY / UNKNOWN COLUMNS
    # ========================================================

    # Tidak ada di tabel articles
    data.pop(
        "keywords",
        None
    )

    # Field sementara dari Google News RSS
    # Tidak ada di tabel articles
    data.pop(
        "rss_description",
        None
    )

    # Field internal jika pernah ikut terbawa
    data.pop(
        "_candidate_score",
        None
    )

    data.pop(
        "_description_length",
        None
    )

    return data
# ============================================================
# TIME
# ============================================================

def now_iso() -> str:
    """
    Waktu UTC dalam ISO-8601.
    """

    return datetime.now(timezone.utc).isoformat()


# ============================================================
# CONNECTION TEST
# ============================================================

def test_connection() -> bool:
    """
    Menguji koneksi ke tabel articles.
    """

    try:
        client = get_supabase()

        response = (
            client
            .table("articles")
            .select("link")
            .limit(1)
            .execute()
        )

        print(
            "[SUPABASE] Koneksi berhasil. "
            f"Test response: {len(response.data or [])} row."
        )

        return True

    except Exception as e:
        print(f"[SUPABASE TEST ERROR] {e}")
        return False


# ============================================================
# GET ALL ARTICLES
# ============================================================

def get_all_articles(
    page_size: int = 1000,
) -> List[Dict[str, Any]]:

    # ========================================================
    # VALIDASI PARAMETER
    # ========================================================

    if not isinstance(page_size, int):
        raise TypeError(
            f"page_size harus integer, "
            f"tetapi menerima {type(page_size).__name__}"
        )

    if page_size <= 0:
        raise ValueError(
            "page_size harus lebih besar dari 0"
        )

    # ========================================================
    # DEBUG
    # ========================================================

    print("=" * 70)
    print("[DEBUG] get_all_articles DIPANGGIL")
    print(f"[DEBUG] page_size = {page_size}")
    print(
        f"[DEBUG] type(page_size) = "
        f"{type(page_size).__name__}"
    )
    print("=" * 70)

    # ========================================================
    # AMBIL SUPABASE CLIENT
    # ========================================================

    client = get_supabase()

    results: List[Dict[str, Any]] = []

    start = 0

    # ========================================================
    # PAGINATION
    # ========================================================

    while True:

        try:

            end = start + page_size - 1

            print(
                f"[SUPABASE] Mengambil artikel "
                f"offset {start} sampai {end}"
            )

            response = (
                client
                .table("articles")
                .select("*")
                .order(
                    "published_date",
                    desc=True,
                )
                .range(
                    start,
                    end,
                )
                .execute()
            )

            rows = response.data or []

        except Exception as e:

            print(
                f"[SUPABASE FETCH ERROR] "
                f"offset={start} -> {e}"
            )

            break

        results.extend(rows)

        print(
            f"[SUPABASE] Mengambil "
            f"{len(rows)} artikel "
            f"(offset {start})."
        )

        # Jika hasil kurang dari page_size,
        # berarti sudah halaman terakhir.
        if len(rows) < page_size:
            break

        start += page_size

    # ========================================================
    # SUMMARY
    # ========================================================

    print(
        f"[SUPABASE] Total artikel: "
        f"{len(results)}"
    )

    return results
# ============================================================
# GET ARTICLE
# ============================================================

def get_article_by_link(
    link: str,
) -> Optional[Dict[str, Any]]:
    """
    Mengambil artikel berdasarkan link yang sudah dinormalisasi.
    """

    normalized = normalize_url(link)

    if not normalized:
        return None

    try:
        response = (
            get_supabase()
            .table("articles")
            .select("*")
            .eq("link", normalized)
            .limit(1)
            .execute()
        )

        rows = response.data or []

        return rows[0] if rows else None

    except Exception as e:
        print(
            f"[DB GET ERROR] "
            f"link={normalized} -> {e}"
        )

        return None


def article_exists(
    link: str,
) -> bool:
    """
    Mengecek apakah artikel dengan link tersebut sudah ada.
    """

    return get_article_by_link(link) is not None


# ============================================================
# UPSERT ARTICLE
# ============================================================

def upsert_article(
    article: Dict[str, Any],
) -> Optional[Dict[str, Any]]:

    """
    Insert artikel baru atau update artikel lama.

    Konflik ditentukan oleh kolom:
        link
    """

    # ========================================================
    # CLEAN PAYLOAD
    # ========================================================

    data = clean_article_payload(
        article
    )

    # ========================================================
    # HAPUS FIELD YANG TIDAK ADA DI DATABASE
    # ========================================================

    data.pop(
        "rss_description",
        None
    )

    # ========================================================
    # VALIDATE LINK
    # ========================================================

    normalized_link = normalize_url(
        data.get("link")
    )

    if not normalized_link:

        raise ValueError(
            "Artikel tidak memiliki link yang valid."
        )

    data["link"] = normalized_link

    # ========================================================
    # TIMESTAMP
    # ========================================================

    current_time = now_iso()

    data.setdefault(
        "created_at",
        current_time,
    )

    data["updated_at"] = current_time

    # ========================================================
    # UPSERT SUPABASE
    # ========================================================

    try:

        response = (
            get_supabase()
            .table("articles")
            .upsert(
                data,
                on_conflict="link",
            )
            .execute()
        )

        rows = response.data or []

        # ====================================================
        # SUCCESS
        # ====================================================

        if rows:

            print(
                "[SUPABASE UPSERT SUCCESS] "
                f"link={normalized_link}"
            )

            return rows[0]

        print(
            "[SUPABASE UPSERT WARNING] "
            f"Tidak ada data dikembalikan untuk "
            f"link={normalized_link}"
        )

        return data

    except Exception as exc:

        print(
            "[SUPABASE UPSERT ERROR] "
            f"link={normalized_link} -> "
            f"{type(exc).__name__}: {exc}"
        )

        # PENTING:
        # Jangan diam-diam return None.
        # Lempar error agar test/run mengetahui
        # bahwa penyimpanan benar-benar gagal.

        raise


# ============================================================
# INSERT ARTICLES
# ============================================================

def insert_articles(
    articles: List[Dict[str, Any]],
) -> int:
    """
    Menyimpan banyak artikel.

    Tetap menggunakan upsert satu per satu agar:
    - error satu artikel tidak menghentikan seluruh proses
    - kompatibel dengan patroli.py
    """

    articles = articles or []

    success = 0

    for article in articles:

        try:
            result = upsert_article(article)

            if result is not None:
                success += 1

        except Exception as e:
            print(
                f"[SUPABASE] Gagal menyimpan artikel: {e}"
            )

    print(
        "[SUPABASE] Berhasil menyimpan "
        f"{success}/{len(articles)} artikel."
    )

    return success


# ============================================================
# UPDATE ARTICLE BY LINK
# ============================================================

def update_article(
    link: str,
    updates: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    Update artikel berdasarkan link.

    Ini dipertahankan sebagai kontrak utama patroli.py.
    """

    normalized_link = normalize_url(link)

    if not normalized_link:
        print("[DB UPDATE ERROR] Link artikel kosong.")
        return None

    if not updates:
        return None

    data = clean_article_payload(updates)

    # Jangan sampai update mengubah link menjadi format berbeda
    if "link" in data:
        data["link"] = normalize_url(
            data.get("link")
        )

    data["updated_at"] = now_iso()

    try:
        response = (
            get_supabase()
            .table("articles")
            .update(data)
            .eq("link", normalized_link)
            .execute()
        )

        rows = response.data or []

        return rows[0] if rows else None

    except Exception as e:
        print(
            "[DB UPDATE ERROR] "
            f"link={normalized_link} -> {e}"
        )

        return None


# ============================================================
# DELETE ALL
# ============================================================

def delete_all_articles() -> bool:
    """
    Menghapus seluruh artikel.

    Fungsi ini dipertahankan untuk kebutuhan maintenance.
    """

    try:
        (
            get_supabase()
            .table("articles")
            .delete()
            .neq("link", "")
            .execute()
        )

        print(
            "[SUPABASE] Semua artikel dihapus."
        )

        return True

    except Exception as e:
        print(
            f"[SUPABASE DELETE ERROR] {e}"
        )

        return False


# ============================================================
# FILTER ARTICLES
# ============================================================

def get_filtered_articles(
    category: Optional[str] = None,
    priority: Optional[str] = None,
    search_query: Optional[str] = None,
    limit: int = 1000,
) -> List[Dict[str, Any]]:

    try:

        query = (
            get_supabase()
            .table("articles")
            .select("*")
        )

        if category and category != "Semua Kategori":
            query = query.eq(
                "category",
                category,
            )

        if priority and priority != "Semua Prioritas":
            query = query.eq(
                "priority",
                priority,
            )

        if search_query:
            query = query.ilike(
                "title",
                f"%{search_query}%",
            )

        return (
            query
            .order(
                "published_date",
                desc=True,
            )
            .limit(limit)
            .execute()
            .data
            or []
        )

    except Exception as e:
        print(
            f"[DB FILTER ERROR] {e}"
        )

        return []


# ============================================================
# RUN LOG
# ============================================================

def save_run_log(
    log_data: Dict[str, Any],
) -> bool:
    """
    Menyimpan hasil satu kali proses patroli.

    Hanya kolom yang memang tersedia di run_logs
    yang diteruskan ke Supabase.
    """

    allowed_columns = {
        "id",
        "created_at",
        "duration_seconds",
        "candidate_count",
        "valid_count",
        "saved_count",
        "failed_count",
        "reclassified_count",
        "negative_count",
        "handling_count",
        "neutral_count",
        "positive_count",
        "telegram_count",
        "status",
    }

    try:

        data = {
            key: value
            for key, value in (log_data or {}).items()
            if key in allowed_columns
        }

        data.setdefault(
            "created_at",
            now_iso(),
        )

        (
            get_supabase()
            .table("run_logs")
            .insert(data)
            .execute()
        )

        print(
            "[DB LOG] Run log berhasil disimpan."
        )

        return True

    except Exception as e:
        print(
            f"[DB LOG ERROR] {e}"
        )

        return False


def get_run_logs(
    limit: int = 200,
) -> List[Dict[str, Any]]:

    try:
        return (
            get_supabase()
            .table("run_logs")
            .select("*")
            .order(
                "created_at",
                desc=True,
            )
            .limit(limit)
            .execute()
            .data
            or []
        )

    except Exception as e:
        print(
            f"[DB RUN LOG ERROR] {e}"
        )

        return []


# ============================================================
# CATEGORY STATISTICS
# ============================================================

def get_category_counts(
    articles: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, int]:

    articles = (
        get_all_articles()
        if articles is None
        else articles
    )

    counts = {
        "Negatif Kuat": 0,
        "Perlu Penanganan": 0,
        "Netral": 0,
        "Positif": 0,
    }

    for article in articles:

        category = (
            article.get("category")
            or "Netral"
        )

        if category not in counts:
            category = "Netral"

        counts[category] += 1

    return counts


def get_category_count_from_db(
    category: str,
) -> int:

    if not category:
        return 0

    try:

        response = (
            get_supabase()
            .table("articles")
            .select(
                "link",
                count="exact",
            )
            .eq(
                "category",
                category,
            )
            .execute()
        )

        return int(
            response.count or 0
        )

    except Exception as e:
        print(
            f"[DB CATEGORY COUNT ERROR] {e}"
        )

        return 0


def get_total_article_count() -> int:

    try:

        response = (
            get_supabase()
            .table("articles")
            .select(
                "link",
                count="exact",
            )
            .execute()
        )

        return int(
            response.count or 0
        )

    except Exception as e:
        print(
            f"[DB TOTAL COUNT ERROR] {e}"
        )

        return 0


# ============================================================
# CLASSIFICATION UPDATE
# ============================================================

def update_article_category(
    link: str,
    category: str,
) -> Optional[Dict[str, Any]]:

    return update_article(
        link,
        {
            "category": category,
        },
    )


def update_article_priority(
    link: str,
    priority: str,
) -> Optional[Dict[str, Any]]:

    return update_article(
        link,
        {
            "priority": priority,
        },
    )


def update_article_classification(
    link: str,
    category: Optional[str] = None,
    priority: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Update category dan/atau priority berdasarkan link.
    """

    updates: Dict[str, Any] = {}

    if category is not None:
        updates["category"] = category

    if priority is not None:
        updates["priority"] = priority

    if not updates:
        return None

    return update_article(
        link,
        updates,
    )


# ============================================================
# CLASSIFICATION UPDATE BY ID
# ============================================================

def update_article_classification_by_id(
    article_id: Any,
    category: Optional[str] = None,
    priority: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Update category dan/atau priority berdasarkan ID artikel.

    Digunakan oleh patroli.py untuk reklasifikasi seluruh
    database.

    ID diperlakukan sebagai identitas utama artikel.
    """

    if article_id is None:
        print(
            "[DB UPDATE ID ERROR] "
            "ID artikel kosong."
        )

        return None

    updates: Dict[str, Any] = {}

    if category is not None:
        updates["category"] = category

    if priority is not None:
        updates["priority"] = priority

    if not updates:
        return None

    updates["updated_at"] = now_iso()

    try:

        response = (
            get_supabase()
            .table("articles")
            .update(updates)
            .eq(
                "id",
                article_id,
            )
            .execute()
        )

        rows = response.data or []

        if rows:
            return rows[0]

        print(
            "[DB UPDATE ID] "
            f"Tidak ada artikel dengan ID={article_id}"
        )

        return None

    except Exception as e:
        print(
            "[DB UPDATE ID ERROR] "
            f"ID={article_id} -> {e}"
        )

        return None


# ============================================================
# DELETE ARTICLE BY ID
# ============================================================

def delete_article_by_id(
    article_id: Any,
) -> bool:
    """
    Menghapus satu artikel berdasarkan ID.

    Digunakan oleh proses deduplikasi.

    Penting:
    Keputusan artikel mana yang harus dihapus tetap berada
    di patroli.py. Fungsi ini hanya melakukan penghapusan
    berdasarkan ID yang diberikan.
    """

    if article_id is None:
        print(
            "[DB DELETE ID ERROR] "
            "ID artikel kosong."
        )

        return False

    try:

        response = (
            get_supabase()
            .table("articles")
            .delete()
            .eq(
                "id",
                article_id,
            )
            .execute()
        )

        rows = response.data or []

        if rows:

            print(
                "[DB DELETE ID] "
                f"Artikel ID={article_id} berhasil dihapus."
            )

            return True

        print(
            "[DB DELETE ID] "
            f"Artikel ID={article_id} "
            "tidak ditemukan atau sudah dihapus."
        )

        return False

    except Exception as e:

        print(
            "[DB DELETE ID ERROR] "
            f"ID={article_id} -> {e}"
        )

        return False


# ============================================================
# CATEGORY / PRIORITY QUERY
# ============================================================

def get_articles_by_category(
    category: str,
    limit: int = 1000,
) -> List[Dict[str, Any]]:

    if not category:
        return []

    try:

        return (
            get_supabase()
            .table("articles")
            .select("*")
            .eq(
                "category",
                category,
            )
            .order(
                "published_date",
                desc=True,
            )
            .limit(limit)
            .execute()
            .data
            or []
        )

    except Exception as e:
        print(
            f"[DB CATEGORY ERROR] {e}"
        )

        return []


def get_articles_by_priority(
    priority: str,
    limit: int = 1000,
) -> List[Dict[str, Any]]:

    if not priority:
        return []

    try:

        return (
            get_supabase()
            .table("articles")
            .select("*")
            .eq(
                "priority",
                priority,
            )
            .order(
                "published_date",
                desc=True,
            )
            .limit(limit)
            .execute()
            .data
            or []
        )

    except Exception as e:
        print(
            f"[DB PRIORITY ERROR] {e}"
        )

        return []


# ============================================================
# SEARCH
# ============================================================

def search_articles(
    search_query: str,
    limit: int = 100,
) -> List[Dict[str, Any]]:

    if not search_query:
        return []

    try:

        return (
            get_supabase()
            .table("articles")
            .select("*")
            .ilike(
                "title",
                f"%{search_query}%",
            )
            .order(
                "published_date",
                desc=True,
            )
            .limit(limit)
            .execute()
            .data
            or []
        )

    except Exception as e:
        print(
            f"[DB SEARCH ERROR] {e}"
        )

        return []


# ============================================================
# LATEST ARTICLES
# ============================================================

def get_latest_articles(
    limit: int = 20,
) -> List[Dict[str, Any]]:

    try:

        return (
            get_supabase()
            .table("articles")
            .select("*")
            .order(
                "published_date",
                desc=True,
            )
            .limit(limit)
            .execute()
            .data
            or []
        )

    except Exception as e:
        print(
            f"[DB LATEST ERROR] {e}"
        )

        return []


# ============================================================
# HEALTH CHECK
# ============================================================

def health_check() -> Dict[str, Any]:
    """
    Mengecek:
    - koneksi Supabase
    - jumlah artikel
    """

    result: Dict[str, Any] = {
        "connected": False,
        "articles": 0,
        "error": None,
    }

    try:

        response = (
            get_supabase()
            .table("articles")
            .select(
                "link",
                count="exact",
            )
            .limit(1)
            .execute()
        )

        result["connected"] = True

        result["articles"] = int(
            response.count or 0
        )

    except Exception as e:

        result["error"] = str(e)

        print(
            f"[DB HEALTH ERROR] {e}"
        )

    return result


# ============================================================
# DIRECT TEST
# ============================================================

if __name__ == "__main__":

    print("=" * 60)
    print("DATABASE.PY - SUPABASE TEST")
    print("=" * 60)

    if test_connection():

        health = health_check()

        print(
            f"[DATABASE] Connected : "
            f"{health.get('connected')}"
        )

        print(
            f"[DATABASE] Articles  : "
            f"{health.get('articles')}"
        )

    else:

        print(
            "[DATABASE] Koneksi database gagal."
        )

    print("=" * 60)

