from database import get_all_articles
from patroli import calculate_article_risk


def main():
    print("=" * 70)
    print("TEST RISK ENGINE — 5 FAKTOR AKTIF")
    print("=" * 70)

    articles = get_all_articles()
    print(f"\nTotal artikel dari Supabase : {len(articles)}")

    if not articles:
        print("Tidak ada artikel.")
        return

    results = []
    for index, article in enumerate(articles, start=1):
        try:
            risk = calculate_article_risk(article, articles)
            results.append({
                "title": article.get("title", ""),
                "category": article.get("category", "Netral"),
                "risk_score": risk["risk_score"],
                "risk_level": risk["risk_level"],
                "factors": risk["factors"],
                "context": risk["context"],
                "reasons": risk["reasons"],
            })
        except Exception as exc:
            print(f"[RISK ERROR] {index}/{len(articles)}: {type(exc).__name__}: {exc}")

    results.sort(key=lambda item: item["risk_score"], reverse=True)

    print("\n" + "=" * 70)
    print("TOP 10 ARTIKEL DENGAN RISK TERTINGGI")
    print("=" * 70)

    for i, item in enumerate(results[:10], start=1):
        print(f"\n{i}. {item['title']}")
        print(f"   Category   : {item['category']}")
        print(f"   Risk Score : {item['risk_score']}/100")
        print(f"   Risk Level : {item['risk_level']}")
        print("   Factors:")
        for name, factor in item["factors"].items():
            print(f"      - {name}: {factor['score']}/{factor['max_score']}")
        ctx = item["context"]
        print("   Context:")
        print(f"      - related_articles : {ctx['related_count']}")
        print(f"      - media_count      : {ctx['media_count']}")
        print(f"      - recurrence_count : {ctx['recurrence_count']}")
        print(f"      - recent_7d        : {ctx['recent_count']}")
        print(f"      - previous_7d      : {ctx['previous_count']}")
        if item["reasons"]:
            print("   Reasons:")
            for reason in item["reasons"]:
                print(f"      - {reason}")

    level_count = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    factor_positive = {
        "sentiment_severity": 0,
        "issue_severity": 0,
        "media_spread": 0,
        "recurrence": 0,
        "trend": 0,
    }

    for item in results:
        level = item["risk_level"]
        if level in level_count:
            level_count[level] += 1
        for factor_name, factor in item["factors"].items():
            if factor.get("score", 0) > 0:
                factor_positive[factor_name] += 1

    print("\n" + "=" * 70)
    print("DISTRIBUSI RISK")
    print("=" * 70)
    print(f"CRITICAL : {level_count['CRITICAL']}")
    print(f"HIGH     : {level_count['HIGH']}")
    print(f"MEDIUM   : {level_count['MEDIUM']}")
    print(f"LOW      : {level_count['LOW']}")

    print("\n" + "=" * 70)
    print("AKTIVASI FAKTOR")
    print("=" * 70)
    print(f"Sentiment Severity > 0 : {factor_positive['sentiment_severity']}")
    print(f"Issue Severity > 0     : {factor_positive['issue_severity']}")
    print(f"Media Spread > 0       : {factor_positive['media_spread']}")
    print(f"Recurrence > 0         : {factor_positive['recurrence']}")
    print(f"Trend > 0              : {factor_positive['trend']}")

    print("\n" + "=" * 70)
    print("TEST SELESAI")
    print("Tidak ada data yang diubah ke Supabase.")
    print("=" * 70)


if __name__ == "__main__":
    main()
