import re
from collections import defaultdict
from itertools import combinations


# ============================================================
# STOPWORDS
# ============================================================

STOPWORDS = {
    "dan",
    "di",
    "ke",
    "dari",
    "yang",
    "untuk",
    "dengan",
    "pada",
    "oleh",
    "ini",
    "itu",
    "ada",
    "akan",
    "jadi",
    "jadi",
    "usai",
    "setelah",
    "hingga",
    "karena",
    "soal",
    "tentang",
    "dalam",
    "atas",
    "atau",
    "sebagai",
    "para",
    "saat",
    "sudah",
    "resmi",
}


# ============================================================
# EVENT KEYWORDS
# ============================================================

EVENT_KEYWORDS = {
    "diperiksa",
    "pemeriksaan",
    "dipanggil",
    "panggil",
    "dicopot",
    "pencopotan",
    "diamankan",
    "pengamanan",
    "ditunjuk",
    "pengganti",
    "pelanggaran",
    "etik",
    "kejagung",
    "kejaksaan",
    "restorative",
    "justice",
    "korupsi",
    "tersangka",
    "penyelidikan",
    "penyidikan",
    "penganiayaan",
    "pembunuhan",
    "tuntut",
    "hukuman",
    "lelang",
}


# ============================================================
# NORMALIZE TEXT
# ============================================================

def normalize_text(text):
    """
    Membersihkan teks agar mudah dibandingkan.
    """

    if not text:
        return ""

    text = text.lower()

    # Hilangkan nama domain/media
    text = re.sub(
        r"\b(detikcom|kompas\.com|inews\.id|waspada\.id|tribunnews\.com|"
        r"tribun-medan\.com|antaranews|tvonenews|medanbisnisdaily\.com)\b",
        "",
        text
    )

    # Hilangkan tanda baca
    text = re.sub(r"[^a-z0-9\s]", " ", text)

    # Hilangkan whitespace berlebih
    text = re.sub(r"\s+", " ", text).strip()

    return text


# ============================================================
# TOKENIZE TITLE
# ============================================================

def get_tokens(text):

    text = normalize_text(text)

    tokens = text.split()

    tokens = [
        token
        for token in tokens
        if token not in STOPWORDS
        and len(token) > 2
    ]

    return set(tokens)


# ============================================================
# GET EVENT KEYWORDS
# ============================================================

def extract_event_keywords(title):

    tokens = get_tokens(title)

    keywords = tokens.intersection(EVENT_KEYWORDS)

    return keywords


# ============================================================
# JACCARD SIMILARITY
# ============================================================

def jaccard_similarity(set_a, set_b):

    if not set_a or not set_b:
        return 0.0

    intersection = set_a.intersection(set_b)

    union = set_a.union(set_b)

    return len(intersection) / len(union)


# ============================================================
# SATKER SIMILARITY
# ============================================================

def satker_match(article_a, article_b):

    satker_a = article_a.get("satker", [])
    satker_b = article_b.get("satker", [])

    if isinstance(satker_a, str):
        satker_a = [satker_a]

    if isinstance(satker_b, str):
        satker_b = [satker_b]

    satker_a = {
        normalize_text(x)
        for x in satker_a
        if x
    }

    satker_b = {
        normalize_text(x)
        for x in satker_b
        if x
    }

    if not satker_a or not satker_b:
        return False

    return bool(satker_a.intersection(satker_b))


# ============================================================
# EVENT KEYWORD MATCH
# ============================================================

def event_keyword_match(article_a, article_b):

    keywords_a = extract_event_keywords(
        article_a.get("title", "")
    )

    keywords_b = extract_event_keywords(
        article_b.get("title", "")
    )

    if not keywords_a or not keywords_b:
        return False

    return bool(
        keywords_a.intersection(keywords_b)
    )


# ============================================================
# CHECK SAME EVENT
# ============================================================

def is_same_event(
    article_a,
    article_b,
    similarity_threshold=0.35
):

    title_a = article_a.get("title", "")
    title_b = article_b.get("title", "")

    tokens_a = get_tokens(title_a)
    tokens_b = get_tokens(title_b)

    similarity = jaccard_similarity(
        tokens_a,
        tokens_b
    )

    same_satker = satker_match(
        article_a,
        article_b
    )

    same_event_keyword = event_keyword_match(
        article_a,
        article_b
    )

    # --------------------------------------------------------
    # RULE 1
    # Judul sangat mirip
    # --------------------------------------------------------

    if similarity >= 0.60:
        return True, similarity

    # --------------------------------------------------------
    # RULE 2
    # Satker sama + keyword event sama + similarity cukup
    # --------------------------------------------------------

    if (
        same_satker
        and same_event_keyword
        and similarity >= similarity_threshold
    ):
        return True, similarity

    return False, similarity


# ============================================================
# UNION FIND
# ============================================================

class UnionFind:

    def __init__(self, n):

        self.parent = list(range(n))

    def find(self, x):

        if self.parent[x] != x:

            self.parent[x] = self.find(
                self.parent[x]
            )

        return self.parent[x]

    def union(self, x, y):

        root_x = self.find(x)

        root_y = self.find(y)

        if root_x != root_y:

            self.parent[root_y] = root_x


# ============================================================
# CLUSTER EVENTS
# ============================================================

def cluster_events(articles):

    total_articles = len(articles)

    union_find = UnionFind(
        total_articles
    )

    similarities = {}

    # --------------------------------------------------------
    # BANDINKAN SETIAP ARTIKEL
    # --------------------------------------------------------

    for i, j in combinations(
        range(total_articles),
        2
    ):

        article_a = articles[i]
        article_b = articles[j]

        same_event, similarity = is_same_event(
            article_a,
            article_b
        )

        if same_event:

            union_find.union(i, j)

            similarities[
                (i, j)
            ] = similarity

    # --------------------------------------------------------
    # BENTUK CLUSTER
    # --------------------------------------------------------

    clusters = defaultdict(list)

    for index, article in enumerate(articles):

        root = union_find.find(index)

        clusters[root].append(article)

    # Hanya cluster dengan >= 2 artikel

    event_clusters = [
        cluster
        for cluster in clusters.values()
        if len(cluster) >= 2
    ]

    # Urutkan berdasarkan jumlah artikel

    event_clusters.sort(
        key=len,
        reverse=True
    )

    return event_clusters


# ============================================================
# GENERATE EVENT NAME
# ============================================================

def generate_event_name(cluster):

    all_keywords = []

    for article in cluster:

        title = article.get("title", "")

        tokens = get_tokens(title)

        all_keywords.extend(tokens)

    counter = defaultdict(int)

    for keyword in all_keywords:

        counter[keyword] += 1

    sorted_keywords = sorted(
        counter.items(),
        key=lambda x: x[1],
        reverse=True
    )

    top_keywords = [
        keyword
        for keyword, count
        in sorted_keywords[:5]
    ]

    return " ".join(top_keywords)


# ============================================================
# AUDIT FUNCTION
# ============================================================

def audit_event_duplicates(articles):

    print("=" * 70)

    print("AUDIT EVENT DUPLICATES")

    print("TIDAK ADA DATA YANG DIUBAH")

    print("=" * 70)

    total_articles = len(articles)

    print()

    print(
        f"[AUDIT] Total artikel: "
        f"{total_articles}"
    )

    print()

    # --------------------------------------------------------
    # CLUSTER
    # --------------------------------------------------------

    event_clusters = cluster_events(
        articles
    )

    clustered_article_ids = set()

    for cluster in event_clusters:

        for article in cluster:

            clustered_article_ids.add(
                article.get("id")
            )

    clustered_articles = len(
        clustered_article_ids
    )

    single_articles = (
        total_articles
        - clustered_articles
    )

    estimated_total_events = (
        len(event_clusters)
        + single_articles
    )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    print("=" * 70)

    print("RINGKASAN EVENT")

    print("=" * 70)

    print()

    print(
        f"Total artikel              : "
        f"{total_articles}"
    )

    print(
        f"Event cluster              : "
        f"{len(event_clusters)}"
    )

    print(
        f"Artikel dalam event cluster: "
        f"{clustered_articles}"
    )

    print(
        f"Single article event       : "
        f"{single_articles}"
    )

    print(
        f"Estimasi total event       : "
        f"{estimated_total_events}"
    )

    print()

    # --------------------------------------------------------
    # DETAIL CLUSTER
    # --------------------------------------------------------

    for number, cluster in enumerate(
        event_clusters,
        start=1
    ):

        print("=" * 70)

        print(
            f"EVENT CLUSTER #{number}"
        )

        print("=" * 70)

        event_name = generate_event_name(
            cluster
        )

        print()

        print(
            f"EVENT : {event_name}"
        )

        print()

        print(
            f"Jumlah artikel : "
            f"{len(cluster)}"
        )

        # SATKER

        satkers = set()

        for article in cluster:

            article_satker = article.get(
                "satker",
                []
            )

            if isinstance(
                article_satker,
                str
            ):
                article_satker = [
                    article_satker
                ]

            for satker in article_satker:

                if satker:
                    satkers.add(satker)

        print()

        print("SATKER:")

        if satkers:

            for satker in sorted(satkers):

                print(
                    f"- {satker}"
                )

        else:

            print("- Tidak terdeteksi")

        # EVENT KEYWORDS

        keywords = set()

        for article in cluster:

            keywords.update(
                extract_event_keywords(
                    article.get(
                        "title",
                        ""
                    )
                )
            )

        print()

        print("EVENT KEYWORDS:")

        if keywords:

            for keyword in sorted(keywords):

                print(
                    f"- {keyword}"
                )

        else:

            print("- Tidak terdeteksi")

        # ARTICLES

        print()

        print("ARTIKEL:")

        for index, article in enumerate(
            cluster,
            start=1
        ):

            article_id = article.get(
                "id",
                "-"
            )

            title = article.get(
                "title",
                "-"
            )

            print()

            print(
                f"[{index}] ID={article_id}"
            )

            print(title)

        print()

    # --------------------------------------------------------
    # FINAL
    # --------------------------------------------------------

    print("=" * 70)

    print(
        "AUDIT EVENT DUPLICATES SELESAI"
    )

    print("=" * 70)

    print()

    print(
        "TIDAK ADA DATA YANG DIUBAH"
    )

    print()

    return event_clusters
