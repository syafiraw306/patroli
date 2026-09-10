import json

from feature13_lapinsus_ai import (
    _candidate_publisher_urls,
    _looks_like_google_wrapper,
    _material_source_highlights,
    _validate_grounding,
    mock_lapinsus_33979,
)


def main():
    checks = []

    wrapper = '<a href="https://news.google.com/rss/articles/XYZ">Judul</a> detikcom'
    checks.append(("Google wrapper detection", _looks_like_google_wrapper(wrapper)))

    candidates = _candidate_publisher_urls("https://www.detik.com/sumut/berita/d-8654895/pemkab-deli-serdang-anggarkan-rp-11-9-m-bangun-rsud-bangun-purba-jadi-tipe-c")
    checks.append(("Detik AMP candidate retained", any("/amp" in x for x in candidates)))

    sentences = [
        "Pemkab Deli Serdang berencana meningkatkan RSUD Bangun Purba menjadi tipe C.",
        "Anggaran pembangunan RSUD Bangun Purba sebesar Rp 11,9 miliar tahun ini.",
        "Proyek tersebut berada di bawah Dinas Cipta Karya dan Tata Ruang Deli Serdang.",
        "Proses tender masih berlangsung dan terdapat 12 perusahaan yang mendaftar.",
    ]
    highlights = _material_source_highlights(sentences)
    checks.append(("Material highlights", len(highlights) >= 3))

    good = {
        "informasi_diperoleh": [
            {"text": "Bahwa anggaran pembangunan RSUD Bangun Purba sebesar Rp 11,9 miliar.", "evidence_sentence_ids": [2]},
            {"text": "Bahwa proses tender masih berlangsung dan terdapat 12 perusahaan yang mendaftar.", "evidence_sentence_ids": [4]},
        ],
        "trend_perkembangan": [
            {"text": "Bahwa proses tender masih berlangsung sehingga perkembangan selanjutnya perlu dicermati pada tahapan pengadaan berikutnya.", "evidence_sentence_ids": [4], "basis": "current_process"}
        ],
    }
    validation = _validate_grounding(good, sentences)
    checks.append(("Grounding positive", validation["passed"]))

    bad = {
        "informasi_diperoleh": [
            {"text": "Bahwa anggaran proyek sebesar Rp 25 miliar.", "evidence_sentence_ids": [2]}
        ],
        "trend_perkembangan": [],
    }
    bad_validation = _validate_grounding(bad, sentences)
    checks.append(("Grounding rejects hallucinated number", not bad_validation["passed"]))

    mock = mock_lapinsus_33979({"title": "Rencana Peningkatan RSUD Bangun Purba Menjadi Tipe C dengan Anggaran Rp11,9 Miliar"})
    checks.append(("Mock V1.4 evidence audit", len(mock.get("fact_evidence", [])) >= 4 and len(mock.get("trend_evidence", [])) >= 1))

    for name, ok in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    failed = [name for name, ok in checks if not ok]
    print("STATUS:", "PASS" if not failed else "FAIL")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
