
"""
Feature #13 — Dashboard UAT (READ-ONLY)

Runs against the real Supabase environment and exercises the Feature #13
Streamlit panel in both Admin and Viewer modes.

Safety:
- SELECT/read-only validation only.
- Does NOT call mark_generated().
- Does NOT click Generate LAPINSUS.
- Does NOT INSERT/UPDATE/DELETE.
- Does NOT send Telegram.
"""
import os
import sys
from pathlib import Path

EXPECTED_ROWS = 770
REVIEW_FLAGS = {4284: False, 4292: False, 4356: False, 4358: False, 4523: True}


def check(cond, label):
    if not cond:
        raise AssertionError(label)
    print(f"[PASS] {label}")


def run_panel_uat(is_admin: bool):
    from streamlit.testing.v1 import AppTest
    import feature13_panel as panel

    # The real panel contains a Folium custom component. For deterministic
    # Streamlit AppTest, replace only the rendering sink; the map data logic
    # still executes normally.
    panel.st_folium = lambda *args, **kwargs: None

    harness = f"""
import streamlit as st
import feature13_panel as panel

st.session_state.clear()
panel.render_feature13_panel(is_admin={is_admin!r})
"""
    at = AppTest.from_string(harness).run(timeout=120)

    return at


def main():
    print("=" * 72)
    print("FEATURE #13 — DASHBOARD UAT (REAL SUPABASE / READ-ONLY)")
    print("=" * 72)

    check(os.environ.get("SUPABASE_URL"), "SUPABASE_URL tersedia")
    check(os.environ.get("SUPABASE_KEY"), "SUPABASE_KEY tersedia")

    import feature13_panel as panel

    # Real production read path used by the dashboard.
    rows = panel.load_feature13_articles()
    check(len(rows) == EXPECTED_ROWS, f"Dashboard loader rows = {len(rows)} expected={EXPECTED_ROWS}")
    check(all(str(r.get("published_date", "")).startswith("2026") for r in rows),
          "Dashboard rows target year 2026")
    check(all(r.get("title") for r in rows), "Dashboard rows have titles")
    check(all(r.get("link") for r in rows), "Dashboard rows have links")

    ids = {int(r["id"]) for r in rows if r.get("id") is not None}
    check(len(ids) == len(rows), "Dashboard row IDs unique")

    review = {int(r["id"]): bool(r.get("location_context_valid"))
              for r in rows if int(r.get("id", -1)) in REVIEW_FLAGS}
    check(set(review) == set(REVIEW_FLAGS), "All 5 approved REVIEW IDs present")
    check(review == REVIEW_FLAGS, f"REVIEW flags preserved: {review}")

    valid = [r for r in rows if bool(r.get("location_context_valid"))]
    check(valid, "At least one VALID article available")

    # Admin UAT: Feature #13 renders and exposes the Generate button,
    # but this test deliberately does not click it.
    admin = run_panel_uat(True)
    admin_text = " ".join(
        [x.value for x in admin.text if hasattr(x, "value")]
        + [x.value for x in admin.markdown if hasattr(x, "value")]
    )
    check(any("Feature #13" in str(x.value) for x in admin.header),
          "Admin: Feature #13 panel header rendered")
    # Streamlit AppTest metric objects expose label/value through different
    # versions. Inspect the metric collection defensively instead of assuming
    # a particular object attribute layout.
    metric_dump = []
    for m in getattr(admin, "metric", []):
        metric_dump.append(str(getattr(m, "label", "")))
        metric_dump.append(str(getattr(m, "value", "")))
        metric_dump.append(str(m))
    check(any("Total artikel" in item for item in metric_dump),
          "Admin: KPI Total artikel rendered")
    check(any(str(EXPECTED_ROWS) in item for item in metric_dump),
          f"Admin: KPI value {EXPECTED_ROWS} rendered")
    check(any("Generate LAPINSUS PDF" in str(x.label) for x in admin.button),
          "Admin: Generate LAPINSUS PDF control available")
    tab_dump = []
    for t in getattr(admin, "tabs", []):
        tab_dump.append(str(getattr(t, "label", "")))
        tab_dump.append(str(t))
    check(any("🗺️ Heatmap" in item for item in tab_dump),
          "Admin: Heatmap tab rendered")
    check(any("📄 LAPINSUS" in item for item in tab_dump),
          "Admin: LAPINSUS tab rendered")

    # Viewer UAT: panel renders, but generation control must not be available.
    viewer = run_panel_uat(False)
    check(any("Feature #13" in str(x.value) for x in viewer.header),
          "Viewer: Feature #13 panel header rendered")
    check(any("Generate LAPINSUS tersedia untuk ADMIN" in str(x.value)
              for x in viewer.info),
          "Viewer: Generate LAPINSUS restricted to Admin")

    # Read-only LAPINSUS preview on a real valid article.
    from feature13_lapinsus_engine import build_lapinsus, make_pdf
    sample = valid[0]
    data = build_lapinsus(sample)
    check(bool(data.get("report_number")), "LAPINSUS preview report number")
    check(bool(data.get("title")), "LAPINSUS preview title")
    pdf = make_pdf(data)
    check(pdf[:4] == b"%PDF", "LAPINSUS PDF bytes valid")
    check(len(pdf) > 10000, f"LAPINSUS PDF generated in memory ({len(pdf)} bytes)")

    print("=" * 72)
    print("STATUS: PASSED")
    print(f"Location rows observed: {len(rows)}")
    print("Admin UI: PASS")
    print("Viewer UI: PASS")
    print("Heatmap tab: PASS")
    print("LAPINSUS preview/PDF: PASS")
    print("Database mutation: NONE")
    print("Telegram: NOT SENT")
    print("Generate LAPINSUS clicked: NO")
    print("=" * 72)


if __name__ == "__main__":
    main()
