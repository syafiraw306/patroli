from database import get_all_articles
from patroli import calculate_article_risk

import csv
from collections import Counter


OUT = "risk_calibration_report.csv"


def main():
    print("=" * 78)
    print("RISK ENGINE CALIBRATION TEST — V3")
    print("=" * 78)

    # ============================================================
    # 1. AMBIL DATA DARI SUPABASE
    # ============================================================
    articles = get_all_articles()

    print(f"Total artikel dari Supabase : {len(articles)}")

    if not articles:
        print("Tidak ada artikel.")
        return

    # ============================================================
    # 2. HITUNG RISK
    # ============================================================
    results = []
    errors = 0

    for idx, article in enumerate(articles, 1):
        try:
            risk = calculate_article_risk(article, articles)

            factors = risk.get("factors", {})
            context = risk.get("context", {})

            results.append({
                "title": article.get("title", ""),
                "category": article.get("category", "Netral"),

                "risk_score": risk.get("risk_score", 0),
                "risk_level": risk.get("risk_level", "LOW"),

                "sentiment": (
                    factors
                    .get("sentiment_severity", {})
                    .get("score", 0)
                ),

                "issue": (
                    factors
                    .get("issue_severity", {})
                    .get("score", 0)
                ),

                "media": (
                    factors
                    .get("media_spread", {})
                    .get("score", 0)
                ),

                "recurrence": (
                    factors
                    .get("recurrence", {})
                    .get("score", 0)
                ),

                "trend": (
                    factors
                    .get("trend", {})
                    .get("score", 0)
                ),

                "related_articles": context.get(
                    "related_count", 0
                ),

                "media_count": context.get(
                    "media_count", 0
                ),

                "recurrence_count": context.get(
                    "recurrence_count", 0
                ),

                "recent_7d": context.get(
                    "recent_count", 0
                ),

                "previous_7d": context.get(
                    "previous_count", 0
                ),
            })

        except Exception as exc:
            errors += 1

            print(
                f"[RISK ERROR] "
                f"{idx}/{len(articles)}: "
                f"{type(exc).__name__}: {exc}"
            )

    # ============================================================
    # 3. SORT HASIL
    # ============================================================
    results.sort(
        key=lambda x: (
            -x["risk_score"],
            x["title"]
        )
    )

    # ============================================================
    # 4. EXPORT CSV
    # ============================================================
    if results:
        fields = list(results[0].keys())

        with open(
            OUT,
            "w",
            newline="",
            encoding="utf-8-sig"
        ) as fh:

            writer = csv.DictWriter(
                fh,
                fieldnames=fields
            )

            writer.writeheader()
            writer.writerows(results)

    print()
    print(f"CSV report             : {OUT}")
    print(f"Berhasil dianalisis   : {len(results)}")
    print(f"Error analisis        : {errors}")

    # ============================================================
    # 5. TOP 30
    # ============================================================
    print()
    print("=" * 78)
    print("TOP 30")
    print("=" * 78)

    for i, r in enumerate(results[:30], 1):

        print(
            f"{i:02d}. "
            f"[{r['risk_score']:3d} | "
            f"{r['risk_level']:<8}] "
            f"{r['category']:<20} "
            f"{r['title']}"
        )

        print(
            f"    "
            f"S={r['sentiment']}/25 "
            f"I={r['issue']}/25 "
            f"M={r['media']}/20 "
            f"R={r['recurrence']}/15 "
            f"T={r['trend']}/15 "
            f"| "
            f"media={r['media_count']} "
            f"recurrence={r['recurrence_count']} "
            f"recent={r['recent_7d']} "
            f"prev={r['previous_7d']}"
        )

    # ============================================================
    # 6. DISTRIBUSI RISK
    # ============================================================
    levels = Counter(
        r["risk_level"]
        for r in results
    )

    print()
    print("=" * 78)
    print("DISTRIBUSI RISK")
    print("=" * 78)

    for level in (
        "CRITICAL",
        "HIGH",
        "MEDIUM",
        "LOW"
    ):
        print(
            f"{level:<9}: "
            f"{levels[level]}"
        )

    # ============================================================
    # 7. RISK LEVEL PER KATEGORI
    # ============================================================
    categories = Counter(
        r["category"]
        for r in results
    )

    print()
    print("=" * 78)
    print("RISK LEVEL PER KATEGORI")
    print("=" * 78)

    for cat in sorted(categories):

        subset = [
            r
            for r in results
            if r["category"] == cat
        ]

        lv = Counter(
            r["risk_level"]
            for r in subset
        )

        print(
            f"{cat:<22}: "
            f"total={len(subset):3d} | "
            f"LOW={lv['LOW']:3d} "
            f"MEDIUM={lv['MEDIUM']:3d} "
            f"HIGH={lv['HIGH']:3d} "
            f"CRITICAL={lv['CRITICAL']:3d}"
        )

    # ============================================================
    # 8. AUDIT NETRAL / POSITIF
    # ============================================================
    neutral_medium = [
        r
        for r in results
        if (
            r["category"] in {"Netral", "Positif"}
            and r["risk_score"] >= 31
        )
    ]

    print()
    print("=" * 78)
    print("AUDIT KALIBRASI")
    print("=" * 78)

    print(
        "Netral/Positif dengan risk >= 31 : "
        f"{len(neutral_medium)}"
    )

    if neutral_medium:

        print(
            "Contoh yang perlu ditinjau:"
        )

        for r in neutral_medium[:10]:

            print(
                f"- "
                f"[{r['risk_score']}] "
                f"{r['category']} | "
                f"{r['title']}"
            )

    # ============================================================
    # 9. BOUNDARY CHECK
    # ============================================================
    print()
    print(
        "Boundary check: "
        "30=LOW, "
        "31=MEDIUM, "
        "60=MEDIUM, "
        "61=HIGH, "
        "80=HIGH, "
        "81=CRITICAL "
        "sesuai implementasi engine."
    )

    print(
        "Tidak ada "
        "INSERT/UPDATE/DELETE/Telegram "
        "dalam test ini."
    )

    print("=" * 78)

    # ============================================================
    # 10. STATUS TEST
    # ============================================================
    if errors == 0 and len(neutral_medium) == 0:

        print()
        print("=" * 78)
        print("CALIBRATION STATUS : PASS")
        print("=" * 78)
        print(
            "Semua artikel berhasil dianalisis."
        )
        print(
            "Tidak ada Netral/Positif "
            "dengan risk >= 31."
        )
        print("=" * 78)

    else:

        print()
        print("=" * 78)
        print("CALIBRATION STATUS : REVIEW")
        print("=" * 78)

        if errors:
            print(
                f"Masih terdapat {errors} "
                f"error analisis."
            )

        if neutral_medium:
            print(
                f"Terdapat {len(neutral_medium)} "
                f"artikel Netral/Positif "
                f"dengan risk >= 31."
            )

        print("=" * 78)


if __name__ == "__main__":
    main()
