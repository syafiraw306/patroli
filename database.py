import os
import re
import html
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
    _supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("[SUPABASE] Client berhasil dibuat.")
    return _supabase


def clean_html(raw_html: Any) -> str:
    if raw_html is None:
        return ""
    text = html.unescape(str(raw_html))
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def clean_article_payload(
    article: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Membersihkan payload artikel sebelum dikirim ke Supabase.

    Field yang diproses di sini hanya field yang memang
    digunakan oleh tabel articles.

    Field yang TIDAK dikirim:
    - summary
    - keywords
    """

    data = dict(article)

    # ========================================================
    # FIELD TEKS
    # ========================================================

    if "title" in data:
        data["title"] = clean_html(
            data.get("title")
        )

    if "content" in data:
        data["content"] = clean_html(
            data.get("content")
        )

    # ========================================================
    # FIELD ARRAY
    # ========================================================

    array_fields = [
        "detected_keywords",
        "satker_matches",
        "satker_title_matches",
        "satker_first_paragraph_matches",
        "strong_context",
        "positive_context",
        "handling_context",
        "first_paragraphs",
    ]

    for field in array_fields:

        if field in data:

            value = data.get(field)

            if value is None:
                data[field] = []

            elif isinstance(value, tuple):
                data[field] = list(value)

    # ========================================================
    # HAPUS FIELD YANG TIDAK ADA
    # ========================================================

    data.pop(
        "summary",
        None
    )

    data.pop(
        "keywords",
        None
    )

    return data

def normalize_link(link: Any) -> str:
    return str(link or "").strip()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def test_connection() -> bool:
    try:
        client = get_supabase()
        response = client.table("articles").select("link").limit(1).execute()
        print(f"[SUPABASE] Koneksi berhasil. Test response: {len(response.data or [])} row.")
        return True
    except Exception as e:
        print(f"[SUPABASE TEST ERROR] {e}")
        return False


def get_all_articles(page_size: int = 1000) -> List[Dict[str, Any]]:
    client = get_supabase()
    results: List[Dict[str, Any]] = []
    start = 0
    while True:
        try:
            response = (
                client.table("articles")
                .select("*")
                .order("published_date", desc=True)
                .range(start, start + page_size - 1)
                .execute()
            )
            rows = response.data or []
        except Exception as e:
            print(f"[SUPABASE FETCH ERROR] {e}")
            break
        results.extend(rows)
        print(f"[SUPABASE] Mengambil {len(rows)} artikel (offset {start}).")
        if len(rows) < page_size:
            break
        start += page_size
    print(f"[SUPABASE] Total artikel: {len(results)}")
    return results


def get_article_by_link(link: str) -> Optional[Dict[str, Any]]:
    link = normalize_link(link)
    if not link:
        return None
    try:
        response = get_supabase().table("articles").select("*").eq("link", link).limit(1).execute()
        rows = response.data or []
        return rows[0] if rows else None
    except Exception as e:
        print(f"[DB GET ERROR] {e}")
        return None


def article_exists(link: str) -> bool:
    return get_article_by_link(link) is not None


def upsert_article(article: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    data = clean_article_payload(article)
    data["link"] = normalize_link(data.get("link"))
    if not data["link"]:
        raise ValueError("Artikel tidak memiliki link.")
    current_time = now_iso()
    data.setdefault("created_at", current_time)
    data["updated_at"] = current_time
    try:
        response = (
            get_supabase().table("articles")
            .upsert(data, on_conflict="link")
            .execute()
        )
        rows = response.data or []
        return rows[0] if rows else data
    except Exception as e:
        print(f"[SUPABASE UPSERT ERROR] {e}")
        return None


def insert_articles(articles: List[Dict[str, Any]]) -> int:
    success = 0
    for article in articles or []:
        try:
            if upsert_article(article) is not None:
                success += 1
        except Exception as e:
            print(f"[SUPABASE] Gagal menyimpan artikel: {e}")
    print(f"[SUPABASE] Berhasil menyimpan {success}/{len(articles or [])} artikel.")
    return success


def update_article(link: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Update berdasarkan link. Ini sengaja menjadi kontrak utama patroli.py."""
    link = normalize_link(link)
    if not link:
        return None
    data = clean_article_payload(updates)
    data["updated_at"] = now_iso()
    if len(data) == 1:
        return None
    try:
        response = get_supabase().table("articles").update(data).eq("link", link).execute()
        rows = response.data or []
        return rows[0] if rows else None
    except Exception as e:
        print(f"[DB UPDATE ERROR] {e}")
        return None


def delete_all_articles() -> bool:
    try:
        get_supabase().table("articles").delete().neq("link", "").execute()
        print("[SUPABASE] Semua artikel dihapus.")
        return True
    except Exception as e:
        print(f"[SUPABASE DELETE ERROR] {e}")
        return False


def get_filtered_articles(category: Optional[str] = None, priority: Optional[str] = None,
                           search_query: Optional[str] = None, limit: int = 1000) -> List[Dict[str, Any]]:
    try:
        query = get_supabase().table("articles").select("*")
        if category and category != "Semua Kategori":
            query = query.eq("category", category)
        if priority and priority != "Semua Prioritas":
            query = query.eq("priority", priority)
        if search_query:
            query = query.ilike("title", f"%{search_query}%")
        return query.order("published_date", desc=True).limit(limit).execute().data or []
    except Exception as e:
        print(f"[DB FILTER ERROR] {e}")
        return []


def save_run_log(
    log_data: Dict[str, Any]
) -> bool:
    """
    Menyimpan log eksekusi patroli ke tabel run_logs.

    Field tambahan yang tidak tersedia di schema akan
    otomatis dibuang sebelum dikirim ke Supabase.
    """

    if not isinstance(log_data, dict):
        print("[DB LOG ERROR] log_data bukan dictionary.")
        return False

    # ========================================================
    # KOLOM YANG DIGUNAKAN APLIKASI
    # ========================================================

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
            for key, value in log_data.items()
            if key in allowed_columns
        }

        data.setdefault(
            "created_at",
            now_iso()
        )

        response = (
            get_supabase()
            .table("run_logs")
            .insert(data)
            .execute()
        )

        if response.data:
            print(
                "[DB LOG] Run log berhasil disimpan."
            )
            return True

        print(
            "[DB LOG] Insert berhasil tetapi "
            "tidak ada data response."
        )
        return True

    except Exception as e:

        print(
            f"[DB LOG ERROR] {e}"
        )

        return False


def get_run_logs(limit: int = 200) -> List[Dict[str, Any]]:
    try:
        return (get_supabase().table("run_logs").select("*")
                .order("created_at", desc=True).limit(limit).execute().data or [])
    except Exception as e:
        print(f"[DB RUN LOG ERROR] {e}")
        return []


def get_category_counts(articles: Optional[List[Dict[str, Any]]] = None) -> Dict[str, int]:
    articles = get_all_articles() if articles is None else articles
    counts = {"Negatif Kuat": 0, "Perlu Penanganan": 0, "Netral": 0, "Positif": 0}
    for article in articles:
        category = article.get("category") or "Netral"
        counts[category if category in counts else "Netral"] += 1
    return counts


def get_category_count_from_db(category: str) -> int:
    if not category:
        return 0
    try:
        response = get_supabase().table("articles").select("link", count="exact").eq("category", category).execute()
        return int(response.count or 0)
    except Exception as e:
        print(f"[DB CATEGORY COUNT ERROR] {e}")
        return 0


def get_total_article_count() -> int:
    try:
        response = get_supabase().table("articles").select("link", count="exact").execute()
        return int(response.count or 0)
    except Exception as e:
        print(f"[DB TOTAL COUNT ERROR] {e}")
        return 0


def update_article_category(link: str, category: str) -> Optional[Dict[str, Any]]:
    return update_article(link, {"category": category})


def update_article_priority(link: str, priority: str) -> Optional[Dict[str, Any]]:
    return update_article(link, {"priority": priority})


def update_article_classification(link: str, category: Optional[str] = None,
                                   priority: Optional[str] = None) -> Optional[Dict[str, Any]]:
    updates: Dict[str, Any] = {}
    if category is not None:
        updates["category"] = category
    if priority is not None:
        updates["priority"] = priority
    return update_article(link, updates) if updates else None


def get_articles_by_category(category: str, limit: int = 1000) -> List[Dict[str, Any]]:
    if not category:
        return []
    try:
        return (get_supabase().table("articles").select("*").eq("category", category)
                .order("published_date", desc=True).limit(limit).execute().data or [])
    except Exception as e:
        print(f"[DB CATEGORY ERROR] {e}")
        return []


def get_articles_by_priority(priority: str, limit: int = 1000) -> List[Dict[str, Any]]:
    if not priority:
        return []
    try:
        return (get_supabase().table("articles").select("*").eq("priority", priority)
                .order("published_date", desc=True).limit(limit).execute().data or [])
    except Exception as e:
        print(f"[DB PRIORITY ERROR] {e}")
        return []


def search_articles(search_query: str, limit: int = 100) -> List[Dict[str, Any]]:
    if not search_query:
        return []
    try:
        return (get_supabase().table("articles").select("*").ilike("title", f"%{search_query}%")
                .order("published_date", desc=True).limit(limit).execute().data or [])
    except Exception as e:
        print(f"[DB SEARCH ERROR] {e}")
        return []


def get_latest_articles(limit: int = 20) -> List[Dict[str, Any]]:
    try:
        return (get_supabase().table("articles").select("*")
                .order("published_date", desc=True).limit(limit).execute().data or [])
    except Exception as e:
        print(f"[DB LATEST ERROR] {e}")
        return []


def health_check() -> Dict[str, Any]:
    result: Dict[str, Any] = {"connected": False, "articles": 0, "error": None}
    try:
        response = get_supabase().table("articles").select("link", count="exact").limit(1).execute()
        result["connected"] = True
        result["articles"] = int(response.count or 0)
    except Exception as e:
        result["error"] = str(e)
        print(f"[DB HEALTH ERROR] {e}")
    return result


if __name__ == "__main__":
    print("=" * 60)
    print("DATABASE.PY - SUPABASE TEST")
    print("=" * 60)
    if test_connection():
        health = health_check()
        print(f"[DATABASE] Connected : {health.get('connected')}")
        print(f"[DATABASE] Articles  : {health.get('articles')}")
    else:
        print("[DATABASE] Koneksi database gagal.")
    print("=" * 60)
