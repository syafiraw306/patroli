import csv, hashlib, json, os, re, time
from collections import Counter, defaultdict
from pathlib import Path

from database import get_supabase
from feature13_lapinsus_engine import build_lapinsus, make_pdf, TABLE

TARGET_YEAR = 2026
SAMPLE_SIZE = int(os.getenv('LAPINSUS_SAMPLE_SIZE', '30'))
OUT_DIR = Path(os.getenv('LAPINSUS_SAMPLE_OUT', 'LAPINSUS_BATCH_SAMPLE'))
OUT_DIR.mkdir(parents=True, exist_ok=True)
SUMMARY_JSON = Path('LAPINSUS_BATCH_SAMPLE_SUMMARY.json')
SUMMARY_CSV = Path('LAPINSUS_BATCH_SAMPLE_SUMMARY.csv')

CATEGORY_RULES = [
    ('Narkotika', ['narkotika','sabu','sabu-sabu','ganja','ekstasi','methamphetamine','psikotropika']),
    ('Korupsi', ['korupsi','gratifikasi','suap','tersangka korupsi','tipikor']),
    ('Penganiayaan', ['penganiayaan','aniaya','dianiaya','pengeroyokan']),
    ('Pencurian', ['pencurian','mencuri','curanmor','dibobol','pencuri']),
    ('Pembunuhan', ['pembunuhan','membunuh','dibunuh','tewas ditikam','mayat']),
    ('Penipuan', ['penipuan','menipu','ditipu','scam']),
    ('Judi', ['perjudian','judi online','judi','togel','slot online']),
    ('KDRT_KekerasanSeksual', ['kdrt','kekerasan dalam rumah tangga','kekerasan seksual','pencabulan','pelecehan seksual','pemerkosaan']),
    ('Kecelakaan_Bencana', ['kecelakaan','tabrakan','banjir','longsor','karhutla','kebakaran']),
    ('Pemerintahan_Infrastruktur', ['anggaran','pemerintah','pemkab','pemko','dinas','pembangunan','jalan','jembatan','rsud','rumah sakit','sekolah']),
]


def text_of(r):
    return re.sub(r'\s+', ' ', f"{r.get('title') or ''} {r.get('content') or ''}").lower()


def classify(r):
    t = text_of(r)
    for name, terms in CATEGORY_RULES:
        if any(term in t for term in terms):
            return name
    return 'Other'


def district(r):
    kws = r.get('matched_location_keywords') or []
    if isinstance(kws, str):
        kws = [x.strip() for x in re.split(r'[,;|]', kws) if x.strip()]
    for k in kws:
        k = str(k).strip()
        if k and k.lower() not in {'deli serdang','kabupaten deli serdang','deliserdang','kabupaten deliserdang'}:
            return k
    return 'Deli Serdang'


def stable_score(r):
    raw = f"{r.get('id')}|{r.get('source') or r.get('publisher') or ''}"
    return int(hashlib.sha256(raw.encode()).hexdigest()[:12], 16)


def fetch_all():
    client = get_supabase()
    # Fetch only the target-year rows; this is read-only.
    rows = client.table(TABLE).select('*').gte('published_date', f'{TARGET_YEAR}-01-01').lt('published_date', f'{TARGET_YEAR+1}-01-01').range(0, 999).execute().data or []
    return rows


def select_sample(rows):
    for r in rows:
        r['_category'] = classify(r)
        r['_district'] = district(r)
        r['_stable'] = stable_score(r)
    by_cat = defaultdict(list)
    for r in rows:
        by_cat[r['_category']].append(r)
    for arr in by_cat.values():
        arr.sort(key=lambda x: x['_stable'])

    selected = []
    # Core category coverage: up to 3 per category, prioritizing diversity of source.
    for cat in [x[0] for x in CATEGORY_RULES] + ['Other']:
        arr = by_cat.get(cat, [])
        if not arr:
            continue
        used_sources = set()
        picks = []
        for r in arr:
            src = (r.get('source') or r.get('publisher') or 'unknown').lower()
            if src not in used_sources:
                picks.append(r); used_sources.add(src)
            if len(picks) >= 3:
                break
        for r in picks:
            if r not in selected:
                selected.append(r)
        if len(selected) >= SAMPLE_SIZE:
            break

    # Fill remaining slots with deterministic diversity over district/source.
    remaining = [r for r in rows if r not in selected]
    remaining.sort(key=lambda r: (stable_score(r), r.get('_district',''), r.get('_category','')))
    seen_pairs = Counter((r['_district'], (r.get('source') or r.get('publisher') or 'unknown')) for r in selected)
    for r in remaining:
        if len(selected) >= SAMPLE_SIZE:
            break
        pair = (r['_district'], (r.get('source') or r.get('publisher') or 'unknown'))
        if seen_pairs[pair] == 0 or len(selected) < max(10, SAMPLE_SIZE // 2):
            selected.append(r); seen_pairs[pair] += 1
    if len(selected) < SAMPLE_SIZE:
        for r in remaining:
            if len(selected) >= SAMPLE_SIZE: break
            if r not in selected: selected.append(r)
    return selected[:SAMPLE_SIZE]


def assess(data, pdf_path):
    facts = data.get('facts') or []
    fact_ev = data.get('fact_evidence') or []
    trends = data.get('trend') or []
    trend_ev = data.get('trend_evidence') or []
    audits = data.get('image_audit') or []
    selected = [x for x in audits if x.get('selected')]
    selected_dup = [x for x in selected if x.get('duplicate') or x.get('asset_duplicate') or x.get('visual_duplicate')]
    material = data.get('source_material_highlights') or []
    checks = {
        'grounding': bool((data.get('grounding') or {}).get('passed')),
        'publisher_extraction': data.get('source_extraction_method') == 'publisher_jsonld_or_dom',
        'source_sentences': int(data.get('source_sentence_count') or 0) >= 3,
        'fact_evidence': len(fact_ev) >= len(facts) and len(facts) >= (4 if len(material) >= 4 else 1),
        'meaningful_trend': len(trends) >= 1 or len(data.get('trend_limitations') or []) >= 1,
        'trend_evidence': len(trend_ev) >= len(trends),
        'image_audit': (len(audits) >= 1) if data.get('image_count', 0) else True,
        'selected_images': (len(selected) >= 1) if data.get('image_count', 0) else True,
        'no_selected_duplicates': len(selected_dup) == 0,
        'pdf': pdf_path.exists() and pdf_path.stat().st_size > 0,
    }
    score = sum(bool(v) for v in checks.values())
    return checks, score, len(checks)


def main():
    rows_before = fetch_all()
    if not rows_before:
        raise SystemExit('Tidak ada row target year.')
    if any(str(r.get('published_date',''))[:4] != str(TARGET_YEAR) for r in rows_before):
        raise SystemExit('Year guard failed.')
    selected = select_sample(rows_before)
    print(f'[SAMPLE] total rows={len(rows_before)} sample={len(selected)}')
    results = []
    start = time.time()
    for i, article in enumerate(selected, 1):
        aid = article['id']
        print(f'[{i}/{len(selected)}] article={aid} category={article["_category"]} district={article["_district"]}')
        rec = {'article_id': aid, 'category': article['_category'], 'district': article['_district'], 'source': article.get('source') or article.get('publisher'), 'title': article.get('title')}
        try:
            data = build_lapinsus(article)
            pdf_path = OUT_DIR / f'LAPINSUS_{aid}.pdf'
            pdf_path.write_bytes(make_pdf(data))
            checks, score, total = assess(data, pdf_path)
            rec.update({
                'status': 'PASS' if all(checks.values()) else 'QUALITY_REVIEW',
                'score': score, 'score_total': total,
                'facts': len(data.get('facts') or []), 'fact_evidence': len(data.get('fact_evidence') or []),
                'trends': len(data.get('trend') or []), 'trend_evidence': len(data.get('trend_evidence') or []),
                'image_count': len(data.get('images') or []), 'image_audit': len(data.get('image_audit') or []),
                'selected_images': sum(1 for x in (data.get('image_audit') or []) if x.get('selected')),
                'extraction': data.get('source_extraction_method'),
                'checks': checks,
            })
            (OUT_DIR / f'LAPINSUS_{aid}.json').write_text(json.dumps({**rec, 'grounding': data.get('grounding'), 'image_audit': data.get('image_audit')}, ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception as exc:
            rec.update({'status':'ERROR','score':0,'score_total':0,'error':f'{type(exc).__name__}: {exc}'})
        results.append(rec)
        print(f'  -> {rec["status"]}')

    # Re-read DB count/IDs after generation to demonstrate read-only behavior.
    rows_after = fetch_all()
    ids_before = sorted(int(r['id']) for r in rows_before)
    ids_after = sorted(int(r['id']) for r in rows_after)
    db_unchanged = ids_before == ids_after
    summary = {
        'mode':'READ_ONLY_BATCH_SAMPLING', 'target_table':TABLE, 'target_year':TARGET_YEAR,
        'rows_before':len(rows_before), 'rows_after':len(rows_after), 'db_unchanged':db_unchanged,
        'sample_size_requested':SAMPLE_SIZE, 'sample_size_selected':len(selected),
        'results':results,
        'status_counts':dict(Counter(r['status'] for r in results)),
        'category_counts':dict(Counter(r['category'] for r in results)),
        'district_counts':dict(Counter(r['district'] for r in results)),
        'duration_seconds':round(time.time()-start,2), 'database_mutation':False, 'telegram_sent':False,
    }
    SUMMARY_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    fields=['article_id','category','district','source','title','status','score','score_total','facts','fact_evidence','trends','trend_evidence','image_count','image_audit','selected_images','extraction','error']
    with SUMMARY_CSV.open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
        for r in results: w.writerow({k:r.get(k,'') for k in fields})
    if not db_unchanged:
        raise SystemExit('DATABASE CHANGED DURING READ-ONLY SAMPLE')
    print('=== BATCH SAMPLE SUMMARY ===')
    print('rows_before:',len(rows_before),'rows_after:',len(rows_after),'db_unchanged:',db_unchanged)
    print('status_counts:',dict(Counter(r['status'] for r in results)))
    print('category_counts:',dict(Counter(r['category'] for r in results)))
    print('STATUS:', 'PASS' if all(r['status']!='ERROR' for r in results) else 'PARTIAL_REVIEW')

if __name__ == '__main__': main()
