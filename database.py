import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from dotenv import load_dotenv
from supabase import create_client, Client


# ============================================================
# LOAD ENVIRONMENT
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

    print(
        "[SUPABASE] Client berhasil dibuat."
    )

    return _supabase


# ============================================================
# UTILITAS
# ============================================================

def normalize_link(link: str) -> str:
    """
    Normalisasi dasar URL/link.
    """

    if not link:
        return ""

    return str(link).strip()


def now_iso() -> str:
    """
    Waktu UTC dalam format ISO.
    """

    return datetime.now(
        timezone.utc
    ).isoformat()


# ============================================================
# TEST CONNECTION
# ============================================================

def test_connection() -> bool:
    """
    Mengecek koneksi ke tabel articles.
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
            "[SUPABASE] Koneksi berhasil."
        )

        print(
            "[SUPABASE] Test response: "
            f"{len(response.data or [])} row."
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
    Mengambil seluruh artikel dari Supabase.
    Pagination digunakan agar database besar tetap bisa dibaca.
    """

    client = get_supabase()

    results: List[Dict[str, Any]] = []

    start = 0

    while True:

        response = (
            client
            .table("articles")
            .select("*")
            .range(
                start,
                start + page_size - 1
            )
            .execute()
        )

        rows = response.data or []

        results.extend(rows)

        print(
            "[SUPABASE] Mengambil "
            f"{len(rows)} artikel "
            f"(offset {start})."
        )

        if len(rows) < page_size:
            break

        start += page_size

    print(
        "[SUPABASE] Total artikel: "
        f"{len(results)}"
    )

    return results


# ============================================================
# GET EXISTING LINKS
# ============================================================

def get_existing_article_links() -> Set[str]:
    """
    Mengambil seluruh link artikel yang sudah ada di database.

    Fungsi ini digunakan oleh patroli.py untuk menentukan
    apakah sebuah artikel merupakan artikel BARU.

    PENTING:
    Fungsi ini hanya digunakan untuk mendeteksi artikel baru.
    Reklasifikasi database tetap dilakukan terhadap seluruh artikel.
    """

    articles = get_all_articles()

    links: Set[str] = set()

    for article in articles:

        link = normalize_link(
            article.get("link", "")
        )

        if link:
            links.add(link)

    print(
        "[SUPABASE] Link artikel existing: "
        f"{len(links)}"
    )

    return links


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

        data = response.data or []

        if not data:
            return None

        return data[0]

    except Exception as e:

        print(
            "[DB GET ERROR] "
            f"{e}"
        )

        return None


# ============================================================
# UPSERT ARTICLE
# ============================================================

def upsert_article(
    article: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Insert artikel baru atau update artikel yang link-nya
    sudah ada.

    Database harus mempunyai UNIQUE constraint pada kolom link
    agar on_conflict='link' berjalan dengan benar.
    """

    client = get_supabase()

    data = dict(article)

    data["link"] = normalize_link(
        data.get("link", "")
    )

    if not data["link"]:
        raise ValueError(
            "Artikel tidak memiliki link."
        )

    current_time = now_iso()

    # created_at hanya dibuat jika belum ada.
    data.setdefault(
        "created_at",
        current_time
    )

    # updated_at selalu diperbarui.
    data["updated_at"] = current_time

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

            upsert_article(
                article
            )

            success += 1

        except Exception as e:

            print(
                "[SUPABASE] Gagal menyimpan artikel: "
                f"{e}"
            )

    print(
        "[SUPABASE] Berhasil menyimpan "
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
    Update artikel berdasarkan link.
    """

    link = normalize_link(link)

    if not link:
        return None

    client = get_supabase()

    data = dict(updates)

    data["updated_at"] = now_iso()

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


# ============================================================
# DELETE ALL ARTICLES
# ============================================================

def delete_all_articles():
    """
    Menghapus seluruh artikel.
    Gunakan hanya jika memang diperlukan.
    """

    client = get_supabase()

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


# ============================================================
# SAVE RUN LOG
# ============================================================

def save_run_log(
    log_data: Dict[str, Any]
):
    """
    Menyimpan log workflow ke tabel run_logs.
    """

    try:

        client = get_supabase()

        allowed_columns = {
            "id",
            "created_at",
            "duration_seconds",
            "candidate_count",
            "valid_count",
            "negative_count",
            "handling_count",
            "neutral_count",
            "positive_count",
            "telegram_count",
            "status"
        }

        data = {
            key: value
            for key, value in log_data.items()
            if key in allowed_columns
        }

        data.setdefault(
            "created_at",
            now_iso()
        )

        (
            client
            .table("run_logs")
            .insert(data)
            .execute()
        )

        print(
            "[DB LOG] Run log berhasil disimpan."
        )

    except Exception as e:

        print(
            f"[DB LOG ERROR] {e}"
        )

        print(
            "[DB LOG] Error log diabaikan. "
            "Patroli tetap dianggap selesai."
        )


# ============================================================
# GET RUN LOGS
# ============================================================

def get_run_logs(
    limit: int = 200
) -> List[Dict[str, Any]]:
    """
    Mengambil riwayat run workflow.
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
):
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
