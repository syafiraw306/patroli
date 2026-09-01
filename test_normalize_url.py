from database import normalize_url


url_1 = (
    "https://news.google.com/rss/articles/"
    "CBMiTEST123?oc=5&hl=id&gl=ID&ceid=ID:id"
)

url_2 = (
    "https://news.google.com/rss/articles/"
    "CBMiTEST123?oc=5&hl=en-US&gl=US&ceid=US:en"
)


normalized_1 = normalize_url(url_1)
normalized_2 = normalize_url(url_2)


print("=" * 70)

print("URL 1:")
print(url_1)

print()
print("NORMALIZED 1:")
print(normalized_1)

print()
print("-" * 70)

print()

print("URL 2:")
print(url_2)

print()
print("NORMALIZED 2:")
print(normalized_2)

print()
print("=" * 70)


if normalized_1 == normalized_2:

    print("✅ PASS")
    print("Google News URL dianggap sama")

else:

    print("❌ FAIL")
    print("Google News URL masih dianggap berbeda")

    raise SystemExit(1)
