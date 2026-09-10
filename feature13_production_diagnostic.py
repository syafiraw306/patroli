
"""
Feature #13 — Production Supabase Data Access Diagnostic
READ-ONLY. Never INSERT/UPDATE/DELETE. Never sends Telegram.

Purpose:
Diagnose why the production Streamlit UI can render Feature #13 but
shows 0 articles while the known Supabase baseline is 770.
"""
import os
from urllib.parse import urlparse

EXPECTED_TOTAL = 770
EXPECTED_YEAR = "2026"
REVIEW_IDS = {4284, 4292, 4356, 4358, 4523}


def mask_key(key: str) -> str:
    if not key:
        return "<EMPTY>"
    if len(key) <= 12:
        return f"<SET length={len(key)}>"
    return f"{key[:6]}...{key[-4:]} (length={len(key)})"


def main():
    print("=" * 76)
    print("FEATURE #13 — PRODUCTION SUPABASE DATA ACCESS DIAGNOSTIC")
    print("READ-ONLY / NO DATABASE MUTATION / NO TELEGRAM")
    print("=" * 76)

    url = (os.getenv("SUPABASE_URL") or "").strip()
    key = (os.getenv("SUPABASE_KEY") or "").strip()

    print(f"[ENV] SUPABASE_URL : {'SET' if url else 'EMPTY'}")
    print(f"[ENV] SUPABASE_KEY : {mask_key(key)}")

    if not url:
        raise RuntimeError("SUPABASE_URL kosong.")
    if not key:
        raise RuntimeError("SUPABASE_KEY kosong.")

    parsed = urlparse(url)
    print(f"[ENV] Supabase host: {parsed.netloc}")

    # Import only after environment validation.
    from database import get_supabase

    sb = get_supabase()

    # Direct SELECT against the exact Feature #13 table.
    result = (
        sb.table("deli_serdang_location_articles")
        .select(
            "id,title,link,published_date,location_context_valid,"
            "matched_location_keywords"
        )
        .order("published_date", desc=True)
        .limit(1000)
        .execute()
    )
    rows = result.data or []

    print(f"[QUERY] deli_serdang_location_articles rows: {len(rows)}")
    print(f"[QUERY] First row: {rows[0] if rows else '<NONE>'}")

    if len(rows) == EXPECTED_TOTAL:
        print("[PASS] Feature #13 table returns expected 770 rows.")
    else:
        print(
            f"[FAIL] Feature #13 table returns {len(rows)} rows; "
            f"expected {EXPECTED_TOTAL}."
        )

    year_rows = [
        r for r in rows if str(r.get("published_date", "")).startswith(EXPECTED_YEAR)
    ]
    print(f"[QUERY] 2026 rows: {len(year_rows)}")

    if len(rows) > 0 and len(year_rows) == len(rows):
        print("[PASS] All returned Feature #13 rows are 2026.")
    else:
        print("[WARN] Returned rows are not exclusively 2026.")

    # Required fields.
    missing = []
    for r in rows:
        for field in ("id", "title", "link", "published_date"):
            if not r.get(field):
                missing.append((r.get("id"), field))

    if not missing:
        print("[PASS] No missing required fields in returned rows.")
    else:
        print(f"[WARN] Missing required fields: {missing[:10]}")

    # Review preservation.
    returned_review = {int(r["id"]): r.get("location_context_valid")
                       for r in rows
                       if r.get("id") is not None and int(r["id"]) in REVIEW_IDS}
    print(f"[QUERY] REVIEW IDs returned: {returned_review}")

    if set(returned_review) == REVIEW_IDS:
        print("[PASS] All 5 REVIEW IDs are accessible.")
    else:
        print("[WARN] REVIEW IDs incomplete in this environment.")

    # Compare exact loader path used by Feature #13.
    import feature13_panel as panel
    try:
        panel.load_feature13_articles.clear()
    except Exception:
        pass

    loaded = panel.load_feature13_articles()
    print(f"[LOADER] feature13_panel.load_feature13_articles(): {len(loaded)} rows")

    if len(loaded) == EXPECTED_TOTAL:
        print("[PASS] Dashboard loader sees 770 rows.")
    else:
        print(f"[FAIL] Dashboard loader sees {len(loaded)} rows.")

    # Exact target-year filtering used by the panel.
    filtered = [
        a for a in loaded
        if str(a.get("published_date", "")).startswith(EXPECTED_YEAR)
    ]
    print(f"[LOADER] After 2026 filter: {len(filtered)} rows")

    if len(filtered) == EXPECTED_TOTAL:
        print("[PASS] Dashboard 2026 filter preserves 770 rows.")
    else:
        print(f"[FAIL] Dashboard 2026 filter returns {len(filtered)} rows.")

    print("=" * 76)
    if len(rows) == EXPECTED_TOTAL and len(loaded) == EXPECTED_TOTAL:
        print("DIAGNOSIS: Supabase access + Feature #13 loader are HEALTHY.")
        print("If the live UI still shows 0, investigate Streamlit deployment")
        print("environment/cache/version mismatch rather than the database.")
        status = 0
    else:
        print("DIAGNOSIS: Production environment cannot see the expected")
        print("Feature #13 data. Inspect Supabase project/key/RLS/environment.")
        status = 1

    print("Database mutation: NONE")
    print("Telegram: NOT SENT")
    print("=" * 76)
    raise SystemExit(status)


if __name__ == "__main__":
    main()
