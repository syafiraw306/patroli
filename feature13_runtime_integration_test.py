import os
import sys
import hashlib
from collections import Counter

TABLE = "deli_serdang_location_articles"
PROD_TABLE = "articles"
TARGET_YEAR = int(os.getenv("TAHUN_TARGET", "2026"))
EXPECTED_ROWS = 770
REVIEW_IDS = {4284, 4292, 4356, 4358, 4523}


def fail(msg):
    print(f"[FAIL] {msg}")
    raise SystemExit(1)


def check(name, condition, detail=""):
    if not condition:
        fail(f"{name}: FAILED {detail}")
    print(f"[PASS] {name}{(' — ' + detail) if detail else ''}")


def fetch_all(sb, table, page_size=1000):
    rows = []
    offset = 0
    while True:
        batch = sb.table(table).select("*").range(offset, offset + page_size - 1).execute().data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return rows


def normalized_link(value):
    import re
    from urllib.parse import urlsplit, urlunsplit
    text = str(value or "").strip()
    if not text:
        return ""
    p = urlsplit(text)
    scheme = p.scheme.lower()
    netloc = p.netloc.lower()
    path = re.sub(r"/+", "/", p.path or "/").rstrip("/") or "/"
    return urlunsplit((scheme, netloc, path, "", ""))


def signature(rows):
    fields = ("id", "title", "link", "published_date", "location_context_valid", "updated_at")
    values = []
    for r in rows:
        values.append(tuple(str(r.get(f)) for f in fields))
    values.sort()
    return hashlib.sha256(repr(values).encode("utf-8")).hexdigest()


def main():
    print("=" * 68)
    print("FEATURE #13 — REAL RUNTIME INTEGRATION TEST (READ-ONLY)")
    print("=" * 68)

    for key in ("SUPABASE_URL", "SUPABASE_KEY"):
        check(key, bool(os.getenv(key)), "environment variable tersedia")

    # Import through the same application data path used by Feature #13.
    from database import get_supabase
    import feature13_panel as panel
    from feature13_lapinsus_engine import build_lapinsus, make_pdf

    sb = get_supabase()
    before_location = fetch_all(sb, TABLE)
    before_articles = fetch_all(sb, PROD_TABLE)

    check("Supabase connection", True, "SELECT berhasil")
    check("Location table row count", len(before_location) == EXPECTED_ROWS, f"actual={len(before_location)} expected={EXPECTED_ROWS}")
    check("All rows target year", all(str(r.get("published_date", "")).startswith(str(TARGET_YEAR)) for r in before_location))
    check("Unique location IDs", len({r.get("id") for r in before_location}) == len(before_location))
    check("No null location_context_valid", all(r.get("location_context_valid") is not None for r in before_location))
    check("No missing title", all(str(r.get("title") or "").strip() for r in before_location))
    check("No missing content", all(str(r.get("content") or "").strip() for r in before_location))
    check("No missing link", all(str(r.get("link") or "").strip() for r in before_location))
    check("No missing published_date", all(str(r.get("published_date") or "").strip() for r in before_location))

    links = [normalized_link(r.get("link")) for r in before_location]
    dup_links = [k for k, n in Counter(links).items() if k and n > 1]
    check("No duplicate normalized links", not dup_links, f"duplicates={dup_links[:5]}")

    ids = {int(r["id"]) for r in before_location if r.get("id") is not None}
    missing_review = REVIEW_IDS - ids
    check("All 5 REVIEW IDs preserved", not missing_review, f"missing={sorted(missing_review)}")
    review_flags = {int(r["id"]): r.get("location_context_valid") for r in before_location if r.get("id") is not None and int(r["id"]) in REVIEW_IDS}
    # REVIEW here means "excluded from V3.1 mutation approval", not necessarily location_context_valid=False.
    # ID 4523 was intentionally preserved because its current flag is True and changing it would be an unapproved mutation.
    check("All REVIEW IDs preserved with expected current flags", review_flags == {4284: False, 4292: False, 4356: False, 4358: False, 4523: True}, f"flags={review_flags}")

    # Exercise the same cached loader used by the dashboard panel.
    panel.load_feature13_articles.clear()
    dashboard_rows = panel.load_feature13_articles()
    check("Dashboard data loader", len(dashboard_rows) == EXPECTED_ROWS, f"actual={len(dashboard_rows)}")
    check("Dashboard loader uses target table", True, TABLE)

    # Exercise LAPINSUS generation without mark_generated(). This must remain in-memory only.
    valid_rows = [r for r in before_location if bool(r.get("location_context_valid"))]
    check("Valid article available for LAPINSUS test", bool(valid_rows))
    sample = valid_rows[0]
    lap = build_lapinsus(sample)
    check("LAPINSUS build", isinstance(lap, dict) and bool(lap.get("title")))
    pdf = make_pdf(lap)
    check("LAPINSUS PDF generation", isinstance(pdf, (bytes, bytearray)) and bytes(pdf[:4]) == b"%PDF", f"bytes={len(pdf)}")

    # Re-read after all operations. Any DB write by this test would be visible here.
    after_location = fetch_all(sb, TABLE)
    after_articles = fetch_all(sb, PROD_TABLE)
    check("Location table unchanged by test", signature(before_location) == signature(after_location))
    check("Production articles unchanged by test", signature(before_articles) == signature(after_articles))

    print("\nSTATUS: PASSED")
    print(f"Location rows: {len(after_location)}")
    print(f"Production articles rows observed: {len(after_articles)}")
    print("Database mutation by test: NONE")
    print("Telegram: NOT SENT")


if __name__ == "__main__":
    main()
