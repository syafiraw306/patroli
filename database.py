import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from supabase import create_client, Client


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()

SUPABASE_URL = (
    os.getenv("SUPABASE_URL") or ""
).strip()

SUPABASE_KEY = (
    os.getenv("SUPABASE_KEY") or ""
).strip()


# ============================================================
# CLIENT
# ============================================================

_supabase: Optional[Client] = None


def get_supabase() -> Client:

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

    try:

        _supabase = create_client(
            SUPABASE_URL,
            SUPABASE_KEY
        )

        print(
            "[SUPABASE] Client berhasil dibuat."
        )

        return _supabase

    except Exception as e:

        print(
            f"[SUPABASE CONNECTION ERROR] {e}"
        )

        raise


# ============================================================
# HELPER
# ============================================================

def normalize_link(link: str) -> str:

    if not link:
        return ""

    return str(link).strip()


def now_iso() -> str:

    return datetime.now(
        timezone.utc
    ).isoformat()


# ============================================================
# TEST CONNECTION
# ============================================================

def test_connection() -> bool:

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
            f"[SUPABASE] Test response: "
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

    client = get_supabase()

    results = []

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
            f"[DB GET ERROR] {e}"
        )

        return None


# ============================================================
# UPSERT ARTICLE
# ============================================================

def upsert_article(
    article: Dict[str, Any]
) -> Dict[str, Any]:

    client = get_supabase()

    data = dict(article)

    # --------------------------------------------------------
    # LINK
    # --------------------------------------------------------

    data["link"] = normalize_link(
        data.get("link", "")
    )

    if not data["link"]:

        raise ValueError(
            "Artikel tidak memiliki link."
        )

    # --------------------------------------------------------
    # TIMESTAMP
    # --------------------------------------------------------

    current_time = now_iso()

    data.setdefault(
        "created_at",
        current_time
    )

    data["updated_at"] = current_time

    # --------------------------------------------------------
    # UPSERT
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

            result = rows[0]

            print(
                "[SUPABASE] UPSERT BERHASIL:"
            )

            print(
                f"  Judul    : "
                f"{result.get('title', '-')}"
            )

            print(
                f"  Kategori : "
                f"{result.get('category', '-')}"
            )

            print(
                f"  Link     : "
                f"{result.get('link', '-')}"
            )

            return result

        print(
            "[SUPABASE] UPSERT berhasil "
            "tetapi response kosong."
        )

        return data

    except Exception as e:

        print(
            "[SUPABASE UPSERT ERROR]"
        )

        print(
            f"Judul: {data.get('title', '-')}"
        )

        print(
            f"Link : {data.get('link', '-')}"
        )

        print(
            f"Error: {e}"
        )

        raise


# ============================================================
# INSERT MANY ARTICLES
# ============================================================

def insert_articles(
    articles: List[Dict[str, Any]]
) -> int:

    if not articles:

        print(
            "[SUPABASE] Tidak ada artikel "
            "untuk disimpan."
        )

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
                f"[SUPABASE] Gagal menyimpan artikel: "
                f"{e}"
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

    link = normalize_link(link)

    if not link:
        raise ValueError(
            "Link artikel kosong saat update."
        )

    client = get_supabase()

    data = dict(updates)

    data["updated_at"] = now_iso()

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
            "[DB UPDATE ERROR]"
        )

        print(
            f"Link: {link}"
        )

        print(
            f"Error: {e}"
        )

        raise


# ============================================================
# DELETE ALL ARTICLES
# ============================================================

def delete_all_articles():

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

    except Exception as e:

        print(
            f"[DB DELETE ERROR] {e}"
        )

        raise


# ============================================================
# RUN LOG
# ============================================================

def save_run_log(
    log_data: Dict[str, Any]
):

    """
    Menyimpan statistik patroli ke run_logs.

    Fungsi ini sengaja hanya mengirim kolom yang
    kemungkinan digunakan oleh tabel run_logs.

    Jika database_total belum tersedia di schema
    run_logs, tidak akan menyebabkan workflow gagal.
    """

    try:

        client = get_supabase()

        data = dict(log_data)

        data.setdefault(
            "created_at",
            now_iso()
        )

        # ----------------------------------------------------
        # Hanya field log utama
        # ----------------------------------------------------

        allowed_fields = {

            "duration_seconds",

            "candidate_count",

            "valid_count",

            "saved_count",

            "save_failed",

            "reclassified_count",

            "reclassify_failed",

            "negative_count",

            "handling_count",

            "neutral_count",

            "positive_count",

            "telegram_count",

            "status",

            "created_at"

        }

        clean_data = {

            key: value

            for key, value in data.items()

            if key in allowed_fields

        }

        (
            client
            .table("run_logs")
            .insert(clean_data)
            .execute()
        )

        print(
            "[SUPABASE] Run log berhasil disimpan."
        )

    except Exception as e:

        # ----------------------------------------------------
        # Run log TIDAK BOLEH membuat patroli gagal.
        # ----------------------------------------------------

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
            .limit(
                limit
            )
            .execute()
        )

        return response.data or []

    except Exception as e:

        print(
            f"[DB RUN LOG ERROR] {e}"
        )

        return []


# ============================================================
# STATISTIK KATEGORI
# ============================================================

def get_category_counts(
    articles: Optional[
        List[Dict[str, Any]]
    ] = None
) -> Dict[str, int]:

    if articles is None:

        articles = (
            get_all_articles()
        )

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
