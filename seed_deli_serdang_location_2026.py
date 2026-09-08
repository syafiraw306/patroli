"""
Seed curated Deli Serdang location articles published in 2026.

Purpose:
- Fetch article pages from a curated list of verified 2026 URLs.
- Extract title/date/content/images.
- Validate final publication year == 2026.
- Upsert into public.deli_serdang_location_articles.

Requires the project's database.py and Supabase environment variables.
"""
import re
from datetime import datetime
from typing import Optional, List, Dict
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from database import get_supabase

TABLE = "deli_serdang_location_articles"
TIMEOUT = 20

KEYWORDS = [
    "kabupaten deli serdang", "deli serdang", "kabupaten deliserdang", "deliserdang",
    "bangun purba", "batang kuis", "sibiru-biru", "deli tua", "galang",
    "gunung meriah", "hamparan perak", "kutalimbaru", "labuhan deli", "lubuk pakam",
    "namorambe", "pagar merbau", "pancur batu", "pantai labu", "patumbak",
    "percut sei tuan", "sibolangit", "stm hilir", "stm hulu", "sunggal", "tanjung morawa",
]

# Curated URLs found during the 2026 web research pass.
SEED_URLS = [
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
    return re.sub(r"\s+", " ", text or "").strip()


def parse_date(value: Optional[str]):
    if not value:
        return None
    try:
        return date_parser.parse(value)
    except Exception:
        return None


def extract_date(soup: BeautifulSoup, response_text: str):
    candidates = []
    for selector, attr in [
        ('meta[property="article:published_time"]', 'content'),
        ('meta[name="publishdate"]', 'content'),
        ('meta[name="date"]', 'content'),
        ('meta[itemprop="datePublished"]', 'content'),
        ('time[datetime]', 'datetime'),
    ]:
        node = soup.select_one(selector)
        if node:
            candidates.append(node.get(attr))

    # JSON-LD datePublished
    for script in soup.select('script[type="application/ld+json"]'):
        txt = script.get_text(" ", strip=True)
        m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', txt)
        if m:
            candidates.append(m.group(1))

    for value in candidates:
        dt = parse_date(value)
        if dt:
            return dt
    return None


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
    ]
    for selector in selectors:
        node = soup.select_one(selector)
        if node:
            text = clean(node.get_text(" ", strip=True))
            if len(text) >= 300:
                return text[:30000]

    paragraphs = [clean(p.get_text(" ", strip=True)) for p in soup.find_all("p")]
    paragraphs = [p for p in paragraphs if len(p) >= 30]
    return clean(" ".join(paragraphs))[:30000]


def extract_images(soup: BeautifulSoup, base_url: str) -> List[str]:
    urls = []
    for selector, attr in [
        ('meta[property="og:image"]', 'content'),
        ('meta[name="twitter:image"]', 'content'),
    ]:
        node = soup.select_one(selector)
        if node and node.get(attr):
            urls.append(urljoin(base_url, node.get(attr)))

    for img in soup.find_all("img"):
        for attr in ("src", "data-src", "data-original", "data-lazy-src"):
            value = img.get(attr)
            if value:
                urls.append(urljoin(base_url, value))
                break

    out = []
    seen = set()
    for u in urls:
        u = u.split("#")[0]
        if u and u not in seen and u.startswith(("http://", "https://")):
            seen.add(u)
            out.append(u)
        if len(out) >= 10:
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


def fetch(url: str):
    headers = {"User-Agent": "Mozilla/5.0 (compatible; DeliSerdangLocationResearch/1.0)"}
    r = requests.get(url, headers=headers, timeout=TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    title = clean((soup.find("h1").get_text(" ", strip=True) if soup.find("h1") else soup.title.get_text(" ", strip=True) if soup.title else ""))
    published = extract_date(soup, r.text)
    content = extract_content(soup)
    images = extract_images(soup, r.url)
    return r.url, title, published, content, images


def main():
    db = get_supabase()
    ok = 0
    skipped = 0
    failed = 0

    for url, seed_keyword in SEED_URLS:
        print("\n[SEED]", url)
        try:
            final_url, title, published, content, images = fetch(url)
            if not published or published.year != 2026:
                print("[SKIP YEAR]", published)
                skipped += 1
                continue
            if len(content) < 180:
                print("[SKIP CONTENT] too short", len(content))
                skipped += 1
                continue

            matches = find_matches(title, content)
            if not matches:
                matches = [seed_keyword]
            payload = {
                "title": title,
                "link": final_url,
                "content": content,
                "published_date": published.isoformat(),
                "source": final_url.split('/')[2],
                "publisher": final_url.split('/')[2],
                "matched_location_keywords": sorted(set(matches)),
                "search_query": seed_keyword,
                "discovery_type": "DELI_SERDANG_LOCATION_KEYWORD",
                "location_context_valid": context_valid(title, content, matches),
                "article_images": images,
            }
            db.table(TABLE).upsert(payload, on_conflict="link").execute()
            ok += 1
            print("[SAVED]", published.date(), title[:100], matches)
        except Exception as exc:
            failed += 1
            print("[FAILED]", type(exc).__name__, exc)

    print("\n========== SUMMARY ==========")
    print("saved:", ok)
    print("skipped:", skipped)
    print("failed:", failed)
    print("ONLY YEAR 2026")


if __name__ == "__main__":
    main()
