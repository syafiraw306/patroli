import argparse
import html
import os
import re
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import feedparser
import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from dotenv import load_dotenv

from database import (
    get_all_articles,
    get_article_by_link,
    save_run_log,
    upsert_article,
    update_article_classification,
)

load_dotenv()

TAHUN_TARGET = int(os.getenv("TAHUN_TARGET", "2026"))
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "10"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "15"))
MAX_ARTICLES_PER_FEED = int(os.getenv("MAX_ARTICLES_PER_FEED", "40"))
MIN_CONTENT_LENGTH = int(os.getenv("MIN_CONTENT_LENGTH", "180"))
NAMA_SATKER = os.getenv("NAMA_SATKER", "Kejaksaan Negeri Deli Serdang").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

TARGET_KEJARI_KEYWORDS = [
    "kejaksaan negeri deli serdang",
    "kejari deli serdang",
    "kejari deliserdang",
    "kejaksaan deli serdang",
    "kajari deli serdang",
    "kepala kejaksaan negeri deli serdang",
    "kejari lubuk pakam",
    "kejaksaan negeri lubuk pakam",
    "cabang kejaksaan negeri deli serdang",
]

SEARCH_TARGETS = [
    '"Kejaksaan Negeri Deli Serdang"',
    '"Kejari Deli Serdang"',
    '"Kajari Deli Serdang"',
    '"Kejari Lubuk Pakam"',
]

# Kata-kata ini sendiri TIDAK cukup untuk membuat berita negatif.
LEGAL_EVENT_TERMS = {
    "kasus", "korupsi", "narkotika", "narkoba", "tersangka", "terdakwa",
    "penyidikan", "penyelidikan", "penuntutan", "perkara", "pidana",
    "pengadilan", "sidang", "vonis", "dakwaan", "suap", "gratifikasi",
    "penggeledahan", "penyitaan", "penangkapan", "ditangkap", "menangkap",
}

# Aktivitas penegakan hukum yang justru menunjukkan kinerja positif.
POSITIVE_ACTION_PATTERNS = [
    r"berhasil\s+(?:mengungkap|mengungkapkan|menangkap|mengamankan|menyita|membongkar)",
    r"berhasil\s+.*?(?:tersangka|pelaku|barang bukti)",
    r"ungkap\s+(?:kasus|perkara)",
    r"tangkap\s+(?:tersangka|pelaku)",
    r"amankan\s+(?:tersangka|pelaku|barang bukti)",
    r"sita\s+(?:barang bukti|aset)",
    r"menetapkan\s+.*?\s+sebagai\s+tersangka",
    r"menindaklanjuti\s+.*?\s+sesuai\s+(?:ketentuan|hukum)",
    r"eksekusi\s+.*?(?:terpidana|putusan|pidana)",
    r"melaksanakan\s+.*?(?:eksekusi|penyuluhan|penerangan hukum)",
]

OFFICIAL_ACTIVITY_PATTERNS = [
    r"apel", r"upacara", r"rapat", r"fgd", r"focus group discussion",
    r"kunjungan", r"silaturahmi", r"konsolidasi", r"koordinasi", r"monitoring",
    r"evaluasi", r"penyuluhan hukum", r"penerangan hukum", r"sosialisasi",
    r"pelantikan", r"pengambilan sumpah", r"serah terima", r"launching",
    r"peresmian", r"penandatanganan", r"kerja sama", r"mo[uU]", r"upacara",
    r"ziarah", r"bakti sosial", r"gotong royong", r"kunjungan kerja",
    r"mengikuti zoom", r"menghadiri", r"hadiri", r"memimpin rapat",
]

# Negatif kuat harus menunjukkan masalah/dugaan terhadap satker atau pimpinan satker.
NEGATIVE_STRONG_PATTERNS = [
    r"kajari\b.*?(?:ditangkap|diamankan|ditetapkan\s+sebagai\s+tersangka|tersangka|terdakwa)",
    r"kajari\b.*?(?:suap|gratifikasi|korupsi|pungli|pemerasan|penggelapan)",
    r"(?:kepala\s+kejaksaan|kajari)\b.*?(?:diperiksa|dipanggil|dilaporkan|diadukan|disidang|diadili)",
    r"(?:kajari|kejari|kejaksaan negeri)\b.*?(?:dicopot|dimutasi\s+karena|diberhentikan\s+karena)",
    r"(?:kejari|kejaksaan negeri)\b.*?(?:diduga|terindikasi|dituding|dituduh)\s+(?:melakukan|terlibat|menerima)",
    r"(?:kejari|kejaksaan negeri)\b.*?(?:pelanggaran etik|pelanggaran hukum|maladministrasi)",
    r"(?:kejari|kejaksaan negeri)\b.*?(?:laporan pengaduan|aduan masyarakat|dilaporkan ke)",
    r"(?:kantor|oknum).*?kejaksaan negeri.*?(?:digeledah|disita|diperiksa)",
]

# Isu hukum yang perlu dipantau tetapi belum cukup kuat untuk Negatif Kuat.
HANDLING_PATTERNS = [
    r"dilaporkan", r"diadukan", r"pengaduan", r"laporan masyarakat",
    r"diperiksa", r"dimintai keterangan", r"klarifikasi", r"dipanggil",
    r"protes", r"soroti", r"disorot", r"kritik", r"kritikan",
    r"dugaan", r"diduga", r"dituding", r"dituduh", r"polemik",
    r"sengketa", r"keberatan", r"somasi", r"demonstrasi", r"unjuk rasa",
    r"viral", r"kontroversi", r"permintaan transparansi",
]

NEGATION_PATTERNS = [
    r"tidak\s+(?:terbukti|benar|ada|melakukan|terlibat)",
    r"belum\s+(?:terbukti|ada|ditemukan)",
    r"bantah", r"membantah", r"dibantah", r"klarifikasi",
    r"hoaks", r"tidak benar", r"fitnah",
]

DANGER_TITLE_TERMS = {
    "ditangkap", "tersangka", "suap", "gratifikasi", "korupsi", "dicopot",
    "dilaporkan", "diadukan", "pungli", "pemerasan", "pelanggaran etik",
}

PRIORITY_BY_CATEGORY = {
    "Negatif Kuat": "Tinggi",
    "Perlu Penanganan": "Sedang",
    "Netral": "Rendah",
    "Positif": "Rendah",
}

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36",
    "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
})


def normalize_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_url(url: Any) -> str:
    url = str(url or "").strip()
    if not url:
        return ""
    try:
        p = urllib.parse.urlsplit(url)
        query = urllib.parse.parse_qs(p.query)
        for key in ("url", "u", "q", "target"):
            if key in query and query[key]:
                candidate = query[key][0]
                if candidate.startswith("http"):
                    url = candidate
                    break
    except Exception:
        pass
    return url.strip()


def parse_date_safe(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    try:
        dt = date_parser.parse(str(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def extract_published_date(entry: Any, fallback: Optional[datetime] = None) -> Optional[datetime]:
    for key in ("published", "updated", "created"):
        dt = parse_date_safe(entry.get(key))
        if dt:
            return dt
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        value = entry.get(key)
        if value:
            try:
                return datetime(*value[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return fallback


def is_article_2026(dt: Optional[datetime]) -> bool:
    return bool(dt and dt.year == TAHUN_TARGET)


def is_url_old(dt: Optional[datetime]) -> bool:
    return not is_article_2026(dt)


def fetch_webpage_content(url: str) -> Tuple[str, str]:
    if not url:
        return "", ""
    try:
        response = SESSION.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        response.raise_for_status()
        final_url = normalize_url(response.url)
        return final_url, response.text
    except Exception as e:
        print(f"[FETCH ERROR] {url} -> {e}")
        return url, ""


def extract_article_text(raw_html: str) -> str:
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "form"]):
        tag.decompose()
    candidates = []
    for selector in ["article", "main", "[itemprop='articleBody']", ".article-body", ".post-content", ".entry-content"]:
        for node in soup.select(selector):
            txt = normalize_text(node.get_text(" ", strip=True))
            if len(txt) > 100:
                candidates.append(txt)
    if candidates:
        return max(candidates, key=len)
    paragraphs = [normalize_text(p.get_text(" ", strip=True)) for p in soup.find_all("p")]
    paragraphs = [p for p in paragraphs if len(p) >= 35]
    return normalize_text(" ".join(paragraphs))


def check_satker_relevance(title: str, content: str) -> bool:
    text = normalize_text(f"{title} {content}").lower()
    return any(keyword in text for keyword in TARGET_KEJARI_KEYWORDS)


def regex_hits(text: str, patterns: List[str]) -> List[str]:
    hits = []
    for pattern in patterns:
        try:
            if re.search(pattern, text, flags=re.I):
                hits.append(pattern)
        except re.error:
            continue
    return hits


def has_negation_near(text: str, term: str, window: int = 90) -> bool:
    text = text.lower()
    for m in re.finditer(re.escape(term.lower()), text):
        before = text[max(0, m.start() - window):m.start()]
        if any(re.search(p, before, re.I) for p in NEGATION_PATTERNS):
            return True
    return False


def calculate_positive_score(title: str, content: str) -> int:
    text = normalize_text(f"{title}. {content}").lower()
    score = 0
    score += 5 * len(regex_hits(text, POSITIVE_ACTION_PATTERNS))
    score += 3 * len(regex_hits(text, OFFICIAL_ACTIVITY_PATTERNS))
    # Judul keberhasilan adalah sinyal yang sangat kuat.
    if any(re.search(p, title.lower()) for p in POSITIVE_ACTION_PATTERNS):
        score += 5
    return min(score, 30)


def calculate_negative_score(title: str, content: str) -> int:
    text = normalize_text(f"{title}. {content}").lower()
    score = 0
    for pattern in NEGATIVE_STRONG_PATTERNS:
        if re.search(pattern, text, re.I):
            score += 10
    # Jangan menghitung kata hukum umum sebagai negatif.
    return min(score, 40)


def calculate_handling_score(title: str, content: str) -> int:
    text = normalize_text(f"{title}. {content}").lower()
    score = 0
    for pattern in HANDLING_PATTERNS:
        if re.search(pattern, text, re.I):
            score += 2
    return min(score, 20)


def classify_article(title: str, content: str) -> Dict[str, Any]:
    title = normalize_text(title)
    content = normalize_text(content)
    full = f"{title}. {content}".lower()

    negative_score = calculate_negative_score(title, content)
    handling_score = calculate_handling_score(title, content)
    positive_score = calculate_positive_score(title, content)

    positive_hits = regex_hits(full, POSITIVE_ACTION_PATTERNS) + regex_hits(full, OFFICIAL_ACTIVITY_PATTERNS)
    negative_hits = regex_hits(full, NEGATIVE_STRONG_PATTERNS)
    handling_hits = regex_hits(full, HANDLING_PATTERNS)

    # 1. Pernyataan bantahan/hoaks tidak boleh otomatis menjadi negatif.
    negated_danger = any(has_negation_near(full, term) for term in DANGER_TITLE_TERMS)

    # 2. Keberhasilan penegakan hukum / kegiatan resmi diprioritaskan sebagai POSITIF,
    #    selama tidak ada indikasi masalah langsung terhadap satker.
    if positive_score >= 5 and negative_score == 0:
        category = "Positif"
    elif negative_score >= 10 and not negated_danger:
        category = "Negatif Kuat"
    elif handling_score >= 2:
        category = "Perlu Penanganan"
    elif positive_score >= 3:
        category = "Positif"
    else:
        category = "Netral"

    # 3. Jika berita hanya menyebut kasus/tersangka/narkotika tetapi Kejari adalah
    #    aparat yang menangani, jangan jadikan negatif.
    if category == "Negatif Kuat" and positive_score >= negative_score and negative_score < 20:
        category = "Positif"

    # 4. Jika ada bantahan kuat, turunkan menjadi handling/netral, bukan negatif kuat.
    if negated_danger and category == "Negatif Kuat":
        category = "Perlu Penanganan" if handling_score else "Netral"

    priority = PRIORITY_BY_CATEGORY[category]
    return {
        "category": category,
        "priority": priority,
        "negative_score": negative_score,
        "handling_score": handling_score,
        "positive_score": positive_score,
        "positive_hits": positive_hits[:12],
        "negative_hits": negative_hits[:12],
        "handling_hits": handling_hits[:12],
        "keywords": sorted({w for w in LEGAL_EVENT_TERMS if re.search(r"\b" + re.escape(w) + r"\b", full, re.I)}),
    }


def parse_google_news_feed(query: str) -> List[Dict[str, Any]]:
    encoded = urllib.parse.quote_plus(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=id&gl=ID&ceid=ID:id"
    try:
        feed = feedparser.parse(url)
        if getattr(feed, "bozo", False) and not feed.entries:
            print(f"[RSS ERROR] Feed bermasalah: {query}")
            return []
        rows = []
        for entry in feed.entries[:MAX_ARTICLES_PER_FEED]:
            published = extract_published_date(entry)
            rows.append({
                "title": normalize_text(entry.get("title")),
                "link": normalize_url(entry.get("link")),
                "published_date": published.isoformat() if published else None,
                "source": normalize_text((entry.get("source") or {}).get("title") if isinstance(entry.get("source"), dict) else entry.get("source")),
                "summary": normalize_text(entry.get("summary")),
            })
        return rows
    except Exception as e:
        print(f"[RSS ERROR] {query}: {e}")
        return []


def collect_candidates() -> List[Dict[str, Any]]:
    all_rows: Dict[str, Dict[str, Any]] = {}
    for query in SEARCH_TARGETS:
        print(f"[RSS] Mencari: {query}")
        for row in parse_google_news_feed(query):
            link = normalize_url(row.get("link"))
            if link:
                all_rows.setdefault(link, row)
    print(f"[PATROLI] Kandidat unik: {len(all_rows)}")
    return list(all_rows.values())


def process_candidate(candidate: Dict[str, Any]) -> Dict[str, Any]:
    title = candidate.get("title", "")
    rss_link = normalize_url(candidate.get("link"))
    rss_date = parse_date_safe(candidate.get("published_date"))

    result = {"ok": False, "saved": False, "telegram": False, "article": None, "reason": ""}
    if not rss_link:
        result["reason"] = "link kosong"
        return result
    if rss_date and not is_article_2026(rss_date):
        result["reason"] = "bukan tahun target"
        return result

    final_url, raw_html = fetch_webpage_content(rss_link)
    content = extract_article_text(raw_html)
    if not final_url:
        final_url = rss_link

    if len(content) < MIN_CONTENT_LENGTH:
        content = normalize_text(candidate.get("summary"))
    if len(content) < MIN_CONTENT_LENGTH:
        result["reason"] = "konten terlalu pendek"
        return result

    if not check_satker_relevance(title, content):
        result["reason"] = "tidak relevan dengan satker"
        return result

    published = rss_date or datetime.now(timezone.utc)
    if not is_article_2026(published):
        result["reason"] = "tanggal artikel bukan 2026"
        return result

    classification = classify_article(title, content)
    article = {
        "title": title,
        "link": final_url,
        "content": content,
        "summary": normalize_text(candidate.get("summary")),
        "published_date": published.isoformat(),
        "source": candidate.get("source") or "Google News",
        "category": classification["category"],
        "priority": classification["priority"],
        # keywords sengaja hanya ada di memori dan dibuang oleh database.py.
        "keywords": classification["keywords"],
    }

    try:
        saved = upsert_article(article)
        if saved is None:
            result["reason"] = "gagal upsert"
            return result
        result.update(ok=True, saved=True, article=article)
        return result
    except Exception as e:
        result["reason"] = str(e)
        return result


def telegram_enabled() -> bool:
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)


def send_telegram_message(text: str) -> bool:
    if not telegram_enabled():
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        response = SESSION.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"[TELEGRAM ERROR] {e}")
        return False


def telegram_text(article: Dict[str, Any]) -> str:
    title = html.escape(normalize_text(article.get("title")))
    category = html.escape(str(article.get("category", "Netral")))
    priority = html.escape(str(article.get("priority", "Rendah")))
    link = html.escape(normalize_url(article.get("link")))
    return f"<b>Patroli Siber {TAHUN_TARGET}</b>\n<b>Kategori:</b> {category}\n<b>Prioritas:</b> {priority}\n<b>Satker:</b> {html.escape(NAMA_SATKER)}\n\n<b>{title}</b>\n{link}"


def send_alert_if_needed(article: Dict[str, Any]) -> bool:
    # Telegram difokuskan untuk kategori yang membutuhkan perhatian atau benar-benar negatif.
    if article.get("category") not in {"Negatif Kuat", "Perlu Penanganan"}:
        return False
    return send_telegram_message(telegram_text(article))


def reclassify_all() -> Dict[str, int]:
    print("[REKLASIFIKASI] Memuat seluruh artikel dari database...")
    articles = get_all_articles()
    counts = {"Negatif Kuat": 0, "Perlu Penanganan": 0, "Netral": 0, "Positif": 0}
    updated = 0

    for article in articles:
        title = normalize_text(article.get("title"))
        content = normalize_text(article.get("content") or article.get("summary"))
        if not title and not content:
            category = "Netral"
            priority = "Rendah"
        else:
            c = classify_article(title, content)
            category, priority = c["category"], c["priority"]
        counts[category] += 1
        link = normalize_url(article.get("link"))
        if link and (article.get("category") != category or article.get("priority") != priority):
            if update_article_classification(link, category, priority) is not None:
                updated += 1

    print("=" * 70)
    print("REKLASIFIKASI SELESAI")
    print(f"Negatif Kuat      : {counts['Negatif Kuat']}")
    print(f"Perlu Penanganan  : {counts['Perlu Penanganan']}")
    print(f"Netral            : {counts['Netral']}")
    print(f"Positif           : {counts['Positif']}")
    print(f"Direklasifikasi    : {updated}")
    print(f"Total              : {sum(counts.values())}")
    print("=" * 70)
    return counts


def run_once() -> Dict[str, Any]:
    started = time.perf_counter()
    candidates = collect_candidates()
    valid = 0
    saved = 0
    failed = 0
    telegram_count = 0
    results: List[Dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=max(1, MAX_WORKERS)) as executor:
        futures = [executor.submit(process_candidate, candidate) for candidate in candidates]
        for future in as_completed(futures):
            try:
                result = future.result()
            except Exception as e:
                result = {"ok": False, "saved": False, "telegram": False, "article": None, "reason": str(e)}
            results.append(result)
            if result.get("ok"):
                valid += 1
            if result.get("saved"):
                saved += 1
                article = result.get("article") or {}
                if send_alert_if_needed(article):
                    telegram_count += 1
            else:
                failed += 1

    # Pastikan statistik klasifikasi berasal dari database setelah penyimpanan.
    articles = get_all_articles()
    counts = {"Negatif Kuat": 0, "Perlu Penanganan": 0, "Netral": 0, "Positif": 0}
    for article in articles:
        category = article.get("category") or "Netral"
        counts[category if category in counts else "Netral"] += 1

    duration = round(time.perf_counter() - started, 2)
    log = {
        "duration_seconds": duration,
        "candidate_count": len(candidates),
        "valid_count": valid,
        "saved_count": saved,
        "failed_count": failed,
        "reclassified_count": len(articles),
        "negative_count": counts["Negatif Kuat"],
        "handling_count": counts["Perlu Penanganan"],
        "neutral_count": counts["Netral"],
        "positive_count": counts["Positif"],
        "telegram_count": telegram_count,
        "status": "Selesai",
    }
    save_run_log(log)

    print("=" * 70)
    print("PATROLI SELESAI")
    print(f"Durasi            : {duration} detik")
    print(f"Kandidat           : {len(candidates)}")
    print(f"Artikel valid      : {valid}")
    print(f"Berhasil disimpan  : {saved}")
    print(f"Gagal              : {failed}")
    print(f"Database           : {len(articles)}")
    print(f"Negatif Kuat       : {counts['Negatif Kuat']}")
    print(f"Perlu Penanganan   : {counts['Perlu Penanganan']}")
    print(f"Netral             : {counts['Netral']}")
    print(f"Positif            : {counts['Positif']}")
    print(f"Telegram terkirim  : {telegram_count}")
    print("=" * 70)
    return log


def main() -> None:
    parser = argparse.ArgumentParser(description="Patroli Siber berita Kejari Deli Serdang")
    parser.add_argument("--once", action="store_true", help="jalankan satu kali")
    parser.add_argument("--reclassify", action="store_true", help="klasifikasi ulang seluruh artikel di Supabase")
    args = parser.parse_args()

    if args.reclassify:
        reclassify_all()
        return

    # Default juga satu kali agar aman dijalankan dari Task Scheduler/cron.
    run_once()


if __name__ == "__main__":
    main()
