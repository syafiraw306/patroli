import json
import re
from pathlib import Path

from feature13_lapinsus_ai import SCHEMA, _validate_grounding, _ensure_bahwa, mock_lapinsus_33979

ARTICLE = {
    "id": 33979,
    "title": "Pemkab Deli Serdang Anggarkan Rp 11,9 M Bangun RSUD Bangun Purba Jadi Tipe C - detikcom",
    "link": "https://detik.com/sumut/berita/d-8654895/pemkab-deli-serdang-anggarkan-rp-11-9-m-bangun-rsud-bangun-purba-jadi-tipe-c",
    "publisher": "detikcom",
    "published_date": "2026-09-09T04:19:06+00:00",
    "matched_location_keywords": ["bangun purba", "deli serdang"],
    "article_images": [],
}

SENTENCES = [
    "Pemkab Deli Serdang berencana meningkatkan RSUD Bangun Purba menjadi tipe C.",
    "Anggaran sebesar Rp 11,9 miliar dialokasikan untuk peningkatan RSUD Bangun Purba.",
    "Paket pekerjaan berada pada Dinas Cipta Karya dan Tata Ruang Kabupaten Deli Serdang.",
    "Proses pengadaan pekerjaan tersebut masih dalam tahap tender.",
    "Sebanyak 12 perusahaan telah terdaftar dalam proses tender.",
]


def main():
    assert SCHEMA["type"] == "object"
    mock = mock_lapinsus_33979(ARTICLE)
    assert mock["grounding"]["passed"] is True
    assert all(x.startswith("Bahwa ") for x in mock["facts"])
    assert all(x.startswith("Bahwa ") for x in mock["trend"])
    assert any("11,9" in x for x in mock["facts"])
    assert any("12 perusahaan" in x for x in mock["facts"])
    assert any("tender" in x.lower() for x in mock["trend"])

    result = {
        "informasi_diperoleh": [
            {"text": "Bahwa anggaran sebesar Rp11,9 miliar dialokasikan untuk peningkatan RSUD Bangun Purba.", "evidence_sentence_ids": [2]},
        ],
        "trend_perkembangan": [
            {"text": "Bahwa proses pengadaan pekerjaan tersebut masih dalam tahap tender.", "evidence_sentence_ids": [4], "basis": "current_process"},
        ],
    }
    check = _validate_grounding(result, SENTENCES)
    assert check["passed"], check

    bad = {
        "informasi_diperoleh": [
            {"text": "Bahwa pekerjaan akan selesai pada Desember 2027 dengan anggaran Rp99 miliar.", "evidence_sentence_ids": [2]},
        ],
        "trend_perkembangan": [],
    }
    bad_check = _validate_grounding(bad, SENTENCES)
    assert not bad_check["passed"]
    assert any("angka 99" in e for e in bad_check["errors"])

    Path("lapinsus_ai_v1_schema.json").write_text(json.dumps(SCHEMA, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Structured schema: PASS")
    print("Mock #33979: PASS")
    print("Grounding positive case: PASS")
    print("Grounding hallucination case: PASS")
    print("STATUS: PASS")


if __name__ == "__main__":
    main()
