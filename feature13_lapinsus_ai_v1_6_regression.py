from feature13_lapinsus_ai import (
    AI_VERSION, _looks_like_google_wrapper, _candidate_publisher_urls,
    _material_source_highlights, _validate_grounding, mock_lapinsus_33979,
    audit_image_urls, _valid_image_url,
)

def main():
    assert AI_VERSION == 'LAPINSUS_DELI_SERDANG_AI_V1_6'
    assert _looks_like_google_wrapper('<a href="https://news.google.com/rss/articles/x">title</a>')
    assert any('/amp' in u for u in _candidate_publisher_urls('https://www.detik.com/sumut/berita/d-8654895/test'))
    sentences = [
        'Pemkab Deli Serdang berencana meningkatkan RSUD Bangun Purba menjadi tipe C.',
        'Anggaran pembangunan RSUD Bangun Purba sebesar Rp 11,9 miliar.',
        'Proyek ini memiliki kode paket 10164331000.',
        'Proyek berada di bawah Dinas Cipta Karya dan Tata Ruang Deli Serdang.',
        'Proses tender masih berlangsung.',
        'Terdapat 12 perusahaan yang mendaftar untuk tender.',
    ]
    assert len(_material_source_highlights(sentences)) >= 5
    assert _valid_image_url("https://cdn.example.com/rsud-bangun-purba.jpg")
    assert not _valid_image_url("https://www.gstatic.com/google-news/logo.png")

    class FakeResponse:
        def __init__(self, content, content_type="image/jpeg"):
            self.content = content
            self.headers = {"content-type": content_type}
            self.ok = True

    class FakeRequests:
        def __init__(self):
            self.calls = []
        def get(self, url, **kwargs):
            self.calls.append(url)
            if "duplicate" in url:
                return FakeResponse(b"SAME-IMAGE-CONTENT" * 600)
            return FakeResponse((url.encode("utf-8") + b"-image") * 600)

    import feature13_lapinsus_ai as ai
    original_get = ai.requests.get
    fake = FakeRequests()
    ai.requests.get = fake.get
    try:
        selected, audit = audit_image_urls([
            "https://www.gstatic.com/google-news/logo.png",
            "https://cdn.example.com/rsud-bangun-purba.jpg",
            "https://cdn.example.com/duplicate-a.jpg",
            "https://cdn.example.com/duplicate-b.jpg",
            "https://cdn.example.com/deli-serdang-office.jpg",
        ], context_text="RSUD Bangun Purba Deli Serdang", max_selected=6)
        assert selected[0].endswith("rsud-bangun-purba.jpg")
        assert len(selected) == 3
        assert len(audit) >= 4
        assert any(x["duplicate"] for x in audit)
        assert all(x["selected"] is False or x["duplicate"] is False for x in audit)
    finally:
        ai.requests.get = original_get
    mock = mock_lapinsus_33979({'article_images': []})
    assert len(mock.get('fact_evidence') or []) >= 4
    assert len(mock.get('trend_evidence') or []) >= 1
    good = _validate_grounding({'informasi_diperoleh':[{'text':'Bahwa anggaran Rp 11,9 miliar.','evidence_sentence_ids':[2]}],'trend_perkembangan':[]}, sentences)
    assert good['passed']
    bad = _validate_grounding({'informasi_diperoleh':[{'text':'Bahwa anggaran Rp 99 miliar.','evidence_sentence_ids':[2]}],'trend_perkembangan':[]}, sentences)
    assert not bad['passed']
    print('[PASS] V1.6 version contract')
    print('[PASS] Google wrapper detection')
    print('[PASS] Detik AMP candidate retained')
    print('[PASS] Material highlights')
    print('[PASS] Grounding positive')
    print('[PASS] Grounding rejects hallucinated number')
    print('[PASS] Mock V1.6 evidence audit')
    print('[PASS] Image relevance filtering')
    print('[PASS] Image URL/hash deduplication audit')
    print('STATUS: PASS')

if __name__ == '__main__': main()
