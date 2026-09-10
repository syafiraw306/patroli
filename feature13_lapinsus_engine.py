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
from reportlab.platypus import BaseDocTemplate, Frame, Image as RLImage, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle

from database import get_supabase

TABLE = "deli_serdang_location_articles"
TEMPLATE_VERSION = "LAPINSUS_DELI_SERDANG_V4_5PAGES"

import os
KEPALA_NAMA = os.getenv("LAPINSUS_KEPALA_NAMA", "SAPTA PUTRA, S.H., M. Hum.")
KEPALA_PANGKAT = os.getenv("LAPINSUS_KEPALA_PANGKAT", "Jaksa Utama Pratama")
KEPALA_NIP = os.getenv("LAPINSUS_KEPALA_NIP", "19740312 199903 1 006")
AUTENTIKASI_NAMA = os.getenv("LAPINSUS_AUTENTIKASI_NAMA", "ROBY SYAHPUTRA, S.H., M.H.")
AUTENTIKASI_PANGKAT = os.getenv("LAPINSUS_AUTENTIKASI_PANGKAT", "Jaksa Madya")
AUTENTIKASI_NIP = os.getenv("LAPINSUS_AUTENTIKASI_NIP", "19801020 200712 1002")

ARTICLE_SELECTORS = [
    "div.detail__body-text", "div.detail__body", "div.detail__article",
    "div.article__content", "div.read__content", "div.content-detail",
    "div.post-content", "div.entry-content", "div.article-content",
    "div.article-body", "[itemprop='articleBody']", "article",
]
REMOVE_SELECTORS = [
    "script", "style", "noscript", "svg", "nav", "header", "footer",
    ".share", ".sharing", ".social", ".related", ".recommend", ".recommended",
    ".advert", ".ads", ".iklan", ".comment", ".comments", ".breadcrumb",
    ".sticky", ".newsletter", ".video", ".tags", ".read-also",
]
CHROME_PATTERNS = re.compile(
    r"tautan telah disalin|scroll to continue|anda menyukai artikel ini|artikel disimpan|baca juga|advertisement|terpopuler|komentar",
    re.I,
)

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


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def clean_article_content(value):
    if not value:
        return ""
    text = str(value)
    if "<" in text and ">" in text:
        soup = BeautifulSoup(html_lib.unescape(text), "html.parser")
        for node in soup(REMOVE_SELECTORS):
            node.decompose()
        text = soup.get_text(" ", strip=True)
    return _clean(html_lib.unescape(text))


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
    months = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
    dt = _parse_date(value)
    return f"{dt.day} {months[dt.month - 1]} {dt.year}" if dt else "Tanggal tidak tersedia"


def _report_number(article_id):
    try:
        seq = int(article_id)
    except Exception:
        seq = 0
    return f"R-LIK-{seq:03d}/L.2.14/Dsb.4/{datetime.now().strftime('%m/%Y')}"


def get_location_articles(limit=1000):
    try:
        return get_supabase().table(TABLE).select("*").order("published_date", desc=True).limit(limit).execute().data or []
    except Exception as exc:
        st.error(f"Gagal membaca {TABLE}: {type(exc).__name__}: {exc}")
        return []


def _is_google_news(url):
    return "news.google.com" in str(url or "").lower()


def _extract_article_text_from_soup(soup):
    candidates = []
    for selector in ARTICLE_SELECTORS:
        for node in soup.select(selector):
            text = _clean(node.get_text(" ", strip=True))
            if len(text) < 120:
                continue
            score = len(text)
            penalty = len(CHROME_PATTERNS.findall(text)) * 300
            candidates.append((score - penalty, text))
    if not candidates:
        return ""
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def _resolve_link_and_fetch(url):
    if not url:
        return "", "", []
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"}, allow_redirects=True)
        r.raise_for_status()
        resolved = r.url
        soup = BeautifulSoup(r.text, "html.parser")
        canonical = soup.select_one("link[rel='canonical']")
        if canonical and canonical.get("href"):
            resolved = canonical["href"]
        og = soup.select_one("meta[property='og:url']")
        if og and og.get("content"):
            resolved = og["content"]
        if _is_google_news(resolved):
            for a in soup.select("a[href]"):
                href = a.get("href", "")
                if href.startswith("http") and "google.com" not in href:
                    resolved = href
                    break
        if resolved != url:
            try:
                rr = requests.get(resolved, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
                rr.raise_for_status()
                soup = BeautifulSoup(rr.text, "html.parser")
            except Exception:
                pass
        text = _extract_article_text_from_soup(soup)
        if not text:
            text = _clean(soup.get_text(" ", strip=True))
        images = []
        for selector in ("meta[property='og:image']", "meta[name='twitter:image']"):
            node = soup.select_one(selector)
            if node and node.get("content"):
                images.append(node["content"])
        for img in soup.select("img[src]"):
            src = img.get("src")
            if src and src.startswith("http"):
                images.append(src)
        dedup = []
        seen = set()
        for img in images:
            if img not in seen:
                seen.add(img); dedup.append(img)
        return resolved, text, dedup[:12]
    except Exception:
        return url, "", []


def get_article_source_text(article):
    stored = clean_article_content(article.get("content"))
    link = _clean(article.get("link"))
    needs_fetch = _is_google_news(link) or len(stored) < 350
    if needs_fetch and link:
        resolved, fetched, images = _resolve_link_and_fetch(link)
        if fetched:
            return {"text": fetched, "images": images, "resolved_link": resolved}
    images = article.get("article_images") or []
    return {"text": stored, "images": images, "resolved_link": link}


def extract_issue_topics(title, content):
    text = _clean(f"{title or ''} {content or ''}").lower()
    found = []
    for label, patterns in ISSUE_TOPIC_RULES.items():
        if any(re.search(p, text, re.I) for p in patterns):
            found.append(label)
    return found


def _extract_sentences(content, max_items=18):
    text = clean_article_content(content)
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+", text)
    out = []
    for part in parts:
        part = _clean(part).strip("-•")
        if len(part) >= 35 and not CHROME_PATTERNS.search(part):
            out.append(part)
        if len(out) >= max_items:
            break
    return out


def _trend_sentences(text, max_items=5):
    patterns = r"\bakan\b|\brencana\b|\bberencana\b|\bdirencanakan\b|\bditargetkan\b|\btarget\b|\bdiproyeksikan\b|\bke depan\b|\bselanjutnya\b|\bberikutnya\b|\bdilanjutkan\b|\bmelanjutkan\b|\bpengembangan\b|\bpercepatan\b|\bdianggarkan\b|\bdibangun\b|\bditingkatkan\b|\bakan dimulai\b|\bsedang\b|\bdalam proses\b|\bproses tender\b|\btender\b|\bterdaftar\b|\bberlangsung\b|\bdimulai\b|\bmulai\b|\btahun ini\b"
    return [s for s in _extract_sentences(text, max_items=30) if re.search(patterns, s, re.I)][:max_items]


def build_lapinsus(article):
    title = _clean(article.get("title")) or "Tanpa Judul"
    published = _date_id(article.get("published_date"))
    source = _clean(article.get("publisher") or article.get("source")) or "Tidak tersedia"
    link = _clean(article.get("link"))
    keywords = article.get("matched_location_keywords") or []
    source_data = get_article_source_text(article)
    content = source_data["text"]
    sentences = _extract_sentences(content)
    allegation_words = r"diduga|dugaan|disinyalir|menurut|disebut|kabarnya|tuding|tuduhan"
    facts = [f"{s} [PERLU VERIFIKASI]" if re.search(allegation_words, s, re.I) else s for s in sentences[:10]]
    if not facts:
        facts = ["Tidak terdapat cukup teks artikel sumber untuk mengekstrak fakta. Verifikasi sumber asli diperlukan."]
    trend = _trend_sentences(content)
    if not trend:
        trend = ["Artikel tidak memuat proyeksi lanjutan yang eksplisit. Perkembangan berikutnya perlu dimonitor berdasarkan sumber asli."]
    actions = [
        "Melakukan verifikasi terhadap informasi utama pada sumber primer dan/atau pihak terkait.",
        "Melakukan monitoring perkembangan pemberitaan dan situasi pada lokasi yang teridentifikasi.",
        "Melaporkan perkembangan penting kepada pimpinan sesuai kebutuhan.",
    ]
    return {
        "article_id": article.get("id"), "title": title, "published_date": published,
        "source": source, "link": source_data.get("resolved_link") or link,
        "locations": ", ".join(map(str, keywords)) if keywords else "Tidak teridentifikasi",
        "facts": facts, "trend": trend, "actions": actions,
        "images": source_data.get("images") or article.get("article_images") or [],
        "report_number": _report_number(article.get("id")),
        "issue_topics": extract_issue_topics(title, content),
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


def _safe_xml(text):
    return html_lib.escape(_clean(text), quote=False)


def _p(text, style):
    return Paragraph(_safe_xml(text).replace("\n", "<br/>") , style)


def _bullet(text, style):
    return Paragraph(f"- {_safe_xml(text)}", style)


def _header(canvas, doc):
    canvas.saveState(); canvas.setFont("Times-Bold", 11)
    canvas.drawCentredString(A4[0] / 2, A4[1] - 0.75 * cm, "R A H A S I A")
    canvas.setFont("Times-Roman", 8)
    canvas.drawRightString(A4[0] - 1.6 * cm, 0.8 * cm, f"Halaman {doc.page}")
    canvas.restoreState()


def _image_flowable(url, max_width, max_height):
    try:
        response = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"}); response.raise_for_status()
        data = io.BytesIO(response.content); reader = ImageReader(data); iw, ih = reader.getSize()
        if not iw or not ih: return None
        scale = min(max_width / iw, max_height / ih, 1.0)
        img = RLImage(data, width=iw * scale, height=ih * scale); img.hAlign = "CENTER"; return img
    except Exception:
        return None

# Keep the existing 5-page LAPINSUS layout below this line.
def make_pdf(data):
    buffer = io.BytesIO(); styles = _styles()
    doc = BaseDocTemplate(buffer, pagesize=A4, rightMargin=1.55*cm, leftMargin=1.55*cm, topMargin=1.45*cm, bottomMargin=1.35*cm, title=f"LAPINSUS {data['report_number']}", author="Kejaksaan Negeri Deli Serdang")
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    doc.addPageTemplates([PageTemplate(id="all", frames=frame, onPage=_header)])
    story=[]
    story += [Spacer(1,.75*cm), _p("KEJAKSAAN NEGERI\nDELI SERDANG",styles["center_bold"]), Spacer(1,.55*cm), _p(f"Lubuk Pakam, {data['published_date']}",styles["body"]), Spacer(1,.25*cm), _p("KEPADA YTH :\nBAPAK KEPALA KEJAKSAAN\nTINGGI SUMATERA UTARA\nDI -\n\nM E D A N",styles["body"]), Spacer(1,.35*cm), _p("SURAT PENGANTAR",styles["center_bold"]), _p(f"Nomor : {data['report_number']}",styles["center"]), Spacer(1,.35*cm)]
    table_data=[[ _p("NOMOR",styles["center_bold"]),_p("ISI SINGKAT",styles["center_bold"]),_p("BANYAKNYA",styles["center_bold"]),_p("KETERANGAN",styles["center_bold"]) ],["",[_p("LAPORAN INFORMASI KHUSUS",styles["center_bold"]),Spacer(1,.15*cm),_p(data["title"],styles["body_small"])],_p("1 (satu) set",styles["center"]),_p("Bersama ini dengan hormat Kami kirimkan kepada Bapak Laporan Informasi Khusus.\n\nDemikian agar Bapak maklum dan menjadi periksa",styles["body_small"])]]
    t=Table(table_data,colWidths=[1.8*cm,8.3*cm,3*cm,4*cm],rowHeights=[.8*cm,6.3*cm]); t.setStyle(TableStyle([("GRID",(0,0),(-1,-1),.7,colors.black),("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),5),("RIGHTPADDING",(0,0),(-1,-1),5),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]))
    story += [t,Spacer(1,.5*cm),_p("KEPALA KEJAKSAAN NEGERI DELI SERDANG",styles["center_bold"]),Spacer(1,.15*cm),_p("Dto.",styles["center_bold"]),Spacer(1,.45*cm),_p(KEPALA_NAMA,styles["center_bold"]),_p(KEPALA_PANGKAT,styles["center"]),_p(f"NIP.{KEPALA_NIP}",styles["center"]),Spacer(1,.65*cm),_p("TEMBUSAN :",styles["body"]),_p("1. Yth. Wakil Kepala Kejaksaan Tinggi Sumatera Utara\n2. Yth. Asisten Intelijen Kejaksaan Tinggi Sumatera Utara\n3. Yth. Asisten Pengawasan Kejaksaan Tinggi Sumatera Utara\n4. A r s i p .",styles["body_small"]),PageBreak()]
    story += [Spacer(1,.25*cm),_p("KEJAKSAAN NEGERI DELI SERDANG",styles["center_bold"]),Spacer(1,.25*cm),_p("COPY KE :",styles["body"]),_p("DARI COPIES",styles["body"]),Spacer(1,.25*cm),_p("LAPORAN INFORMASI KHUSUS",styles["title"]),_p(f"NOMOR : {data['report_number']}",styles["center_bold"]),Spacer(1,.15*cm),_p(f"PERIHAL: {data['title']}",styles["body"]),_p("_"*112,styles["tiny"]),Spacer(1,.2*cm),_p("I. INFORMASI YANG DIPEROLEH :",styles["section"])]
    story += [_bullet(x,styles["body"]) for x in data["facts"]]; story += [PageBreak()]
    story += [Spacer(1,.25*cm),_p("II. SUMBER INFORMASI :",styles["section"]),_p(f"Sumber: {data['source']}. Tautan: {data['link']}",styles["body"]),_p("Informasi berasal dari pemberitaan media dan tetap memerlukan verifikasi terhadap sumber primer/pihak terkait.",styles["body"]),_p("III. TREND PERKEMBANGAN / PERKIRAAN :",styles["section"])]
    story += [_bullet(x,styles["body"]) for x in data["trend"]] + [_p("IV. SARAN / TINDAK :",styles["section"])] + [Paragraph(f"{i}. {_safe_xml(x)}",styles["body"]) for i,x in enumerate(data["actions"],1)]
    story += [Spacer(1,.1*cm),_p("Demikian agar Bapak maklum adanya dan perkembangan selanjutnya akan kami laporkan dalam kesempatan pertama.",styles["body"]),Spacer(1,.2*cm),_p(f"Lubuk Pakam, {data['published_date']}",styles["right"]),_p("Kepala Kejaksaan Negeri Deli Serdang",styles["right"]),Spacer(1,.12*cm),_p("Dto.",styles["right"]),Spacer(1,.42*cm),_p(KEPALA_NAMA,styles["right"]),_p(KEPALA_PANGKAT,styles["right"]),_p(f"NIP.{KEPALA_NIP}",styles["right"]),Spacer(1,.45*cm),_p("Otentikasi :",styles["body"]),_p("Kepala Seksi Intelijen\nKejaksaan Negeri Deli Serdang",styles["body"]),Spacer(1,.42*cm),_p(AUTENTIKASI_NAMA,styles["body"]),_p(AUTENTIKASI_PANGKAT,styles["body"]),_p(f"NIP. {AUTENTIKASI_NIP}",styles["body"]),PageBreak()]
    images=list(data.get("images") or []); story += [Spacer(1,.2*cm),_p("DOKUMENTASI",styles["title"]),Spacer(1,.15*cm)]
    rendered=0
    for url in images[:2]:
        img=_image_flowable(url,17.5*cm,8*cm)
        if img: story += [img,Spacer(1,.3*cm)]; rendered += 1
    if rendered==0: story.append(_p("Dokumentasi gambar tidak tersedia pada sumber artikel yang dapat diakses.",styles["center"]))
    story.append(PageBreak()); story += [Spacer(1,.2*cm),_p("DOKUMENTASI",styles["title"]),Spacer(1,.15*cm)]
    rendered2=0
    for url in images[2:5]:
        img=_image_flowable(url,17.5*cm,9.5*cm)
        if img: story += [img,Spacer(1,.3*cm)]; rendered2 += 1
    if rendered2==0: story.append(_p("Dokumentasi tambahan tidak tersedia pada sumber artikel yang dapat diakses.",styles["center"]))
    doc.build(story); return buffer.getvalue()


def mark_generated(article_id, pdf_bytes, data):
    generated_at=datetime.now(timezone.utc).isoformat(); filename=f"LAPINSUS_{article_id}.pdf"
    payload={"filename":filename,"generated_at":generated_at,"sha256":hashlib.sha256(pdf_bytes).hexdigest(),"template":TEMPLATE_VERSION,"status":"DRAFT_REQUIRES_VERIFICATION","report_number":data["report_number"],"source_link":data["link"]}
    try:
        response=get_supabase().table(TABLE).update({"lapinsus_status":"GENERATED","lapinsus_generated_at":generated_at,"lapinsus_document":payload}).eq("id",article_id).execute()
        return bool(response.data is not None)
    except Exception as exc:
        st.warning(f"PDF berhasil dibuat, tetapi metadata belum tersimpan: {type(exc).__name__}: {exc}"); return False


def mark_failed(article_id,error):
    try:
        get_supabase().table(TABLE).update({"lapinsus_status":"FAILED","lapinsus_document":{"template":TEMPLATE_VERSION,"status":"FAILED","error":str(error)[:1000]}}).eq("id",article_id).execute()
    except Exception:
        pass
