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
AI_VERSION = "LAPINSUS_DELI_SERDANG_AI_V1_3"
REQUEST_TIMEOUT = int(os.getenv("LAPINSUS_SOURCE_TIMEOUT", "15"))

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


def extract_article_body(html: str) -> Tuple[str, List[str], str]:
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

    # Collect article images after chrome removal, while excluding Google News
    # wrappers, favicons, logos and generic UI assets.
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
        if _valid_image_url(src) and src not in images:
            images.append(src)

    canonical = jsonld_canonical or ""
    canon = soup.find("link", rel=lambda x: x and "canonical" in x)
    if canon and canon.get("href"):
        canonical = canon["href"]
    if not canonical:
        og = soup.find("meta", property="og:url")
        canonical = og.get("content") if og else ""

    return text, images[:12], canonical or ""

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


def _fetch_publisher(url: str) -> Tuple[str, List[str], str, str]:
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
            text, fetched_images, canonical = extract_article_body(r.text)
            sentences = split_sentences(text)
            if len(text) >= 250 and len(sentences) >= 3 and not _looks_like_google_wrapper(text):
                return text, fetched_images, canonical or r.url, "publisher_jsonld_or_dom"
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
            text, fetched_images, canonical, method = _fetch_publisher(publisher_url)
            sentences = split_sentences(text)
            return {
                "text": text,
                "sentences": sentences,
                "images": list(dict.fromkeys(fetched_images))[:12],
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
        return {
            "text": stored,
            "sentences": sentences,
            "images": images,
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

    facts = [_ensure_bahwa(x["text"]) for x in result.get("informasi_diperoleh", [])]
    trends = [_ensure_bahwa(x["text"]) for x in result.get("trend_perkembangan", [])]
    actions = [clean_text(x["text"]) for x in result.get("saran_tindak", [])]

    if not facts:
        raise RuntimeError("AI tidak menghasilkan fakta untuk Section I.")
    if not trends:
        trends = [_ensure_bahwa("sumber artikel belum memuat perkembangan lanjutan yang eksplisit; perkembangan selanjutnya perlu dipantau berdasarkan informasi tambahan yang terverifikasi")]
    if not actions:
        actions = [
            "Melakukan verifikasi terhadap informasi utama pada sumber primer dan/atau pihak terkait.",
            "Melakukan monitoring terhadap perkembangan informasi pada sumber yang relevan.",
            "Melaporkan perkembangan penting kepada pimpinan pada kesempatan pertama.",
        ]

    return {
        "perihal": clean_text(result.get("perihal")) or clean_text(article.get("title")),
        "facts": facts[:10],
        "trend": trends[:5],
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
        "trend": [
            "Bahwa proses pengadaan pekerjaan peningkatan RSUD Bangun Purba masih berlangsung melalui tahapan tender.",
            "Bahwa perkembangan selanjutnya berkaitan dengan hasil proses tender dan pelaksanaan pekerjaan peningkatan RSUD Bangun Purba menjadi tipe C.",
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
