import json
import os
import re
from html import unescape
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None

DEFAULT_MODEL = os.getenv("LAPINSUS_AI_MODEL", "gpt-5.6-luna")
AI_VERSION = "LAPINSUS_DELI_SERDANG_AI_V1_6"
REQUEST_TIMEOUT = int(os.getenv("LAPINSUS_SOURCE_TIMEOUT", "15"))
IMAGE_HASH_TIMEOUT = int(os.getenv("LAPINSUS_IMAGE_HASH_TIMEOUT", "8"))
IMAGE_MAX = int(os.getenv("LAPINSUS_IMAGE_MAX", "6"))

SYSTEM_PROMPT = r"""
Anda adalah AI penyusun DRAFT LAPORAN INFORMASI KHUSUS (LAPINSUS)
Kejaksaan Negeri Deli Serdang.

Anda BUKAN sumber fakta. Satu-satunya sumber fakta adalah ARTIKEL SUMBER
yang diberikan bersama nomor kalimat sumber.

TUJUAN:
Menyusun draft LAPINSUS dengan bahasa Indonesia formal, objektif,
ringkas, dan bergaya laporan kedinasan seperti contoh LAPINSUS.

ATURAN WAJIB:
1. Jangan mengarang fakta, angka, nama orang, nama instansi, tanggal,
   lokasi, jumlah, status pekerjaan, jadwal, atau kejadian.
2. Setiap fakta wajib memiliki evidence_sentence_ids yang menunjuk ke
   kalimat artikel yang benar-benar mendukungnya.
3. Jangan mengubah dugaan menjadi fakta. Pertahankan kata/nuansa seperti
   "diduga", "menurut", "disebut", atau "berdasarkan pemberitaan" bila ada.
4. Jika sebuah informasi tidak terdapat dalam artikel, jangan memasukkannya.
5. Bagian I berisi fakta/informasi yang diberitakan, bukan opini AI.
6. Bagian III hanya boleh berisi perkembangan/perkiraan yang mempunyai
   dasar eksplisit dalam artikel: rencana, target, proses yang sedang
   berlangsung, tender, jadwal, tahapan berikutnya, konsekuensi yang
   dinyatakan sumber, atau inferensi terbatas yang jelas ditandai sebagai
   perkiraan.
7. Dilarang membuat prediksi baru seolah-olah merupakan fakta.
8. Untuk trend yang tidak tersedia, tuliskan keterbatasan sumber secara
   jujur. Jangan membuat trend generik yang tidak terkait artikel.
9. Kalimat fakta dan trend idealnya dimulai dengan "Bahwa".
10. Gunakan bahasa kedinasan Indonesia. Hindari bahasa promosi, clickbait,
    opini pribadi, emoji, markdown, dan komentar tentang AI.
11. Saran/tindak harus berupa langkah verifikasi/monitoring yang wajar dan
    tidak mengklaim bahwa tindakan tersebut sudah dilakukan.
12. Jangan menyebut sumber lain di luar artikel.
13. Jangan menyalin elemen UI situs berita seperti "Tautan telah disalin",
    "Baca juga", "Artikel terkait", "Komentar", atau menu situs.
14. Maksimum 10 fakta, 5 trend, dan 4 saran/tindak.
15. Jika artikel memuat sedikitnya 4 fakta material yang berbeda, usahakan menghasilkan sedikitnya 4 butir informasi_diperoleh. Jangan menggabungkan banyak fakta material menjadi satu kalimat hanya agar jumlah fakta sedikit.
16. Prioritaskan fakta material: angka anggaran/nilai, sumber anggaran, nama instansi, nama paket/kegiatan, kode paket, metode/proses pengadaan, status proses, jumlah peserta/pihak, lokasi, target, dan tahapan pekerjaan apabila benar-benar disebutkan dalam artikel.
17. Bagian III bukan tempat mengulang Bagian I. Jika artikel menyebut proses yang sedang berjalan, tender, pendaftaran, target, jadwal, tahapan, atau perkembangan konkret, gunakan informasi tersebut sebagai current_process/explicit_future dan jelaskan perkembangan yang dapat dipantau tanpa menambahkan fakta baru.
18. Jika membuat limited_inference, nyatakan secara hati-hati sebagai perkiraan dan tetap grounded pada kalimat sumber. Jangan menciptakan akibat baru yang tidak wajar dari artikel.
19. Untuk source_limitation, cukup jelaskan keterbatasan informasi yang benar-benar relevan; evidence_sentence_ids boleh kosong.
20. Bagian III harus bernilai analitis, bukan sekadar mengulang fakta. Untuk current_process, jelaskan posisi proses saat ini dan perkembangan yang secara logis dapat dipantau dari proses tersebut. Untuk explicit_future, gunakan hanya rencana/target/tahapan yang benar-benar disebutkan. Untuk limited_inference, gunakan formulasi hati-hati seperti "diperkirakan", "perlu dicermati", atau "perkembangan selanjutnya bergantung pada" dan wajib memiliki dasar fakta yang jelas.
21. Bila artikel memuat status proses + jumlah peserta + target kegiatan, prioritaskan trend yang menghubungkan ketiganya secara faktual tanpa menciptakan jadwal, hasil, pemenang, dampak, atau keputusan yang belum disebutkan.
22. Jangan menggunakan kalimat trend yang hanya mengatakan "artikel menyebut..." atau "arah pengembangan..." jika dapat ditulis sebagai status/perkembangan konkret.
23. Jika artikel tidak memiliki dasar perkembangan yang memadai, boleh ada satu source_limitation yang singkat. Jangan mengisi Bagian III dengan kalimat generik berulang.
24. Source_limitation adalah catatan keterbatasan sumber, bukan trend utama. Jika ada current_process/explicit_future/limited_inference yang valid, utamakan itu dan jangan menjadikan source_limitation sebagai bullet trend utama.

FORMAT:
Kembalikan JSON sesuai schema. Jangan menambahkan field lain.
"""

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "perihal": {"type": "string"},
        "informasi_diperoleh": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "text": {"type": "string"},
                    "evidence_sentence_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                    },
                },
                "required": ["text", "evidence_sentence_ids"],
            },
        },
        "trend_perkembangan": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "text": {"type": "string"},
                    "evidence_sentence_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                    },
                    "basis": {
                        "type": "string",
                        "enum": [
                            "explicit_future",
                            "current_process",
                            "limited_inference",
                            "source_limitation",
                        ],
                    },
                },
                "required": ["text", "evidence_sentence_ids", "basis"],
            },
        },
        "saran_tindak": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "text": {"type": "string"},
                    "basis": {
                        "type": "string",
                        "enum": ["verification", "monitoring", "reporting"],
                    },
                },
                "required": ["text", "basis"],
            },
        },
        "source_statement": {"type": "string"},
    },
    "required": [
        "perihal",
        "informasi_diperoleh",
        "trend_perkembangan",
        "saran_tindak",
        "source_statement",
    ],
}

UI_NOISE = re.compile(
    r"tautan telah disalin|scroll to continue|anda menyukai artikel ini|"
    r"artikel disimpan|baca juga|komentar|advertisement|terpopuler|"
    r"berita terkait|artikel terkait|ikuti kami|share|bagikan",
    re.I,
)

SELECTORS = [
    "div.detail__body-text",
    "div.detail__body",
    "div.detail__article",
    "div.article__content",
    "div.read__content",
    "div.content-detail",
    "div.post-content",
    "div.entry-content",
    "div.article-content",
    "div.article-body",
    "[itemprop='articleBody']",
    "article",
]

CHROME_SELECTORS = [
    "header", "footer", "nav", "aside", "script", "style", "noscript",
    ".share", ".sharing", ".social", ".related", ".recommend", ".advert",
    ".advertisement", ".iklan", ".comment", ".comments", ".breadcrumb",
    ".sticky", ".newsletter", ".video", ".footer", ".header", ".navigation",
]


IMAGE_BAD_PATTERNS = re.compile(
    r"news\.google\.com|gstatic\.com|googleusercontent\.com|google\.com/logos|google-news|google_news|favicon|sprite|logo-google|googlelogo|/icons/",
    re.I,
)


def _valid_image_url(url: Any) -> bool:
    u = clean_text(url)
    if not u or not u.startswith(("http://", "https://")):
        return False
    return not IMAGE_BAD_PATTERNS.search(u)


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", unescape(str(value or ""))).strip()


def split_sentences(text: str, max_items: int = 120) -> List[str]:
    text = clean_text(text)
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+", text)
    out = []
    for p in parts:
        p = clean_text(p).strip("-•")
        if len(p) >= 25 and not UI_NOISE.search(p):
            out.append(p)
        if len(out) >= max_items:
            break
    return out


def _score_candidate(text: str, selector: str) -> float:
    score = min(len(text), 18000) / 100.0
    if len(text) < 350:
        score -= 10
    if "tautan telah disalin" in text.lower():
        score -= 40
    if "baca juga" in text.lower():
        score -= 20
    if selector == "article":
        score -= 3
    return score


def _walk_jsonld(value):
    """Yield JSON-LD objects recursively, including @graph entries."""
    if isinstance(value, dict):
        yield value
        graph = value.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                yield from _walk_jsonld(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_jsonld(item)


def _extract_jsonld_article(html: str) -> Tuple[str, List[str], str]:
    """Extract articleBody/image/canonical from JSON-LD before DOM cleanup."""
    soup = BeautifulSoup(html or "", "html.parser")
    bodies: List[str] = []
    images: List[str] = []
    canonical = ""
    for node in soup.select("script[type='application/ld+json']"):
        raw = node.string or node.get_text(" ", strip=True)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        for obj in _walk_jsonld(data):
            body = obj.get("articleBody")
            if isinstance(body, str) and len(clean_text(body)) >= 250:
                bodies.append(clean_text(body))
            image = obj.get("image")
            if isinstance(image, str):
                images.append(image)
            elif isinstance(image, list):
                for item in image:
                    if isinstance(item, str):
                        images.append(item)
                    elif isinstance(item, dict) and item.get("url"):
                        images.append(item["url"])
            elif isinstance(image, dict) and image.get("url"):
                images.append(image["url"])
            url = obj.get("url")
            if isinstance(url, str) and url.startswith(("http://", "https://")) and not canonical:
                canonical = url
    # Prefer the longest articleBody because news pages sometimes expose a
    # short description and a full Article object in separate JSON-LD blocks.
    body = max(bodies, key=len) if bodies else ""
    valid_images = []
    for image in images:
        if _valid_image_url(image) and image not in valid_images:
            valid_images.append(image)
    return body, valid_images[:12], canonical


def _material_source_highlights(sentences: List[str]) -> List[Tuple[int, str]]:
    patterns = [
        r"rp\s*[\d.,]+\s*(?:miliar|juta)?",
        r"apbd", r"spse", r"kode paket", r"\b\d{6,}\b", r"tender",
        r"pengadaan", r"perusahaan", r"mendaftar", r"pagu", r"hps",
        r"dinas", r"tahun anggaran", r"masih berlangsung", r"type c", r"tipe c",
    ]
    out = []
    for idx, sentence in enumerate(sentences, 1):
        if any(re.search(p, sentence, re.I) for p in patterns):
            out.append((idx, sentence))
    return out


def audit_image_urls(urls: List[str], context_text: str = "", max_selected: int = IMAGE_MAX) -> Tuple[List[str], List[Dict[str, Any]]]:
    """V1.6 deterministic image selection/audit for both publisher and stored candidates."""
    import hashlib
    ranked = []
    seen_urls = set()
    context_tokens = _tokenize(context_text) if context_text else set()
    for order, src in enumerate(urls or []):
        if not _valid_image_url(src):
            continue
        norm = clean_text(src).split("#", 1)[0].strip()
        if norm in seen_urls:
            continue
        seen_urls.add(norm)
        hay = clean_text(src).lower()
        score = 0.0
        for token in context_tokens:
            if len(token) >= 5 and token in hay:
                score += 2.0
        if any(x in hay for x in ("rsud", "bangun-purba", "bangun_purba", "rumah-sakit")):
            score += 8.0
        if any(x in hay for x in ("deli-serdang", "deli_serdang", "deliserdang")):
            score += 4.0
        if any(x in hay for x in ("kantor-bupati", "kantor_bupati", "bupati")):
            score += 0.5
        if any(x in hay for x in ("logo", "icon", "avatar", "placeholder", "default-image", "banner", "sprite", "favicon")):
            score -= 15.0
        ranked.append((score, -order, src))
    ranked.sort(reverse=True)

    selected, audit, seen_hashes = [], [], set()
    for rank, (score, _neg_order, src) in enumerate(ranked, 1):
        content_hash = ""
        content_type = ""
        byte_size = 0
        try:
            r = requests.get(
                src,
                timeout=IMAGE_HASH_TIMEOUT,
                headers={
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140.0 Safari/537.36",
                    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
                },
            )
            content_type = (r.headers.get("content-type") or "").lower()
            byte_size = len(r.content or b"")
            if r.ok and content_type.startswith("image/") and byte_size >= 2048:
                content_hash = hashlib.sha256(r.content).hexdigest()
        except Exception:
            pass
        duplicate = bool(content_hash and content_hash in seen_hashes)
        rec = {
            "url": src,
            "rank": rank,
            "score": round(score, 2),
            "duplicate": duplicate,
            "sha256": content_hash,
            "content_type": content_type,
            "byte_size": byte_size,
            "selected": False,
        }
        if duplicate:
            audit.append(rec)
            continue
        if content_hash:
            seen_hashes.add(content_hash)
        rec["selected"] = True
        audit.append(rec)
        selected.append(src)
        if len(selected) >= max_selected:
            break
    return selected, audit

def extract_article_body(html: str, context_text: str = "") -> Tuple[str, List[str], str]:
    # JSON-LD is often the cleanest and most complete representation of a
    # publisher article. Extract it BEFORE removing script/chrome nodes.
    jsonld_text, jsonld_images, jsonld_canonical = _extract_jsonld_article(html)

    soup = BeautifulSoup(html or "", "html.parser")
    for node in soup.select(",".join(CHROME_SELECTORS)):
        node.decompose()

    images: List[str] = list(jsonld_images)
    for meta in soup.select("meta[property='og:image'], meta[name='twitter:image']"):
        url = meta.get("content")
        if _valid_image_url(url) and url not in images:
            images.append(url)

    candidates = []
    if jsonld_text:
        candidates.append((1000000 + min(len(jsonld_text), 50000) / 100.0, jsonld_text))

    for selector in SELECTORS:
        for node in soup.select(selector):
            text = clean_text(node.get_text(" ", strip=True))
            if text:
                candidates.append((_score_candidate(text, selector), text))

    if not candidates:
        body = soup.body or soup
        text = clean_text(body.get_text(" ", strip=True))
    else:
        text = max(candidates, key=lambda x: x[0])[1]

    # V1.6 image pipeline: collect broad candidates, normalize them, filter
    # publisher chrome, then rank + deduplicate by URL and downloaded bytes.
    image_candidates = [(u, "jsonld") for u in images]
    for img in soup.find_all("img"):
        attrs = img.attrs or {}
        srcs = []
        for key in ("src", "data-src", "data-original", "data-lazy-src", "data-image", "data-url"):
            val = attrs.get(key)
            if isinstance(val, str):
                srcs.append(val)
        for key in ("srcset", "data-srcset"):
            val = attrs.get(key)
            if isinstance(val, str):
                for part in val.split(","):
                    candidate = part.strip().split(" ")[0]
                    if candidate:
                        srcs.append(candidate)
        label_parts = [attrs.get("alt") or "", attrs.get("title") or ""]
        parent = img.parent
        if parent and getattr(parent, "name", None) == "figure":
            cap = parent.find("figcaption")
            if cap:
                label_parts.append(cap.get_text(" ", strip=True))
        label = clean_text(" ".join(label_parts))
        for src in srcs:
            image_candidates.append((src, label))

    context_tokens = _tokenize(context_text) if context_text else set()
    ranked = []
    seen_candidate_urls = set()
    for order, (src, label) in enumerate(image_candidates):
        if not _valid_image_url(src):
            continue
        norm = src.split("#", 1)[0].strip()
        if norm in seen_candidate_urls:
            continue
        seen_candidate_urls.add(norm)
        hay = clean_text(f"{src} {label}").lower()
        score = 0.0
        for token in context_tokens:
            if len(token) >= 5 and token in hay:
                score += 2.0
        # Strong topic relevance for this project and generic Deli Serdang context.
        if any(x in hay for x in ("rsud", "bangun-purba", "bangun_purba", "rumah-sakit")):
            score += 8.0
        if any(x in hay for x in ("deli-serdang", "deli_serdang", "deliserdang")):
            score += 4.0
        if any(x in hay for x in ("kantor-bupati", "kantor_bupati", "bupati")):
            score += 0.5
        if any(x in hay for x in ("logo", "icon", "avatar", "placeholder", "default-image", "banner", "sprite", "favicon")):
            score -= 15.0
        ranked.append((score, -order, src, label))
    ranked.sort(reverse=True)

    ranked_urls = [item[2] for item in ranked]
    images, image_audit = audit_image_urls(ranked_urls, context_text=context_text, max_selected=12)

    canonical = jsonld_canonical or ""
    canon = soup.find("link", rel=lambda x: x and "canonical" in x)
    if canon and canon.get("href"):
        canonical = canon["href"]
    if not canonical:
        og = soup.find("meta", property="og:url")
        canonical = og.get("content") if og else ""

    return text, images[:12], canonical or "", image_audit

def _looks_like_google_wrapper(text: str) -> bool:
    t = clean_text(text).lower()
    return (
        "news.google.com" in t
        or "target=\"_blank\">" in t
        or "<a href=" in t and "detikcom" in t
    )


def _candidate_publisher_urls(url: str) -> List[str]:
    """Generate safe publisher URL variants, including AMP for known publishers."""
    base = clean_text(url)
    if not base or "news.google.com" in base:
        return []
    candidates = [base]
    parsed = urlparse(base)
    path = parsed.path or ""
    host = parsed.netloc.lower()
    # Detik exposes a stable AMP representation and it is often accessible when
    # the regular page is protected by anti-bot/challenge middleware.
    if "detik.com" in host and not path.endswith("/amp"):
        candidates.append(base.rstrip("/") + "/amp")
    return list(dict.fromkeys(candidates))


def resolve_google_news(url: str) -> str:
    if "news.google.com" not in (url or ""):
        return url
    try:
        r = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
            allow_redirects=True,
        )
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for selector in ["link[rel='canonical']", "meta[property='og:url']"]:
            node = soup.select_one(selector)
            candidate = (node.get("href") or node.get("content")) if node else ""
            if candidate and "news.google.com" not in candidate:
                return candidate
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith(("http://", "https://")) and "news.google.com" not in href:
                host = urlparse(href).netloc.lower()
                if host and not host.endswith("google.com"):
                    return href
    except Exception:
        pass
    return url


def _fetch_publisher(url: str, context_text: str = "") -> Tuple[str, List[str], str, str, List[Dict[str, Any]]]:
    """Fetch publisher URL variants and return the first substantial article."""
    last_error = ""
    for candidate in _candidate_publisher_urls(url):
        try:
            r = requests.get(
                candidate,
                timeout=REQUEST_TIMEOUT,
                headers={
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
                    "Cache-Control": "no-cache",
                },
                allow_redirects=True,
            )
            r.raise_for_status()
            text, fetched_images, canonical, image_audit = extract_article_body(r.text, context_text=context_text)
            sentences = split_sentences(text)
            if len(text) >= 250 and len(sentences) >= 3 and not _looks_like_google_wrapper(text):
                if not fetched_images:
                    stored_candidates = article.get("article_images") or []
                    if isinstance(stored_candidates, str):
                        try:
                            stored_candidates = json.loads(stored_candidates)
                        except Exception:
                            stored_candidates = []
                    stored_candidates = [u for u in stored_candidates if _valid_image_url(u)]
                    fetched_images, image_audit = audit_image_urls(stored_candidates, context_text=context_text, max_selected=IMAGE_MAX)
                return text, fetched_images, canonical or r.url, "publisher_jsonld_or_dom", image_audit
            last_error = f"{candidate}: extraction too short ({len(text)} chars/{len(sentences)} sentences)"
        except Exception as exc:
            last_error = f"{candidate}: {type(exc).__name__}: {exc}"
    raise RuntimeError(last_error or "publisher fetch failed")


def fetch_source_article(article: Dict[str, Any]) -> Dict[str, Any]:
    original_link = clean_text(article.get("link"))
    resolved = resolve_google_news(original_link)
    stored_raw = str(article.get("content") or "")
    stored = clean_text(stored_raw)
    stored_is_wrapper = _looks_like_google_wrapper(stored_raw)

    # Stored article_images may contain a Google News/logo asset. Never use them
    # as documentation when the stored content itself is only a wrapper.
    images = article.get("article_images") or []
    if isinstance(images, str):
        try:
            images = json.loads(images)
        except Exception:
            images = []
    images = [u for u in images if _valid_image_url(u)][:12]
    if stored_is_wrapper:
        images = []

    publisher_candidates = []
    if resolved and "news.google.com" not in resolved:
        publisher_candidates.append(resolved)
    if original_link and "news.google.com" not in original_link:
        publisher_candidates.append(original_link)

    for publisher_url in list(dict.fromkeys(publisher_candidates)):
        try:
            text, fetched_images, canonical, method, image_audit = _fetch_publisher(publisher_url, context_text=clean_text(article.get("title")))
            sentences = split_sentences(text)
            return {
                "text": text,
                "sentences": sentences,
                "images": list(dict.fromkeys(fetched_images))[:IMAGE_MAX],
                "image_audit": image_audit[:IMAGE_MAX],
                "resolved_link": canonical or publisher_url,
                "extraction_method": method,
                "material_highlights": _material_source_highlights(sentences),
            }
        except Exception:
            continue

    # A Google News wrapper is not an article source. Do NOT silently turn its
    # title/link markup into a one-sentence source and let AI generate a report.
    if stored_is_wrapper or "news.google.com" in original_link:
        raise RuntimeError(
            "Ekstraksi sumber artikel gagal: tautan Google News berhasil dikenali, "
            "tetapi halaman publisher tidak dapat diambil. Stored content hanya wrapper/metadata, "
            "bukan isi artikel. LAPINSUS dihentikan agar tidak menghasilkan laporan dari sumber yang tidak lengkap."
        )

    sentences = split_sentences(stored)
    if len(sentences) >= 3:
        # V1.6: stored images are also passed through the same dedupe/hash audit.
        selected, audit = audit_image_urls(images[:12], context_text=clean_text(article.get("title")), max_selected=IMAGE_MAX)
        return {
            "text": stored,
            "sentences": sentences,
            "images": selected[:IMAGE_MAX],
            "image_audit": audit[:IMAGE_MAX],
            "resolved_link": resolved or original_link,
            "extraction_method": "stored_content",
            "material_highlights": _material_source_highlights(sentences),
        }
    raise RuntimeError(
        "Ekstraksi sumber artikel tidak mencukupi: hanya "
        f"{len(sentences)} kalimat yang tersedia."
    )

def _input_text(article: Dict[str, Any], source: Dict[str, Any]) -> str:
    title = clean_text(article.get("title"))
    publisher = clean_text(article.get("publisher") or article.get("source"))
    date = clean_text(article.get("published_date"))
    sentences = source.get("sentences") or split_sentences(source.get("text", ""))
    numbered = "\n".join(f"[{i}] {s}" for i, s in enumerate(sentences, 1))
    highlights = source.get("material_highlights") or _material_source_highlights(sentences)
    highlight_text = "\n".join(f"[{i}] {s}" for i, s in highlights)
    return f"""ARTIKEL METADATA
Judul: {title}
Sumber/media: {publisher}
Tanggal terbit: {date}
Link sumber: {source.get('resolved_link') or article.get('link')}

KALIMAT SUMBER (gunakan nomor [n] sebagai evidence)
{numbered}

SOROTAN FAKTA MATERIAL DARI SUMBER
Bagian ini adalah daftar kalimat sumber yang secara mekanis terdeteksi mengandung
angka, anggaran, SPSE, kode paket, tender/pengadaan, instansi, perusahaan,
pagu/HPS, pendaftaran, atau status proses. Gunakan sebagai checklist agar tidak
ada fakta material yang terlewat. Jangan menambah fakta yang tidak ada pada
kalimat sumber.
{highlight_text or '(tidak ada sorotan otomatis)'}

TUGAS
Susun draft LAPINSUS dari artikel di atas.
- Bagian I: ekstrak semua fakta material yang benar-benar diberitakan; jangan
  berhenti pada ringkasan satu-dua kalimat bila sumber memuat beberapa fakta
  berbeda. Pisahkan fakta yang berbeda menjadi butir terpisah.
- Bagian III: jangan mengulang Bagian I. Prioritaskan proses/status yang sedang
  berjalan, tender, pendaftaran, target, jadwal, tahapan, atau perkembangan
  konkret yang disebut sumber. Jika hanya ada keterbatasan sumber, nyatakan
  keterbatasan tersebut secara singkat.
- Setiap fakta/trend harus dapat ditelusuri ke evidence_sentence_ids.
- Jangan memasukkan informasi dari pengetahuan umum, sumber lain, atau inferensi
  yang tidak didukung.
"""

def _ensure_bahwa(text: str) -> str:
    text = clean_text(text)
    if not text:
        return text
    if text.lower().startswith("bahwa "):
        return text
    return "Bahwa " + text[:1].lower() + text[1:]


def _tokenize(text: str) -> set:
    return set(re.findall(r"[a-zA-ZÀ-ÿ0-9]+", text.lower()))


def _validate_grounding(result: Dict[str, Any], sentences: List[str]) -> Dict[str, Any]:
    errors: List[str] = []
    evidence_ids = set(range(1, len(sentences) + 1))

    for idx, item in enumerate(result.get("informasi_diperoleh", []), 1):
        ids = item.get("evidence_sentence_ids") or []
        if not ids or not set(ids).issubset(evidence_ids):
            errors.append(f"fakta_{idx}: evidence_sentence_ids tidak valid")
        text_tokens = _tokenize(item.get("text", ""))
        source_tokens = set().union(*[_tokenize(sentences[i - 1]) for i in ids if i in evidence_ids]) if ids else set()
        # Strict enough to catch invented numeric/name-heavy claims, but allows paraphrase.
        meaningful = {t for t in text_tokens if len(t) >= 4 or t.isdigit()}
        overlap = len(meaningful & source_tokens) / max(len(meaningful), 1)
        if overlap < 0.18:
            errors.append(f"fakta_{idx}: dukungan leksikal terlalu rendah ({overlap:.2f})")

    for idx, item in enumerate(result.get("trend_perkembangan", []), 1):
        ids = item.get("evidence_sentence_ids") or []
        basis = item.get("basis")
        if basis != "source_limitation" and (not ids or not set(ids).issubset(evidence_ids)):
            errors.append(f"trend_{idx}: trend tidak memiliki evidence yang valid")
        elif basis == "source_limitation" and ids and not set(ids).issubset(evidence_ids):
            errors.append(f"trend_{idx}: evidence source_limitation tidak valid")

    # Hard check: every number appearing in AI text must appear in its cited evidence.
    for section_name in ("informasi_diperoleh", "trend_perkembangan"):
        for idx, item in enumerate(result.get(section_name, []), 1):
            nums = set(re.findall(r"\d+(?:[.,]\d+)?", item.get("text", "")))
            ids = item.get("evidence_sentence_ids") or []
            evidence_text = " ".join(sentences[i - 1] for i in ids if 1 <= i <= len(sentences))
            for n in nums:
                if n not in evidence_text:
                    errors.append(f"{section_name}_{idx}: angka {n} tidak ditemukan pada evidence")

    return {"passed": not errors, "errors": errors}


def generate_ai_lapinsus(article: Dict[str, Any], source: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if OpenAI is None:
        raise RuntimeError("Paket openai belum terpasang. Tambahkan 'openai' ke requirements.")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY belum dikonfigurasi.")

    source = source or fetch_source_article(article)
    sentences = source.get("sentences") or split_sentences(source.get("text", ""))
    if not sentences:
        raise RuntimeError("Sumber artikel tidak memiliki teks yang cukup untuk dianalisis AI.")
    if source.get("extraction_method") == "stored_content_fallback":
        raise RuntimeError("Source extraction fallback lama tidak diizinkan pada V1.3.")

    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model=os.getenv("LAPINSUS_AI_MODEL", DEFAULT_MODEL),
        instructions=SYSTEM_PROMPT,
        input=_input_text(article, source),
        text={
            "format": {
                "type": "json_schema",
                "name": "lapinsus_draft",
                "description": "Draft LAPINSUS yang grounded pada kalimat sumber.",
                "strict": True,
                "schema": SCHEMA,
            }
        },
    )

    try:
        result = json.loads(response.output_text)
    except Exception as exc:
        raise RuntimeError(f"Output AI bukan JSON valid: {exc}") from exc

    validation = _validate_grounding(result, sentences)
    if not validation["passed"]:
        raise RuntimeError("Validasi grounding AI gagal: " + "; ".join(validation["errors"][:8]))

    # Guardrail against an under-detailed Section I when the source contains
    # several material, distinct claims. This is intentionally based on source
    # evidence, not on a fixed article-specific fact count.
    material_hints = len(_material_source_highlights(sentences))
    fact_count = len(result.get("informasi_diperoleh", []))
    distinct_material_categories = sum([
        bool(re.search(r"rp\s*[\d.,]+|pagu|hps|anggaran", " ".join(sentences), re.I)),
        bool(re.search(r"spse|kode paket|pengadaan|tender", " ".join(sentences), re.I)),
        bool(re.search(r"apbd|tahun anggaran", " ".join(sentences), re.I)),
        bool(re.search(r"dinas|instansi|pemkab|pemerintah", " ".join(sentences), re.I)),
        bool(re.search(r"perusahaan|mendaftar|peserta", " ".join(sentences), re.I)),
        bool(re.search(r"masih berlangsung|tahap|jadwal|target|proses", " ".join(sentences), re.I)),
    ])
    if distinct_material_categories >= 4 and material_hints >= 4 and fact_count < 4:
        raise RuntimeError(
            "Output AI terlalu ringkas untuk sumber yang memuat banyak fakta material "
            f"(kategori={distinct_material_categories}, sorotan={material_hints}, fakta={fact_count})."
        )

    # V1.4 trend quality guard: reject trends that merely repeat a fact when
    # the source contains an identifiable current process / future / status.
    source_lower = " ".join(sentences).lower()
    has_process = bool(re.search(r"tender|pengadaan|masih berlangsung|mendaftar|proses|tahap|target|rencana|akan ", source_lower))
    trend_texts = [clean_text(x.get("text")) for x in result.get("trend_perkembangan", [])]
    if has_process and trend_texts:
        weak = 0
        for t in trend_texts:
            if re.search(r"artikel (tidak )?memuat|arah pengembangan proyek sebagaimana tercantum|informasi belum dapat diuraikan", t, re.I):
                weak += 1
        if weak == len(trend_texts):
            raise RuntimeError("Output Section III terlalu generik untuk sumber yang memiliki status/proses konkret.")

    facts = [_ensure_bahwa(x["text"]) for x in result.get("informasi_diperoleh", [])]
    raw_trend_items = result.get("trend_perkembangan", [])
    meaningful_trend_items = [x for x in raw_trend_items if x.get("basis") != "source_limitation"]
    limitation_items = [x for x in raw_trend_items if x.get("basis") == "source_limitation"]
    trends = [_ensure_bahwa(x["text"]) for x in meaningful_trend_items]
    trend_limitations = [_ensure_bahwa(x["text"]) for x in limitation_items]
    actions = [clean_text(x["text"]) for x in result.get("saran_tindak", [])]
    fact_evidence = [
        {
            "fact": facts[i],
            "source_sentence_ids": list(result.get("informasi_diperoleh", [])[i].get("evidence_sentence_ids") or []),
        }
        for i in range(min(len(facts), 10))
    ]
    trend_evidence = [
        {
            "trend": trends[i],
            "source_sentence_ids": list(meaningful_trend_items[i].get("evidence_sentence_ids") or []),
            "basis": meaningful_trend_items[i].get("basis"),
        }
        for i in range(min(len(trends), 5))
    ]

    if not facts:
        raise RuntimeError("AI tidak menghasilkan fakta untuk Section I.")
    if not trends:
        trends = [trend_limitations[0] if trend_limitations else _ensure_bahwa("sumber artikel belum memuat perkembangan lanjutan yang cukup untuk diuraikan lebih lanjut")]
        trend_evidence = [{"trend": trends[0], "source_sentence_ids": [], "basis": "source_limitation"}]
    if not actions:
        actions = [
            "Melakukan verifikasi terhadap informasi utama pada sumber primer dan/atau pihak terkait.",
            "Melakukan monitoring terhadap perkembangan informasi pada sumber yang relevan.",
            "Melaporkan perkembangan penting kepada pimpinan pada kesempatan pertama.",
        ]

    return {
        "perihal": clean_text(result.get("perihal")) or clean_text(article.get("title")),
        "facts": facts[:10],
        "fact_evidence": fact_evidence[:10],
        "trend": trends[:5],
        "trend_evidence": trend_evidence[:5],
        "trend_limitations": trend_limitations[:2],
        "actions": actions[:4],
        "source_statement": clean_text(result.get("source_statement")) or (
            f"Bahwa informasi diperoleh dari pemberitaan media {clean_text(article.get('publisher') or article.get('source')) or 'sebagaimana tercantum pada sumber artikel'} dan masih memerlukan verifikasi terhadap sumber primer/pihak terkait."
        ),
        "source_text": source.get("text", ""),
        "source_sentences": sentences,
        "source_extraction_method": source.get("extraction_method"),
        "source_sentence_count": len(sentences),
        "source_material_highlights": source.get("material_highlights") or _material_source_highlights(sentences),
        "resolved_link": source.get("resolved_link") or article.get("link"),
        "images": source.get("images") or article.get("article_images") or [],
        "image_audit": source.get("image_audit") or [],
        "grounding": validation,
        "model": os.getenv("LAPINSUS_AI_MODEL", DEFAULT_MODEL),
        "ai_version": AI_VERSION,
    }


def mock_lapinsus_33979(article: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic local fixture used to test the PDF pipeline without an API key."""
    return {
        "perihal": clean_text(article.get("title")),
        "facts": [
            "Bahwa Pemerintah Kabupaten Deli Serdang berencana meningkatkan RSUD Bangun Purba menjadi rumah sakit tipe C.",
            "Bahwa untuk pelaksanaan peningkatan RSUD Bangun Purba tersebut telah dianggarkan dana sebesar Rp11,9 miliar dari APBD Kabupaten Deli Serdang Tahun Anggaran 2026.",
            "Bahwa paket pekerjaan peningkatan RSUD Bangun Purba berada pada Dinas Cipta Karya dan Tata Ruang Kabupaten Deli Serdang.",
            "Bahwa proses pengadaan pekerjaan tersebut masih berada pada tahap tender.",
            "Bahwa berdasarkan pemberitaan, terdapat 12 perusahaan yang telah terdaftar dalam proses tender.",
        ],
        "fact_evidence": [
            {"fact": "Bahwa Pemerintah Kabupaten Deli Serdang berencana meningkatkan RSUD Bangun Purba menjadi rumah sakit tipe C.", "source_sentence_ids": [1]},
            {"fact": "Bahwa untuk pelaksanaan peningkatan RSUD Bangun Purba tersebut telah dianggarkan dana sebesar Rp11,9 miliar dari APBD Kabupaten Deli Serdang Tahun Anggaran 2026.", "source_sentence_ids": [2, 8]},
            {"fact": "Bahwa paket pekerjaan peningkatan RSUD Bangun Purba berada pada Dinas Cipta Karya dan Tata Ruang Kabupaten Deli Serdang.", "source_sentence_ids": [7]},
            {"fact": "Bahwa proses pengadaan pekerjaan tersebut masih berada pada tahap tender.", "source_sentence_ids": [10]},
            {"fact": "Bahwa berdasarkan pemberitaan, terdapat 12 perusahaan yang telah terdaftar dalam proses tender.", "source_sentence_ids": [11]},
        ],
        "trend": [
            "Bahwa proses pengadaan pekerjaan peningkatan RSUD Bangun Purba masih berlangsung melalui tahapan tender.",
            "Bahwa dengan telah adanya 12 perusahaan yang mendaftar, perkembangan selanjutnya perlu dicermati pada tahapan proses tender berikutnya sampai dengan penetapan hasil pengadaan.",
        ],
        "trend_evidence": [
            {"trend": "Bahwa proses pengadaan pekerjaan peningkatan RSUD Bangun Purba masih berlangsung melalui tahapan tender.", "source_sentence_ids": [10], "basis": "current_process"},
            {"trend": "Bahwa dengan telah adanya 12 perusahaan yang mendaftar, perkembangan selanjutnya perlu dicermati pada tahapan proses tender berikutnya sampai dengan penetapan hasil pengadaan.", "source_sentence_ids": [10, 11], "basis": "limited_inference"},
        ],
        "actions": [
            "Melakukan verifikasi terhadap tahapan dan hasil proses pengadaan pekerjaan pada sumber primer atau pihak terkait.",
            "Melakukan monitoring terhadap perkembangan pelaksanaan peningkatan RSUD Bangun Purba.",
            "Melaporkan perkembangan penting kepada pimpinan pada kesempatan pertama.",
        ],
        "source_statement": "Bahwa informasi diperoleh dari pemberitaan media detikcom dan masih memerlukan verifikasi terhadap sumber primer/pihak terkait.",
        "source_text": "",
        "source_sentences": [],
        "resolved_link": article.get("link", ""),
        "images": article.get("article_images") or [],
        "grounding": {"passed": True, "errors": [], "mode": "mock_fixture"},
        "model": "mock-fixture",
    }
