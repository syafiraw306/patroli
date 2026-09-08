"""
Seed + repair curated Deli Serdang location articles published in 2026.

Purpose:
- Fetch curated article pages.
- Extract title/date/content/images.
- Protect verified publication dates from bad CMS/meta dates.
- Enforce STRICTLY publication year 2026.
- Use a conservative Google News RSS fallback when the publisher returns 403/5xx.
- Upsert into public.deli_serdang_location_articles.
- Preserve existing full content/images when a fallback only returns an excerpt.

Requires the project's database.py and Supabase environment variables.
The GitHub Actions workflow should pass SUPABASE_SERVICE_ROLE_KEY as SUPABASE_KEY.
"""

import html as html_lib
import json
import re
import time
from datetime import datetime, timezone
from typing import Optional, List, Dict, Tuple
from urllib.parse import quote_plus, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from database import get_supabase

TABLE = "deli_serdang_location_articles"
TIMEOUT = 25
MIN_CONTENT_LENGTH = 180
MAX_CONTENT_LENGTH = 30000
MAX_IMAGES = 10

KEYWORDS = [
    "kabupaten deli serdang", "deli serdang", "kabupaten deliserdang", "deliserdang",
    "bangun purba", "batang kuis", "sibiru-biru", "deli tua", "galang",
    "gunung meriah", "hamparan perak", "kutalimbaru", "labuhan deli", "lubuk pakam",
    "namorambe", "pagar merbau", "pancur batu", "pantai labu", "patumbak",
    "percut sei tuan", "sibolangit", "stm hilir", "stm hulu", "sunggal", "tanjung morawa",
]

# Dates verified during the research pass. These override unreliable CMS/meta dates.
# This is deliberately keyed by URL so a rerun cannot turn an article into the run date.
VERIFIED_DATES: Dict[str, str] = {
    "https://sumut.antaranews.com/berita/663445/warga-deli-serdang-divonis-dua-tahun-penjara-karena-perdagangkan-13-kg-sisik-tenggiling": "2026-06-10",
    "https://sumut.antaranews.com/berita/666017/jpu-tuntut-mati-dua-terdakwa-pembunuhan-pelajar-smp-jawab-keraguan-atas-penanganan-perkara": "2026-07-16",
    "https://sumut.antaranews.com/berita/662139/polresta-deli-serdang-sita-38-paket-ganja-dan-40-batang-tanaman-satu-pelaku-ditangkap": "2026-05-20",
    "https://sumut.antaranews.com/berita/659268/pengurus-nazir-masjid-di-namorambe-minta-kepastian-hukum-atas-laporan-dugaan-pencemaran-nama-baik": "2026-04-14",
    "https://sinata.id/kontrak-perbaikan-jalan-darsono-hamparan-perak-masih-berjalan": "2026-08-23",
    "https://radarmedan.com/delapan-lokasi-tambang-ilegal-di-galang-deli-serdang-resmi-ditutup": "2026-06-26",
    "https://sumut.antaranews.com/berita/665240/kades-kolam-lepas-turangga-ceta-fc-u-10-wakili-sumut-di-grassroots-piala-presiden-2026": "2026-07-04",
    "https://rri.co.id/medan/regional/2563185/kwarcab-deli-serdang-raih-predikat-kontingen-terbaik-i-jamdasu-xi-sumut": "2026-07-13",
    "https://utamanews.com/sosial-budaya/Selesai-Direnovasi--Kini-TPI-Pantai-Labu-Lebih-Modern-dan-Instagramable": "2026-01-13",
    "https://mistar.id/news/sumut/20-ranperda-deli-serdang-2026-disahkan-pemekaran-percut-sei-tuan-dan-sunggal-jadi-sorotan": "2026-04-23",
    "https://www.detik.com/sumut/berita/d-8476163/pasar-deli-tua-titik-temu-stasiun-yang-jadi-pusat-ekonomi-warga": "2026-05-06",
    "https://www.harianbersama.com/2026/06/17/bahh-rsud-bangun-purba-ditambah-bangunan-lama-tidak-terurus/": "2026-06-17",
    "https://tribrata.tv/11/08/sumatera-utara/178259/waduh-agunan-shm-diduga-hilang-di-bri/": "2026-08-11",
    "https://mistar.id/news/hukum-peristiwa/kaca-depan-dump-truk-dilempar-otk-pemilik-lapor-ke-polsek-talun-kenas": "2026-08-11",
    "https://rri.co.id/medan/berita-lain/2632822/pemkab-pertemukan-pt-indofarm-dan-petani-ikan-sengketa-berakhir-damai": "2026-08-07",
    "https://analisasibernews.com/2026/08/20/aktivitas-galian-c-di-tandukan-raga-disorot-warga-minta-aparat-dan-esdm-lakukan-verifikasi/": "2026-08-20",
    "https://gerindrasumut.id/pasang-pembatas-akses-truk-ke-sungai-ular-dibatasi-cegah-abrasi/": "2026-08-29",
}

SEED_URLS: List[Tuple[str, str]] = [
    ("https://sumut.antaranews.com/berita/663445/warga-deli-serdang-divonis-dua-tahun-penjara-karena-perdagangkan-13-kg-sisik-tenggiling", "sibiru-biru"),
    ("https://sumut.antaranews.com/berita/666017/jpu-tuntut-mati-dua-terdakwa-pembunuhan-pelajar-smp-jawab-keraguan-atas-penanganan-perkara", "lubuk pakam"),
    ("https://sumut.antaranews.com/berita/662139/polresta-deli-serdang-sita-38-paket-ganja-dan-40-batang-tanaman-satu-pelaku-ditangkap", "tanjung morawa"),
    ("https://sumut.antaranews.com/berita/659268/pengurus-nazir-masjid-di-namorambe-minta-kepastian-hukum-atas-laporan-dugaan-pencemaran-nama-baik", "namorambe"),
    ("https://sinata.id/kontrak-perbaikan-jalan-darsono-hamparan-perak-masih-berjalan", "hamparan perak"),
    ("https://radarmedan.com/delapan-lokasi-tambang-ilegal-di-galang-deli-serdang-resmi-ditutup", "galang"),
    ("https://sumut.antaranews.com/berita/665240/kades-kolam-lepas-turangga-ceta-fc-u-10-wakili-sumut-di-grassroots-piala-presiden-2026", "percut sei tuan"),
    ("https://rri.co.id/medan/regional/2563185/kwarcab-deli-serdang-raih-predikat-kontingen-terbaik-i-jamdasu-xi-sumut", "sibolangit"),
    ("https://utamanews.com/sosial-budaya/Selesai-Direnovasi--Kini-TPI-Pantai-Labu-Lebih-Modern-dan-Instagramable", "pantai labu"),
    ("https://mistar.id/news/sumut/20-ranperda-deli-serdang-2026-disahkan-pemekaran-percut-sei-tuan-dan-sunggal-jadi-sorotan", "sunggal"),
    ("https://www.detik.com/sumut/berita/d-8476163/pasar-deli-tua-titik-temu-stasiun-yang-jadi-pusat-ekonomi-warga", "deli tua"),
    ("https://www.harianbersama.com/2026/06/17/bahh-rsud-bangun-purba-ditambah-bangunan-lama-tidak-terurus/", "bangun purba"),
    ("https://tribrata.tv/11/08/sumatera-utara/178259/waduh-agunan-shm-diduga-hilang-di-bri/", "pagar merbau"),
    ("https://mistar.id/news/hukum-peristiwa/kaca-depan-dump-truk-dilempar-otk-pemilik-lapor-ke-polsek-talun-kenas", "stm hilir"),
    ("https://rri.co.id/medan/berita-lain/2632822/pemkab-pertemukan-pt-indofarm-dan-petani-ikan-sengketa-berakhir-damai", "patumbak"),
    ("https://analisasibernews.com/2026/08/20/aktivitas-galian-c-di-tandukan-raga-disorot-warga-minta-aparat-dan-esdm-lakukan-verifikasi/", "stm hilir"),
    ("https://gerindrasumut.id/pasang-pembatas-akses-truk-ke-sungai-ular-dibatasi-cegah-abrasi/", "pagar merbau"),
]


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(text or "")).strip()


def build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        status=2,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/128 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.7,en;q=0.6",
        "Cache-Control": "no-cache",
    })
    return session


def parse_date(value: Optional[str]):
    if not value:
        return None
    try:
        dt = date_parser.parse(value)
        if dt.year < 2000 or dt.year > 2100:
            return None
        return dt
    except Exception:
        return None


def extract_date_candidates(soup: BeautifulSoup) -> List[Tuple[str, datetime]]:
    found: List[Tuple[str, datetime]] = []

    selectors = [
        ('meta[property="article:published_time"]', 'content', 'meta:article:published_time'),
        ('meta[name="publishdate"]', 'content', 'meta:publishdate'),
        ('meta[name="date"]', 'content', 'meta:date'),
        ('meta[itemprop="datePublished"]', 'content', 'meta:datePublished'),
        ('meta[property="datePublished"]', 'content', 'meta:property:datePublished'),
        ('time[datetime]', 'datetime', 'time:datetime'),
    ]
    for selector, attr, source in selectors:
        for node in soup.select(selector):
            dt = parse_date(node.get(attr))
            if dt:
                found.append((source, dt))

    def walk_json(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if str(key).lower() in {"datepublished", "datecreated"}:
                    dt = parse_date(str(item))
                    if dt:
                        found.append((f"jsonld:{key}", dt))
                walk_json(item)
        elif isinstance(value, list):
            for item in value:
                walk_json(item)

    for script in soup.select('script[type="application/ld+json"]'):
        raw = script.get_text(" ", strip=True)
        if not raw:
            continue
        try:
            walk_json(json.loads(raw))
        except Exception:
            for key in ("datePublished", "dateCreated"):
                for match in re.findall(rf'"{key}"\s*:\s*"([^"]+)"', raw, flags=re.I):
                    dt = parse_date(match)
                    if dt:
                        found.append((f"jsonld:{key}", dt))

    # De-duplicate while preserving order.
    out = []
    seen = set()
    for source, dt in found:
        key = (source, dt.isoformat())
        if key not in seen:
            seen.add(key)
            out.append((source, dt))
    return out


def extract_date(soup: BeautifulSoup) -> Optional[datetime]:
    candidates = extract_date_candidates(soup)
    if not candidates:
        return None

    # Prefer publication-specific metadata over generic date/time fields.
    priority = {
        "meta:article:published_time": 0,
        "meta:datePublished": 1,
        "meta:property:datePublished": 1,
        "jsonld:datePublished": 2,
        "meta:publishdate": 3,
        "meta:date": 4,
        "time:datetime": 5,
    }
    candidates.sort(key=lambda item: (priority.get(item[0], 9), item[1]))
    return candidates[0][1]


def extract_title(soup: BeautifulSoup) -> str:
    for selector in ("h1", 'meta[property="og:title"]', 'meta[name="twitter:title"]'):
        node = soup.select_one(selector)
        if not node:
            continue
        if node.name == "meta":
            value = node.get("content")
        else:
            value = node.get_text(" ", strip=True)
        value = clean(value)
        if value:
            return value
    return clean(soup.title.get_text(" ", strip=True) if soup.title else "")


def extract_content(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "form"]):
        tag.decompose()

    selectors = [
        "article",
        "main",
        ".article-content",
        ".post-content",
        ".entry-content",
        ".content-detail",
        ".detail-content",
        ".news-content",
        ".article__content",
        ".post__content",
        ".detail-article",
    ]
    best = ""
    for selector in selectors:
        node = soup.select_one(selector)
        if node:
            text = clean(node.get_text(" ", strip=True))
            if len(text) > len(best):
                best = text
            if len(text) >= 300:
                return text[:MAX_CONTENT_LENGTH]

    paragraphs = [clean(p.get_text(" ", strip=True)) for p in soup.find_all("p")]
    paragraphs = [p for p in paragraphs if len(p) >= 30]
    para_text = clean(" ".join(paragraphs))
    if len(para_text) > len(best):
        best = para_text
    return best[:MAX_CONTENT_LENGTH]


def extract_images(soup: BeautifulSoup, base_url: str) -> List[str]:
    urls: List[str] = []
    for selector, attr in [
        ('meta[property="og:image"]', "content"),
        ('meta[name="twitter:image"]', "content"),
    ]:
        for node in soup.select(selector):
            value = node.get(attr)
            if value:
                urls.append(urljoin(base_url, value))

    for img in soup.find_all("img"):
        for attr in ("src", "data-src", "data-original", "data-lazy-src", "data-lazy"):
            value = img.get(attr)
            if value:
                urls.append(urljoin(base_url, value))
                break

    out: List[str] = []
    seen = set()
    for url in urls:
        url = url.split("#")[0].strip()
        if url.startswith(("http://", "https://")) and url not in seen:
            seen.add(url)
            out.append(url)
        if len(out) >= MAX_IMAGES:
            break
    return out


def find_matches(title: str, content: str) -> List[str]:
    text = f"{title} ; {content}".lower()
    matches = []
    for kw in KEYWORDS:
        if re.search(r"(?<!\w)" + re.escape(kw) + r"(?!\w)", text, re.I):
            matches.append(kw)
    return sorted(set(matches))


def context_valid(title: str, content: str, matches: List[str]) -> bool:
    text = clean(f"{title} ; {content}")
    if re.search(r"\b(?:deli serdang|deliserdang)\b", text, re.I):
        return True
    for location in matches:
        loc = re.escape(location)
        if re.search(rf"\bkecamatan\s+{loc}\b", text, re.I):
            return True
        if re.search(rf"\b{loc}\s*,\s*(?:kabupaten|kab\.?|pemkab)\s+deli\s+serdang\b", text, re.I):
            return True
        if re.search(rf"\b{loc}\s+(?:kabupaten|kab\.?|pemkab)\s+deli\s+serdang\b", text, re.I):
            return True
    return False


def parse_verified_date(url: str) -> Optional[datetime]:
    value = VERIFIED_DATES.get(url)
    if not value:
        return None
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def google_news_rss_query(title: str, domain: str) -> str:
    # Exact-ish title plus domain helps avoid an unrelated same-title story.
    q = f'"{title}" {domain}'
    return "https://news.google.com/rss/search?q=" + quote_plus(q) + "&hl=id&gl=ID&ceid=ID:id"


def fetch_google_news_fallback(
    session: requests.Session,
    original_url: str,
    expected_title: str,
    seed_keyword: str,
) -> Optional[Dict]:
    domain = urlparse(original_url).netloc.lower().replace("www.", "")
    queries = [
        google_news_rss_query(expected_title, domain),
        "https://news.google.com/rss/search?q=" + quote_plus(f'"{seed_keyword}" "Deli Serdang" {domain}') + "&hl=id&gl=ID&ceid=ID:id",
    ]

    for rss_url in queries:
        try:
            response = session.get(rss_url, timeout=TIMEOUT)
            if response.status_code != 200:
                continue
            soup = BeautifulSoup(response.text, "xml")
            items = soup.find_all("item")
            for item in items[:15]:
                title = clean(item.find("title").get_text(" ", strip=True) if item.find("title") else "")
                description = clean(item.find("description").get_text(" ", strip=True) if item.find("description") else "")
                pub = parse_date(item.find("pubDate").get_text(" ", strip=True) if item.find("pubDate") else "")
                link = clean(item.find("link").get_text(" ", strip=True) if item.find("link") else "")

                # Prefer an item whose title is materially similar to the seed title.
                title_tokens = set(re.findall(r"[a-z0-9]+", expected_title.lower()))
                item_tokens = set(re.findall(r"[a-z0-9]+", title.lower()))
                similarity = len(title_tokens & item_tokens) / max(1, len(title_tokens))
                if similarity < 0.45 and domain not in title.lower() and seed_keyword.lower() not in title.lower():
                    continue

                if not description:
                    continue

                return {
                    "title": expected_title or title,
                    "published": pub,
                    "content": description[:MAX_CONTENT_LENGTH],
                    "images": [],
                    "fallback_url": link,
                    "source": domain,
                    "content_source": "google_news_rss_excerpt",
                }
        except Exception as exc:
            print(f"[RSS FALLBACK WARNING] {domain} -> {type(exc).__name__}: {exc}")

    return None


def fetch_direct(session: requests.Session, url: str) -> Dict:
    last_error = None
    header_variants = [
        {},
        {"Referer": "https://www.google.com/", "Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "navigate"},
    ]
    for extra_headers in header_variants:
        try:
            response = session.get(url, headers=extra_headers, timeout=TIMEOUT, allow_redirects=True)
            if response.status_code >= 400:
                last_error = requests.HTTPError(
                    f"HTTP {response.status_code} for {response.url}",
                    response=response,
                )
                if response.status_code in (403, 406, 451):
                    continue
                response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            return {
                "final_url": response.url,
                "title": extract_title(soup),
                "published": extract_date(soup),
                "content": extract_content(soup),
                "images": extract_images(soup, response.url),
                "content_source": "publisher_html",
            }
        except Exception as exc:
            last_error = exc
            time.sleep(0.5)
    raise last_error if last_error else RuntimeError("fetch failed")


def get_existing(db, link: str) -> Optional[Dict]:
    try:
        result = db.table(TABLE).select(
            "id,link,title,content,published_date,article_images,matched_location_keywords,location_context_valid"
        ).eq("link", link).limit(1).execute()
        rows = getattr(result, "data", None) or []
        return rows[0] if rows else None
    except Exception as exc:
        print(f"[DB READ WARNING] {link} -> {type(exc).__name__}: {exc}")
        return None


def build_payload(
    url: str,
    seed_keyword: str,
    data: Dict,
    existing: Optional[Dict],
) -> Tuple[Optional[Dict], str]:
    title = clean(data.get("title", ""))
    content = clean(data.get("content", ""))
    images = data.get("images") or []
    published = data.get("published")
    verified = parse_verified_date(url)

    # Verified dates take precedence over publisher metadata for curated URLs.
    if verified:
        published = verified
        date_source = "verified_seed_date"
    else:
        date_source = "publisher_metadata"

    # Preserve an already-known full article if a fallback only produced an excerpt.
    if existing:
        old_content = clean(existing.get("content") or "")
        if len(old_content) > len(content) and data.get("content_source") == "google_news_rss_excerpt":
            content = old_content
        if not images and existing.get("article_images"):
            images = existing.get("article_images") or []
        if not title:
            title = clean(existing.get("title") or "")

    if not published or published.year != 2026:
        return None, f"year_invalid:{published}"
    if len(content) < MIN_CONTENT_LENGTH:
        return None, f"content_too_short:{len(content)}"

    matches = find_matches(title, content)
    if not matches:
        matches = [seed_keyword]

    if not context_valid(title, content, matches):
        # The seed itself is curated for a Deli Serdang location. Do not invent context,
        # but keep the record reviewable and make the seed keyword explicit.
        matches = sorted(set(matches + [seed_keyword]))

    payload = {
        "title": title,
        "link": url,
        "content": content[:MAX_CONTENT_LENGTH],
        "published_date": published.isoformat(),
        "source": urlparse(url).netloc.lower().replace("www.", ""),
        "publisher": urlparse(url).netloc.lower().replace("www.", ""),
        "matched_location_keywords": sorted(set(matches)),
        "search_query": seed_keyword,
        "discovery_type": (
            "DELI_SERDANG_LOCATION_KEYWORD_RSS_FALLBACK"
            if data.get("content_source") == "google_news_rss_excerpt"
            else "DELI_SERDANG_LOCATION_KEYWORD"
        ),
        "location_context_valid": context_valid(title, content, matches),
    }

    # Do not overwrite good image data with [] on a fallback.
    if images:
        payload["article_images"] = images[:MAX_IMAGES]

    return payload, date_source


def main() -> int:
    db = get_supabase()
    session = build_session()

    ok = 0
    skipped = 0
    failed = 0
    fallback_saved = 0

    print("[SEED] STRICT YEAR = 2026")
    print(f"[SEED] Curated URLs = {len(SEED_URLS)}")

    for url, seed_keyword in SEED_URLS:
        print("\n[SEED]", url)
        existing = None
        try:
            existing = get_existing(db, url)
            data = fetch_direct(session, url)
            data["title"] = data.get("title") or (existing or {}).get("title", "")

            payload, reason = build_payload(url, seed_keyword, data, existing)
            if payload is None:
                # If direct page is readable but date/content is bad, still try RSS fallback.
                fallback = fetch_google_news_fallback(
                    session,
                    url,
                    data.get("title") or (existing or {}).get("title", ""),
                    seed_keyword,
                )
                if fallback:
                    payload, reason = build_payload(url, seed_keyword, fallback, existing)
                    if payload:
                        fallback_saved += 1

            if payload is None:
                print("[SKIP]", reason)
                skipped += 1
                continue

            db.table(TABLE).upsert(payload, on_conflict="link").execute()
            ok += 1
            print(
                "[SAVED]",
                payload["published_date"][:10],
                payload["title"][:100],
                payload["matched_location_keywords"],
                "|", payload["discovery_type"],
            )

        except Exception as exc:
            # 403/5xx: use conservative RSS fallback instead of bypassing the publisher.
            try:
                expected_title = (existing or {}).get("title", "")
                fallback = fetch_google_news_fallback(session, url, expected_title, seed_keyword)
                if fallback:
                    payload, reason = build_payload(url, seed_keyword, fallback, existing)
                    if payload:
                        db.table(TABLE).upsert(payload, on_conflict="link").execute()
                        ok += 1
                        fallback_saved += 1
                        print(
                            "[SAVED:FALLBACK]",
                            payload["published_date"][:10],
                            payload["title"][:100],
                            payload["matched_location_keywords"],
                        )
                        continue
            except Exception as fallback_exc:
                print(
                    "[FALLBACK FAILED]",
                    type(fallback_exc).__name__,
                    fallback_exc,
                )

            failed += 1
            print("[FAILED]", type(exc).__name__, exc)

    print("\n========== SUMMARY ==========")
    print("saved:", ok)
    print("fallback_saved:", fallback_saved)
    print("skipped:", skipped)
    print("failed:", failed)
    print("ONLY YEAR 2026")

    # A non-zero exit is reserved for actual failures. Skips are reported but do not
    # make the workflow red because a publisher can legitimately block a seed URL.
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
