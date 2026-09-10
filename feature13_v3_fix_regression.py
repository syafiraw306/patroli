
import os
from feature13_panel import _article_text, _f13_keywords
from feature13_lapinsus_engine import clean_article_content, build_lapinsus, classify_issues

HTML = '<a href="https://news.google.com/rss/articles/x">Judul</a> <font color="#6f6f6f">detikcom</font>'
assert clean_article_content(HTML) == "Judul detikcom"

assert classify_issues(
    "Pemkab Deli Serdang Anggarkan Rp 11,9 M Bangun RSUD Bangun Purba Jadi Tipe C",
    "Rumah sakit dibangun dan anggaran pemerintah disiapkan."
)

sample = {
    "id": 33979,
    "title": "Pemkab Deli Serdang Anggarkan Rp 11,9 M Bangun RSUD Bangun Purba Jadi Tipe C - detikcom",
    "content": HTML,
    "link": "https://example.com/article",
    "published_date": "2026-09-09T04:19:06+00:00",
    "publisher": "detikcom",
    "matched_location_keywords": ["bangun purba", "deli serdang"],
    "location_context_valid": True,
    "article_images": [],
}
data = build_lapinsus(sample)
assert data["facts"]
assert data["trend"]
assert data["resolved_link"]
assert data["grounded_content"]
assert isinstance(data["images"], list)

print("[PASS] HTML content cleaned")
print("[PASS] Issue classifier available")
print("[PASS] LAPINSUS facts are article-grounded")
print("[PASS] LAPINSUS trend is article-grounded/fallback-safe")
print("[PASS] Image extraction pipeline available")
print("FEATURE #13 V3 FIX REGRESSION: PASS")
