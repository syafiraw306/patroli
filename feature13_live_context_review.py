import os
import urllib.parse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

import patroli

TABLE = patroli.DELI_SERDANG_LOCATION_TABLE
YEAR = patroli.DELI_SERDANG_LOCATION_YEAR
MIN_CONTENT_LENGTH = patroli.MIN_CONTENT_LENGTH


def domain(url):
    try:
        return (urllib.parse.urlparse(str(url or '').strip()).netloc or '').lower().removeprefix('www.') or '[no-domain]'
    except Exception:
        return '[invalid-url]'


def load_rows():
    sb = patroli.get_supabase()
    rows = []
    offset = 0
    batch = 500
    while True:
        res = (sb.table(TABLE)
               .select('id,title,link,content,published_date,matched_location_keywords,location_context_valid')
               .range(offset, offset + batch - 1)
               .execute())
        data = list(res.data or [])
        rows.extend(data)
        if len(data) < batch:
            break
        offset += batch
    return rows


def review(row):
    title = patroli.normalize_text(row.get('title'))
    link = patroli.normalize_url(row.get('link'))
    keywords = row.get('matched_location_keywords') or []
    out = {'row': row, 'status': 'FETCH_FAILED', 'final_url': link, 'content': '', 'error': '', 'live_matches': []}
    if not link:
        out['error'] = 'link kosong'
        return out
    try:
        fetched_url, raw_html = patroli.fetch_webpage_content(link)
        final_url = patroli.normalize_url(fetched_url) or link
        try:
            resolved, _ = patroli.resolve_article_url_details(
                rss_url=link, response_url=fetched_url, raw_html=raw_html,
                source_url='', title=title,
            )
            final_url = patroli.normalize_url(resolved) or final_url
        except Exception:
            pass
        content = ''
        if raw_html:
            try:
                content = patroli.normalize_text(patroli.extract_article_text(raw_html))
            except Exception as exc:
                out['error'] = f'extract gagal: {type(exc).__name__}: {exc}'
        out['final_url'] = final_url
        out['content'] = content
        if len(content) < MIN_CONTENT_LENGTH:
            if not out['error']:
                out['error'] = f'content publisher terlalu pendek (len={len(content)})'
            return out
        # Jangan mempercayai matched_location_keywords lama sebagai bukti
        # konteks. Hitung ulang keyword dari title + publisher content yang
        # benar-benar berhasil di-fetch.
        live_matches = patroli.find_location_matches(title, content)
        out['live_matches'] = live_matches
        valid = patroli._has_deli_serdang_location_context(title, content, live_matches)
        out['status'] = 'VALID' if valid else 'INVALID'
        return out
    except Exception as exc:
        out['error'] = f'{type(exc).__name__}: {exc}'
        return out


def main():
    print('=' * 70)
    print('FEATURE #13 — LIVE LOCATION CONTEXT REVIEW / READ-ONLY')
    print('=' * 70)
    print(f'Target year        : {YEAR}')
    print(f'Location table     : {TABLE}')
    print('Supabase write     : DISABLED')
    print('Delete/update      : DISABLED')
    print('Telegram           : NOT SENT')
    print('Publisher fetch    : ENABLED')
    print('=' * 70)

    rows = load_rows()
    targets = []
    for row in rows:
        d = patroli.parse_date_safe(row.get('published_date'))
        if not d or d.year != YEAR:
            continue
        if not patroli._has_deli_serdang_location_context(
            patroli.normalize_text(row.get('title')),
            patroli.normalize_text(row.get('content')),
            row.get('matched_location_keywords') or [],
        ):
            targets.append(row)

    print(f'[LIVE] Existing rows           : {len(rows)}')
    print(f'[LIVE] Rows needing live review : {len(targets)}')

    workers = max(1, min(int(os.getenv('FEATURE13_LIVE_REVIEW_WORKERS') or '5'), 10))
    results = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(review, r) for r in targets]
        for f in as_completed(futures):
            results.append(f.result())

    valid = [r for r in results if r['status'] == 'VALID']
    invalid = [r for r in results if r['status'] == 'INVALID']
    failed = [r for r in results if r['status'] == 'FETCH_FAILED']

    print('=' * 70)
    print('[LIVE] RESULT SUMMARY')
    print('=' * 70)
    print(f'[LIVE] Need review            : {len(targets)}')
    print(f'[LIVE] Valid after live fetch  : {len(valid)}')
    print(f'[LIVE] Still invalid            : {len(invalid)}')
    print(f'[LIVE] Fetch indeterminate      : {len(failed)}')

    vc, ic = Counter(), Counter()
    for item in valid:
        for k in item['row'].get('matched_location_keywords') or []:
            vc[patroli.normalize_text(k).lower()] += 1
    for item in invalid:
        for k in item['row'].get('matched_location_keywords') or []:
            ic[patroli.normalize_text(k).lower()] += 1

    print('=' * 70)
    print('[LIVE] VALID AFTER PUBLISHER FETCH — GROUP BY KEYWORD')
    print('=' * 70)
    for k, n in vc.most_common(): print(f'[LIVE-VALID-KEYWORD] {k} : {n}')
    if not vc: print('[LIVE-VALID-KEYWORD] none')

    print('=' * 70)
    print('[LIVE] STILL INVALID — GROUP BY KEYWORD')
    print('=' * 70)
    for k, n in ic.most_common(): print(f'[LIVE-INVALID-KEYWORD] {k} : {n}')
    if not ic: print('[LIVE-INVALID-KEYWORD] none')

    print('=' * 70)
    print('[LIVE] VALIDATED ROWS')
    print('=' * 70)
    for x in sorted(valid, key=lambda z: str(z['row'].get('id'))):
        r=x['row']; c=x['content']
        print(f"[LIVE-VALID] id={r.get('id')} | domain={domain(r.get('link'))} | stored_keywords={r.get('matched_location_keywords') or []} | live_matches={x.get('live_matches') or []}")
        print(f"  title={patroli.normalize_text(r.get('title'))[:240]}")
        print(f"  final_url={x['final_url']} | content_length={len(c)}")
        print(f"  evidence={c[:700]}")

    print('=' * 70)
    print('[LIVE] STILL INVALID ROWS')
    print('=' * 70)
    for x in sorted(invalid, key=lambda z: str(z['row'].get('id'))):
        r=x['row']; c=x['content']
        print(f"[LIVE-INVALID] id={r.get('id')} | domain={domain(r.get('link'))} | stored_keywords={r.get('matched_location_keywords') or []} | live_matches={x.get('live_matches') or []}")
        print(f"  title={patroli.normalize_text(r.get('title'))[:240]}")
        print(f"  final_url={x['final_url']} | content_length={len(c)}")
        print(f"  evidence={c[:700]}")

    print('=' * 70)
    print('[LIVE] FETCH INDETERMINATE ROWS')
    print('=' * 70)
    for x in sorted(failed, key=lambda z: str(z['row'].get('id'))):
        r=x['row']
        print(f"[LIVE-FETCH-FAILED] id={r.get('id')} | domain={domain(r.get('link'))} | keywords={r.get('matched_location_keywords') or []}")
        print(f"  title={patroli.normalize_text(r.get('title'))[:240]}")
        print(f"  link={r.get('link')}")
        print(f"  reason={x.get('error')}")

    print('=' * 70)
    print('[ACTION] READ-ONLY: tidak ada INSERT/UPDATE/DELETE.')
    print('[ACTION] Hasil ini menjadi dasar tahap sinkronisasi dan cleanup.')
    print('FEATURE #13 LIVE LOCATION CONTEXT REVIEW: COMPLETED')
    print('=' * 70)


if __name__ == '__main__':
    main()
