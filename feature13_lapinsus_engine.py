import hashlib
import html
import io
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import requests
import streamlit as st
from bs4 import BeautifulSoup
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image as RLImage,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
)

from database import get_supabase

TABLE = "deli_serdang_location_articles"
TEMPLATE_VERSION = "LAPINSUS_DELI_SERDANG_V3_ARTICLE_GROUNDED"

import os

KEPALA_NAMA = os.getenv("LAPINSUS_KEPALA_NAMA", "SAPTA PUTRA, S.H., M. Hum.")
KEPALA_PANGKAT = os.getenv("LAPINSUS_KEPALA_PANGKAT", "Jaksa Utama Pratama")
KEPALA_NIP = os.getenv("LAPINSUS_KEPALA_NIP", "19740312 199903 1 006")
AUTENTIKASI_NAMA = os.getenv("LAPINSUS_AUTENTIKASI_NAMA", "ROBY SYAHPUTRA, S.H., M.H.")
AUTENTIKASI_PANGKAT = os.getenv("LAPINSUS_AUTENTIKASI_PANGKAT", "Jaksa Madya")
AUTENTIKASI_NIP = os.getenv("LAPINSUS_AUTENTIKASI_NIP", "19801020 200712 1002")


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def clean_article_content(value):
    """Convert RSS/HTML content into human-readable article text."""
    raw = html.unescape(str(value or ""))
    if not raw:
        return ""
    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    return _clean(html.unescape(text))


def _extract_html_links_images(value, base_url=""):
    raw = html.unescape(str(value or ""))
    if not raw:
        return [], []
    soup = BeautifulSoup(raw, "html.parser")
    links = []
    images = []
    for tag in soup.find_all("a", href=True):
        href = urljoin(base_url, tag.get("href"))
        if href:
            links.append(href)
    for tag in soup.find_all("img", src=True):
        src = urljoin(base_url, tag.get("src"))
        if src:
            images.append(src)
    for tag in soup.find_all("source", src=True):
        src = urljoin(base_url, tag.get("src"))
        if src:
            images.append(src)
    return list(dict.fromkeys(links)), list(dict.fromkeys(images))


def _looks_google_news(url):
    try:
        host = urlparse(url).netloc.lower()
        return "news.google.com" in host
    except Exception:
        return False


def resolve_article_url(url):
    url = _clean(url)
    if not url:
        return ""
    if not _looks_google_news(url):
        return url

    try:
        response = requests.get(
            url,
            timeout=15,
            allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        final = _clean(response.url)
        soup = BeautifulSoup(response.text, "html.parser")

        for selector in (
            'link[rel="canonical"]',
            'meta[property="og:url"]',
        ):
            tag = soup.select_one(selector)
            candidate = tag.get("href") or tag.get("content") if tag else ""
            if candidate and not _looks_google_news(candidate):
                return urljoin(final, candidate)

        for a in soup.find_all("a", href=True):
            href = urljoin(final, a.get("href"))
            if href and not _looks_google_news(href):
                host = urlparse(href).netloc.lower()
                if host and host != "news.google.com":
                    return href

        if final and not _looks_google_news(final):
            return final
    except Exception:
        pass

    return url


def _extract_article_text_from_soup(soup):
    """Extract the publisher's article body, excluding page chrome/UI noise."""
    # Remove elements that are almost never part of the article body.
    for tag in soup.find_all([
        "script", "style", "noscript", "svg", "nav", "footer", "header",
        "form", "iframe"
    ]):
        tag.decompose()

    selectors = [
        # detik / Indonesian publisher patterns
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

    candidates = []
    for selector in selectors:
        for node in soup.select(selector):
            # Remove nested UI blocks from the candidate.
            clone = BeautifulSoup(str(node), "html.parser")
            for bad in clone.find_all(class_=re.compile(
                r"share|related|recommend|advert|iklan|comment|breadcrumb|sticky|footer|header|navigation|newsletter|video|social",
                re.I,
            )):
                bad.decompose()
            for bad in clone.find_all(id=re.compile(
                r"share|related|recommend|advert|iklan|comment|breadcrumb|sticky|footer|header|navigation|newsletter|social",
                re.I,
            )):
                bad.decompose()
            paragraphs = [
                x.get_text(" ", strip=True)
                for x in clone.find_all(["p", "h2", "h3", "li"])
            ]
            paragraphs = [x for x in paragraphs if len(x) >= 25]
            if paragraphs:
                text = " ".join(paragraphs)
            else:
                text = clone.get_text(" ", strip=True)
            if len(text) >= 180:
                candidates.append(text)

    if candidates:
        # Prefer the most article-like candidate, not the longest page-wide wrapper.
        def score(text):
            lower = text.lower()
            boilerplate = sum(lower.count(x) for x in (
                "tautan telah disalin", "scroll to continue", "artikel ini telah tayang",
                "anda menyukai artikel ini", "artikel disimpan", "baca juga",
                "komentar", "advertisement", "terpopuler"
            ))
            return len(text) - (boilerplate * 500)
        return max(candidates, key=score)

    return ""


def _fetch_article_page(url):
    """Fetch publisher page, returning clean article text + image URLs."""
    url = resolve_article_url(url)
    if not url:
        return "", []

    try:
        response = requests.get(
            url,
            timeout=18,
            allow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 Chrome/140 Safari/537.36"
                )
            },
        )
        response.raise_for_status()
        final_url = response.url or url
        soup = BeautifulSoup(response.text, "html.parser")

        images = []
        for selector in (
            'meta[property="og:image"]',
            'meta[name="twitter:image"]',
        ):
            for tag in soup.select(selector):
                value = tag.get("content")
                if value:
                    images.append(urljoin(final_url, value))

        for tag in soup.find_all("img", src=True):
            src = urljoin(final_url, tag.get("src"))
            if src:
                images.append(src)

        text = _extract_article_text_from_soup(soup)
        if not text:
            # Last-resort fallback: strip page chrome and use visible text.
            fallback = BeautifulSoup(response.text, "html.parser")
            for tag in fallback(["script", "style", "noscript", "nav", "footer", "header", "form", "iframe"]):
                tag.decompose()
            text = fallback.get_text(" ", strip=True)

        text = _clean(html.unescape(text))
        images = list(dict.fromkeys(images))
        return text, images
    except Exception:
        return "", []

def _article_grounding(article):
    stored_content = clean_article_content(article.get("content"))
    stored_links, stored_images = _extract_html_links_images(
        article.get("content"), article.get("link") or ""
    )

    source_link = _clean(article.get("link"))
    candidates = [source_link] + stored_links
    resolved = ""
    fetched_text = ""
    fetched_images = []

    for candidate in candidates:
        if not candidate:
            continue
        resolved = resolve_article_url(candidate)
        fetched_text, fetched_images = _fetch_article_page(resolved)
        if fetched_text or fetched_images:
            break

    text = fetched_text or stored_content
    if len(text) < 120 and stored_content:
        text = stored_content

    images = list(dict.fromkeys(fetched_images + stored_images + list(article.get("article_images") or [])))
    return text, images[:8], resolved or source_link




def get_article_source_text(article):
    """Return article text grounded in the publisher link when possible."""
    text, images, resolved = _article_grounding(article)
    return {"text": text, "images": images, "resolved_link": resolved}

def _parse_date(value):
    if not value:
        return None
    text = _clean(value)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        pass
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text[:10], fmt)
        except Exception:
            continue
    return None


def _date_id(value):
    months = [
        "Januari", "Februari", "Maret", "April", "Mei", "Juni",
        "Juli", "Agustus", "September", "Oktober", "November", "Desember",
    ]
    dt = _parse_date(value)
    if not dt:
        return "Tanggal tidak tersedia"
    return f"{dt.day} {months[dt.month - 1]} {dt.year}"


def _report_number(article_id):
    try:
        seq = int(article_id)
    except Exception:
        seq = 0
    return f"R-LIK-{seq:03d}/L.2.14/Dsb.4/{datetime.now().strftime('%m/%Y')}"


def get_location_articles(limit=500):
    try:
        return (
            get_supabase()
            .table(TABLE)
            .select("*")
            .order("published_date", desc=True)
            .limit(limit)
            .execute()
            .data
            or []
        )
    except Exception as exc:
        st.error(f"Gagal membaca {TABLE}: {type(exc).__name__}: {exc}")
        return []


def _extract_sentences(content, max_items=18):
    text = clean_article_content(content)
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+", text)
    out = []
    seen = set()
    for part in parts:
        part = _clean(part).strip("-•")
        key = part.lower()
        if len(part) >= 35 and key not in seen:
            out.append(part)
            seen.add(key)
        if len(out) >= max_items:
            break
    return out


ISSUE_RULES = [
    ("Kesehatan", r"\brsud\b|\brumah sakit\b|\bpuskesmas\b|\bkesehatan\b|\bpasien\b|\bdokter\b"),
    ("Infrastruktur", r"\bjembatan\b|\bjalan\b|\binfrastruktur\b|\bpembangunan\b|\bdibangun\b|\bproyek\b"),
    ("Pemerintahan", r"\bpemkab\b|\bbupati\b|\bdprd\b|\bpemerintah\b|\banggaran\b|\banggarkan\b|\bperda\b"),
    ("Korupsi", r"\bkorupsi\b|\bsuap\b|\bgratifikasi\b|\bpungli\b|\btipikor\b|\btersangka\b"),
    ("Narkotika", r"\bnarkoba\b|\bnarkotika\b|\bsabu\b|\bganja\b|\bpil ekstasi\b"),
    ("Kriminalitas", r"\bkriminal\b|\bpencurian\b|\bperampokan\b|\bpembunuhan\b|\bpenganiayaan\b|\bpenipuan\b"),
    ("Peradilan / Hukum", r"\bsidang\b|\bputusan\b|\bterdakwa\b|\btersangka\b|\bkejaksaan\b|\bpolisi\b|\bhukum\b"),
    ("Keamanan / Kamtibmas", r"\bkeamanan\b|\bkamtibmas\b|\bpatroli\b|\bpolsek\b|\bpolres\b|\bkeributan\b"),
    ("Sosial", r"\bbantuan\b|\bsosial\b|\bwarga\b|\bmasyarakat\b|\bdonasi\b|\bsantunan\b"),
    ("Pendidikan", r"\bsekolah\b|\bsiswa\b|\bguru\b|\bpendidikan\b|\bkampus\b|\buniversitas\b"),
    ("Lingkungan", r"\blingkungan\b|\bsampah\b|\bbanjir\b|\blongsor\b|\bhutan\b|\bpencemaran\b"),
    ("Ekonomi", r"\busaha\b|\bumkm\b|\bekonomi\b|\bpasar\b|\bpedagang\b|\binvestasi\b"),
    ("Bencana", r"\bbanjir\b|\blongsor\b|\bgempa\b|\bkarhutla\b|\bbencana\b"),
]


def classify_issues(title, content):
    text = _clean(f"{title} {content}").lower()
    found = [name for name, pattern in ISSUE_RULES if re.search(pattern, text, re.I)]
    return found or ["Umum / lainnya"]


# Fine-grained issue labels for the map. These are deliberately event/issue terms,
# not broad administrative categories such as "Kriminalitas".
ISSUE_TOPIC_RULES = [
    ("Narkotika", r"\bnarkotika\b|\bnarkoba\b|\bsabu\b|\bganja\b|\bekstasi\b|\bpil ekstasi\b|\bobat terlarang\b"),
    ("Penganiayaan", r"\bpenganiayaan\b|\bdianiaya\b|\bmenganiaya\b|\baniaya\b"),
    ("Pencurian", r"\bpencurian\b|\bmencuri\b|\bdicuri\b|\bcuranmor\b|\bpencurian kendaraan\b"),
    ("Pembunuhan", r"\bpembunuhan\b|\bdibunuh\b|\bmembunuh\b|\bpembunuh\b"),
    ("Penipuan", r"\bpenipuan\b|\bmenipu\b|\bditipu\b|\bpenyelewengan\b"),
    ("Korupsi", r"\bkorupsi\b|\btindak pidana korupsi\b|\btipikor\b"),
    ("Suap / Gratifikasi", r"\bsuap\b|\bgratifikasi\b|\bpungli\b"),
    ("Judi", r"\bperjudian\b|\bjudi\b|\btogel\b|\bkasino\b"),
    ("Kekerasan Seksual", r"\bkekerasan seksual\b|\bpencabulan\b|\bpelecehan seksual\b|\bpersetubuhan\b"),
    ("KDRT", r"\bkdrt\b|\bkekerasan dalam rumah tangga\b"),
    ("Kecelakaan", r"\bkecelakaan\b|\btabrakan\b|\btertabrak\b|\blaka lantas\b"),
    ("Banjir", r"\bbanjir\b|\bterendam\b|\bgenangan\b"),
    ("Longsor", r"\blongsor\b|\btanah longsor\b"),
    ("Karhutla", r"\bkarhutla\b|\bkebakaran hutan\b|\bkebakaran lahan\b"),
    ("Infrastruktur", r"\bjembatan\b|\bjalan\b|\binfrastruktur\b|\bpembangunan\b|\bproyek\b|\btender\b"),
    ("Kesehatan", r"\brsud\b|\brumah sakit\b|\bpuskesmas\b|\bkesehatan\b|\bpasien\b|\bdokter\b"),
    ("Pendidikan", r"\bsekolah\b|\bsiswa\b|\bguru\b|\bpendidikan\b|\bkampus\b|\buniversitas\b"),
    ("Lingkungan", r"\blingkungan\b|\bsampah\b|\bpencemaran\b|\bhutan\b"),
    ("Konflik / Kamtibmas", r"\bkeributan\b|\bkonflik\b|\bbentrokan\b|\bkamtibmas\b|\bkeamanan\b|\bpatroli\b"),
    ("Pertanahan / Sengketa", r"\bpertanahan\b|\bsengketa tanah\b|\bsengketa lahan\b|\bsertifikat\b"),
    ("Anggaran / Pemerintahan", r"\banggaran\b|\banggarkan\b|\bapbd\b|\bpemkab\b|\bbupati\b|\bdprd\b|\bpemerintah\b"),
]


def extract_issue_topics(title, content):
    """Extract specific issue/event labels from the article text."""
    text = _clean(f"{title} {content}").lower()
    found = [name for name, pattern in ISSUE_TOPIC_RULES if re.search(pattern, text, re.I)]
    return found or ["Isu umum / lainnya"]


def _trend_sentences(sentences):
    """Return only trend/progress statements actually present in the article."""
    trend_patterns = (
        r"\bakan\b|\brencana\b|\bberencana\b|\bdirencanakan\b|\bditargetkan\b|"
        r"\btarget\b|\bdiproyeksikan\b|\bke depan\b|\bselanjutnya\b|\bberikutnya\b|"
        r"\bdilanjutkan\b|\bmelanjutkan\b|\bpengembangan\b|\bpercepatan\b|"
        r"\bdianggarkan\b|\bdibangun\b|\bditingkatkan\b|\bakan dimulai\b|"
        r"\bsedang\b|\bdalam proses\b|\bproses tender\b|\btender\b|\bterdaftar\b|"
        r"\bberlangsung\b|\bdimulai\b|\bmulai\b|\btahun ini\b"
    )
    noise = (
        "tautan telah disalin", "scroll to continue", "anda menyukai artikel ini",
        "artikel disimpan", "baca juga", "ikuti kami", "advertisement"
    )
    selected = []
    seen = set()
    for sentence in sentences:
        low = sentence.lower()
        if any(x in low for x in noise):
            continue
        if re.search(trend_patterns, sentence, re.I):
            key = low[:400]
            if key not in seen:
                selected.append(sentence)
                seen.add(key)
        if len(selected) >= 5:
            break
    return selected


def _fallback_trend(sentences):
    """No invented trend: explicitly state that the article has no explicit projection."""
    if sentences:
        return [
            "Artikel tidak memuat proyeksi lanjutan yang eksplisit. Perkembangan berikutnya perlu dimonitor berdasarkan sumber asli.",
        ]
    return [
        "Tidak terdapat cukup teks artikel untuk menilai trend perkembangan/perkiraan. Verifikasi sumber asli diperlukan."
    ]


def build_lapinsus(article):
    title = _clean(article.get("title")) or "Tanpa Judul"
    source = _clean(article.get("publisher") or article.get("source")) or "Tidak tersedia"
    stored_link = _clean(article.get("link"))
    grounded_text, images, resolved_link = _article_grounding(article)
    sentences = _extract_sentences(grounded_text)

    allegation_words = r"diduga|dugaan|disinyalir|menurut|disebut|kabarnya|tuding|tuduhan"
    evidence = []
    for sentence in sentences:
        if re.search(allegation_words, sentence, re.I):
            evidence.append(f"{sentence} [PERLU VERIFIKASI]")
        else:
            evidence.append(sentence)

    # Facts are article sentences only. No generic facts are inserted when the source is available.
    facts = evidence[:10]
    if not facts:
        facts = [
            "Konten artikel yang berhasil diambil tidak cukup untuk mengekstrak fakta. Verifikasi langsung pada sumber asli diperlukan."
        ]

    trend = _trend_sentences(sentences)
    if not trend:
        trend = _fallback_trend(sentences)

    issues = classify_issues(title, grounded_text)

    return {
        "article_id": article.get("id"),
        "title": title,
        "published_date": article.get("published_date"),
        "source": source,
        "link": stored_link,
        "resolved_link": resolved_link,
        "locations": ", ".join(map(str, article.get("matched_location_keywords") or []))
        or "Tidak teridentifikasi",
        "issues": issues,
        "facts": facts,
        "trend": trend,
        "actions": [
            "Melakukan verifikasi terhadap informasi utama pada sumber primer dan/atau pihak terkait.",
            "Melakukan monitoring perkembangan pemberitaan dan situasi pada lokasi yang teridentifikasi.",
            "Melaporkan perkembangan penting kepada pimpinan pada kesempatan pertama sesuai kebutuhan.",
        ],
        "images": images,
        "grounded_content": grounded_text,
        "report_number": _report_number(article.get("id")),
    }

def _styles():
    base = getSampleStyleSheet()
    return {
        "body": ParagraphStyle("BodyL", parent=base["BodyText"], fontName="Times-Roman", fontSize=10.5, leading=14, spaceAfter=4),
        "center": ParagraphStyle("Center", parent=base["BodyText"], fontName="Times-Roman", fontSize=10.5, leading=14, alignment=TA_CENTER),
        "center_bold": ParagraphStyle("CenterBold", parent=base["BodyText"], fontName="Times-Bold", fontSize=10.5, leading=14, alignment=TA_CENTER),
        "section": ParagraphStyle("Section", parent=base["Heading2"], fontName="Times-Bold", fontSize=10.5, leading=14, spaceBefore=7, spaceAfter=5),
        "title": ParagraphStyle("DocTitle", parent=base["Title"], fontName="Times-Bold", fontSize=13, leading=16, alignment=TA_CENTER, spaceAfter=4),
        "right": ParagraphStyle("Right", parent=base["BodyText"], fontName="Times-Roman", fontSize=10.5, leading=14, alignment=TA_RIGHT),
        "tiny": ParagraphStyle("Tiny", parent=base["BodyText"], fontName="Times-Roman", fontSize=8, leading=10),
    }


def _safe_paragraph(text, style):
    value = _clean(text)
    value = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return Paragraph(value, style)


def _bullet(text, style):
    return _safe_paragraph(f"- {_clean(text)}", style)


def _header(canvas, doc):
    canvas.saveState()
    canvas.setFont("Times-Bold", 11)
    canvas.drawCentredString(A4[0] / 2, A4[1] - 0.75 * cm, "R A H A S I A")
    canvas.setFont("Times-Roman", 8)
    canvas.drawRightString(A4[0] - 1.6 * cm, 0.8 * cm, f"Halaman {doc.page}")
    canvas.restoreState()


def _image_flowable(url, max_width, max_height):
    try:
        response = requests.get(
            url,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()
        content_type = (response.headers.get("content-type") or "").lower()
        if "image" not in content_type and not re.search(r"\.(jpe?g|png|webp)(?:\?|$)", url, re.I):
            return None
        data = io.BytesIO(response.content)
        reader = ImageReader(data)
        iw, ih = reader.getSize()
        if not iw or not ih:
            return None
        scale = min(max_width / iw, max_height / ih, 1.0)
        img = RLImage(data, width=iw * scale, height=ih * scale)
        img.hAlign = "CENTER"
        return img
    except Exception:
        return None


def make_pdf(data):
    buffer = io.BytesIO()
    styles = _styles()
    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.55 * cm,
        leftMargin=1.55 * cm,
        topMargin=1.45 * cm,
        bottomMargin=1.35 * cm,
    )
    frame = Frame(
        doc.leftMargin,
        doc.bottomMargin,
        doc.width,
        doc.height,
        id="normal",
    )
    doc.addPageTemplates([PageTemplate(id="main", frames=frame, onPage=_header)])

    story = [
        Spacer(1, 0.25 * cm),
        _safe_paragraph("LAPORAN INFORMASI KHUSUS", styles["title"]),
        _safe_paragraph(f"NOMOR : {data['report_number']}", styles["center_bold"]),
        Spacer(1, 0.15 * cm),
        _safe_paragraph(f"PERIHAL: {data['title']}", styles["body"]),
        _safe_paragraph("_" * 112, styles["tiny"]),
        Spacer(1, 0.2 * cm),
        _safe_paragraph("I. INFORMASI YANG DIPEROLEH :", styles["section"]),
    ]

    for fact in data["facts"]:
        story.append(_bullet(fact, styles["body"]))

    story += [
        Spacer(1, 0.12 * cm),
        _safe_paragraph(
            f"Sumber: {data['source']}. Tautan artikel: {data.get('resolved_link') or data.get('link') or 'tidak tersedia'}.",
            styles["body"],
        ),
        PageBreak(),
        Spacer(1, 0.25 * cm),
        _safe_paragraph("II. SUMBER INFORMASI :", styles["section"]),
        _safe_paragraph(
            "Bahwa informasi diperoleh dari pemberitaan media yang tercantum pada sumber artikel "
            "dan masih memerlukan verifikasi terhadap sumber primer/pihak terkait.",
            styles["body"],
        ),
        _safe_paragraph("III. TREND PERKEMBANGAN / PERKIRAAN :", styles["section"]),
    ]

    for item in data["trend"]:
        story.append(_bullet(item, styles["body"]))

    story += [
        _safe_paragraph("IV. SARAN / TINDAK :", styles["section"]),
    ]
    for i, action in enumerate(data["actions"], 1):
        story.append(_safe_paragraph(f"{i}. {action}", styles["body"]))

    story += [
        Spacer(1, 0.1 * cm),
        _safe_paragraph(
            "Demikian agar Bapak maklum adanya dan perkembangan selanjutnya akan kami laporkan "
            "dalam kesempatan pertama.",
            styles["body"],
        ),
        Spacer(1, 0.2 * cm),
        _safe_paragraph(f"Lubuk Pakam, {_date_id(data['published_date'])}", styles["right"]),
        _safe_paragraph("Kepala Kejaksaan Negeri Deli Serdang", styles["right"]),
        Spacer(1, 0.12 * cm),
        _safe_paragraph("Dto.", styles["right"]),
        Spacer(1, 0.42 * cm),
        _safe_paragraph(KEPALA_NAMA, styles["right"]),
        _safe_paragraph(KEPALA_PANGKAT, styles["right"]),
        _safe_paragraph(f"NIP.{KEPALA_NIP}", styles["right"]),
        Spacer(1, 0.45 * cm),
        _safe_paragraph("Otentikasi :", styles["body"]),
        _safe_paragraph("Kepala Seksi Intelijen", styles["body"]),
        _safe_paragraph("Kejaksaan Negeri Deli Serdang", styles["body"]),
        Spacer(1, 0.42 * cm),
        _safe_paragraph(AUTENTIKASI_NAMA, styles["body"]),
        _safe_paragraph(AUTENTIKASI_PANGKAT, styles["body"]),
        _safe_paragraph(f"NIP. {AUTENTIKASI_NIP}", styles["body"]),
        PageBreak(),
    ]

    # PAGE 4 — first two article images
    story += [
        Spacer(1, 0.2 * cm),
        _safe_paragraph("DOKUMENTASI", styles["title"]),
        Spacer(1, 0.15 * cm),
    ]
    images = list(data.get("images") or [])
    rendered = 0
    for url in images[:2]:
        img = _image_flowable(url, 17.5 * cm, 8.0 * cm)
        if img:
            story += [img, Spacer(1, 0.3 * cm)]
            rendered += 1
    if rendered == 0:
        story.append(
            _safe_paragraph(
                "Dokumentasi gambar tidak tersedia atau tidak dapat diunduh dari sumber artikel.",
                styles["center"],
            )
        )
    story.append(PageBreak())

    # PAGE 5 — additional image
    story += [
        Spacer(1, 0.2 * cm),
        _safe_paragraph("DOKUMENTASI", styles["title"]),
        Spacer(1, 0.15 * cm),
    ]
    rendered_extra = 0
    for url in images[2:5]:
        img = _image_flowable(url, 17.5 * cm, 9.5 * cm)
        if img:
            story += [img, Spacer(1, 0.3 * cm)]
            rendered_extra += 1
            break
    if rendered_extra == 0:
        story.append(
            _safe_paragraph(
                "Dokumentasi tambahan tidak tersedia dari sumber artikel yang berhasil diakses.",
                styles["center"],
            )
        )

    doc.build(story)
    return buffer.getvalue()


def mark_generated(article_id, pdf_bytes, data):
    generated_at = datetime.now(timezone.utc).isoformat()
    filename = f"LAPINSUS_{article_id}.pdf"
    payload = {
        "filename": filename,
        "generated_at": generated_at,
        "sha256": hashlib.sha256(pdf_bytes).hexdigest(),
        "template": TEMPLATE_VERSION,
        "status": "DRAFT_REQUIRES_VERIFICATION",
        "report_number": data["report_number"],
        "source_link": data.get("resolved_link") or data.get("link"),
    }
    try:
        response = (
            get_supabase()
            .table(TABLE)
            .update(
                {
                    "lapinsus_status": "GENERATED",
                    "lapinsus_generated_at": generated_at,
                    "lapinsus_document": payload,
                }
            )
            .eq("id", article_id)
            .execute()
        )
        return bool(response.data is not None)
    except Exception as exc:
        st.warning(
            f"PDF berhasil dibuat, tetapi metadata belum tersimpan: "
            f"{type(exc).__name__}: {exc}"
        )
        return False


def mark_failed(article_id, error):
    try:
        get_supabase().table(TABLE).update(
            {
                "lapinsus_status": "FAILED",
                "lapinsus_document": {
                    "template": TEMPLATE_VERSION,
                    "status": "FAILED",
                    "error": str(error)[:1000],
                },
            }
        ).eq("id", article_id).execute()
    except Exception:
        pass
