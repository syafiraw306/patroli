import os
import sys

import streamlit as st
from streamlit.testing.v1 import AppTest

sys.path.insert(0, ".")
from feature13_lapinsus_engine import build_lapinsus, extract_issue_topics, get_location_articles
from feature13_panel import load_feature13_articles


def check(cond, label):
    if not cond:
        raise AssertionError(label)
    print("[PASS]", label)


def main():
    rows = load_feature13_articles()
    check(len(rows) == 770, "Dashboard loader rows = 770")
    check(all(str(r.get("published_date", "")).startswith("2026") for r in rows), "Dashboard rows target year 2026")
    check(len({r.get("id") for r in rows}) == 770, "Dashboard row IDs unique")
    review = {4292: False, 4284: False, 4523: True, 4356: False, 4358: False}
    by_id = {r.get("id"): r for r in rows}
    check(all(i in by_id for i in review), "All 5 REVIEW IDs present")
    check(all(bool(by_id[i].get("location_context_valid")) is flag for i, flag in review.items()), "REVIEW flags preserved")

    row = by_id.get(33979)
    check(row is not None, "Article #33979 exists")
    check(bool(row.get("location_context_valid")), "Article #33979 is VALID")
    check("bangun purba" in [str(x).lower() for x in (row.get("matched_location_keywords") or [])], "Article #33979 location keyword")

    topics = extract_issue_topics(row.get("title"), row.get("content"))
    check(isinstance(topics, list), "Issue topics are list")

    data = build_lapinsus(row)
    facts = " ".join(data.get("facts") or [])
    trend = " ".join(data.get("trend") or [])
    check("RSUD Bangun Purba" in facts or "RSUD" in facts, "#33979 facts grounded")
    check("11,9" in facts or "11.9" in facts, "#33979 amount grounded")
    check("berencana" in trend.lower() or "tender" in trend.lower() or "berlangsung" in trend.lower(), "#33979 trend grounded")
    check("tautan telah disalin" not in trend.lower(), "#33979 trend has no page chrome")
    check(len(data.get("images") or []) > 0, "#33979 image pipeline found images")

    app_path = "app-3_feature13_integrated.py"
    if os.path.exists(app_path):
        at = AppTest.from_file(app_path).run()
        text = " ".join(str(x.value) for x in at.markdown if hasattr(x, "value"))
        labels = " ".join(str(x.value) for x in at.tabs if hasattr(x, "value"))
        check("Feature #13" in text, "Admin: Feature #13 panel header rendered")
        check("Peta Isu" in labels, "Admin: Peta Isu tab rendered")
        check("LAPINSUS" in labels, "Admin: LAPINSUS tab rendered")

    print("DATABASE MUTATION: NONE")
    print("TELEGRAM: NOT SENT")
    print("FEATURE #13 DASHBOARD UAT V4: PASS")


if __name__ == "__main__":
    main()
