from database import get_all_articles
from risk_engine import calculate_risk_score


def main():
    print("=" * 70)
    print("TEST RISK ENGINE DARI SUPABASE")
    print("=" * 70)

    # READ ONLY
    articles = get_all_articles()

    print(f"\nTotal artikel dari Supabase : {len(articles)}")

    if not articles:
        print("Tidak ada artikel.")
        return

    print("\nMenghitung Risk Score...\n")

    results = []

    for article in articles:

        risk = calculate_risk_score(article)

        results.append({
            "title": article.get("title", ""),
            "category": article.get("category", "Netral"),
            "risk_score": risk["risk_score"],
            "risk_level": risk["risk_level"],
            "factors": risk["factors"],
            "reasons": risk["reasons"],
        })

    # Urutkan dari risiko tertinggi
    results.sort(
        key=lambda x: x["risk_score"],
        reverse=True
    )

    print("=" * 70)
    print("TOP 10 ARTIKEL DENGAN RISK TERTINGGI")
    print("=" * 70)

    for i, item in enumerate(results[:10], start=1):

        print(f"\n{i}. {item['title']}")
        print(f"   Category   : {item['category']}")
        print(f"   Risk Score : {item['risk_score']}/100")
        print(f"   Risk Level : {item['risk_level']}")

        print("   Factors:")

        for factor_name, factor in item["factors"].items():

            print(
                f"      - {factor_name}: "
                f"{factor['score']}/{factor['max_score']}"
            )

        if item["reasons"]:
            print("   Reasons:")

            for reason in item["reasons"]:
                print(f"      - {reason}")

    # Statistik
    level_count = {
        "CRITICAL": 0,
        "HIGH": 0,
        "MEDIUM": 0,
        "LOW": 0,
    }

    for item in results:
        level = item["risk_level"]

        if level in level_count:
            level_count[level] += 1

    print("\n" + "=" * 70)
    print("DISTRIBUSI RISK")
    print("=" * 70)

    print(f"CRITICAL : {level_count['CRITICAL']}")
    print(f"HIGH     : {level_count['HIGH']}")
    print(f"MEDIUM   : {level_count['MEDIUM']}")
    print(f"LOW      : {level_count['LOW']}")

    print("\n" + "=" * 70)
    print("TEST SELESAI")
    print("Tidak ada data yang diubah ke Supabase.")
    print("=" * 70)


if __name__ == "__main__":
    main()
