import os
import re
import sys
import json
import time
import html
import urllib.parse
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import feedparser
from bs4 import BeautifulSoup
from dateutil import parser

from database import (
    upsert_article,
    get_all_articles,
    get_article_by_link,
    update_article,
    save_run_log,
)

TAHUN_TARGET = 2026
MAX_WORKERS = 10
REQUEST_TIMEOUT = 15
FIRST_PARAGRAPH_LIMIT = 3
MIN_ARTICLE_TEXT = 100

NAMA_SATKER = os.getenv("NAMA_SATKER", "Kejaksaan Negeri Deli Serdang").strip()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.getenv("CHAT_ID", "").strip()

TARGET_KEJARI_KEYWORDS = [
    "kejaksaan negeri deli serdang", "kejari deli serdang", "kajari deli serdang",
    "kejari deliserdang", "kejaksaan deliserdang", "kejaksaan deli serdang",
    "cabang kejaksaan negeri pancur batu", "cabjari pancur batu", "kacabjari pancur batu",
    "cabang kejaksaan negeri labuhan deli", "cabjari labuhan deli", "kacabjari labuhan deli",
]

SEARCH_TARGETS = [
    '"Kejaksaan Negeri Deli Serdang"', '"Kejari Deli Serdang"', '"Kajari Deli Serdang"',
    '"Kejari Deliserdang"', '"Kejaksaan Deli Serdang"', '"Cabjari Pancur Batu"', '"Cabjari Labuhan Deli"',
]

NEGATIVE_STRONG_RULES = {
    "skandal": 12, "skandal perselingkuhan": 18, "perselingkuhan": 15, "selingkuh": 14,
    "pelakor": 15, "dugaan skandal": 14, "dugaan perselingkuhan": 16, "viral": 5, "aib": 12,
    "dicopot": 13, "pencopotan": 13, "copot kajari": 16, "kajari dicopot": 18, "kejagung copot kajari": 20,
    "pelanggaran etik": 16, "pelanggaran kode etik": 18, "didesak mundur": 17, "didesak dicopot": 18,
    "maladministrasi": 15, "arogan": 11, "pemerasan": 14, "dugaan pemerasan": 17, "suap": 13,
    "dugaan suap": 16, "gratifikasi": 13, "dugaan gratifikasi": 16, "pungli": 13, "dugaan pungli": 16,
    "mafia hukum": 18, "kolusi": 14, "nepotisme": 13, "penyalahgunaan wewenang": 17, "penyelewengan": 15,
    "batal dilantik": 18, "pelantikan batal": 18, "pelantikan dibatalkan": 22, "pelantikan ditunda": 18,
    "pelantikan cpns dibatalkan": 24, "pelantikan cpns ditunda": 22, "pelantikan cpns kejari dibatalkan": 26,
}

STRONG_NEGATIVE_CONTEXT = [
    "skandal perselingkuhan", "dugaan perselingkuhan", "papan bunga pelakor", "karangan bunga pelakor",
    "kajari dicopot", "pelanggaran etik", "didesak mundur", "dugaan pemerasan", "dugaan suap",
    "dugaan gratifikasi", "dugaan pungli", "mafia hukum", "penyalahgunaan wewenang", "pelantikan dibatalkan",
]

SOFT_NEGATIVE_CONTEXT = ["menuai sorotan", "disorot", "menuai kritik", "kritik keras", "diprotes", "demonstrasi", "janggal"]

HANDLING_RULES = {
    "korupsi": 7, "dugaan korupsi": 9, "kasus korupsi": 8, "penyelidikan": 5, "penyidikan": 5,
    "diperiksa": 7, "diperiksa kejagung": 11, "dipanggil": 6, "dipanggil kejagung": 10, "dilaporkan": 7,
    "laporan masyarakat": 7, "pengaduan": 6, "pengaduan masyarakat": 7, "tersangka": 7, "terlapor": 7,
    "tuntutan": 5, "dituntut": 5, "narkotika": 6, "kasus narkotika": 8, "keluhan pelayanan": 8,
}

POSITIVE_RULES = {
    "berhasil mengungkap": 10, "berhasil menangkap": 10, "berhasil mengamankan": 9, "mengungkap korupsi": 9,
    "menangkap tersangka": 8, "menyita barang bukti": 8, "penghargaan": 9, "prestasi": 9, "capaian kinerja": 9,
    "pelayanan prima": 9, "penyuluhan hukum": 8, "sosialisasi hukum": 8, "jaksa masuk sekolah": 9,
    "jaksa menyapa": 7, "upacara": 5, "apel": 5, "kunjungan kerja": 7, "rapat koordinasi": 7,
    "penandatanganan mou": 8, "kerja sama": 8, "peresmian": 8, "pelantikan": 6, "bakti sosial": 8,
}

OFFICIAL_ACTIVITY_CONTEXT = ["upacara", "apel", "kunjungan kerja", "rapat koordinasi", "penandatanganan mou", "peresmian", "pelantikan", "bakti sosial"]
SUCCESS_LAW_ENFORCEMENT_CONTEXT = ["berhasil mengungkap", "berhasil menangkap", "mengungkap korupsi", "menangkap tersangka", "menyita barang bukti"]
HANDLING_CONTEXT = ["diperiksa kejagung", "dipanggil kejagung", "penyelidikan", "penyidikan", "menangani kasus", "kasus korupsi"]
DANGER_TITLE_TERMS = ["dicopot", "dipanggil kejagung", "diperiksa kejagung", "skandal", "perselingkuhan", "pelakor", "didesak", "batal dilantik"]
LEGAL_RISK_TERMS = ["korupsi", "narkotika", "tersangka", "terlapor", "diperiksa", "dipanggil", "penyelidikan", "penyidikan", "pengaduan", "dicopot"]
CANCELLATION_CONTEXT = ["pelantikan dibatalkan", "pelantikan cpns dibatalkan", "pelantikan ditunda", "batal dilantik"]

def clean_html_text(text):
    if not text:
        return ""
    text = html.unescape(str(text))
    text = re.sub(r'<[^>]+>', '', text)
    return re.sub(r"\s+", " ", text).strip()

def normalize_text(text):
    return clean_html_text(text).lower()

def normalize_url(url):
    return str(url).strip().split("#")[0] if url else ""

def parse_indonesian_date(text):
    if not text: return None
    bulan = {
        "januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5, "juni": 6,
        "juli": 7, "agustus": 8, "september": 9, "oktober": 10, "november": 11, "desember": 12,
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "agu": 8, "sep": 9, "okt": 10, "nov": 11, "des": 12
    }
    match = re.search(r"(\d{1,2})\s+([a-z]+)\s+(\d{4})", normalize_text(text))
    if not match or match.group(2) not in bulan: return None
    try:
        return datetime.datetime(int(match.group(3)), bulan[match.group(2)], int(match.group(1)))
    except Exception:
        return None

def parse_date_safe(value):
    if not value: return None
    try:
        dt = parser.parse(str(value), fuzzy=True, dayfirst=True)
        if dt.tzinfo:
            dt = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        return parse_indonesian_date(str(value))

def extract_published_date(soup):
    candidates = []
    for script in soup.find_all("script", attrs={"type": re.compile(r"application/ld\+json", re.I)}):
        try:
            raw = script.string or script.get_text()
            if not raw: continue
            data = json.loads(raw)
            objects = data if isinstance(data, list) else [data]
            if isinstance(data, dict) and "@graph" in data:
                objects.extend(data["@graph"])
            for obj in objects:
                if isinstance(obj, dict):
                    for key in ["datePublished", "dateCreated", "dateModified"]:
                        if obj.get(key): candidates.append(obj[key])
        except Exception: continue

    selectors = [{"property": "article:published_time"}, {"name": "article:published_time"}, {"itemprop": "datePublished"}]
    for attrs in selectors:
        element = soup.find("meta", attrs=attrs)
        if element and element.get("content"):
            candidates.append(element.get("content"))

    for tag in soup.find_all("time"):
        if tag.get("datetime") or tag.get_text():
            candidates.append(tag.get("datetime") or tag.get_text())

    for val in candidates:
        dt = parse_date_safe(val)
        if dt: return dt
    return None

def get_rss_date(entry):
    for attr in ["published_parsed", "updated_parsed"]:
        val = getattr(entry, attr, None)
        if val:
            try: return datetime.datetime(val.tm_year, val.tm_mon, val.tm_mday, val.tm_hour, val.tm_min, val.tm_sec)
            except Exception: pass
    for attr in ["published", "updated"]:
        val = getattr(entry, attr, None)
        if val:
            dt = parse_date_safe(val)
            if dt: return dt
    return None

def validate_date(article_date, rss_date):
    now = datetime.datetime.now()
    dt = article_date or rss_date
    if not dt or dt.year != TAHUN_TARGET or dt > (now + datetime.timedelta(days=1)):
        return False, dt
    return True, dt

def get_headers():
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0 Safari/537.36",
        "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
    }

def fetch_webpage(url):
    try:
        res = requests.get(url, headers=get_headers(), timeout=REQUEST_TIMEOUT, allow_redirects=True)
        if res.status_code == 200:
            return {"html": res.text, "final_url": res.url}
    except Exception as e:
        print(f"[FETCH ERROR] {url}: {e}")
    return None

def resolve_redirect_url(url):
    try:
        res = requests.get(url, headers=get_headers(), timeout=REQUEST_TIMEOUT, allow_redirects=True, stream=True)
        final_url = res.url or url
        res.close()
        return final_url
    except Exception:
        return url

def extract_article_text(soup):
    copy_soup = BeautifulSoup(str(soup), "html.parser")
    for tag in copy_soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "form", "aside", "iframe"]):
        tag.decompose()
    article = copy_soup.find("article") or copy_soup.find("main")
    text = article.get_text(" ", strip=True) if article else copy_soup.get_text(" ", strip=True)
    return clean_html_text(text)

def extract_first_paragraphs(soup, limit=FIRST_PARAGRAPH_LIMIT):
    copy_soup = BeautifulSoup(str(soup), "html.parser")
    for tag in copy_soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "form", "aside", "iframe"]):
        tag.decompose()
    article = copy_soup.find("article") or copy_soup.find("main") or copy_soup
    paragraphs = []
    for p in article.find_all("p"):
        text = clean_html_text(p.get_text(" ", strip=True))
        if len(text) >= 25 and normalize_text(text) not in ["baca juga", "iklan", "advertisement"]:
            paragraphs.append(text)
            if len(paragraphs) >= limit: break
    return paragraphs

def satker_is_relevant(title, first_paragraphs):
    title_n = normalize_text(title)
    first_text = normalize_text(" ".join(first_paragraphs))
    title_matches = [k for k in TARGET_KEJARI_KEYWORDS if normalize_text(k) in title_n]
    first_matches = [k for k in TARGET_KEJARI_KEYWORDS if normalize_text(k) in first_text]
    locs = []
    if title_matches: locs.append("title")
    if first_matches: locs.append("first_paragraphs")
    return bool(title_matches or first_matches), title_matches, first_matches, ",".join(locs)

def calculate_rule_score(text, rules):
    score, detected = 0, []
    text_n = normalize_text(text)
    for kw, weight in rules.items():
        if kw in text_n:
            score += weight
            detected.append(kw)
    return score, detected

def has_negation_near(text, keyword, window=60):
    text_n = normalize_text(text)
    start = text_n.find(keyword)
    negations = ["tidak", "bukan", "tanpa", "belum terbukti", "tidak terbukti", "menepis", "membantah"]
    while start != -1:
        before = text_n[max(0, start - window):start]
        if any(neg in before for neg in negations): return True
        start = text_n.find(keyword, start + 1)
    return False

def classify_article(title, snippet, content, first_paragraphs=None):
    first_paragraphs = first_paragraphs or []
    title_clean = clean_html_text(title)
    content_clean = clean_html_text(content)

    satker_ok, t_matches, f_matches, loc = satker_is_relevant(title_clean, first_paragraphs)
    if not satker_ok:
        return {
            "category": "Netral", "priority": "RENDAH", "negative_score": 0, "handling_score": 0,
            "positive_score": 0, "detected_keywords": [], "satker_matches": [], "satker_match_location": ""
        }

    full_text = f"{title_clean} {clean_html_text(snippet)} {' '.join(first_paragraphs)} {content_clean}"
    strong_score, strong_kw = calculate_rule_score(full_text, NEGATIVE_STRONG_RULES)
    handling_score, handling_kw = calculate_rule_score(full_text, HANDLING_RULES)
    positive_score, positive_kw = calculate_rule_score(full_text, POSITIVE_RULES)

    t_strong_s, t_strong_kw = calculate_rule_score(title_clean, NEGATIVE_STRONG_RULES)
    t_hand_s, _ = calculate_rule_score(title_clean, HANDLING_RULES)
    t_pos_s, _ = calculate_rule_score(title_clean, POSITIVE_RULES)

    danger_hits = [term for term in DANGER_TITLE_TERMS if term in normalize_text(title_clean) and not has_negation_near(title_clean, term)]
    legal_hits = [term for term in LEGAL_RISK_TERMS if term in normalize_text(full_text) and not has_negation_near(full_text, term)]

    cancellation_matches = [x for x in CANCELLATION_CONTEXT if x in normalize_text(full_text) and not has_negation_near(full_text, x)]
    strong_context_matches = [x for x in STRONG_NEGATIVE_CONTEXT if x in normalize_text(full_text) and not has_negation_near(full_text, x)]

    strong_score += (t_strong_s * 2) + (len(strong_context_matches) * 10)
    handling_score += (t_hand_s * 2)
    positive_score += (t_pos_s * 2)

    hard_negative = bool(strong_context_matches or danger_hits or t_strong_s >= 8 or strong_score >= 22 or cancellation_matches)

    if hard_negative:
        category, priority = "Negatif Kuat", "TINGGI"
    elif handling_score >= 8 or t_hand_s >= 5 or len(legal_hits) >= 2:
        category, priority = "Perlu Penanganan", "SEDANG"
    elif positive_score >= 6 or t_pos_s >= 4:
        category, priority = "Positif", "RENDAH"
    else:
        category, priority = "Netral", "RENDAH"

    all_detected = list(dict.fromkeys(strong_kw + handling_kw + positive_kw + danger_hits + legal_hits))

    return {
        "category": category, "priority": priority, "negative_score": strong_score,
        "handling_score": handling_score, "positive_score": positive_score,
        "detected_keywords": all_detected, "satker_matches": list(set(t_matches + f_matches)),
        "satker_match_location": loc,
    }

def fetch_rss_feed(query):
    encoded_query = urllib.parse.quote(query)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=id&gl=ID&ceid=ID:id"
    feed = feedparser.parse(rss_url)
    entries = []
    for entry in feed.entries:
        entries.append({
            "title": clean_html_text(entry.get("title", "")),
            "link": entry.get("link", ""),
            "rss_date": get_rss_date(entry),
        })
    return entries

def process_single_article(entry):
    resolved_url = resolve_redirect_url(entry["link"])
    norm_url = normalize_url(resolved_url)
    web_data = fetch_webpage(norm_url)
    if not web_data: return None

    soup = BeautifulSoup(web_data["html"], "html.parser")
    article_text = extract_article_text(soup)
    if len(article_text) < MIN_ARTICLE_TEXT: return None

    first_paragraphs = extract_first_paragraphs(soup)
    extracted_dt = extract_published_date(soup)
    is_valid, final_dt = validate_date(extracted_dt, entry["rss_date"])
    if not is_valid: return None

    analysis = classify_article(entry["title"], "", article_text, first_paragraphs)
    return {
        "title": clean_html_text(entry["title"]),
        "url": norm_url,
        "content": article_text,
        "published_date": final_dt.isoformat() if final_dt else None,
        "category": analysis["category"],
        "priority": analysis["priority"],
        "satker": NAMA_SATKER,
        "keywords": analysis["detected_keywords"],
    }

def send_telegram_alert(article):
    if not TELEGRAM_TOKEN or not CHAT_ID: return
    category = article.get("category", "Netral")
    emoji = "🔴" if category == "Negatif Kuat" else "🟡" if category == "Perlu Penanganan" else "🟢"
    msg = (
        f"{emoji} <b>PATROLI SIBER - BERITA BARU</b>\n\n"
        f"<b>Judul:</b> {html.escape(article['title'])}\n"
        f"<b>Kategori:</b> {category}\n"
        f"<b>Prioritas:</b> {article.get('priority', 'RENDAH')}\n"
        f"<b>Satker:</b> {article.get('satker', NAMA_SATKER)}\n"
        f"<b>Link:</b> <a href='{article['url']}'>Baca Artikel</a>"
    )
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=10)
    except Exception as e:
        print(f"[TELEGRAM ERROR] {e}")

def reclassify_all_existing_articles():
    print("[INFO] Memulai pembersihan tag HTML dan reklasifikasi database...")
    articles = get_all_articles()
    updated_count = 0
    for art in articles:
        clean_title = clean_html_text(art.get("title", ""))
        clean_content = clean_html_text(art.get("content", ""))
        first_p = [p.strip() for p in clean_content.split(".") if len(p.strip()) > 25][:3]
        analysis = classify_article(clean_title, "", clean_content, first_p)

        update_article(art["id"], {
            "title": clean_title,
            "content": clean_content,
            "category": analysis["category"],
            "priority": analysis["priority"],
            "keywords": analysis["detected_keywords"]
        })
        updated_count += 1
    print(f"[INFO] Pembersihan dan reklasifikasi selesai: {updated_count} artikel.")

def run_patrol():
    start_time = time.time()
    print(f"=== MENJALANKAN PATROLI SIBER ({NAMA_SATKER}) ===")
    raw_entries = []
    for query in SEARCH_TARGETS:
        raw_entries.extend(fetch_rss_feed(query))

    unique_entries = {e["link"]: e for e in raw_entries}.values()
    processed_count, new_articles_count = 0, 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_single_article, entry): entry for entry in unique_entries}
        for future in as_completed(futures):
            processed_count += 1
            res = future.result()
            if res:
                existing = get_article_by_link(res["url"])
                upsert_article(res)
                if not existing:
                    new_articles_count += 1
                    send_telegram_alert(res)

    reclassify_all_existing_articles()
    exec_time = round(time.time() - start_time, 2)
    save_run_log({"satker": NAMA_SATKER, "processed_urls": processed_count, "new_articles": new_articles_count, "execution_time_seconds": exec_time, "status": "SUCCESS"})

if __name__ == "__main__":
    run_patrol()
