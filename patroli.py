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
    update_article_classification_by_id,
    update_article_classification,
)

load_dotenv()

TAHUN_TARGET = int(os.getenv("TAHUN_TARGET", "2026"))
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "10"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "15"))
MAX_ARTICLES_PER_FEED = int(os.getenv("MAX_ARTICLES_PER_FEED", "40"))
MIN_CONTENT_LENGTH = int(os.getenv("MIN_CONTENT_LENGTH", "180"))

NAMA_SATKER = os.getenv(
    "NAMA_SATKER",
    "Kejaksaan Negeri Deli Serdang",
).strip()

TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN",
    "",
).strip()

TELEGRAM_CHAT_ID = os.getenv(
    "TELEGRAM_CHAT_ID",
    "",
).strip()


TARGET_KEJARI_KEYWORDS = [
    "kejaksaan negeri deli serdang",
    "kejari deli serdang",
    "kejari deliserdang",
    "kejaksaan deli serdang",
    "kajari deli serdang",
    "kepala kejaksaan negeri deli serdang",

    "cabang kejaksaan negeri pancur batu",
    "cabjari pancur batu",
    "kacabjari pancur batu",

    "cabang kejaksaan negeri labuhan deli",
    "cabjari labuhan deli",
    "kacabjari labuhan deli",
]


SEARCH_TARGETS = [
    '"Kejaksaan Negeri Deli Serdang"',
    '"Kejari Deli Serdang"',
    '"Kajari Deli Serdang"',
    '"Kejari Deliserdang"',
    '"Kejaksaan Deli Serdang"',
    '"Cabjari Pancur Batu"',
    '"Cabjari Labuhan Deli"',
]


# Kata-kata ini sendiri TIDAK cukup untuk membuat berita negatif.
LEGAL_EVENT_TERMS = {
    "kasus",
    "korupsi",
    "narkotika",
    "narkoba",
    "tersangka",
    "terdakwa",
    "penyidikan",
    "penyelidikan",
    "penuntutan",
    "perkara",
    "pidana",
    "pengadilan",
    "sidang",
    "vonis",
    "dakwaan",
    "suap",
    "gratifikasi",
    "penggeledahan",
    "penyitaan",
    "penangkapan",
    "ditangkap",
    "menangkap",
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
    r"apel",
    r"upacara",
    r"rapat",
    r"fgd",
    r"focus group discussion",
    r"kunjungan",
    r"silaturahmi",
    r"konsolidasi",
    r"koordinasi",
    r"monitoring",
    r"evaluasi",
    r"penyuluhan hukum",
    r"penerangan hukum",
    r"sosialisasi",
    r"pelantikan",
    r"pengambilan sumpah",
    r"serah terima",
    r"launching",
    r"peresmian",
    r"penandatanganan",
    r"kerja sama",
    r"mo[uU]",
    r"ziarah",
    r"bakti sosial",
    r"gotong royong",
    r"kunjungan kerja",
    r"mengikuti zoom",
    r"menghadiri",
    r"hadiri",
    r"memimpin rapat",
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
    r"dilaporkan",
    r"diadukan",
    r"pengaduan",
    r"laporan masyarakat",
    r"diperiksa",
    r"dimintai keterangan",
    r"klarifikasi",
    r"dipanggil",
    r"protes",
    r"soroti",
    r"disorot",
    r"kritik",
    r"kritikan",
    r"dugaan",
    r"diduga",
    r"dituding",
    r"dituduh",
    r"polemik",
    r"sengketa",
    r"keberatan",
    r"somasi",
    r"demonstrasi",
    r"unjuk rasa",
    r"viral",
    r"kontroversi",
    r"permintaan transparansi",
]


NEGATION_PATTERNS = [
    r"tidak\s+(?:terbukti|benar|ada|melakukan|terlibat)",
    r"belum\s+(?:terbukti|ada|ditemukan)",
    r"bantah",
    r"membantah",
    r"dibantah",
    r"klarifikasi",
    r"hoaks",
    r"tidak benar",
    r"fitnah",
]


DANGER_TITLE_TERMS = {
    "ditangkap",
    "tersangka",
    "suap",
    "gratifikasi",
    "korupsi",
    "dicopot",
    "dilaporkan",
    "diadukan",
    "pungli",
    "pemerasan",
    "pelanggaran etik",
}


PRIORITY_BY_CATEGORY = {
    "Negatif Kuat": "Tinggi",
    "Perlu Penanganan": "Sedang",
    "Netral": "Rendah",
    "Positif": "Rendah",
}


SESSION = requests.Session()

SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/151 Safari/537.36"
        ),
        "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
    }
)


def normalize_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_url(url: Any) -> str:
    """
    Menormalisasi URL agar pengecekan duplikat lebih konsisten.
    """

    url = str(url or "").strip()

    if not url:
        return ""

    try:
        parsed = urllib.parse.urlsplit(url)

        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()

        if netloc.startswith("www."):
            netloc = netloc[4:]

        path = parsed.path.rstrip("/")

        query_pairs = urllib.parse.parse_qsl(
            parsed.query,
            keep_blank_values=True,
        )

        tracking_keys = {
            "utm_source",
            "utm_medium",
            "utm_campaign",
            "utm_term",
            "utm_content",
            "fbclid",
            "gclid",
            "ref",
        }

        clean_query = [
            (key, value)
            for key, value in query_pairs
            if key.lower() not in tracking_keys
        ]

        query = urllib.parse.urlencode(clean_query)

        normalized = urllib.parse.urlunsplit(
            (
                scheme,
                netloc,
                path,
                query,
                "",
            )
        )

        return normalized

    except Exception:
        return url.split("#")[0].strip()


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


def extract_published_date(
    entry: Any,
    fallback: Optional[datetime] = None,
) -> Optional[datetime]:

    for key in (
        "published",
        "updated",
        "created",
    ):
        dt = parse_date_safe(entry.get(key))

        if dt:
            return dt

    for key in (
        "published_parsed",
        "updated_parsed",
        "created_parsed",
    ):
        value = entry.get(key)

        if value:
            try:
                return datetime(
                    *value[:6],
                    tzinfo=timezone.utc,
                )
            except Exception:
                pass

    return fallback


def is_article_2026(
    dt: Optional[datetime],
) -> bool:
    return bool(
        dt and dt.year == TAHUN_TARGET
    )


def is_url_old(
    dt: Optional[datetime],
) -> bool:
    return not is_article_2026(dt)


def fetch_webpage_content(
    url: str,
) -> Tuple[str, str]:

    if not url:
        return "", ""

    try:
        response = SESSION.get(
            url,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )

        response.raise_for_status()

        final_url = normalize_url(
            response.url
        )

        return final_url, response.text

    except Exception as exc:
        print(
            f"[FETCH ERROR] "
            f"{url} -> "
            f"{type(exc).__name__}: {exc}"
        )

        return url, ""


def extract_article_text(
    raw_html: str,
) -> str:

    if not raw_html:
        return ""

    soup = BeautifulSoup(
        raw_html,
        "html.parser",
    )

    for tag in soup(
        [
            "script",
            "style",
            "noscript",
            "svg",
            "nav",
            "footer",
            "header",
            "form",
        ]
    ):
        tag.decompose()

    candidates = []

    selectors = [
        "article",
        "main",
        "[itemprop='articleBody']",
        ".article-body",
        ".post-content",
        ".entry-content",
    ]

    for selector in selectors:
        for node in soup.select(selector):
            txt = normalize_text(
                node.get_text(
                    " ",
                    strip=True,
                )
            )

            if len(txt) > 100:
                candidates.append(txt)

    if candidates:
        return max(
            candidates,
            key=len,
        )

    paragraphs = [
        normalize_text(
            paragraph.get_text(
                " ",
                strip=True,
            )
        )
        for paragraph in soup.find_all("p")
    ]

    paragraphs = [
        paragraph
        for paragraph in paragraphs
        if len(paragraph) >= 35
    ]

    return normalize_text(
        " ".join(paragraphs)
    )


def check_satker_relevance(
    title: str,
    content: str,
) -> bool:

    text = normalize_text(
        f"{title} {content}"
    ).lower()

    return any(
        keyword in text
        for keyword in TARGET_KEJARI_KEYWORDS
    )


def regex_hits(
    text: str,
    patterns: List[str],
) -> List[str]:

    hits = []

    for pattern in patterns:
        try:
            if re.search(
                pattern,
                text,
                flags=re.I,
            ):
                hits.append(pattern)

        except re.error:
            continue

    return hits


def has_negation_near(
    text: str,
    term: str,
    window: int = 90,
) -> bool:

    text = text.lower()

    for match in re.finditer(
        re.escape(term.lower()),
        text,
    ):

        before = text[
            max(
                0,
                match.start() - window,
            ):match.start()
        ]

        if any(
            re.search(
                pattern,
                before,
                re.I,
            )
            for pattern in NEGATION_PATTERNS
        ):
            return True

    return False


def calculate_positive_score(
    title: str,
    content: str,
) -> int:

    text = normalize_text(
        f"{title}. {content}"
    ).lower()

    score = 0

    score += 5 * len(
        regex_hits(
            text,
            POSITIVE_ACTION_PATTERNS,
        )
    )

    score += 3 * len(
        regex_hits(
            text,
            OFFICIAL_ACTIVITY_PATTERNS,
        )
    )

    if any(
        re.search(
            pattern,
            title.lower(),
        )
        for pattern in POSITIVE_ACTION_PATTERNS
    ):
        score += 5

    return min(score, 30)


def calculate_negative_score(
    title: str,
    content: str,
) -> int:

    text = normalize_text(
        f"{title}. {content}"
    ).lower()

    score = 0

    for pattern in NEGATIVE_STRONG_PATTERNS:
        if re.search(
            pattern,
            text,
            re.I,
        ):
            score += 10

    return min(score, 40)


def calculate_handling_score(
    title: str,
    content: str,
) -> int:

    text = normalize_text(
        f"{title}. {content}"
    ).lower()

    score = 0

    for pattern in HANDLING_PATTERNS:
        if re.search(
            pattern,
            text,
            re.I,
        ):
            score += 2

    return min(score, 20)


def classify_article(
    title: str,
    content: str,
) -> Dict[str, Any]:

    title = normalize_text(title)
    content = normalize_text(content)

    full = f"{title}. {content}".lower()

    negative_score = calculate_negative_score(
        title,
        content,
    )

    handling_score = calculate_handling_score(
        title,
        content,
    )

    positive_score = calculate_positive_score(
        title,
        content,
    )

    positive_hits = (
        regex_hits(
            full,
            POSITIVE_ACTION_PATTERNS,
        )
        + regex_hits(
            full,
            OFFICIAL_ACTIVITY_PATTERNS,
        )
    )

    negative_hits = regex_hits(
        full,
        NEGATIVE_STRONG_PATTERNS,
    )

    handling_hits = regex_hits(
        full,
        HANDLING_PATTERNS,
    )

    negated_danger = any(
        has_negation_near(
            full,
            term,
        )
        for term in DANGER_TITLE_TERMS
    )

    # Keberhasilan penegakan hukum / kegiatan resmi
    # diprioritaskan sebagai POSITIF.
    if positive_score >= 5 and negative_score == 0:
        category = "Positif"

    elif (
        negative_score >= 10
        and not negated_danger
    ):
        category = "Negatif Kuat"

    elif handling_score >= 2:
        category = "Perlu Penanganan"

    elif positive_score >= 3:
        category = "Positif"

    else:
        category = "Netral"

    # Bila konteks positif jelas lebih kuat daripada
    # indikasi negatif ringan, pertahankan POSITIF.
    if (
        category == "Negatif Kuat"
        and positive_score >= negative_score
        and negative_score < 20
    ):
        category = "Positif"

    # Bila ada bantahan kuat, turunkan dari negatif.
    if (
        negated_danger
        and category == "Negatif Kuat"
    ):
        category = (
            "Perlu Penanganan"
            if handling_score
            else "Netral"
        )

    priority = PRIORITY_BY_CATEGORY[
        category
    ]

    return {
        "category": category,
        "priority": priority,
        "negative_score": negative_score,
        "handling_score": handling_score,
        "positive_score": positive_score,
        "positive_hits": positive_hits[:12],
        "negative_hits": negative_hits[:12],
        "handling_hits": handling_hits[:12],
        "keywords": sorted(
            {
                word
                for word in LEGAL_EVENT_TERMS
                if re.search(
                    r"\b"
                    + re.escape(word)
                    + r"\b",
                    full,
                    re.I,
                )
            }
        ),
    }


def extract_feed_date(
    entry: Any,
) -> Optional[datetime]:

    """
    Mengambil tanggal publikasi dari
    entry Google News RSS.
    """

    for key in (
        "published_parsed",
        "updated_parsed",
        "created_parsed",
    ):

        value = entry.get(key)

        if value:
            try:
                return datetime(
                    value.tm_year,
                    value.tm_mon,
                    value.tm_mday,
                    value.tm_hour,
                    value.tm_min,
                    value.tm_sec,
                    tzinfo=timezone.utc,
                )
            except Exception:
                pass

    for key in (
        "published",
        "updated",
        "created",
    ):

        value = entry.get(key)

        if value:
            parsed = parse_date_safe(
                value
            )

            if parsed:
                return parsed

    return None


def parse_google_news_feed(
    query: str,
) -> List[Dict[str, Any]]:

    encoded = urllib.parse.quote_plus(
        query
    )

    url = (
        "https://news.google.com/rss/search?"
        f"q={encoded}"
        "&hl=id"
        "&gl=ID"
        "&ceid=ID:id"
    )

    try:
        response = SESSION.get(
            url,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )

        response.raise_for_status()

        feed = feedparser.parse(
            response.content
        )

        print(
            f"[RSS DEBUG] "
            f"query={query} | "
            f"status={response.status_code} | "
            f"bytes={len(response.content)} | "
            f"entries={len(feed.entries)} | "
            f"bozo={getattr(feed, 'bozo', False)}"
        )

        if getattr(
            feed,
            "bozo",
            False,
        ):

            bozo_exception = getattr(
                feed,
                "bozo_exception",
                None,
            )

            if bozo_exception:
                print(
                    f"[RSS BOZO ERROR] "
                    f"{query} -> "
                    f"{type(bozo_exception).__name__}: "
                    f"{bozo_exception}"
                )

        if not feed.entries:

            print(
                f"[RSS EMPTY] "
                f"Tidak ada entry untuk: {query}"
            )

            return []

        rows = []

        for entry in feed.entries[
            :MAX_ARTICLES_PER_FEED
        ]:

            link = normalize_url(
                entry.get("link")
            )

            if not link:
                continue

            published = extract_feed_date(
                entry
            )

            source_value = entry.get(
                "source"
            )

            if isinstance(
                source_value,
                dict,
            ):
                source = source_value.get(
                    "title",
                    "",
                )
            else:
                source = (
                    source_value
                    or ""
                )

            rows.append(
                {
                    "title": normalize_text(
                        entry.get("title")
                    ),
                    "link": link,
                    "published_date": (
                        published.isoformat()
                        if published
                        else None
                    ),
                    "source": normalize_text(
                        source
                    ),
                    "rss_description": normalize_text(
                        entry.get("summary")
                    ),
                }
            )

        print(
            f"[RSS OK] "
            f"{query} -> "
            f"{len(rows)} kandidat"
        )

        return rows

    except Exception as exc:

        print(
            f"[RSS ERROR] "
            f"{query} -> "
            f"{type(exc).__name__}: {exc}"
        )

        return []


def collect_candidates() -> List[Dict[str, Any]]:

    all_rows: Dict[
        str,
        Dict[str, Any],
    ] = {}

    for query in SEARCH_TARGETS:

        print(
            f"[RSS] Mencari: {query}"
        )

        for row in parse_google_news_feed(
            query
        ):

            link = normalize_url(
                row.get("link")
            )

            if link:
                all_rows.setdefault(
                    link,
                    row,
                )

    print(
        f"[PATROLI] Kandidat unik: "
        f"{len(all_rows)}"
    )

    return list(
        all_rows.values()
    )


def process_candidate(
    candidate: Dict[str, Any],
) -> Dict[str, Any]:

    title = normalize_text(
        candidate.get("title")
    )

    rss_link = normalize_url(
        candidate.get("link")
    )

    rss_date = parse_date_safe(
        candidate.get("published_date")
    )

    result = {
        "ok": False,
        "article": None,
        "reason": "",
    }

    if not rss_link:
        result["reason"] = "link kosong"
        return result

    if (
        rss_date
        and not is_article_2026(rss_date)
    ):
        result["reason"] = "bukan tahun target"
        return result

    final_url, raw_html = fetch_webpage_content(
        rss_link
    )

    final_url = normalize_url(
        final_url or rss_link
    )

    if not final_url:
        final_url = rss_link

    content = extract_article_text(
        raw_html
    )

    if len(content) < MIN_CONTENT_LENGTH:
        content = normalize_text(
            candidate.get(
                "rss_description"
            )
        )

    if len(content) < MIN_CONTENT_LENGTH:
        result["reason"] = (
            "konten terlalu pendek"
        )
        return result

    if not check_satker_relevance(
        title,
        content,
    ):
        result["reason"] = (
            "tidak relevan dengan satker"
        )
        return result

    published = (
        rss_date
        or datetime.now(timezone.utc)
    )

    if not is_article_2026(published):
        result["reason"] = (
            "tanggal artikel bukan 2026"
        )
        return result

    classification = classify_article(
        title,
        content,
    )

    article = {
        "title": title,
        "link": final_url,
        "content": content[:15000],
        "published_date": published.isoformat(),
        "source": (
            normalize_text(
                candidate.get("source")
            )
            or "Google News"
        ),
        "category": classification.get(
            "category",
            "Netral",
        ),
        "priority": classification.get(
            "priority",
            "Rendah",
        ),
        "negative_score": int(
            classification.get(
                "negative_score",
                0,
            )
        ),
        "handling_score": int(
            classification.get(
                "handling_score",
                0,
            )
        ),
        "positive_score": int(
            classification.get(
                "positive_score",
                0,
            )
        ),
        "detected_keywords": classification.get(
            "keywords",
            [],
        ),
        "satker_matches": classification.get(
            "satker_matches",
            [],
        ),
        "satker_match_location": classification.get(
            "satker_match_location",
            "",
        ),
        "strong_context": classification.get(
            "strong_context",
            [],
        ),
        "positive_context": classification.get(
            "positive_context",
            [],
        ),
        "handling_context": classification.get(
            "handling_context",
            [],
        ),
    }

    result["ok"] = True
    result["article"] = article

    return result


def telegram_enabled() -> bool:
    return bool(
        TELEGRAM_BOT_TOKEN
        and TELEGRAM_CHAT_ID
    )


def send_telegram_message(
    text: str,
) -> bool:

    if not telegram_enabled():
        return False

    url = (
        "https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:

        response = SESSION.post(
            url,
            data=payload,
            timeout=REQUEST_TIMEOUT,
        )

        response.raise_for_status()

        return True

    except Exception as exc:

        print(
            f"[TELEGRAM ERROR] "
            f"{type(exc).__name__}: {exc}"
        )

        return False


def telegram_text(
    article: Dict[str, Any],
) -> str:

    title = html.escape(
        normalize_text(
            article.get("title")
        )
    )

    category = html.escape(
        str(
            article.get(
                "category",
                "Netral",
            )
        )
    )

    priority = html.escape(
        str(
            article.get(
                "priority",
                "Rendah",
            )
        )
    )

    link = html.escape(
        normalize_url(
            article.get("link")
        )
    )

    return (
        f"<b>Patroli Siber "
        f"{TAHUN_TARGET}</b>\n"
        f"<b>Kategori:</b> {category}\n"
        f"<b>Prioritas:</b> {priority}\n"
        f"<b>Satker:</b> "
        f"{html.escape(NAMA_SATKER)}\n\n"
        f"<b>{title}</b>\n"
        f"{link}"
    )


def send_alert_if_needed(
    article: Dict[str, Any],
) -> bool:

    if article.get("category") not in {
        "Negatif Kuat",
        "Perlu Penanganan",
    }:
        return False

    return send_telegram_message(
        telegram_text(article)
    )


def reclassify_all() -> Dict[str, int]:

    print("=" * 70)
    print(
        "MEMULAI REKLASIFIKASI "
        "SELURUH DATABASE"
    )
    print("=" * 70)

    articles = get_all_articles()
    total = len(articles)

    print(
        f"[REKLASIFIKASI] "
        f"Total artikel: {total}"
    )

    counts = {
        "Negatif Kuat": 0,
        "Perlu Penanganan": 0,
        "Netral": 0,
        "Positif": 0,
    }

    updated = 0
    failed = 0

    for index, article in enumerate(
        articles,
        start=1,
    ):

        try:

            title = normalize_text(
                article.get("title")
            )

            content = normalize_text(
                article.get("content")
                or article.get("summary")
                or ""
            )

            if not title and not content:

                category = "Netral"
                priority = "Rendah"

            else:

                classification = classify_article(
                    title,
                    content,
                )

                category = classification.get(
                    "category",
                    "Netral",
                )

                priority = classification.get(
                    "priority",
                    "Rendah",
                )

            if category not in counts:
                category = "Netral"

            counts[category] += 1

            article_id = article.get("id")

            if article_id is None:

                failed += 1

                print(
                    f"[REKLASIFIKASI ERROR] "
                    f"{index}/{total} -> "
                    f"ID artikel tidak ditemukan"
                )

                continue

            result = (
                update_article_classification_by_id(
                    article_id,
                    category,
                    priority,
                )
            )

            if result is not None:

                updated += 1

                print(
                    f"[REKLASIFIKASI OK] "
                    f"{index}/{total} -> "
                    f"ID={article_id} | "
                    f"{category} | "
                    f"{priority}"
                )

            else:

                failed += 1

                print(
                    f"[REKLASIFIKASI ERROR] "
                    f"{index}/{total} -> "
                    f"gagal update "
                    f"ID={article_id}"
                )

        except Exception as exc:

            failed += 1

            print(
                f"[REKLASIFIKASI ERROR] "
                f"{index}/{total} -> "
                f"{type(exc).__name__}: {exc}"
            )

        if (
            index % 25 == 0
            or index == total
        ):
            print(
                f"[REKLASIFIKASI] "
                f"Progress {index}/{total}"
            )

    print()
    print("=" * 70)
    print("REKLASIFIKASI SELESAI")
    print("=" * 70)

    print(
        f"Negatif Kuat      : "
        f"{counts['Negatif Kuat']}"
    )

    print(
        f"Perlu Penanganan  : "
        f"{counts['Perlu Penanganan']}"
    )

    print(
        f"Netral            : "
        f"{counts['Netral']}"
    )

    print(
        f"Positif           : "
        f"{counts['Positif']}"
    )

    print(
        f"Total             : "
        f"{total}"
    )

    print(
        f"Berhasil update   : "
        f"{updated}"
    )

    print(
        f"Gagal update      : "
        f"{failed}"
    )

    print("=" * 70)

    return counts


def run_once() -> Dict[str, Any]:

    started = time.perf_counter()

    print("=" * 70)
    print("MEMULAI PATROLI SIBER")
    print("=" * 70)

    existing_articles = get_all_articles()

    existing_links = {
        normalize_url(
            article.get("link")
        )
        for article in existing_articles
        if normalize_url(
            article.get("link")
        )
    }

    print(
        f"[DATABASE] "
        f"Link sebelum run: "
        f"{len(existing_links)}"
    )

    candidates = collect_candidates()

    valid_articles = []
    failed = 0

    with ThreadPoolExecutor(
        max_workers=max(
            1,
            MAX_WORKERS,
        )
    ) as executor:

        futures = [
            executor.submit(
                process_candidate,
                candidate,
            )
            for candidate in candidates
        ]

        for future in as_completed(
            futures
        ):

            try:

                result = future.result()

                if result.get("ok"):

                    article = result.get(
                        "article"
                    )

                    if article:
                        valid_articles.append(
                            article
                        )

                else:

                    failed += 1

                    reason = result.get(
                        "reason",
                        "",
                    )

                    if reason:
                        print(
                            f"[FILTER] "
                            f"{reason}"
                        )

            except Exception as exc:

                failed += 1

                print(
                    f"[WORKER ERROR] "
                    f"{type(exc).__name__}: {exc}"
                )

    print(
        f"[PATROLI] "
        f"Artikel valid: "
        f"{len(valid_articles)}"
    )

    unique_articles = {}

    for article in valid_articles:

        link = normalize_url(
            article.get("link")
        )

        if not link:
            continue

        unique_articles.setdefault(
            link,
            article,
        )

    valid_articles = list(
        unique_articles.values()
    )

    saved_count = 0
    save_failed = 0
    new_articles = []

    for article in valid_articles:

        link = normalize_url(
            article.get("link")
        )

        if not link:
            continue

        print(
            f"[CHECK LINK] "
            f"{'LAMA' if link in existing_links else 'BARU'} | "
            f"{link}"
        )

        was_existing = (
            link in existing_links
        )

        try:

            saved = upsert_article(
                article
            )

            if saved is None:

                save_failed += 1

                print(
                    f"[SAVE ERROR] "
                    f"Gagal menyimpan: "
                    f"{link}"
                )

                continue

            saved_count += 1

            if not was_existing:

                new_articles.append(
                    article
                )

        except Exception as exc:

            save_failed += 1

            print(
                f"[SAVE ERROR] "
                f"{link}: "
                f"{type(exc).__name__}: {exc}"
            )

    print(
        f"[DATABASE] "
        f"Berhasil disimpan/update: "
        f"{saved_count}"
    )

    print(
        f"[DATABASE] "
        f"Gagal: "
        f"{save_failed}"
    )

    print(
        f"[DATABASE] "
        f"Artikel baru: "
        f"{len(new_articles)}"
    )

    telegram_count = 0

    if telegram_enabled():

        print(
            f"[TELEGRAM] "
            f"Kandidat artikel baru: "
            f"{len(new_articles)}"
        )

        for article in new_articles:

            if not send_alert_if_needed(
                article
            ):
                continue

            telegram_count += 1

            print(
                "[TELEGRAM] Terkirim: "
                f"{article.get('title', '')[:100]}"
            )

    else:

        print(
            "[TELEGRAM] Tidak aktif. "
            "Periksa TELEGRAM_BOT_TOKEN "
            "dan TELEGRAM_CHAT_ID."
        )

    counts = reclassify_all()

    final_articles = get_all_articles()

    duration = round(
        time.perf_counter() - started,
        2,
    )

    log = {
        "duration_seconds": duration,
        "candidate_count": len(candidates),
        "valid_count": len(valid_articles),
        "saved_count": saved_count,
        "failed_count": (
            failed + save_failed
        ),
        "reclassified_count": len(
            final_articles
        ),
        "negative_count": counts.get(
            "Negatif Kuat",
            0,
        ),
        "handling_count": counts.get(
            "Perlu Penanganan",
            0,
        ),
        "neutral_count": counts.get(
            "Netral",
            0,
        ),
        "positive_count": counts.get(
            "Positif",
            0,
        ),
        "telegram_count": telegram_count,
        "status": "Selesai",
    }

    save_run_log(log)

    print()
    print("=" * 70)
    print("PATROLI SELESAI")
    print("=" * 70)

    print(
        f"Durasi            : "
        f"{duration} detik"
    )

    print(
        f"Kandidat           : "
        f"{len(candidates)}"
    )

    print(
        f"Artikel valid      : "
        f"{len(valid_articles)}"
    )

    print(
        f"Berhasil disimpan  : "
        f"{saved_count}"
    )

    print(
        f"Gagal              : "
        f"{failed + save_failed}"
    )

    print(
        f"Artikel baru       : "
        f"{len(new_articles)}"
    )

    print(
        f"Database           : "
        f"{len(final_articles)}"
    )

    print(
        f"Negatif Kuat       : "
        f"{counts.get('Negatif Kuat', 0)}"
    )

    print(
        f"Perlu Penanganan   : "
        f"{counts.get('Perlu Penanganan', 0)}"
    )

    print(
        f"Netral             : "
        f"{counts.get('Netral', 0)}"
    )

    print(
        f"Positif            : "
        f"{counts.get('Positif', 0)}"
    )

    print(
        f"Telegram terkirim  : "
        f"{telegram_count}"
    )

    print("=" * 70)

    return log

def dedupe_dry_run() -> Dict[str, Any]:
    """
    Audit duplicate link tanpa mengubah database.

    Hasil:
    - dedupe_report.csv
    - dedupe_report.json

    Tidak ada INSERT, UPDATE, atau DELETE.
    """

    import csv
    import json

    print("=" * 70)
    print("DEDUPE DRY RUN")
    print("CEK DUPLICATE LINK TANPA MENGUBAH DATABASE")
    print("=" * 70)

    try:
        articles = get_all_articles()
    except Exception as exc:
        print(
            f"[DEDUPE ERROR] "
            f"Gagal mengambil database: "
            f"{type(exc).__name__}: {exc}"
        )

        return {
            "total_articles": 0,
            "unique_links": 0,
            "duplicate_groups": 0,
            "duplicate_articles": 0,
            "empty_links": 0,
            "error": True,
        }

    total_articles = len(articles)

    print(
        f"[DATABASE] Total artikel: "
        f"{total_articles}"
    )

    # ============================================================
    # KELOMPOKKAN BERDASARKAN NORMALIZED URL
    # ============================================================

    groups: Dict[str, List[Dict[str, Any]]] = {}
    empty_links = []

    for article in articles:

        raw_link = article.get("link")

        normalized_link = normalize_url(
            raw_link
        )

        if not normalized_link:
            empty_links.append(article)
            continue

        groups.setdefault(
            normalized_link,
            [],
        ).append(article)

    duplicate_groups = {
        link: rows
        for link, rows in groups.items()
        if len(rows) > 1
    }

    duplicate_articles = sum(
        len(rows) - 1
        for rows in duplicate_groups.values()
    )

    unique_links = len(groups)

    # ============================================================
    # SIAPKAN LAPORAN
    # ============================================================

    report_rows = []
    json_groups = []

    for group_number, (
        normalized_link,
        rows,
    ) in enumerate(
        duplicate_groups.items(),
        start=1,
    ):

        # --------------------------------------------------------
        # Tentukan record yang direkomendasikan untuk dipertahankan
        #
        # Prioritas:
        # 1. content paling panjang
        # 2. title tersedia
        # 3. published_date tersedia
        # 4. ID terkecil sebagai tie-breaker
        # --------------------------------------------------------

        def record_score(row):
            content = normalize_text(
                row.get("content")
                or row.get("summary")
                or ""
            )

            title = normalize_text(
                row.get("title")
            )

            published = normalize_text(
                row.get("published_date")
            )

            try:
                article_id = int(
                    row.get("id")
                )
            except Exception:
                article_id = 999999999

            return (
                len(content),
                bool(title),
                bool(published),
                -article_id,
            )

        rows_sorted = sorted(
            rows,
            key=record_score,
            reverse=True,
        )

        keep = rows_sorted[0]
        delete_candidates = rows_sorted[1:]

        keep_id = keep.get("id")

        keep_title = normalize_text(
            keep.get("title")
        )

        keep_content_length = len(
            normalize_text(
                keep.get("content")
                or keep.get("summary")
                or ""
            )
        )

        delete_ids = [
            row.get("id")
            for row in delete_candidates
        ]

        # --------------------------------------------------------
        # JSON
        # --------------------------------------------------------

        json_group = {
            "group": group_number,
            "normalized_link": normalized_link,
            "total_records": len(rows),
            "recommended_keep": {
                "id": keep_id,
                "title": keep_title,
                "content_length": keep_content_length,
                "published_date": keep.get(
                    "published_date"
                ),
                "link": keep.get("link"),
            },
            "delete_candidates": [],
        }

        # --------------------------------------------------------
        # CSV + JSON detail
        # --------------------------------------------------------

        for row_number, row in enumerate(
            rows_sorted,
            start=1,
        ):

            article_id = row.get("id")

            title = normalize_text(
                row.get("title")
            )

            content_length = len(
                normalize_text(
                    row.get("content")
                    or row.get("summary")
                    or ""
                )
            )

            is_keep = (
                article_id == keep_id
            )

            action = (
                "KEEP"
                if is_keep
                else "DELETE_CANDIDATE"
            )

            report_rows.append(
                {
                    "duplicate_group": group_number,
                    "normalized_link": normalized_link,
                    "record_count": len(rows),
                    "recommended_action": action,
                    "article_id": article_id,
                    "title": title,
                    "content_length": content_length,
                    "published_date": row.get(
                        "published_date"
                    ),
                    "category": row.get(
                        "category",
                        "",
                    ),
                    "priority": row.get(
                        "priority",
                        "",
                    ),
                    "original_link": row.get(
                        "link",
                        "",
                    ),
                }
            )

            if not is_keep:

                json_group[
                    "delete_candidates"
                ].append(
                    {
                        "id": article_id,
                        "title": title,
                        "content_length": content_length,
                        "published_date": row.get(
                            "published_date"
                        ),
                        "link": row.get(
                            "link"
                        ),
                    }
                )

        json_groups.append(
            json_group
        )

    # ============================================================
    # TULIS CSV
    # ============================================================

    csv_path = "dedupe_report.csv"

    csv_fields = [
        "duplicate_group",
        "normalized_link",
        "record_count",
        "recommended_action",
        "article_id",
        "title",
        "content_length",
        "published_date",
        "category",
        "priority",
        "original_link",
    ]

    try:

        with open(
            csv_path,
            "w",
            newline="",
            encoding="utf-8",
        ) as csv_file:

            writer = csv.DictWriter(
                csv_file,
                fieldnames=csv_fields,
            )

            writer.writeheader()

            writer.writerows(
                report_rows
            )

        print(
            f"[REPORT] CSV berhasil dibuat: "
            f"{csv_path}"
        )

    except Exception as exc:

        print(
            f"[REPORT ERROR] CSV: "
            f"{type(exc).__name__}: {exc}"
        )

    # ============================================================
    # TULIS JSON
    # ============================================================

    json_path = "dedupe_report.json"

    json_report = {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "tahun_target": TAHUN_TARGET,
        "nama_satker": NAMA_SATKER,
        "total_articles": total_articles,
        "unique_links": unique_links,
        "duplicate_groups": len(
            duplicate_groups
        ),
        "duplicate_articles": duplicate_articles,
        "empty_links": len(empty_links),
        "groups": json_groups,
    }

    try:

        with open(
            json_path,
            "w",
            encoding="utf-8",
        ) as json_file:

            json.dump(
                json_report,
                json_file,
                ensure_ascii=False,
                indent=2,
                default=str,
            )

        print(
            f"[REPORT] JSON berhasil dibuat: "
            f"{json_path}"
        )

    except Exception as exc:

        print(
            f"[REPORT ERROR] JSON: "
            f"{type(exc).__name__}: {exc}"
        )

    # ============================================================
    # TAMPILKAN RINGKASAN
    # ============================================================

    print()
    print("=" * 70)
    print("HASIL DEDUPE DRY RUN")
    print("=" * 70)

    print(
        f"Total artikel       : "
        f"{total_articles}"
    )

    print(
        f"Link unik           : "
        f"{unique_links}"
    )

    print(
        f"Kelompok duplicate  : "
        f"{len(duplicate_groups)}"
    )

    print(
        f"Artikel duplicate   : "
        f"{duplicate_articles}"
    )

    print(
        f"Link kosong         : "
        f"{len(empty_links)}"
    )

    print("=" * 70)

    # ============================================================
    # TAMPILKAN REKOMENDASI KEEP / DELETE CANDIDATE
    # ============================================================

    if duplicate_groups:

        print()
        print("REKOMENDASI DUPLICATE")
        print("=" * 70)

        for group in json_groups:

            print()
            print(
                f"DUPLICATE #{group['group']}"
            )

            print(
                f"Jumlah record : "
                f"{group['total_records']}"
            )

            keep = group[
                "recommended_keep"
            ]

            print(
                f"PERTAHANKAN  : "
                f"ID={keep['id']} | "
                f"{keep['title'][:100]}"
            )

            print(
                f"Content      : "
                f"{keep['content_length']} karakter"
            )

            candidates = group[
                "delete_candidates"
            ]

            if candidates:

                print(
                    "HAPUS KANDIDAT:"
                )

                for candidate in candidates:

                    print(
                        f"  - ID={candidate['id']} | "
                        f"{candidate['title'][:100]}"
                    )

    else:

        print()
        print(
            "[DEDUPE] Tidak ditemukan "
            "duplicate link."
        )

    # ============================================================
    # LINK KOSONG
    # ============================================================

    if empty_links:

        print()
        print("=" * 70)
        print("ARTIKEL DENGAN LINK KOSONG")
        print("=" * 70)

        for article in empty_links:

            print(
                f"ID={article.get('id', '-')}"
                f" | "
                f"{normalize_text(article.get('title'))[:100]}"
            )

    print()
    print("=" * 70)
    print("DEDUPE DRY RUN SELESAI")
    print("TIDAK ADA DATA YANG DIUBAH")
    print("=" * 70)

    return {
        "total_articles": total_articles,
        "unique_links": unique_links,
        "duplicate_groups": len(
            duplicate_groups
        ),
        "duplicate_articles": duplicate_articles,
        "empty_links": len(empty_links),
        "error": False,
        "csv_report": csv_path,
        "json_report": json_path,
    }

def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Patroli Siber berita "
            "Kejari Deli Serdang"
        )
    )

    parser.add_argument(
        "--once",
        action="store_true",
        help="jalankan satu kali",
    )

    parser.add_argument(
        "--reclassify",
        action="store_true",
        help=(
            "klasifikasi ulang seluruh "
            "artikel di Supabase"
        ),
    )

    parser.add_argument(
        "--dedupe-dry-run",
        action="store_true",
        help=(
            "cek duplicate link tanpa "
            "mengubah database"
        ),
    )

    args = parser.parse_args()

    if args.dedupe_dry_run:
        dedupe_dry_run()
        return

    if args.reclassify:
        reclassify_all()
        return

    # Default juga satu kali agar aman
    # dijalankan dari Task Scheduler/cron.
    run_once()
    

if __name__ == "__main__":
    main()

