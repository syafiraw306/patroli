from patroli import classify_article


TEST_CASES = [

    {
        "title": "Kajari Deli Serdang diperiksa Kejagung",
        "content": "",
        "expected": "Negatif Kuat",
    },

    {
        "title": "Kajari Deli Serdang dicopot",
        "content": "",
        "expected": "Negatif Kuat",
    },

    {
        "title": "Jaksa di Madina diperiksa",
        "content": "",
        "expected": "Netral",
    },

    {
        "title": "Kajari Sergai diamankan Kejagung",
        "content": "",
        "expected": "Netral",
    },

    {
        "title": "Kajari Palas dicopot",
        "content": "",
        "expected": "Netral",
    },

    {
        "title": (
            "Kajari Deliserdang Pimpin Sertijab Kasi Pidsus, "
            "Tekankan Integritas dan Percepatan Penanganan Korupsi"
        ),
        "content": "",
        "expected": "Positif",
    },

    {
        "title": (
            "Kejari Deli Serdang berhasil menangkap "
            "tersangka korupsi"
        ),
        "content": "",
        "expected": "Positif",
    },

    {
        "title": (
            "Kejari Deli Serdang melakukan penyidikan "
            "kasus korupsi"
        ),
        "content": "",
        "expected": "Netral",
    },

]


failed = 0


for i, test in enumerate(TEST_CASES, start=1):

    title = test["title"]
    content = test["content"]
    expected = test["expected"]

    result = classify_article(
        title,
        content,
    )

    actual = result.get(
        "category",
        "UNKNOWN",
    )

    print("=" * 70)

    print(f"TEST #{i}")
    print()
    print("TITLE:")
    print(title)
    print()
    print("EXPECTED:", expected)
    print("ACTUAL  :", actual)
    print()
    print("NEGATIVE SCORE:", result.get("negative_score"))
    print("POSITIVE SCORE:", result.get("positive_score"))
    print("HANDLING SCORE:", result.get("handling_score"))
    print("NEGATIVE CONTEXT:", result.get("negative_context"))
    print("POSITIVE CONTEXT:", result.get("positive_context"))

    if actual == expected:

        print()
        print("✅ PASS")

    else:

        print()
        print("❌ FAIL")

        failed += 1


print("=" * 70)

if failed > 0:

    print(f"❌ TOTAL FAILED: {failed}")

    raise SystemExit(1)

else:

    print("✅ ALL CLASSIFICATION TESTS PASSED")
