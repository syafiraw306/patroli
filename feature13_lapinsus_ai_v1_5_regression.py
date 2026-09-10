from feature13_lapinsus_ai import (
    AI_VERSION, _looks_like_google_wrapper, _candidate_publisher_urls,
    _material_source_highlights, _validate_grounding, mock_lapinsus_33979,
)

def main():
    assert AI_VERSION == 'LAPINSUS_DELI_SERDANG_AI_V1_5'
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
    mock = mock_lapinsus_33979({'article_images': []})
    assert len(mock.get('fact_evidence') or []) >= 4
    assert len(mock.get('trend_evidence') or []) >= 1
    good = _validate_grounding({'informasi_diperoleh':[{'text':'Bahwa anggaran Rp 11,9 miliar.','evidence_sentence_ids':[2]}],'trend_perkembangan':[]}, sentences)
    assert good['passed']
    bad = _validate_grounding({'informasi_diperoleh':[{'text':'Bahwa anggaran Rp 99 miliar.','evidence_sentence_ids':[2]}],'trend_perkembangan':[]}, sentences)
    assert not bad['passed']
    print('[PASS] V1.5 version contract')
    print('[PASS] Google wrapper detection')
    print('[PASS] Detik AMP candidate retained')
    print('[PASS] Material highlights')
    print('[PASS] Grounding positive')
    print('[PASS] Grounding rejects hallucinated number')
    print('[PASS] Mock V1.5 evidence audit')
    print('STATUS: PASS')

if __name__ == '__main__': main()
