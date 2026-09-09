import csv, json
from pathlib import Path
from datetime import datetime, timezone
from patroli import get_supabase

WL = Path("feature13_v31_final_approval_whitelist.json")
OUT_JSON = Path("feature13_v31_approved_mutation_dry_run.json")
OUT_CSV = Path("feature13_v31_approved_mutation_dry_run.csv")
TABLE = "deli_serdang_location_articles"

def main():
    wl = json.loads(WL.read_text(encoding="utf-8"))
    update_ids = set(wl["approved_update_ids_all_v31"])
    delete_ids = set(wl["approved_delete_ids_all_v31"])
    review_ids = set(wl["remaining_review_ids"])

    if update_ids & delete_ids:
        raise RuntimeError("GUARDRAIL FAIL: update/delete whitelist overlap")
    if (update_ids | delete_ids) & review_ids:
        raise RuntimeError("GUARDRAIL FAIL: REVIEW ID masuk mutation whitelist")

    sb = get_supabase()
    rows, offset, batch = [], 0, 500
    while True:
        resp = (sb.table(TABLE)
                  .select("id,title,link,published_date,location_context_valid")
                  .range(offset, offset + batch - 1).execute())
        chunk = list(resp.data or [])
        rows.extend(chunk)
        if len(chunk) < batch: break
        offset += batch

    by_id = {int(r["id"]): r for r in rows}
    missing_u = sorted(update_ids - set(by_id))
    missing_d = sorted(delete_ids - set(by_id))
    if missing_u or missing_d:
        raise RuntimeError(f"GUARDRAIL FAIL: missing IDs update={missing_u}, delete={missing_d}")

    actions = []
    for rid in sorted(update_ids):
        r = by_id[rid]
        actions.append({
            "id": rid,
            "planned_action": "UPDATE_LOCATION_CONTEXT_TRUE",
            "current_location_context_valid": bool(r.get("location_context_valid")),
            "title": r.get("title"), "link": r.get("link"),
            "published_date": r.get("published_date")
        })
    for rid in sorted(delete_ids):
        r = by_id[rid]
        actions.append({
            "id": rid,
            "planned_action": "DELETE_LOCATION_ROW",
            "current_location_context_valid": bool(r.get("location_context_valid")),
            "title": r.get("title"), "link": r.get("link"),
            "published_date": r.get("published_date")
        })

    update_needed = sum(a["planned_action"]=="UPDATE_LOCATION_CONTEXT_TRUE" and not a["current_location_context_valid"] for a in actions)
    update_noop = sum(a["planned_action"]=="UPDATE_LOCATION_CONTEXT_TRUE" and a["current_location_context_valid"] for a in actions)
    delete_candidates = sum(a["planned_action"]=="DELETE_LOCATION_ROW" for a in actions)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target_year": 2026, "table": TABLE,
        "mode": "FEATURE13-V31-APPROVED-MUTATION-DRY-RUN",
        "database_mutated": False, "production_articles_touched": False,
        "telegram_sent": False, "input_rows": len(rows),
        "approved_update_whitelist": len(update_ids),
        "approved_delete_whitelist": len(delete_ids),
        "remaining_review": sorted(review_ids),
        "update_needed": update_needed,
        "update_noop_already_true": update_noop,
        "delete_candidates": delete_candidates,
        "total_planned_actions": len(actions),
        "rows": actions,
        "guardrails": {
            "only_location_table": True,
            "production_articles_touched": False,
            "telegram_sent": False,
            "database_mutated": False,
            "review_ids_excluded": True,
            "whitelist_overlap": False,
            "missing_whitelist_ids": False
        }
    }
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    fields = ["id","planned_action","current_location_context_valid","title","link","published_date"]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(actions)

    print("="*70)
    print("FEATURE #13 — V3.1 APPROVED MUTATION DRY-RUN")
    print("="*70)
    print("Mode                  : READ-ONLY")
    print("INSERT/UPDATE/DELETE  : DISABLED")
    print(f"Rows read             : {len(rows)}")
    print(f"UPDATE whitelist      : {len(update_ids)}")
    print(f"UPDATE actually needed: {update_needed}")
    print(f"UPDATE already true   : {update_noop}")
    print(f"DELETE candidates     : {delete_candidates}")
    print(f"REVIEW excluded       : {len(review_ids)}")
    print(f"JSON report           : {OUT_JSON}")
    print(f"CSV report            : {OUT_CSV}")
    print("[ACTION] READ-ONLY: DATABASE TIDAK DIUBAH")

if __name__ == "__main__":
    main()
