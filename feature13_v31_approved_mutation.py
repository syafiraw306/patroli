import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from supabase import create_client

TABLE = "deli_serdang_location_articles"
TARGET_YEAR = 2026
WHITELIST_PATH = Path(__file__).with_name("feature13_v31_final_approval_whitelist_CORRECTED.json")
REPORT_JSON = Path("feature13_v31_approved_mutation_report.json")
REPORT_CSV = Path("feature13_v31_approved_mutation_report.csv")

EXPECTED_BEFORE = 793
EXPECTED_AFTER = 770
EXPECTED_UPDATES = 56
EXPECTED_DELETES = 23
REVIEW_IDS = {4284, 4292, 4356, 4358, 4523}


def client():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY belum tersedia")
    return create_client(url, key)


def load_whitelist():
    d = json.loads(WHITELIST_PATH.read_text(encoding="utf-8"))
    updates = {int(x) for x in d["approved_update_ids_all_v31"]}
    deletes = {int(x) for x in d["approved_delete_ids_all_v31"]}
    review = {int(x) for x in d["remaining_review_ids"]}
    return d, updates, deletes, review


def fetch_all(sb):
    rows = []
    start = 0
    page = 500
    while True:
        res = (
            sb.table(TABLE)
            .select("id,location_context_valid,published_date,title,link")
            .order("id")
            .range(start, start + page - 1)
            .execute()
        )
        batch = res.data or []
        rows.extend(batch)
        if len(batch) < page:
            break
        start += page
    return rows


def write_report(report):
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["id,action,status,current_flag,title"]
    import csv
    with REPORT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "action", "status", "current_flag", "title"])
        for r in report.get("actions", []):
            w.writerow([r["id"], r["action"], r["status"], r.get("current_flag"), r.get("title", "")])


def fail(report, message):
    report["status"] = "FAILED"
    report.setdefault("failures", []).append(message)
    write_report(report)
    print(f"[FAIL] {message}")
    print(f"[REPORT] {REPORT_JSON}")
    sys.exit(1)


def main():
    print("=" * 70)
    print("FEATURE #13 — V3.1 APPROVED MUTATION")
    print("=" * 70)

    d, update_ids, delete_ids, review_ids = load_whitelist()
    if d.get("table") != TABLE or int(d.get("target_year")) != TARGET_YEAR:
        raise RuntimeError("Whitelist table/target_year tidak sesuai")
    if len(update_ids) != EXPECTED_UPDATES:
        raise RuntimeError(f"UPDATE whitelist harus {EXPECTED_UPDATES}, ditemukan {len(update_ids)}")
    if len(delete_ids) != EXPECTED_DELETES:
        raise RuntimeError(f"DELETE whitelist harus {EXPECTED_DELETES}, ditemukan {len(delete_ids)}")
    if review_ids != REVIEW_IDS:
        raise RuntimeError(f"REVIEW IDs tidak sesuai: {sorted(review_ids)}")
    if update_ids & delete_ids or update_ids & review_ids or delete_ids & review_ids:
        raise RuntimeError("Overlap whitelist UPDATE/DELETE/REVIEW terdeteksi")

    sb = client()
    print("[SUPABASE] Client berhasil dibuat.")
    rows = fetch_all(sb)
    before = len(rows)
    by_id = {int(r["id"]): r for r in rows}

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "FEATURE13-V31-APPROVED-MUTATION",
        "table": TABLE,
        "target_year": TARGET_YEAR,
        "database_mutated": False,
        "production_articles_touched": False,
        "telegram_sent": False,
        "current_row_count_before": before,
        "expected_row_count_before": EXPECTED_BEFORE,
        "expected_row_count_after": EXPECTED_AFTER,
        "approved_update_whitelist": len(update_ids),
        "approved_delete_whitelist": len(delete_ids),
        "remaining_review": sorted(review_ids),
        "actions": [],
        "failures": [],
    }

    # HARD PRE-CHECKS — no mutation before every check passes.
    if before != EXPECTED_BEFORE:
        fail(report, f"Row count sebelum mutation {before}, expected {EXPECTED_BEFORE}")
    if len(by_id) != before:
        fail(report, "ID tidak unik")
    missing_updates = sorted(update_ids - set(by_id))
    missing_deletes = sorted(delete_ids - set(by_id))
    if missing_updates:
        fail(report, f"UPDATE IDs hilang: {missing_updates}")
    if missing_deletes:
        fail(report, f"DELETE IDs hilang: {missing_deletes}")
    for rid in review_ids:
        if rid not in by_id:
            fail(report, f"REVIEW ID hilang: {rid}")
    bad_year = []
    for rid in update_ids | delete_ids:
        value = by_id[rid].get("published_date")
        if not value or not str(value).startswith("2026-"):
            bad_year.append(rid)
    if bad_year:
        fail(report, f"Whitelist rows bukan 2026: {bad_year}")
    bad_delete_flags = [rid for rid in delete_ids if by_id[rid].get("location_context_valid") is not False]
    if bad_delete_flags:
        fail(report, f"DELETE guard gagal, flag bukan false: {bad_delete_flags}")
    bad_review = [rid for rid in review_ids if rid in update_ids or rid in delete_ids]
    if bad_review:
        fail(report, f"REVIEW overlap mutation: {bad_review}")

    print(f"[PRECHECK PASS] rows={before} | UPDATE={len(update_ids)} | DELETE={len(delete_ids)} | REVIEW={len(review_ids)}")
    print("[PRECHECK PASS] Tidak ada mutation sebelum seluruh guardrail lolos.")

    # Phase 1: idempotent UPDATE. Only approved IDs are touched.
    updated = []
    for rid in sorted(update_ids):
        current = by_id[rid].get("location_context_valid")
        if current is True:
            status = "NOOP_ALREADY_TRUE"
        else:
            sb.table(TABLE).update({"location_context_valid": True}).eq("id", rid).execute()
            status = "UPDATED"
            updated.append(rid)
        report["actions"].append({
            "id": rid, "action": "UPDATE_LOCATION_CONTEXT_TRUE", "status": status,
            "current_flag": current, "title": by_id[rid].get("title", "")
        })
    print(f"[MUTATION] UPDATE phase complete: {len(updated)} rows changed, {len(update_ids)-len(updated)} already true.")

    # Phase 2: DELETE. Each delete is re-guarded immediately before execution.
    deleted = []
    for rid in sorted(delete_ids):
        check = sb.table(TABLE).select("id,location_context_valid,published_date,title").eq("id", rid).limit(1).execute()
        current_rows = check.data or []
        if len(current_rows) != 1:
            fail(report, f"DELETE precheck failed for id={rid}: row tidak ditemukan/unik")
        row = current_rows[0]
        if row.get("location_context_valid") is not False:
            fail(report, f"DELETE guard failed for id={rid}: current flag bukan false")
        if not str(row.get("published_date", "")).startswith("2026-"):
            fail(report, f"DELETE guard failed for id={rid}: bukan tahun 2026")
        sb.table(TABLE).delete().eq("id", rid).execute()
        deleted.append(rid)
        report["actions"].append({
            "id": rid, "action": "DELETE_LOCATION_ROW", "status": "DELETED",
            "current_flag": False, "title": row.get("title", "")
        })
    print(f"[MUTATION] DELETE phase complete: {len(deleted)} rows deleted.")

    # Phase 3: post-mutation verification.
    after_rows = fetch_all(sb)
    after = len(after_rows)
    after_ids = {int(r["id"]) for r in after_rows}
    failures = []
    if after != EXPECTED_AFTER:
        failures.append(f"post row count={after}, expected={EXPECTED_AFTER}")
    remaining_deletes = sorted(delete_ids & after_ids)
    if remaining_deletes:
        failures.append(f"DELETE IDs masih ada: {remaining_deletes}")
    missing_updates_after = sorted(update_ids - after_ids)
    if missing_updates_after:
        failures.append(f"UPDATE IDs hilang setelah mutation: {missing_updates_after}")
    for rid in update_ids:
        row = next((r for r in after_rows if int(r["id"]) == rid), None)
        if row and row.get("location_context_valid") is not True:
            failures.append(f"UPDATE flag gagal untuk id={rid}")
    missing_review_after = sorted(review_ids - after_ids)
    if missing_review_after:
        failures.append(f"REVIEW IDs hilang: {missing_review_after}")

    report["current_row_count_after"] = after
    report["updated_ids"] = updated
    report["deleted_ids"] = deleted
    report["deleted_count"] = len(deleted)
    report["updated_changed_count"] = len(updated)
    report["database_mutated"] = True
    report["failures"] = failures
    report["status"] = "PASSED" if not failures else "FAILED_POST_VERIFY"
    write_report(report)

    print("=" * 70)
    print(f"Status                    : {report['status']}")
    print(f"Rows before               : {before}")
    print(f"Rows after                : {after} (expected {EXPECTED_AFTER})")
    print(f"UPDATE whitelist          : {len(update_ids)}")
    print(f"UPDATE changed            : {len(updated)}")
    print(f"DELETE whitelist          : {len(delete_ids)}")
    print(f"DELETE executed            : {len(deleted)}")
    print(f"REVIEW preserved          : {sorted(review_ids)}")
    print("Production articles       : untouched")
    print("Telegram                  : not sent")
    print(f"JSON report               : {REPORT_JSON}")
    print(f"CSV report                : {REPORT_CSV}")
    print("=" * 70)
    if failures:
        for x in failures:
            print(f"[POST-VERIFY FAIL] {x}")
        sys.exit(1)


if __name__ == "__main__":
    main()
