import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

from database import get_supabase

TABLE = "deli_serdang_location_articles"
TARGET_YEAR = 2026
EXPECTED_ROWS = 770
EXPECTED_REVIEW_IDS = {4284, 4292, 4356, 4358, 4523}
APPROVED_DELETED_IDS = {
    4211, 4224, 4234, 4285, 4291, 4293, 4301, 4317, 4335, 4339,
    4346, 4350, 4354, 4355, 4357, 4359, 4360, 4364, 4365, 4366,
    4367, 4368, 4369,
}

REPORT_JSON = "feature13_final_data_audit.json"
REPORT_CSV = "feature13_final_data_audit.csv"


def normalize_url(url):
    if not url:
        return ""
    try:
        p = urlsplit(str(url).strip())
        host = (p.netloc or "").lower()
        if host.startswith("www."):
            host = host[4:]
        path = re.sub(r"/+", "/", p.path or "/").rstrip("/") or "/"
        return urlunsplit((p.scheme.lower() or "https", host, path, p.query, ""))
    except Exception:
        return str(url).strip().lower().rstrip("/")


def fetch_all(sb):
    rows = []
    page_size = 500
    offset = 0
    while True:
        res = (
            sb.table(TABLE)
            .select("*")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        batch = res.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return rows


def as_bool(v):
    return v is True


def main():
    print("=" * 70)
    print("FEATURE #13 — FINAL DATA AUDIT (READ-ONLY)")
    print("=" * 70)

    sb = get_supabase()
    print("[SUPABASE] Client berhasil dibuat.")

    rows = fetch_all(sb)
    ids = [r.get("id") for r in rows]
    id_counts = Counter(ids)
    duplicate_ids = sorted([i for i, c in id_counts.items() if i is not None and c > 1])

    years = []
    non_target_rows = []
    missing_title = []
    missing_content = []
    missing_link = []
    missing_date = []
    invalid_flag = []
    null_flag = []
    empty_keywords = []

    url_groups = defaultdict(list)
    for r in rows:
        rid = r.get("id")
        pd = r.get("published_date")
        year = None
        if pd:
            try:
                year = datetime.fromisoformat(str(pd).replace("Z", "+00:00")).year
            except Exception:
                year = None
        years.append(year)
        if year != TARGET_YEAR:
            non_target_rows.append(rid)

        if not str(r.get("title") or "").strip():
            missing_title.append(rid)
        if not str(r.get("content") or "").strip():
            missing_content.append(rid)
        if not str(r.get("link") or "").strip():
            missing_link.append(rid)
        if not pd:
            missing_date.append(rid)

        flag = r.get("location_context_valid")
        if flag is None:
            null_flag.append(rid)
        elif flag is False:
            invalid_flag.append(rid)

        kw = r.get("matched_location_keywords")
        if kw is None or (isinstance(kw, list) and len(kw) == 0) or (isinstance(kw, str) and not kw.strip()):
            empty_keywords.append(rid)

        norm = normalize_url(r.get("link"))
        if norm:
            url_groups[norm].append(rid)

    duplicate_url_groups = {u: ids_ for u, ids_ in url_groups.items() if len(ids_) > 1}

    row_id_set = {i for i in ids if i is not None}
    missing_review = sorted(EXPECTED_REVIEW_IDS - row_id_set)
    deleted_still_present = sorted(APPROVED_DELETED_IDS & row_id_set)

    true_count = sum(1 for r in rows if r.get("location_context_valid") is True)
    false_count = sum(1 for r in rows if r.get("location_context_valid") is False)
    null_count = sum(1 for r in rows if r.get("location_context_valid") is None)

    checks = {
        "row_count_770": len(rows) == EXPECTED_ROWS,
        "all_rows_target_year_2026": len(non_target_rows) == 0,
        "all_rows_have_ids": all(i is not None for i in ids),
        "unique_ids": len(duplicate_ids) == 0,
        "no_missing_title": len(missing_title) == 0,
        "no_missing_content": len(missing_content) == 0,
        "no_missing_link": len(missing_link) == 0,
        "no_missing_published_date": len(missing_date) == 0,
        "no_null_location_context_valid": len(null_flag) == 0,
        "no_duplicate_normalized_links": len(duplicate_url_groups) == 0,
        "all_review_ids_preserved": len(missing_review) == 0,
        "all_approved_deleted_ids_absent": len(deleted_still_present) == 0,
    }

    status = "PASSED" if all(checks.values()) else "FAILED"

    print(f"Rows                         : {len(rows)}")
    print(f"Target year                 : {TARGET_YEAR}")
    print(f"location_context_valid TRUE : {true_count}")
    print(f"location_context_valid FALSE: {false_count}")
    print(f"location_context_valid NULL : {null_count}")
    print(f"Duplicate IDs               : {len(duplicate_ids)}")
    print(f"Duplicate normalized links  : {len(duplicate_url_groups)}")
    print(f"Missing title               : {len(missing_title)}")
    print(f"Missing content             : {len(missing_content)}")
    print(f"Missing link                : {len(missing_link)}")
    print(f"Missing published date      : {len(missing_date)}")
    print(f"Review preserved            : {sorted(EXPECTED_REVIEW_IDS)}")
    print(f"Approved deleted still here : {len(deleted_still_present)}")
    print("-" * 70)
    print("CHECKS")
    for name, ok in checks.items():
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    print("-" * 70)
    print(f"Status                       : {status}")
    print("Database mutated             : False")
    print("Production articles          : untouched")
    print("Telegram                     : not sent")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "FEATURE13-FINAL-DATA-AUDIT-READ-ONLY",
        "table": TABLE,
        "target_year": TARGET_YEAR,
        "database_mutated": False,
        "production_articles_touched": False,
        "telegram_sent": False,
        "row_count": len(rows),
        "expected_row_count": EXPECTED_ROWS,
        "location_context_valid_true": true_count,
        "location_context_valid_false": false_count,
        "location_context_valid_null": null_count,
        "duplicate_ids": duplicate_ids,
        "duplicate_normalized_link_groups": duplicate_url_groups,
        "missing_title_ids": missing_title,
        "missing_content_ids": missing_content,
        "missing_link_ids": missing_link,
        "missing_published_date_ids": missing_date,
        "empty_keyword_ids": empty_keywords,
        "expected_review_ids": sorted(EXPECTED_REVIEW_IDS),
        "missing_review_ids": missing_review,
        "approved_deleted_ids_still_present": deleted_still_present,
        "checks": checks,
        "status": status,
    }

    with open(REPORT_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    with open(REPORT_CSV, "w", encoding="utf-8", newline="") as f:
        import csv
        w = csv.writer(f)
        w.writerow(["check", "status"])
        for name, ok in checks.items():
            w.writerow([name, "PASS" if ok else "FAIL"])
        w.writerow(["STATUS", status])

    print(f"JSON report                  : {REPORT_JSON}")
    print(f"CSV report                   : {REPORT_CSV}")
    print("=" * 70)

    if status != "PASSED":
        sys.exit(1)


if __name__ == "__main__":
    main()
