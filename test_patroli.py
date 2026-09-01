from patroli import (
    sentence_contains_satker,
    sentence_contains_internal_actor
)

TEST_CASES = [
    (
        "Kajari Deli Serdang diperiksa Kejagung",
        True,
        True,
    ),
    (
        "Kajari Deli Serdang dicopot",
        True,
        True,
    ),
    (
        "Jaksa di Madina diperiksa",
        False,
        False,
    ),
    (
        "Kajari Sergai diamankan Kejagung",
        False,
        False,
    ),
    (
        "Kajari Palas dicopot",
        False,
        False,
    ),
    (
    "Kajari Deliserdang Pimpin Sertijab Kasi Pidsus, Tekankan Integritas dan Percepatan Penanganan Korupsi",
    True,
    True,
    ),
    (
    "Kejari Deli Serdang berhasil menangkap tersangka korupsi",
    True,
    True,
    ),
    (
    "Kejari Deli Serdang melakukan penyidikan kasus korupsi",
    True,
    True,
    ),
]

for text, expected_satker, expected_actor in TEST_CASES:

    satker = sentence_contains_satker(text)
    actor = sentence_contains_internal_actor(text)

    print("=" * 70)
    print("TEXT:", text)
    print()
    print("SATKER RESULT :", satker)
    print("EXPECTED      :", expected_satker)
    print()
    print("ACTOR RESULT  :", actor)
    print("EXPECTED      :", expected_actor)

    if (
        satker == expected_satker
        and actor == expected_actor
    ):
        print("\n✅ PASS")
    else:
        print("\n❌ FAIL")
