import os
import re
import html
import json
from typing import List, Dict, Any, Optional

from supabase import create_client, Client


# ============================================================
# KONFIGURASI SUPABASE
# ============================================================

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()


def get_supabase() -> Client:
    """
    Membuat koneksi ke Supabase.
    """
    if not SUPABASE_URL:
        raise ValueError(
            "SUPABASE_URL belum dikonfigurasi di Environment Variable."
        )

    if not SUPABASE_KEY:
        raise ValueError(
            "SUPABASE_KEY belum dikonfigurasi di Environment Variable."
        )

    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ============================================================
# CLEAN HTML
# ============================================================

def clean_html(raw_html: Any) -> str:
    """
    Membersihkan tag HTML, entity HTML, whitespace berlebih,
    dan karakter yang tidak diperlukan.
    """
    if raw_html is None:
        return ""

    text = html.unescape(str(raw_html))

    # Hapus script/style
    text = re.sub(
        r"<(script|style|noscript).*?>.*?</\1>",
        " ",
        text,
        flags=re.IGNORECASE | re.DOTALL
    )

    # Hapus seluruh tag HTML
    text = re.sub(r"<[^>]+>", " ", text)

    # Bersihkan whitespace
    text = re.sub(r"\s+", " ", text)

    return text.strip()


# ============================================================
# CLEAN KEYWORDS
# ============================================================

def clean_keywords(value: Any) -> List[str]:
    """
    Memastikan kolom keywords selalu berbentuk list.
    Supabase bisa mengembalikan list, string JSON, atau None.
    """
    if value is None:
        return []

    if isinstance(value, list):
        return [
            clean_html(str(x)).strip()
            for x in value
            if str(x).strip()
        ]

    if isinstance(value, tuple):
        return [
            clean_html(str(x)).strip()
            for x in value
            if str(x).strip()
        ]

    if isinstance(value, str):
        value = value.strip()

        if not value:
            return []

        # Coba JSON
        try:
            parsed = json.loads(value)

            if isinstance(parsed, list):
                return [
                    clean_html(str(x)).strip()
                    for x in parsed
                    if str(x).strip()
                ]
        except Exception:
            pass

        # Fallback jika format "a, b, c"
        return [
            clean_html(x).strip()
            for x in value.split(",")
            if x.strip()
        ]

    return []


# ============================================================
# CLEAN ARTICLE
# ============================================================

def clean_article_payload(article: Dict[str, Any]) -> Dict[str, Any]:
    """
    Membersihkan payload artikel sebelum disimpan.
    Tidak mengubah struktur field database.
    """

    cleaned = dict(article)

    if "title" in cleaned:
        cleaned["title"] = clean_html(cleaned["title"])

    if "content" in cleaned:
        cleaned["content"] = clean_html(cleaned["content"])

    if "keywords" in cleaned:
        cleaned["keywords"] = clean_keywords(cleaned["keywords"])

    if "url" in cleaned and cleaned["url"]:
        cleaned["url"] = str(cleaned["url"]).strip()

    return cleaned


# ============================================================
# UPSERT ARTICLE
# ============================================================

def upsert_article(
    article: Dict[str, Any]
) -> Optional[Dict[str, Any]]:

    try:
        client = get_supabase()
        cleaned = clean_article_payload(article)

        if not cleaned.get("url"):
            print("[DB UPSERT] URL kosong, artikel dilewati.")
            return None

        response = (
            client
            .table("articles")
            .upsert(
                cleaned,
                on_conflict="url"
            )
            .execute()
        )

        if response.data:
            return response.data[0]

        return None

    except Exception as e:
        print(f"[DB UPSERT ERROR] {e}")
        return None


# ============================================================
# UPDATE ARTICLE
# ============================================================

def update_article(
    article_id: str,
    data: Dict[str, Any]
) -> Optional[Dict[str, Any]]:

    try:
        client = get_supabase()
        cleaned = clean_article_payload(data)

        response = (
            client
            .table("articles")
            .update(cleaned)
            .eq("id", article_id)
            .execute()
        )

        if response.data:
            return response.data[0]

        return None

    except Exception as e:
        print(f"[DB UPDATE ERROR] {e}")
        return None


# ============================================================
# GET ALL ARTICLES
# ============================================================

def get_all_articles() -> List[Dict[str, Any]]:

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
            .execute()
        )

        return response.data or []

    except Exception as e:
        print(f"[DB FETCH ERROR] {e}")
        return []


# ============================================================
# GET ARTICLE BY URL
# ============================================================

def get_article_by_link(
    url: str
) -> Optional[Dict[str, Any]]:

    try:
        client = get_supabase()

        if not url:
            return None

        response = (
            client
            .table("articles")
            .select("*")
            .eq("url", url)
            .limit(1)
            .execute()
        )

        if response.data:
            return response.data[0]

        return None

    except Exception as e:
        print(f"[DB FETCH BY LINK ERROR] {e}")
        return None


# ============================================================
# FILTER ARTICLES
# ============================================================

def get_filtered_articles(
    category: Optional[str] = None,
    priority: Optional[str] = None,
    search_query: Optional[str] = None,
    limit: int = 1000
) -> List[Dict[str, Any]]:

    try:
        client = get_supabase()

        query = (
            client
            .table("articles")
            .select("*")
        )

        # Filter kategori
        if category and category != "Semua Kategori":
            query = query.eq(
                "category",
                category
            )

        # Filter prioritas
        if priority and priority != "Semua Prioritas":
            query = query.eq(
                "priority",
                priority
            )

        # Pencarian judul
        if search_query:
            search_query = search_query.strip()

            if search_query:
                query = query.ilike(
                    "title",
                    f"%{search_query}%"
                )

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
        print(f"[DB FILTER ERROR] {e}")
        return []


# ============================================================
# SAVE RUN LOG
# ============================================================

def save_run_log(
    log_data: Dict[str, Any]
) -> bool:

    try:
        client = get_supabase()

        cleaned = dict(log_data)

        response = (
            client
            .table("run_logs")
            .insert(cleaned)
            .execute()
        )

        return bool(response.data)

    except Exception as e:
        print(f"[DB LOG ERROR] {e}")
        return False
