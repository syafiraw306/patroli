from feature13_lapinsus_ai import _candidate_publisher_urls, _looks_like_google_wrapper, split_sentences


def main():
    wrapper = '<a href="https://news.google.com/rss/articles/ABC?oc=5" target="_blank">Pemkab Deli Serdang Anggarkan Rp 11,9 M</a> <font>detikcom</font>'
    assert _looks_like_google_wrapper(wrapper), 'Google wrapper not detected'
    urls = _candidate_publisher_urls('https://www.detik.com/sumut/berita/d-8654895/example')
    assert urls[0].endswith('/example')
    assert urls[1].endswith('/example/amp')
    assert len(split_sentences(wrapper)) == 1
    print('[PASS] Google News wrapper detection')
    print('[PASS] Detik AMP candidate generation')
    print('[PASS] Wrapper is not treated as article body')
    print('STATUS: PASS')


if __name__ == '__main__':
    main()
