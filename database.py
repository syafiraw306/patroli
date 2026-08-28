```python
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from supabase import create_client, Client


load_dotenv()

SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").strip()
SUPABASE_KEY = (os.getenv("SUPABASE_KEY") or "").strip()

_supabase: Optional[Client] = None


def get_supabase() -> Client:
    global _supabase

    if _supabase is not None:
        return _supabase

    if not SUPABASE_URL:
        raise RuntimeError("SUPABASE_URL belum dikonfigurasi.")

    if not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_KEY belum dikonfigurasi.")

    _supabase = create_client(
        SUPABASE_URL,
        SUPABASE_KEY
    )

    print("[SUPABASE] Client berhasil dibuat.")

    return _supabase


def normalize_link(link: str) -> str:
    if not link:
        return ""

    return str(link).strip()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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

        print("[SUPABASE] Koneksi berhasil.")
        print(
            f"[SUPABASE] Test response: "
            f"{len(response.data or [])} row."
        )

        return True

    except Exception as e:
        print(f"[SUPABASE TEST ERROR] {e}")
        return False


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
            .eq("link", link)
            .limit(1)
            .execute()
        )

        data = response.data or []

        if not data:
            return None

        return data[0]

    except Exception as e:

        print(f"[DB GET ERROR] {e}")

        return None


def upsert_article(
    article: Dict[str, Any]
) -> Dict[str, Any]:

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

    data.setdefault(
        "created_at",
        current_time
    )

    data["updated_at"] = current_time

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

        print("[SUPABASE UPSERT ERROR]")
        print(
            f"Judul: {data.get('title', '-')}"
        )
        print(
            f"Link : {data.get('link', '-')}"
        )
        print(f"Error: {e}")

        raise


def insert_articles(
    articles: List[Dict[str, Any]]
) -> int:

    if not articles:
        return 0

    success = 0

    for article in articles:

        try:

            upsert_article(article)
            success += 1

        except Exception as e:

            print(
                f"[SUPABASE] Gagal menyimpan artikel: {e}"
            )

    print(
        f"[SUPABASE] Berhasil menyimpan "
        f"{success}/{len(articles)} artikel."
    )

    return success


def update_article(
    link: str,
    updates: Dict[str, Any]
) -> Optional[Dict[str, Any]]:

    link = normalize_link(link)

    if not link:
        return None

    client = get_supabase()

    data = dict(updates)

    data["updated_at"] = now_iso()

    try:

        response = (
            client
            .table("articles")
            .update(data)
            .eq("link", link)
            .execute()
        )

        rows = response.data or []

        if rows:
            return rows[0]

        return None

    except Exception as e:

        print(f"[DB UPDATE ERROR] {e}")

        raise


def delete_all_articles():

    client = get_supabase()

    try:

        (
            client
            .table("articles")
            .delete()
            .neq("link", "")
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


def save_run_log(
    log_data: Dict[str, Any]
):

    try:

        client = get_supabase()

        source = dict(log_data)

        # Hanya kolom yang BENAR-BENAR ada
        # di tabel run_logs Anda.
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

        data = {}

        for key in allowed_columns:

            if key in source:
                data[key] = source[key]

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
            .limit(limit)
            .execute()
        )

        return response.data or []

    except Exception as e:

        print(
            f"[DB RUN LOG ERROR] {e}"
        )

        return []


def get_category_counts(
    articles: Optional[
        List[Dict[str, Any]]
    ] = None
):

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
```
