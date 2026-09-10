import json
from feature13_lapinsus_ai import extract_article_body, split_sentences, _material_source_highlights

ARTICLE_BODY = """Pemkab Deli Serdang berencana meningkatkan RSUD Bangun Purba menjadi tipe C. Anggaran digelontorkan Rp 11,9 miliar untuk pembangunan RSUD Bangun Purba tahun ini. Hal itu diketahui dari Sistem Pengadaan Secara Elektronik (SPSE) Deli Serdang. Proyek ini memiliki kode paket 10164331000. Pembangunan Gedung RSUD Bangun Purba Kab. Deli Serdang menuju RSUD Type C. Proyek ini berada di bawah Dinas Cipta Karya dan Tata Ruang Deli Serdang. Anggaran untuk proyek dengan metode tender ini sebesar Rp 11,9 miliar bersumber dari APBD Deli Serdang 2026. Nilai Pagu Paket: Rp 11.940.000.000, Nilai HPS Paket: Rp 11.938.466.888,79. Saat ini proses tender masih berlangsung. Terdapat 12 perusahaan yang mendaftar untuk tender sejauh ini."""
JSONLD = json.dumps({"@context":"https://schema.org","@type":"NewsArticle","articleBody":ARTICLE_BODY,"image":["https://cdn.detik.com/images/kantor-bupati-deli-serdang.jpg"],"url":"https://www.detik.com/sumut/berita/d-8654895/pemkab-deli-serdang-anggarkan-rp-11-9-m-bangun-rsud-bangun-purba-jadi-tipe-c"})
HTML = '<html><head><meta property="og:image" content="https://cdn.detik.com/images/kantor-bupati-deli-serdang.jpg"></head><body><script type="application/ld+json">' + JSONLD + '</script><div class="detail__body-text">' + ARTICLE_BODY + '</div></body></html>'

def main():
    text, images, canonical = extract_article_body(HTML)
    sentences = split_sentences(text)
    highlights = _material_source_highlights(sentences)
    required = ["10164331000", "Dinas Cipta Karya dan Tata Ruang", "APBD Deli Serdang 2026", "Rp 11.940.000.000", "Rp 11.938.466.888,79", "12 perusahaan", "tender masih berlangsung"]
    missing = [x for x in required if x.lower() not in text.lower()]
    assert len(sentences) >= 7, f"sentence_count={len(sentences)}"
    assert not missing, f"missing={missing}"
    assert images and "google" not in images[0].lower()
    assert canonical.startswith("https://www.detik.com/")
    assert len(highlights) >= 6, f"highlights={len(highlights)}"
    print(f"[PASS] JSON-LD/full article extraction sentences={len(sentences)}")
    print(f"[PASS] Material markers={len(highlights)}")
    print(f"[PASS] Image extraction={images[0]}")
    print(f"[PASS] Canonical={canonical}")
    print("STATUS: PASS")

if __name__ == "__main__":
    main()
