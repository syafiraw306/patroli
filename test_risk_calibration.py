from database import get_all_articles
from patroli import calculate_article_risk
import csv
from collections import Counter

OUT = "risk_calibration_report.csv"

def main():
    print("=" * 78)
    print("RISK ENGINE CALIBRATION TEST — 232 ARTIKEL")
    print("=" * 78)

    articles = get_all_articles()
    print(f"Total artikel dari Supabase : {len(articles)}")
    if not articles:
        print("Tidak ada artikel.")
        return

    results = []
    errors = 0
    for idx, article in enumerate(articles, 1):
        try:
            risk = calculate_article_risk(article, articles)
            f = risk.get("factors", {})
            c = risk.get("context", {})
            results.append({
                "title": article.get("title", ""),
                "category": article.get("category", "Netral"),
                "risk_score": risk.get("risk_score", 0),
                "risk_level": risk.get("risk_level", "LOW"),
                "sentiment": f.get("sentiment_severity", {}).get("score", 0),
                "issue": f.get("issue_severity", {}).get("score", 0),
                "media": f.get("media_spread", {}).get("score", 0),
                "recurrence": f.get("recurrence", {}).get("score", 0),
                "trend": f.get("trend", {}).get("score", 0),
                "related_articles": c.get("related_count", 0),
                "media_count": c.get("media_count", 0),
                "recurrence_count": c.get("recurrence_count", 0),
                "recent_7d": c.get("recent_count", 0),
                "previous_7d": c.get("previous_count", 0),
            })
        except Exception as exc:
            errors += 1
            print(f"[RISK ERROR] {idx}/{len(articles)}: {type(exc).__name__}: {exc}")

    results.sort(key=lambda x: (-x["risk_score"], x["title"]))

    fields = list(results[0].keys())
    with open(OUT, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)

    print(f"\nCSV report             : {OUT}")
    print(f"Berhasil dianalisis   : {len(results)}")
    print(f"Error analisis        : {errors}")

    print("\n" + "=" * 78)
    print("TOP 30")
    print("=" * 78)
    for i, r in enumerate(results[:30], 1):
        print(f"{i:02d}. [{r['risk_score']:3d} | {r['risk_level']:<8}] {r['category']:<20} {r['title']}")
        print(f"    S={r['sentiment']}/25 I={r['issue']}/25 M={r['media']}/20 R={r['recurrence']}/15 T={r['trend']}/15 | media={r['media_count']} recurrence={r['recurrence_count']} recent={r['recent_7d']} prev={r['previous_7d']}")

    levels = Counter(r["risk_level"] for r in results)
    categories = Counter(r["category"] for r in results)
    print("\n" + "=" * 78)
    print("DISTRIBUSI RISK")
    print("=" * 78)
    for level in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
        print(f"{level:<9}: {levels[level]}")

    print("\n" + "=" * 78)
    print("RISK LEVEL PER KATEGORI")
    print("=" * 78)
    for cat in sorted(categories):
        subset = [r for r in results if r["category"] == cat]
        lv = Counter(r["risk_level"] for r in subset)
        print(f"{cat:<22}: total={len(subset):3d} | LOW={lv['LOW']:3d} MEDIUM={lv['MEDIUM']:3d} HIGH={lv['HIGH']:3d} CRITICAL={lv['CRITICAL']:3d}")

    neutral_medium = [r for r in results if r["category"] in {"Netral", "Positif"} and r["risk_score"] >= 31]
    print("\n" + "=" * 78)
    print("AUDIT KALIBRASI")
    print("=" * 78)
    print(f"Netral/Positif dengan risk >= 31 : {len(neutral_medium)}")
    if neutral_medium:
        print("Contoh yang perlu ditinjau:")
        for r in neutral_medium[:10]:
            print(f"- [{r['risk_score']}] {r['category']} | {r['title']}")

    print("\nBoundary check: 30=LOW, 31=MEDIUM, 60=MEDIUM, 61=HIGH, 80=HIGH, 81=CRITICAL sesuai implementasi engine.")
    print("Tidak ada INSERT/UPDATE/DELETE/Telegram dalam test ini.")
    print("=" * 78)

if __name__ == "__main__":
    main()
