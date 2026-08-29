import os
import re
import html
from typing import List, Dict, Any, Optional
from supabase import create_client, Client

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()

def get_supabase() -> Client:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("SUPABASE_URL dan SUPABASE_KEY harus dikonfigurasi di Environment Variable.")
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def clean_html(raw_html: str) -> str:
    """Menghapus seluruh tag HTML dan unescape entitas teks."""
    if not raw_html:
        return ""
    text = html.unescape(str(raw_html))
    text = re.sub(r'<[^>]+>', '', text)
    return re.sub(r'\s+', ' ', text).strip()

def clean_article_payload(article: Dict[str, Any]) -> Dict[str, Any]:
    """Memastikan teks title dan content bersih dari tag HTML sebelum disimpan."""
    if "title" in article:
        article["title"] = clean_html(article["title"])
    if "content" in article:
        article["content"] = clean_html(article["content"])
    return article

def upsert_article(article: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    client = get_supabase()
    cleaned = clean_article_payload(article)
    try:
        res = client.table("articles").upsert(cleaned, on_conflict="url").execute()
        return res.data[0] if res.data else None
    except Exception as e:
        print(f"[DB UPSERT ERROR] {e}")
        return None

def update_article(article_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    client = get_supabase()
    cleaned = clean_article_payload(data)
    try:
        res = client.table("articles").update(cleaned).eq("id", article_id).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        print(f"[DB UPDATE ERROR] {e}")
        return None

def get_all_articles() -> List[Dict[str, Any]]:
    client = get_supabase()
    try:
        res = client.table("articles").select("*").order("published_date", desc=True).execute()
        return res.data or []
    except Exception as e:
        print(f"[DB FETCH ERROR] {e}")
        return []

def get_article_by_link(url: str) -> Optional[Dict[str, Any]]:
    client = get_supabase()
    try:
        res = client.table("articles").select("*").eq("url", url).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        print(f"[DB FETCH BY LINK ERROR] {e}")
        return None

def get_filtered_articles(
    category: Optional[str] = None,
    priority: Optional[str] = None,
    search_query: Optional[str] = None,
    limit: int = 1000
) -> List[Dict[str, Any]]:
    client = get_supabase()
    try:
        query = client.table("articles").select("*")
        if category and category != "Semua Kategori":
            query = query.eq("category", category)
        if priority and priority != "Semua Prioritas":
            query = query.eq("priority", priority)
        if search_query:
            query = query.ilike("title", f"%{search_query}%")
            
        res = query.order("published_date", desc=True).limit(limit).execute()
        return res.data or []
    except Exception as e:
        print(f"[DB FILTER ERROR] {e}")
        return []

def save_run_log(log_data: Dict[str, Any]) -> None:
    client = get_supabase()
    try:
        client.table("run_logs").insert(log_data).execute()
    except Exception as e:
        print(f"[DB LOG ERROR] {e}")
