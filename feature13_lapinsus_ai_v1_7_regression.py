from pathlib import Path

from feature13_lapinsus_ai import (
    AI_VERSION, _looks_like_google_wrapper, _candidate_publisher_urls,
    _material_source_highlights, _validate_grounding, mock_lapinsus_33979,
    audit_image_urls, _valid_image_url, _normalize_image_url, _image_asset_key,
)

def main():
    assert AI_VERSION == 'LAPINSUS_DELI_SERDANG_AI_V1_7'
    engine_text = Path('feature13_lapinsus_engine.py').read_text(encoding='utf-8')
    assert '"image_audit": ai.get("image_audit") or []' in engine_text
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
    assert _valid_image_url('https://cdn.example.com/rsud-bangun-purba.jpg')
    assert not _valid_image_url('https://www.gstatic.com/google-news/logo.png')
    assert _normalize_image_url('https://cdn.example.com/a.jpg?w=1200&q=80') == _normalize_image_url('https://cdn.example.com/a.jpg?w=54&q=60')
    assert _image_asset_key('https://cdn.example.com/path/kantor-bupati-deli-serdang_169.jpeg') == _image_asset_key('https://cdn.example.com/api/wm/kantor-bupati-deli-serdang_169.jpeg')

    class FakeResponse:
        def __init__(self, content, content_type='image/jpeg'):
            self.content = content
            self.headers = {'content-type': content_type}
            self.ok = True
            self.status_code = 200

    class FakeRequests:
        def __init__(self): self.calls = []
        def get(self, url, **kwargs):
            self.calls.append(url)
            if 'kantor-bupati-deli-serdang_169' in url:
                return FakeResponse(b'PHOTO-BYTES-ONE' * 1000)
            return FakeResponse((url.encode('utf-8') + b'-image') * 600)

    import feature13_lapinsus_ai as ai
    original_get = ai.requests.get
    fake = FakeRequests(); ai.requests.get = fake.get
    try:
        selected, audit = audit_image_urls([
            'https://cdn.example.com/logo.png',
            'https://awsimages.detik.net.id/community/media/2023/11/01/kantor-bupati-deli-serdang_169.jpeg?w=1200',
            'https://awsimages.detik.net.id/api/wm/2023/11/01/kantor-bupati-deli-serdang_169.jpeg?wid=54&w=1200&v=1&t=jpeg',
            'https://awsimages.detik.net.id/api/wm/2023/11/01/kantor-bupati-deli-serdang_169.jpeg?wid=60&w=1200&v=1&t=jpeg',
            'https://cdn.example.com/rsud-bangun-purba.jpg',
        ], context_text='RSUD Bangun Purba Deli Serdang', max_selected=6)
        assert len(audit) == 4
        assert len(selected) == 2
        dupes = [x for x in audit if x.get('duplicate')]
        assert len(dupes) == 2
        assert all(x['selected'] is False for x in dupes)
        assert any('asset_identity' in (x.get('duplicate_reason') or '') for x in dupes)
        assert all('normalized_url' in x and 'visual_hash' in x for x in audit)
    finally:
        ai.requests.get = original_get

    mock = mock_lapinsus_33979({'article_images': []})
    assert len(mock.get('fact_evidence') or []) >= 4
    assert len(mock.get('trend_evidence') or []) >= 1
    good = _validate_grounding({'informasi_diperoleh':[{'text':'Bahwa anggaran Rp 11,9 miliar.','evidence_sentence_ids':[2]}],'trend_perkembangan':[]}, sentences)
    assert good['passed']
    bad = _validate_grounding({'informasi_diperoleh':[{'text':'Bahwa anggaran Rp 99 miliar.','evidence_sentence_ids':[2]}],'trend_perkembangan':[]}, sentences)
    assert not bad['passed']
    print('[PASS] V1.7 version contract')
    print('[PASS] Engine image_audit propagation')
    print('[PASS] Google wrapper detection')
    print('[PASS] Detik AMP candidate retained')
    print('[PASS] Material highlights')
    print('[PASS] Image URL normalization')
    print('[PASS] Asset identity deduplication')
    print('[PASS] Visual audit fields')
    print('[PASS] Grounding positive')
    print('[PASS] Grounding rejects hallucinated number')
    print('[PASS] Mock V1.7 evidence audit')
    print('STATUS: PASS')

if __name__ == '__main__': main()
