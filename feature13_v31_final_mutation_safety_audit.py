import csv, json
from pathlib import Path
from datetime import datetime, timezone
from patroli import get_supabase

TABLE = 'deli_serdang_location_articles'
TARGET_YEAR = 2026
EXPECTED_CURRENT_ROWS = 793
EXPECTED_UPDATE_IDS = 56
EXPECTED_DELETE_IDS = 23
EXPECTED_REVIEW_IDS = 5
EXPECTED_ROWS_AFTER_DELETE = 770
WL = Path('feature13_v31_final_approval_whitelist.json')
OUT_JSON = Path('feature13_v31_final_mutation_safety_audit.json')
OUT_CSV = Path('feature13_v31_final_mutation_safety_audit.csv')


def main():
    wl = json.loads(WL.read_text(encoding='utf-8'))
    update_ids = set(map(int, wl['approved_update_ids_all_v31']))
    delete_ids = set(map(int, wl['approved_delete_ids_all_v31']))
    review_ids = set(map(int, wl['remaining_review_ids']))

    failures = []
    checks = {}
    checks['whitelist_update_count_56'] = len(update_ids) == EXPECTED_UPDATE_IDS
    checks['whitelist_delete_count_23'] = len(delete_ids) == EXPECTED_DELETE_IDS
    checks['review_count_5'] = len(review_ids) == EXPECTED_REVIEW_IDS
    checks['no_update_delete_overlap'] = not (update_ids & delete_ids)
    checks['no_review_mutation_overlap'] = not ((update_ids | delete_ids) & review_ids)
    if not all(checks.values()):
        failures.append('static whitelist invariant failed')

    sb = get_supabase()
    rows, offset, batch = [], 0, 500
    while True:
        resp = (sb.table(TABLE)
                  .select('id,title,link,published_date,location_context_valid')
                  .range(offset, offset + batch - 1).execute())
        chunk = list(resp.data or [])
        rows.extend(chunk)
        if len(chunk) < batch:
            break
        offset += batch

    by_id = {int(r['id']): r for r in rows}
    checks['current_row_count_793'] = len(rows) == EXPECTED_CURRENT_ROWS
    checks['all_rows_have_ids'] = len(by_id) == len(rows)

    missing_update = sorted(update_ids - set(by_id))
    missing_delete = sorted(delete_ids - set(by_id))
    checks['no_missing_update_ids'] = not missing_update
    checks['no_missing_delete_ids'] = not missing_delete
    if missing_update or missing_delete:
        failures.append(f'missing IDs update={missing_update} delete={missing_delete}')

    bad_year = []
    delete_not_false = []
    update_records = []
    delete_records = []
    for rid in sorted(update_ids):
        r = by_id.get(rid)
        if not r:
            continue
        pd = str(r.get('published_date') or '')
        if not pd.startswith('2026-'):
            bad_year.append(rid)
        update_records.append(r)
    for rid in sorted(delete_ids):
        r = by_id.get(rid)
        if not r:
            continue
        pd = str(r.get('published_date') or '')
        if not pd.startswith('2026-'):
            bad_year.append(rid)
        if bool(r.get('location_context_valid')):
            delete_not_false.append(rid)
        delete_records.append(r)

    checks['all_whitelist_rows_target_year_2026'] = not bad_year
    checks['all_delete_rows_current_flag_false'] = not delete_not_false
    if bad_year:
        failures.append(f'non-2026 whitelist IDs: {bad_year}')
    if delete_not_false:
        failures.append(f'delete IDs with location_context_valid=True: {delete_not_false}')

    # Remaining REVIEW rows must still exist and must not be scheduled for mutation.
    missing_review = sorted(review_ids - set(by_id))
    checks['review_rows_still_exist'] = not missing_review
    checks['review_rows_not_mutation'] = not ((update_ids | delete_ids) & review_ids)
    if missing_review:
        failures.append(f'review rows missing unexpectedly: {missing_review}')

    # Expected post-mutation row count is current rows minus approved deletes.
    checks['expected_post_delete_count_770'] = len(rows) - len(delete_ids) == EXPECTED_ROWS_AFTER_DELETE

    actions = []
    for r in update_records:
        actions.append({'id': int(r['id']), 'action': 'UPDATE_LOCATION_CONTEXT_TRUE',
                        'current_flag': bool(r.get('location_context_valid')), 'title': r.get('title'),
                        'link': r.get('link'), 'published_date': r.get('published_date')})
    for r in delete_records:
        actions.append({'id': int(r['id']), 'action': 'DELETE_LOCATION_ROW',
                        'current_flag': bool(r.get('location_context_valid')), 'title': r.get('title'),
                        'link': r.get('link'), 'published_date': r.get('published_date')})

    passed = not failures and all(checks.values())
    payload = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'mode': 'FEATURE13-V31-FINAL-MUTATION-SAFETY-AUDIT-READ-ONLY',
        'table': TABLE, 'target_year': TARGET_YEAR,
        'database_mutated': False, 'production_articles_touched': False, 'telegram_sent': False,
        'current_row_count': len(rows),
        'expected_row_count_after_delete': EXPECTED_ROWS_AFTER_DELETE,
        'approved_update_whitelist': len(update_ids),
        'approved_delete_whitelist': len(delete_ids),
        'remaining_review': sorted(review_ids),
        'planned_actions': len(update_ids) + len(delete_ids),
        'checks': checks,
        'failures': failures,
        'status': 'PASSED' if passed else 'FAILED',
        'actions_snapshot': actions,
    }
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    with OUT_CSV.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['id','action','current_flag','title','link','published_date'])
        w.writeheader(); w.writerows(actions)

    print('=' * 70)
    print('FEATURE #13 — V3.1 FINAL MUTATION SAFETY AUDIT')
    print('=' * 70)
    print(f'Status                    : {payload["status"]}')
    print(f'Current rows              : {len(rows)} (expected 793)')
    print(f'UPDATE whitelist          : {len(update_ids)}')
    print(f'DELETE whitelist          : {len(delete_ids)}')
    print(f'REVIEW excluded           : {len(review_ids)}')
    print(f'Expected rows after delete: {EXPECTED_ROWS_AFTER_DELETE}')
    print(f'Checks passed             : {sum(checks.values())}/{len(checks)}')
    print(f'Database mutated          : False')
    print(f'Production articles      : untouched')
    print(f'Telegram                  : not sent')
    print(f'JSON report               : {OUT_JSON}')
    print(f'CSV report                : {OUT_CSV}')
    print('=' * 70)
    if not passed:
        raise SystemExit(1)

if __name__ == '__main__':
    main()
