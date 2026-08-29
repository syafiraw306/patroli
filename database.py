import os
import re
import html
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from supabase import create_client, Client


# ============================================================
# LOAD ENVIRONMENT
# ============================================================

load_dotenv()

SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").strip()
SUPABASE_KEY = (os.getenv("SUPABASE_KEY") or "").strip()


# ============================================================
# SUPABASE CLIENT
# ============================================================

_supabase: Optional[Client] = None


def get_supabase() -> Client:
    """
    Membuat dan mengembalikan client Supabase.
    Client dibuat satu kali dan digunakan kembali.
    """

    global _supabase

    if _supabase is not None:
        return _supabase

    if not SUPABASE_URL:
        raise RuntimeError(
            "SUPABASE_URL belum dikonfigurasi."
        )

    if not SUPABASE_KEY:
        raise RuntimeError(
            "SUPABASE_KEY belum dikonfigurasi."
        )

    _supabase = create_client(
        SUPABASE_URL,
        SUPABASE_KEY
    )

    print("[SUPABASE] Client berhasil dibuat.")

    return _supabase


# ============================================================
# UTILITAS HTML
# ============================================================

def clean_html(raw_html: Any) -> str:
    """
    Menghapus tag HTML dan membersihkan whitespace.
    """

    if raw_html is None:
        return ""

    text = html.unescape(str(raw_html))

    # Hapus script dan style
    text = re.sub(
        r"<(script|style).*?>.*?</\1>",
        " ",
        text,
        flags=re.I | re.S
    )

    # Hapus tag HTML lainnya
    text = re.sub(
        r"<[^>]+>",
        " ",
        text
    )

    # Normalisasi whitespace
    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# ============================================================
# CLEAN ARTICLE PAYLOAD
# ============================================================

def clean_article_payload(
    article: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Membersihkan data artikel sebelum dikirim ke Supabase.

    PENTING:
    Kolom 'keywords' TIDAK dikirim ke tabel articles karena
    schema Supabase saat ini tidak memiliki kolom tersebut.

    Jika patroli.py menghasilkan 'keywords', field tersebut
    akan dibuang secara otomatis.
    """

    data = dict(article)

    # --------------------------------------------------------
    # Bersihkan title
    # --------------------------------------------------------

    if "title" in data:
        data["title"] = clean_html(
            data.get("title")
        )

    # --------------------------------------------------------
    # Bersihkan content
    # --------------------------------------------------------

    if "content" in data:
        data["content"] = clean_html(
            data.get("content")
        )

    # --------------------------------------------------------
    # HAPUS keywords
    #
    # Supabase articles TIDAK memiliki kolom keywords.
    # --------------------------------------------------------

    data.pop(
        "keywords",
        None
    )

    return data


# ============================================================
# NORMALIZE LINK
# ============================================================

def normalize_link(link: Any) -> str:
    """
    Membersihkan link artikel.
    """

    if link is None:
        return ""

    return str(link).strip()


# ============================================================
# CURRENT UTC TIME
# ============================================================

def now_iso() -> str:
    """
    Menghasilkan waktu UTC dalam format ISO.
    """

    return datetime.now(
        timezone.utc
    ).isoformat()


# ============================================================
# TEST CONNECTION
# ============================================================

def test_connection() -> bool:
    """
    Menguji koneksi ke Supabase.
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

        rows = response.data or []

        print(
            "[SUPABASE] Koneksi berhasil."
        )

        print(
            f"[SUPABASE] Test response: "
            f"{len(rows)} row."
        )

        return True

    except Exception as e:

        print(
            f"[SUPABASE TEST ERROR] {e}"
        )

        return False


# ============================================================
# GET ALL ARTICLES
# ============================================================

def get_all_articles(
    page_size: int = 1000
) -> List[Dict[str, Any]]:
    """
    Mengambil seluruh artikel dari Supabase secara bertahap.
    """

    client = get_supabase()

    results: List[Dict[str, Any]] = []

    start = 0

    while True:

        try:

            response = (
                client
                .table("articles")
                .select("*")
                .order(
                    "published_date",
                    desc=True
                )
                .range(
                    start,
                    start + page_size - 1
                )
                .execute()
            )

            rows = response.data or []

        except Exception as e:

            print(
                f"[SUPABASE FETCH ERROR] {e}"
            )

            break

        results.extend(rows)

        print(
            f"[SUPABASE] Mengambil "
            f"{len(rows)} artikel "
            f"(offset {start})."
        )

        if len(rows) < page_size:
            break

        start += page_size

    print(
        f"[SUPABASE] Total artikel: "
        f"{len(results)}"
    )

    return results


# ============================================================
# GET ARTICLE BY LINK
# ============================================================

def get_article_by_link(
    link: str
) -> Optional[Dict[str, Any]]:
    """
    Mengambil satu artikel berdasarkan link.
    """

    link = normalize_link(link)

    if not link:
        return None

    client = get_supabase()

    try:

        response = (
            client
            .table("articles")
            .select("*")
            .eq(
                "link",
                link
            )
            .limit(1)
            .execute()
        )

        rows = response.data or []

        if not rows:
            return None

        return rows[0]

    except Exception as e:

        print(
            f"[DB GET ERROR] {e}"
        )

        return None


# ============================================================
# CHECK ARTICLE EXISTS
# ============================================================

def article_exists(
    link: str
) -> bool:
    """
    Mengecek apakah artikel sudah ada berdasarkan link.
    """

    link = normalize_link(link)

    if not link:
        return False

    client = get_supabase()

    try:

        response = (
            client
            .table("articles")
            .select("link")
            .eq(
                "link",
                link
            )
            .limit(1)
            .execute()
        )

        return bool(
            response.data
        )

    except Exception as e:

        print(
            f"[DB EXISTS ERROR] {e}"
        )

        return False


# ============================================================
# UPSERT ARTICLE
# ============================================================

def upsert_article(
    article: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """
    Insert atau update artikel berdasarkan link.

    Field yang tidak terdapat di schema Supabase seperti
    'keywords' akan dibuang sebelum request.
    """

    client = get_supabase()

    # --------------------------------------------------------
    # Bersihkan payload
    # --------------------------------------------------------

    data = clean_article_payload(
        article
    )

    # --------------------------------------------------------
    # Normalisasi link
    # --------------------------------------------------------

    data["link"] = normalize_link(
        data.get(
            "link",
            ""
        )
    )

    if not data["link"]:

        raise ValueError(
            "Artikel tidak memiliki link."
        )

    # --------------------------------------------------------
    # Timestamp
    # --------------------------------------------------------

    current_time = now_iso()

    data.setdefault(
        "created_at",
        current_time
    )

    data["updated_at"] = current_time

    # --------------------------------------------------------
    # Upsert
    # --------------------------------------------------------

    try:

        response = (
            client
            .table("articles")
            .upsert(
                data,
                on_conflict="link"
            )
            .execute()
        )

        rows = response.data or []

        if rows:
            return rows[0]

        return data

    except Exception as e:

        print(
            f"[SUPABASE UPSERT ERROR] {e}"
        )

        return None


# ============================================================
# INSERT ARTICLES
# ============================================================

def insert_articles(
    articles: List[Dict[str, Any]]
) -> int:
    """
    Menyimpan banyak artikel.
    """

    if not articles:
        return 0

    success = 0

    for article in articles:

        try:

            result = upsert_article(
                article
            )

            if result is not None:
                success += 1

        except Exception as e:

            print(
                "[SUPABASE] "
                f"Gagal menyimpan artikel: {e}"
            )

    print(
        f"[SUPABASE] Berhasil menyimpan "
        f"{success}/{len(articles)} artikel."
    )

    return success


# ============================================================
# UPDATE ARTICLE
# ============================================================

def update_article(
    link: str,
    updates: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """
    Mengupdate artikel berdasarkan link.

    Field keywords otomatis dibuang karena tidak tersedia
    di tabel articles.
    """

    link = normalize_link(
        link
    )

    if not link:
        return None

    client = get_supabase()

    # --------------------------------------------------------
    # Bersihkan update
    # --------------------------------------------------------

    data = clean_article_payload(
        updates
    )

    # --------------------------------------------------------
    # Timestamp
    # --------------------------------------------------------

    data["updated_at"] = now_iso()

    # --------------------------------------------------------
    # Jangan melakukan update jika tidak ada data
    # selain updated_at.
    # --------------------------------------------------------

    if len(data) == 1 and "updated_at" in data:
        return None

    try:

        response = (
            client
            .table("articles")
            .update(data)
            .eq(
                "link",
                link
            )
            .execute()
        )

        rows = response.data or []

        if rows:
            return rows[0]

        return None

    except Exception as e:

        print(
            f"[DB UPDATE ERROR] {e}"
        )

        return None


# ============================================================
# DELETE ALL ARTICLES
# ============================================================

def delete_all_articles() -> bool:
    """
    Menghapus seluruh artikel.
    """

    client = get_supabase()

    try:

        (
            client
            .table("articles")
            .delete()
            .neq(
                "link",
                ""
            )
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
    limit: int = 1000
) -> List[Dict[str, Any]]:
    """
    Mengambil artikel berdasarkan filter.
    """

    client = get_supabase()

    try:

        query = (
            client
            .table("articles")
            .select("*")
        )

        # ----------------------------------------------------
        # Filter kategori
        # ----------------------------------------------------

        if (
            category
            and category != "Semua Kategori"
        ):

            query = query.eq(
                "category",
                category
            )

        # ----------------------------------------------------
        # Filter prioritas
        # ----------------------------------------------------

        if (
            priority
            and priority != "Semua Prioritas"
        ):

            query = query.eq(
                "priority",
                priority
            )

        # ----------------------------------------------------
        # Search judul
        # ----------------------------------------------------

        if search_query:

            query = query.ilike(
                "title",
                f"%{search_query}%"
            )

        # ----------------------------------------------------
        # Execute
        # ----------------------------------------------------

        response = (
            query
            .order(
                "published_date",
                desc=True
            )
            .limit(limit)
            .execute()
        )

        return response.data or []

    except Exception as e:

        print(
            f"[DB FILTER ERROR] {e}"
        )

        return []


# ============================================================
# SAVE RUN LOG
# ============================================================

def save_run_log(
    log_data: Dict[str, Any]
) -> bool:
    """
    Menyimpan log setiap proses patroli.

    Hanya kolom yang kompatibel dengan tabel run_logs
    yang dikirim ke Supabase.
    """

    try:

        client = get_supabase()

        # ----------------------------------------------------
        # Kolom yang diperbolehkan di run_logs
        # ----------------------------------------------------

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
            "status"
        }

        # ----------------------------------------------------
        # Filter payload
        # ----------------------------------------------------

        data = {
            key: value
            for key, value in log_data.items()
            if key in allowed_columns
        }

        # ----------------------------------------------------
        # created_at
        # ----------------------------------------------------

        data.setdefault(
            "created_at",
            now_iso()
        )

        # ----------------------------------------------------
        # Insert log
        # ----------------------------------------------------

        (
            client
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

        # Error run log tidak menghentikan patroli
        print(
            "[DB LOG] Error log diabaikan."
        )

        return False


# ============================================================
# GET RUN LOGS
# ============================================================

def get_run_logs(
    limit: int = 200
) -> List[Dict[str, Any]]:
    """
    Mengambil riwayat run log.
    """

    try:

        client = get_supabase()

        response = (
            client
            .table("run_logs")
            .select("*")
            .order(
                "created_at",
                desc=True
            )
            .limit(limit)
            .execute()
        )

        return response.data or []

    except Exception as e:

        print(
            f"[DB RUN LOG ERROR] {e}"
        )

        return []


# ============================================================
# CATEGORY COUNTS
# ============================================================

def get_category_counts(
    articles: Optional[
        List[Dict[str, Any]]
    ] = None
) -> Dict[str, int]:
    """
    Menghitung jumlah artikel berdasarkan kategori.
    """

    if articles is None:

        articles = get_all_articles()

    counts = {
        "Negatif Kuat": 0,
        "Perlu Penanganan": 0,
        "Netral": 0,
        "Positif": 0
    }

    for article in articles:

        category = article.get(
            "category",
            "Netral"
        )

        if category not in counts:

            category = "Netral"

        counts[category] += 1

    return counts


# ============================================================
# CATEGORY COUNT FROM DATABASE
# ============================================================

def get_category_count_from_db(
    category: str
) -> int:
    """
    Mengambil jumlah artikel berdasarkan kategori langsung
    dari Supabase.
    """

    if not category:
        return 0

    try:

        client = get_supabase()

        response = (
            client
            .table("articles")
            .select(
                "link",
                count="exact"
            )
            .eq(
                "category",
                category
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


# ============================================================
# TOTAL ARTICLE COUNT
# ============================================================

def get_total_article_count() -> int:
    """
    Mengambil jumlah seluruh artikel.
    """

    try:

        client = get_supabase()

        response = (
            client
            .table("articles")
            .select(
                "link",
                count="exact"
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
# UPDATE CATEGORY
# ============================================================

def update_article_category(
    link: str,
    category: str
) -> Optional[Dict[str, Any]]:
    """
    Update kategori artikel tanpa menyentuh field lain.
    """

    return update_article(
        link,
        {
            "category": category
        }
    )


# ============================================================
# UPDATE PRIORITY
# ============================================================

def update_article_priority(
    link: str,
    priority: str
) -> Optional[Dict[str, Any]]:
    """
    Update prioritas artikel.
    """

    return update_article(
        link,
        {
            "priority": priority
        }
    )


# ============================================================
# UPDATE CATEGORY + PRIORITY
# ============================================================

def update_article_classification(
    link: str,
    category: Optional[str] = None,
    priority: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Update klasifikasi artikel.

    Bisa mengubah:
    - category
    - priority
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
        updates
    )


# ============================================================
# GET ARTICLES BY CATEGORY
# ============================================================

def get_articles_by_category(
    category: str,
    limit: int = 1000
) -> List[Dict[str, Any]]:
    """
    Mengambil artikel berdasarkan kategori.
    """

    if not category:
        return []

    client = get_supabase()

    try:

        response = (
            client
            .table("articles")
            .select("*")
            .eq(
                "category",
                category
            )
            .order(
                "published_date",
                desc=True
            )
            .limit(limit)
            .execute()
        )

        return response.data or []

    except Exception as e:

        print(
            f"[DB CATEGORY ERROR] {e}"
        )

        return []


# ============================================================
# GET ARTICLES BY PRIORITY
# ============================================================

def get_articles_by_priority(
    priority: str,
    limit: int = 1000
) -> List[Dict[str, Any]]:
    """
    Mengambil artikel berdasarkan prioritas.
    """

    if not priority:
        return []

    client = get_supabase()

    try:

        response = (
            client
            .table("articles")
            .select("*")
            .eq(
                "priority",
                priority
            )
            .order(
                "published_date",
                desc=True
            )
            .limit(limit)
            .execute()
        )

        return response.data or []

    except Exception as e:

        print(
            f"[DB PRIORITY ERROR] {e}"
        )

        return []


# ============================================================
# SEARCH ARTICLES
# ============================================================

def search_articles(
    search_query: str,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Mencari artikel berdasarkan judul.
    """

    if not search_query:
        return []

    client = get_supabase()

    try:

        response = (
            client
            .table("articles")
            .select("*")
            .ilike(
                "title",
                f"%{search_query}%"
            )
            .order(
                "published_date",
                desc=True
            )
            .limit(limit)
            .execute()
        )

        return response.data or []

    except Exception as e:

        print(
            f"[DB SEARCH ERROR] {e}"
        )

        return []


# ============================================================
# GET LATEST ARTICLES
# ============================================================

def get_latest_articles(
    limit: int = 20
) -> List[Dict[str, Any]]:
    """
    Mengambil artikel terbaru.
    """

    try:

        client = get_supabase()

        response = (
            client
            .table("articles")
            .select("*")
            .order(
                "published_date",
                desc=True
            )
            .limit(limit)
            .execute()
        )

        return response.data or []

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
    Mengecek kondisi koneksi database dan jumlah artikel.
    """

    result = {
        "connected": False,
        "articles": 0,
        "error": None
    }

    try:

        client = get_supabase()

        response = (
            client
            .table("articles")
            .select(
                "link",
                count="exact"
            )
            .limit(1)
            .execute()
        )

        result["connected"] = True

        result["articles"] = int(
            response.count or 0
        )

        return result

    except Exception as e:

        result["error"] = str(e)

        print(
            f"[DB HEALTH ERROR] {e}"
        )

        return result


# ============================================================
# MAIN TEST
# ============================================================

if __name__ == "__main__":

    print(
        "=" * 60
    )

    print(
        "DATABASE.PY - SUPABASE TEST"
    )

    print(
        "=" * 60
    )

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

    print(
        "=" * 60
    )

