import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from supabase import create_client, Client


# ============================================================
# ENV
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

    _supabase = create_client(
        SUPABASE_URL,
        SUPABASE_KEY
    )

    return _supabase


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
# ARTICLES
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

        if len(rows) < page_size:
            break

        start += page_size

    return results


def get_article_by_link(
    link: str
) -> Optional[Dict[str, Any]]:

    link = normalize_link(link)

    if not link:
        return None

    client = get_supabase()

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

    data["updated_at"] = now_iso()

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


# ============================================================
# DELETE
# ============================================================

def delete_all_articles():

    client = get_supabase()

    # id tidak boleh NULL, sehingga filter neq kosong
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


# ============================================================
# LOGS
# ============================================================

def save_run_log(
    log_data: Dict[str, Any]
):

    try:

        client = get_supabase()

        data = dict(log_data)

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

    except Exception as e:

        print(
            f"[DB LOG ERROR] {e}"
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

    except Exception:

        return []


# ============================================================
# STATISTIK
# ============================================================

def get_category_counts(
    articles: Optional[List[Dict[str, Any]]] = None
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
