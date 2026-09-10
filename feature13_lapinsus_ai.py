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


def extract_article_body(html: str) -> Tuple[str, List[str], str]:
    soup = BeautifulSoup(html or "", "html.parser")
    for node in soup.select(",".join(CHROME_SELECTORS)):
        node.decompose()

    images: List[str] = []
    for meta in soup.select("meta[property='og:image'], meta[name='twitter:image']"):
        url = meta.get("content")
        if url and url.startswith(("http://", "https://")) and url not in images:
            images.append(url)

    candidates = []
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

    # Collect article images after chrome removal.
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
        if src and src.startswith(("http://", "https://")) and src not in images:
            images.append(src)

    canonical = ""
    canon = soup.find("link", rel=lambda x: x and "canonical" in x)
    if canon and canon.get("href"):
        canonical = canon["href"]
    if not canonical:
        og = soup.find("meta", property="og:url")
        canonical = og.get("content") if og else ""

    return text, images[:12], canonical or ""


def resolve_google_news(url: str) -> str:
    if "news.google.com" not in (url or ""):
        return url
    try:
        r = requests.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"}, allow_redirects=True)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for selector in ["link[rel='canonical']", "meta[property='og:url']"]:
            node = soup.select_one(selector)
            candidate = node.get("href") or node.get("content") if node else ""
            if candidate and "news.google.com" not in candidate:
                return candidate
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith(("http://", "https://")) and "news.google.com" not in href:
                host = urlparse(href).netloc.lower()
                if host and not host.endswith("google.com"):
                    return href
        return r.url
    except Exception:
        return url


def fetch_source_article(article: Dict[str, Any]) -> Dict[str, Any]:
    original_link = clean_text(article.get("link"))
    link = resolve_google_news(original_link)
    stored = clean_text(article.get("content"))
    images = article.get("article_images") or []
    if isinstance(images, str):
        try:
            images = json.loads(images)
        except Exception:
            images = []

    if not link:
        return {"text": stored, "sentences": split_sentences(stored), "images": images, "resolved_link": ""}

    try:
        r = requests.get(link, timeout=REQUEST_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"}, allow_redirects=True)
        r.raise_for_status()
        text, fetched_images, canonical = extract_article_body(r.text)
        if len(text) >= 250:
            merged_images = list(dict.fromkeys(list(images) + fetched_images))[:12]
            return {
                "text": text,
                "sentences": split_sentences(text),
                "images": merged_images,
                "resolved_link": canonical or r.url,
            }
    except Exception:
        pass

    return {"text": stored, "sentences": split_sentences(stored), "images": images, "resolved_link": link}


def _input_text(article: Dict[str, Any], source: Dict[str, Any]) -> str:
    title = clean_text(article.get("title"))
    publisher = clean_text(article.get("publisher") or article.get("source"))
    date = clean_text(article.get("published_date"))
    sentences = source.get("sentences") or split_sentences(source.get("text", ""))
    numbered = "\n".join(f"[{i}] {s}" for i, s in enumerate(sentences, 1))
    return f"""ARTIKEL METADATA
Judul: {title}
Sumber/media: {publisher}
Tanggal terbit: {date}
Link sumber: {source.get('resolved_link') or article.get('link')}

KALIMAT SUMBER (gunakan nomor [n] sebagai evidence)
{numbered}

TUGAS
Susun draft LAPINSUS dari artikel di atas. Utamakan fakta yang paling relevan,
angka/nama/tanggal/lokasi/status proses, kemudian trend yang benar-benar
mempunyai dasar di artikel. Jangan memasukkan informasi yang tidak didukung.
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
        # source_limitation is a meta-level statement about the limits of the
        # supplied article, not a claim that needs article evidence. Some models
        # may still return evidence_sentence_ids despite the instruction; do not
        # fail the whole draft for that harmless extra field.
        if basis == "source_limitation":
            continue

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

    facts = [_ensure_bahwa(x["text"]) for x in result.get("informasi_diperoleh", [])]
    trends = [_ensure_bahwa(x["text"]) for x in result.get("trend_perkembangan", [])]
    actions = [clean_text(x["text"]) for x in result.get("saran_tindak", [])]

    if not facts:
        facts = [_ensure_bahwa("pemberitaan telah memuat informasi sebagaimana tercantum dalam sumber artikel")]
    if not trends:
        trends = [_ensure_bahwa("sumber artikel belum memuat proyeksi lanjutan yang eksplisit sehingga perkembangan berikutnya memerlukan monitoring")]
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
        "resolved_link": source.get("resolved_link") or article.get("link"),
        "images": source.get("images") or article.get("article_images") or [],
        "grounding": validation,
        "model": os.getenv("LAPINSUS_AI_MODEL", DEFAULT_MODEL),
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
