import sys
from unittest.mock import patch

sys.path.insert(0, ".")
import feature13_lapinsus_engine as e

ARTICLE_HTML = """
<html><body>
<header>MENU</header>
<div class='detail__body-text'>
<p>Medan - Pemkab Deli Serdang berencana meningkatkan RSUD Bangun Purba menjadi tipe C.</p>
<p>Anggaran digelontorkan Rp 11,9 miliar untuk pembangunan RSUD Bangun Purba tahun ini.</p>
<p>Proyek ini memiliki kode paket 10164331000.</p>
<p>Proyek ini berada di bawah Dinas Cipta Karya dan Tata Ruang Deli Serdang.</p>
<p>Anggaran untuk proyek dengan metode tender ini sebesar Rp 11,9 miliar bersumber dari APBD Deli Serdang 2026.</p>
<p>Saat ini proses tender masih berlangsung. Terdapat 12 perusahaan yang mendaftar untuk tender sejauh ini.</p>
</div>
<div class='related'>Baca juga artikel lain</div>
</body></html>
"""


def check(cond, label):
    if not cond:
        raise AssertionError(label)
    print("[PASS]", label)


def main():
    cleaned = e.clean_article_content("<a href='x'>Pemkab</a> Deli Serdang")
    check("<a" not in cleaned and "Pemkab Deli Serdang" in cleaned, "HTML cleaning")

    topics = e.extract_issue_topics(
        "Pemkab Deli Serdang Anggarkan Rp 11,9 M Bangun RSUD Bangun Purba Jadi Tipe C",
        "RSUD Bangun Purba pembangunan rumah sakit APBD tender"
    )
    check("Kesehatan" in topics and "Infrastruktur" in topics, "Specific issue topics")

    with patch.object(e, "_fetch_article_page", return_value=(
        e._clean(e.html.unescape(e.BeautifulSoup(ARTICLE_HTML, "html.parser").get_text(" ", strip=True))),
        ["https://example.com/image.jpg"],
    )):
        # Patch the stronger extractor directly for deterministic regression.
        with patch.object(e, "_article_grounding", return_value=(
            "Medan - Pemkab Deli Serdang berencana meningkatkan RSUD Bangun Purba menjadi tipe C. "
            "Anggaran digelontorkan Rp 11,9 miliar untuk pembangunan RSUD Bangun Purba tahun ini. "
            "Proyek ini memiliki kode paket 10164331000. Proyek ini berada di bawah Dinas Cipta Karya dan Tata Ruang Deli Serdang. "
            "Anggaran untuk proyek dengan metode tender ini sebesar Rp 11,9 miliar bersumber dari APBD Deli Serdang 2026. "
            "Saat ini proses tender masih berlangsung. Terdapat 12 perusahaan yang mendaftar untuk tender sejauh ini.",
            ["https://example.com/image.jpg"],
            "https://www.detik.com/sumut/berita/d-8654895/example",
        )):
            data = e.build_lapinsus({
                "id": 33979,
                "title": "Pemkab Deli Serdang Anggarkan Rp 11,9 M Bangun RSUD Bangun Purba Jadi Tipe C",
                "publisher": "detikcom",
                "link": "https://news.google.com/rss/articles/example",
                "published_date": "2026-09-09",
                "matched_location_keywords": ["bangun purba"],
            })

    joined_facts = " ".join(data["facts"])
    joined_trend = " ".join(data["trend"])
    check("RSUD Bangun Purba" in joined_facts, "LAPINSUS facts grounded to article")
    check("11,9 miliar" in joined_facts, "LAPINSUS retains article amount")
    check("berencana" in joined_trend.lower() or "tender" in joined_trend.lower(), "LAPINSUS trend grounded to article")
    check("tautan telah disalin" not in joined_trend.lower(), "Trend excludes page chrome")
    check(len(data["images"]) == 1, "Article image pipeline")
    print("FEATURE #13 V4 REGRESSION: PASS")


if __name__ == "__main__":
    main()
