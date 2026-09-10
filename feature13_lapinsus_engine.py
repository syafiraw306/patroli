import hashlib
import html as html_lib
import io
import re
from datetime import datetime, timezone

import requests
import streamlit as st
from bs4 import BeautifulSoup
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
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
    Table,
    TableStyle,
)

from database import get_supabase
from feature13_lapinsus_ai import generate_ai_lapinsus, fetch_source_article

TABLE = "deli_serdang_location_articles"
TEMPLATE_VERSION = "LAPINSUS_DELI_SERDANG_AI_V1_3_5PAGES"

# Nilai default mengikuti dokumen contoh yang diberikan sebagai template.
# Seluruh identitas dapat dioverride melalui environment variable bila terjadi perubahan pejabat.
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
    """Convert stored RSS/HTML article content into readable plain text."""
    if not value:
        return ""
    text = str(value)
    if "<" in text and ">" in text:
        soup = BeautifulSoup(html_lib.unescape(text), "html.parser")
        for node in soup.select(
            "script, style, noscript, svg, nav, header, footer, "
            ".share, .sharing, .social, .related, .recommend, .recommended, "
            ".advert, .ads, .iklan, .comment, .comments, .breadcrumb, "
            ".sticky, .newsletter, .video, .tags, .read-also"
        ):
            node.decompose()
        text = soup.get_text(" ", strip=True)
    return _clean(html_lib.unescape(text))


ISSUE_TOPIC_RULES = {
    "Narkotika": [r"\bnarkoba\b", r"\bnarkotika\b", r"\bsabu\b", r"\bganja\b", r"\bkokain\b", r"\becstasy\b", r"\bpil ekstasi\b"],
    "Penganiayaan": [r"penganiayaan", r"aniaya", r"dianiaya", r"menganiaya"],
    "Pencurian": [r"pencurian", r"mencuri", r"dicuri", r"curanmor", r"pencuri"],
    "Pembunuhan": [r"pembunuhan", r"membunuh", r"dibunuh", r"tewas dibunuh"],
    "Penipuan": [r"penipuan", r"menipu", r"ditipu", r"penipu"],
    "Korupsi": [r"korupsi", r"korupt", r"gratifikasi"],
    "Suap / Gratifikasi": [r"suap", r"menyuap", r"disuap", r"gratifikasi"],
    "Judi": [r"perjudian", r"judi online", r"judi", r"togel", r"slot online"],
    "Kekerasan Seksual": [r"kekerasan seksual", r"pelecehan seksual", r"pemerkosaan", r"perkosaan", r"pencabulan"],
    "KDRT": [r"kdrt", r"kekerasan dalam rumah tangga"],
    "Kecelakaan": [r"kecelakaan", r"tabrakan", r"lakalantas", r"laka lantas"],
    "Banjir": [r"\bbanjir\b", r"terendam", r"genangan"],
    "Longsor": [r"longsor", r"tanah longsor"],
    "Karhutla": [r"karhutla", r"kebakaran hutan", r"kebakaran lahan"],
    "Kebakaran": [r"kebakaran", r"terbakar", r"dilalap api"],
    "Infrastruktur": [r"infrastruktur", r"jalan rusak", r"jembatan", r"pembangunan jalan", r"rsud", r"rumah sakit", r"gedung"],
    "Kesehatan": [r"kesehatan", r"rumah sakit", r"rsud", r"puskesmas", r"pasien", r"dokter"],
    "Pendidikan": [r"pendidikan", r"sekolah", r"siswa", r"guru", r"universitas", r"kampus"],
    "Lingkungan": [r"lingkungan", r"sampah", r"limbah", r"pencemaran", r"sungai", r"hutan"],
    "Konflik / Kamtibmas": [r"konflik", r"keributan", r"bentrok", r"kamtibmas", r"tawuran", r"gangguan keamanan"],
    "Pertanahan / Sengketa": [r"sengketa tanah", r"sengketa lahan", r"pertanahan", r"sertifikat tanah", r"konflik lahan"],
    "Anggaran / Pemerintahan": [r"anggaran", r"apbd", r"pemkab", r"pemerintah kabupaten", r"bupati", r"dprd"],
}


def extract_issue_topics(title, content):
    text = _clean(f"{title or ''} {content or ''}").lower()
    found = []
    for label, patterns in ISSUE_TOPIC_RULES.items():
        if any(re.search(p, text, re.I) for p in patterns):
            found.append(label)
    return found


def get_article_source_text(article):
    """Panel-compatible adapter around the AI V1 source resolver."""
    source = fetch_source_article(article)
    return {
        "text": clean_article_content(source.get("text")),
        "images": source.get("images") or article.get("article_images") or [],
        "resolved_link": source.get("resolved_link") or _clean(article.get("link")),
    }


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
    # Deterministik dan tidak memerlukan tabel sequence baru.
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
    for part in parts:
        part = _clean(part).strip("-•")
        if len(part) >= 35:
            out.append(part)
        if len(out) >= max_items:
            break
    return out


def build_lapinsus(article):
    """Build an evidence-grounded LAPINSUS draft using AI.

    The AI receives only the resolved source article and numbered source
    sentences. Its structured output is validated before reaching the PDF
    renderer. No generic facts are silently substituted on API failure.
    """
    title = _clean(article.get("title")) or "Tanpa Judul"
    published = _date_id(article.get("published_date"))
    source_name = _clean(article.get("publisher") or article.get("source")) or "Tidak tersedia"
    link = _clean(article.get("link"))
    keywords = article.get("matched_location_keywords") or []

    source = fetch_source_article(article)
    ai = generate_ai_lapinsus(article, source=source)

    return {
        "article_id": article.get("id"),
        "title": ai.get("perihal") or title,
        "published_date": published,
        "source": source_name,
        "link": _clean(ai.get("resolved_link") or link),
        "locations": ", ".join(map(str, keywords)) if keywords else "Tidak teridentifikasi",
        "facts": ai["facts"],
        "trend": ai["trend"],
        "actions": ai["actions"],
        "source_statement": ai["source_statement"],
        "images": ai.get("images") or [],
        "report_number": _report_number(article.get("id")),
        "ai_model": ai.get("model"),
        "grounding": ai.get("grounding", {}),
        "ai_version": ai.get("ai_version"),
        "source_extraction_method": ai.get("source_extraction_method"),
        "source_sentence_count": ai.get("source_sentence_count", 0),
        "source_material_highlights": ai.get("source_material_highlights") or [],
    }


def _styles():
    base = getSampleStyleSheet()
    return {
        "body": ParagraphStyle("BodyL", parent=base["BodyText"], fontName="Times-Roman", fontSize=10.5, leading=14, spaceAfter=4),
        "body_small": ParagraphStyle("BodyS", parent=base["BodyText"], fontName="Times-Roman", fontSize=9, leading=12),
        "center": ParagraphStyle("Center", parent=base["BodyText"], fontName="Times-Roman", fontSize=10.5, leading=14, alignment=TA_CENTER),
        "center_bold": ParagraphStyle("CenterBold", parent=base["BodyText"], fontName="Times-Bold", fontSize=10.5, leading=14, alignment=TA_CENTER),
        "section": ParagraphStyle("Section", parent=base["Heading2"], fontName="Times-Bold", fontSize=10.5, leading=14, spaceBefore=7, spaceAfter=5),
        "title": ParagraphStyle("DocTitle", parent=base["Title"], fontName="Times-Bold", fontSize=13, leading=16, alignment=TA_CENTER, spaceAfter=4),
        "right": ParagraphStyle("Right", parent=base["BodyText"], fontName="Times-Roman", fontSize=10.5, leading=14, alignment=TA_RIGHT),
        "tiny": ParagraphStyle("Tiny", parent=base["BodyText"], fontName="Times-Roman", fontSize=8, leading=10),
    }


def _p(text, style):
    return Paragraph(_clean(text).replace("&", "&amp;"), style)


def _bullet(text, style):
    safe = _clean(text).replace("&", "&amp;")
    return Paragraph(f"- {safe}", style)


def _header(canvas, doc):
    canvas.saveState()
    canvas.setFont("Times-Bold", 11)
    canvas.drawCentredString(A4[0] / 2, A4[1] - 0.75 * cm, "R A H A S I A")
    canvas.setFont("Times-Roman", 8)
    canvas.drawRightString(A4[0] - 1.6 * cm, 0.8 * cm, f"Halaman {doc.page}")
    canvas.restoreState()


def _image_flowable(url, max_width, max_height):
    try:
        response = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
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
        title=f"LAPINSUS {data['report_number']}",
        author="Kejaksaan Negeri Deli Serdang",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    doc.addPageTemplates([PageTemplate(id="all", frames=frame, onPage=_header)])

    story = []

    # ==================== PAGE 1 ====================
    story += [
        Spacer(1, 0.75 * cm),
        _p("KEJAKSAAN NEGERI<br/>DELI SERDANG", styles["center_bold"]),
        Spacer(1, 0.55 * cm),
        _p(f"Lubuk Pakam, {_date_id(data['published_date'])}", styles["body"]),
        Spacer(1, 0.25 * cm),
        _p("KEPADA YTH :<br/>BAPAK KEPALA KEJAKSAAN<br/>TINGGI SUMATERA UTARA<br/>DI -<br/><br/><u>M E D A N</u>", styles["body"]),
        Spacer(1, 0.35 * cm),
        _p("<u>SURAT PENGANTAR</u>", styles["center_bold"]),
        _p(f"Nomor : {data['report_number']}", styles["center"]),
        Spacer(1, 0.35 * cm),
    ]
    short_title = data["title"]
    table_data = [
        [_p("NOMOR", styles["center_bold"]), _p("ISI SINGKAT", styles["center_bold"]), _p("BANYAKNYA", styles["center_bold"]), _p("KETERANGAN", styles["center_bold"])],
        [
            "",
            [_p("LAPORAN INFORMASI KHUSUS", styles["center_bold"]), Spacer(1, 0.15 * cm), _p(short_title, styles["body_small"])],
            _p("1 (satu) set", styles["center"]),
            _p("Bersama ini dengan hormat Kami kirimkan kepada Bapak Laporan Informasi Khusus.<br/><br/>Demikian agar Bapak maklum dan menjadi periksa", styles["body_small"]),
        ],
    ]
    t = Table(table_data, colWidths=[1.8 * cm, 8.3 * cm, 3.0 * cm, 4.0 * cm], rowHeights=[0.8 * cm, 6.3 * cm])
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.7, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [t, Spacer(1, 0.5 * cm), _p("KEPALA KEJAKSAAN NEGERI DELI SERDANG", styles["center_bold"]), Spacer(1, 0.15 * cm), _p("Dto.", styles["center_bold"]), Spacer(1, 0.45 * cm), _p(KEPALA_NAMA, styles["center_bold"]), _p(KEPALA_PANGKAT, styles["center"]), _p(f"NIP.{KEPALA_NIP}", styles["center"]), Spacer(1, 0.65 * cm), _p("TEMBUSAN :", styles["body"]), _p("1. Yth. Wakil Kepala Kejaksaan Tinggi Sumatera Utara<br/>2. Yth. Asisten Intelijen Kejaksaan Tinggi Sumatera Utara<br/>3. Yth. Asisten Pengawasan Kejaksaan Tinggi Sumatera Utara<br/>4. A r s i p .", styles["body_small"]), PageBreak()]

    # ==================== PAGE 2 ====================
    story += [
        Spacer(1, 0.25 * cm),
        _p("KEJAKSAAN NEGERI DELI SERDANG", styles["center_bold"]),
        Spacer(1, 0.25 * cm),
        _p("COPY KE :", styles["body"]),
        _p("DARI COPIES", styles["body"]),
        Spacer(1, 0.25 * cm),
        _p("LAPORAN INFORMASI KHUSUS", styles["title"]),
        _p(f"NOMOR : {data['report_number']}", styles["center_bold"]),
        Spacer(1, 0.15 * cm),
        _p(f"PERIHAL: {data['title']}", styles["body"]),
        _p("_" * 112, styles["tiny"]),
        Spacer(1, 0.2 * cm),
        _p("I. INFORMASI YANG DIPEROLEH :", styles["section"]),
    ]
    story += [_bullet(x, styles["body"]) for x in data["facts"]]
    story += [PageBreak()]

    # ==================== PAGE 3 ====================
    story += [
        Spacer(1, 0.25 * cm),
        _p("II. SUMBER INFORMASI :", styles["section"]),
        _p(data.get("source_statement") or "Bahwa informasi diperoleh dari pemberitaan media yang tercantum pada sumber artikel dan masih memerlukan verifikasi terhadap sumber primer/pihak terkait.", styles["body"]),
        _p("III. TREND PERKEMBANGAN / PERKIRAAN :", styles["section"]),
    ]
    story += [_bullet(x, styles["body"]) for x in data["trend"]]
    story += [_p("IV. SARAN / TINDAK :", styles["section"])]
    story += [Paragraph(f"{i}. {_clean(x)}", styles["body"]) for i, x in enumerate(data["actions"], 1)]
    story += [
        Spacer(1, 0.1 * cm),
        _p("Demikian agar Bapak maklum adanya dan perkembangan selanjutnya akan kami laporkan dalam kesempatan pertama.", styles["body"]),
        Spacer(1, 0.2 * cm),
        _p(f"Lubuk Pakam, {_date_id(data['published_date'])}", styles["right"]),
        _p("Kepala Kejaksaan Negeri Deli Serdang", styles["right"]),
        Spacer(1, 0.12 * cm),
        _p("Dto.", styles["right"]),
        Spacer(1, 0.42 * cm),
        _p(KEPALA_NAMA, styles["right"]),
        _p(KEPALA_PANGKAT, styles["right"]),
        _p(f"NIP.{KEPALA_NIP}", styles["right"]),
        Spacer(1, 0.45 * cm),
        _p("Otentikasi :", styles["body"]),
        _p("Kepala Seksi Intelijen<br/>Kejaksaan Negeri Deli Serdang", styles["body"]),
        Spacer(1, 0.42 * cm),
        _p(AUTENTIKASI_NAMA, styles["body"]),
        _p(AUTENTIKASI_PANGKAT, styles["body"]),
        _p(f"NIP. {AUTENTIKASI_NIP}", styles["body"]),
        PageBreak(),
    ]

    # ==================== PAGE 4 ====================
    story += [Spacer(1, 0.2 * cm), _p("DOKUMENTASI", styles["title"]), Spacer(1, 0.15 * cm)]
    images = list(data.get("images") or [])
    rendered = 0
    for url in images[:2]:
        img = _image_flowable(url, 17.5 * cm, 8.0 * cm)
        if img:
            story += [img, Spacer(1, 0.3 * cm)]
            rendered += 1
    if rendered == 0:
        story.append(_p("Dokumentasi gambar tidak tersedia pada data artikel yang tersimpan.", styles["center"]))
    story.append(PageBreak())

    # ==================== PAGE 5 ====================
    story += [Spacer(1, 0.2 * cm), _p("DOKUMENTASI", styles["title"]), Spacer(1, 0.15 * cm)]
    third = images[2:5]
    for url in third[:1]:
        img = _image_flowable(url, 17.5 * cm, 9.5 * cm)
        if img:
            story += [img, Spacer(1, 0.3 * cm)]
    if not third:
        story.append(_p("Dokumentasi tambahan tidak tersedia pada data artikel yang tersimpan.", styles["center"]))

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
        "source_link": data["link"],
    }
    try:
        response = (
            get_supabase().table(TABLE)
            .update({"lapinsus_status": "GENERATED", "lapinsus_generated_at": generated_at, "lapinsus_document": payload})
            .eq("id", article_id).execute()
        )
        return bool(response.data is not None)
    except Exception as exc:
        st.warning(f"PDF berhasil dibuat, tetapi metadata belum tersimpan: {type(exc).__name__}: {exc}")
        return False


def mark_failed(article_id, error):
    try:
        get_supabase().table(TABLE).update({
            "lapinsus_status": "FAILED",
            "lapinsus_document": {"template": TEMPLATE_VERSION, "status": "FAILED", "error": str(error)[:1000]},
        }).eq("id", article_id).execute()
    except Exception:
        pass




# Feature #13 engine module: UI is intentionally omitted.

