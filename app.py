import streamlit as st

from database import (
    get_filtered_articles,
    get_category_counts,
    clean_html,
)


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="Dashboard Patroli Siber 2026",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# CUSTOM CSS
# ============================================================

st.markdown(
    """
    <style>

    .main-header {
        font-size: 2rem;
        font-weight: 700;
        margin-bottom: 0.2rem;
    }

    .sub-header {
        color: #6c757d;
        margin-bottom: 1.5rem;
    }

    .news-card {
        padding: 10px 0px;
    }

    .badge {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 5px;
        font-weight: 600;
        font-size: 0.85rem;
    }

    .badge-negative {
        background-color: #ff4d4f;
        color: white;
    }

    .badge-handling {
        background-color: #faad14;
        color: white;
    }

    .badge-positive {
        background-color: #52c41a;
        color: white;
    }

    .badge-neutral {
        background-color: #8c8c8c;
        color: white;
    }

    .article-preview {
        line-height: 1.6;
        color: #444;
    }

    </style>
    """,
    unsafe_allow_html=True
)


# ============================================================
# HEADER
# ============================================================

st.markdown(
    '<div class="main-header">'
    '⚖️ Dashboard Patroli Siber - '
    'Kejaksaan Negeri Deli Serdang'
    '</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="sub-header">'
    'Sistem Pemantauan dan Klasifikasi Media Berita Otomatis'
    '</div>',
    unsafe_allow_html=True
)


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.header(
    "🔍 Filter Data"
)

category_filter = st.sidebar.selectbox(
    "Kategori",
    [
        "Semua Kategori",
        "Negatif Kuat",
        "Perlu Penanganan",
        "Positif",
        "Netral",
    ]
)

priority_filter = st.sidebar.selectbox(
    "Prioritas",
    [
        "Semua Prioritas",
        "TINGGI",
        "SEDANG",
        "RENDAH",
    ]
)

search_query = st.sidebar.text_input(
    "Cari Judul Berita",
    placeholder="Masukkan kata kunci..."
)


# ============================================================
# LOAD DATA
# ============================================================

articles = get_filtered_articles(
    category=category_filter,
    priority=priority_filter,
    search_query=search_query,
    limit=1000,
)


# ============================================================
# STATISTICS
# ============================================================

counts = get_category_counts(
    articles
)

total_articles = len(
    articles
)

negative_count = counts[
    "Negatif Kuat"
]

handling_count = counts[
    "Perlu Penanganan"
]

neutral_count = counts[
    "Netral"
]

positive_count = counts[
    "Positif"
]


# ============================================================
# KPI
# ============================================================

col1, col2, col3, col4, col5 = (
    st.columns(5)
)

col1.metric(
    "📰 Total Berita",
    total_articles
)

col2.metric(
    "🔴 Negatif Kuat",
    negative_count
)

col3.metric(
    "🟡 Perlu Penanganan",
    handling_count
)

col4.metric(
    "🟢 Positif",
    positive_count
)

col5.metric(
    "⚪ Netral",
    neutral_count
)


st.markdown("---")


# ============================================================
# EMPTY STATE
# ============================================================

if not articles:

    st.info(
        "Tidak ada berita yang sesuai "
        "dengan filter."
    )

else:

    # --------------------------------------------------------
    # ARTICLE LIST
    # --------------------------------------------------------

    for index, article in enumerate(
        articles,
        start=1
    ):

        title = clean_html(
            article.get(
                "title",
                "Tanpa Judul"
            )
        )

        content = clean_html(
            article.get(
                "content",
                ""
            )
        )

        category = article.get(
            "category",
            "Netral"
        )

        priority = article.get(
            "priority",
            "RENDAH"
        )

        published_date = article.get(
            "published_date",
            "-"
        )

        link = article.get(
            "link",
            ""
        )

        keywords = article.get(
            "keywords",
            []
        )

        # ----------------------------------------------------
        # BADGE
        # ----------------------------------------------------

        if category == "Negatif Kuat":

            badge = "🔴"
            badge_class = (
                "badge badge-negative"
            )

        elif category == "Perlu Penanganan":

            badge = "🟡"
            badge_class = (
                "badge badge-handling"
            )

        elif category == "Positif":

            badge = "🟢"
            badge_class = (
                "badge badge-positive"
            )

        else:

            badge = "⚪"
            badge_class = (
                "badge badge-neutral"
            )

        # ----------------------------------------------------
        # EXPANDER
        # ----------------------------------------------------

        with st.expander(
            f"{badge} {title}"
        ):

            # ------------------------------------------------
            # META
            # ------------------------------------------------

            meta_col1, meta_col2, meta_col3 = (
                st.columns(3)
            )

            with meta_col1:

                st.markdown(
                    f"**Kategori**  \n"
                    f'<span class="{badge_class}">'
                    f'{category}'
                    f'</span>',
                    unsafe_allow_html=True
                )

            with meta_col2:

                st.write(
                    f"**Prioritas**  \n"
                    f"{priority}"
                )

            with meta_col3:

                st.write(
                    f"**Tanggal**  \n"
                    f"{published_date}"
                )

            st.markdown("---")

            # ------------------------------------------------
            # KEYWORDS
            # ------------------------------------------------

            if keywords:

                if isinstance(
                    keywords,
                    list
                ):

                    keyword_text = (
                        ", ".join(
                            str(k)
                            for k in keywords
                        )
                    )

                else:

                    keyword_text = str(
                        keywords
                    )

                st.write(
                    "**🔎 Kata Kunci Terdeteksi:**"
                )

                st.caption(
                    keyword_text
                )

            # ------------------------------------------------
            # CONTENT
            # ------------------------------------------------

            st.write(
                "**Ringkasan Berita:**"
            )

            if content:

                preview = content[:700]

                if len(content) > 700:

                    preview += "..."

                st.markdown(
                    f'<div class="article-preview">'
                    f'{preview}'
                    f'</div>',
                    unsafe_allow_html=True
                )

            else:

                st.caption(
                    "Konten berita tidak tersedia."
                )

            # ------------------------------------------------
            # LINK
            # ------------------------------------------------

            if link:

                st.markdown(
                    f"[🔗 Baca Berita Selengkapnya]"
                    f"({link})"
                )

            else:

                st.warning(
                    "Link berita tidak tersedia."
                )
st.markdown(
    """
    <div class="main-header">
        ⚖️ Dashboard Patroli Siber 2026
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="sub-header">
        Sistem Pemantauan dan Klasifikasi Media Berita Otomatis
        — Kejaksaan Negeri Deli Serdang
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.header(
    "🔍 Filter Data"
)

category_filter = st.sidebar.selectbox(
    "Kategori",
    [
        "Semua Kategori",
        "Negatif Kuat",
        "Perlu Penanganan",
        "Positif",
        "Netral",
    ],
)

priority_filter = st.sidebar.selectbox(
    "Prioritas",
    [
        "Semua Prioritas",
        "TINGGI",
        "SEDANG",
        "RENDAH",
    ],
)

search_query = st.sidebar.text_input(
    "Cari Judul Berita",
    placeholder="Masukkan kata pada judul..."
)

limit_data = st.sidebar.number_input(
    "Jumlah berita",
    min_value=10,
    max_value=5000,
    value=1000,
    step=100,
)


# ============================================================
# AMBIL DATA
# ============================================================

articles = get_filtered_articles(

    category=category_filter,

    priority=priority_filter,

    search_query=search_query,

    limit=int(limit_data),
)


# ============================================================
# NORMALISASI DATA
# ============================================================

if not articles:

    articles = []


# ============================================================
# STATISTIK
# ============================================================

total_art = len(
    articles
)

neg_count = sum(
    1
    for article in articles
    if article.get(
        "category"
    ) == "Negatif Kuat"
)

handling_count = sum(
    1
    for article in articles
    if article.get(
        "category"
    ) == "Perlu Penanganan"
)

positive_count = sum(
    1
    for article in articles
    if article.get(
        "category"
    ) == "Positif"
)

neutral_count = sum(
    1
    for article in articles
    if article.get(
        "category"
    ) == "Netral"
)


# ============================================================
# KPI
# ============================================================

col1, col2, col3, col4, col5 = st.columns(5)

col1.metric(
    "📰 Total Berita",
    total_art
)

col2.metric(
    "🔴 Negatif Kuat",
    neg_count
)

col3.metric(
    "🟡 Perlu Penanganan",
    handling_count
)

col4.metric(
    "🟢 Positif",
    positive_count
)

col5.metric(
    "⚪ Netral",
    neutral_count
)


st.markdown("---")


# ============================================================
# RINGKASAN
# ============================================================

if articles:

    df = pd.DataFrame(
        articles
    )

    if "category" in df.columns:

        st.subheader(
            "📊 Ringkasan Kategori"
        )

        category_df = (
            df[
                "category"
            ]
            .fillna("Netral")
            .value_counts()
            .rename_axis("Kategori")
            .reset_index(
                name="Jumlah"
            )
        )

        st.dataframe(
            category_df,
            use_container_width=True,
            hide_index=True,
        )


# ============================================================
# DAFTAR BERITA
# ============================================================

st.markdown("---")

st.subheader(
    "📰 Daftar Berita"
)


if not articles:

    st.info(
        "Tidak ada berita yang sesuai dengan filter."
    )

else:

    for index, article in enumerate(
        articles,
        start=1
    ):

        # ----------------------------------------------------
        # DATA
        # ----------------------------------------------------

        title = clean_html(
            article.get(
                "title",
                "Tanpa Judul"
            )
        )

        content = clean_html(
            article.get(
                "content",
                ""
            )
        )

        category = article.get(
            "category",
            "Netral"
        )

        priority = article.get(
            "priority",
            "RENDAH"
        )

        published_date = article.get(
            "published_date",
            "-"
        )

        url = article.get(
            "url",
            ""
        )

        keywords = clean_keywords(
            article.get(
                "keywords",
                []
            )
        )

        # ----------------------------------------------------
        # BADGE
        # ----------------------------------------------------

        if category == "Negatif Kuat":

            badge = "🔴"

        elif category == "Perlu Penanganan":

            badge = "🟡"

        elif category == "Positif":

            badge = "🟢"

        else:

            badge = "⚪"

        # ----------------------------------------------------
        # EXPANDER
        # ----------------------------------------------------

        with st.expander(
            f"{badge} {title}"
        ):

            # ------------------------------------------------
            # INFORMASI UTAMA
            # ------------------------------------------------

            info_col1, info_col2, info_col3 = st.columns(3)

            info_col1.write(
                f"**Kategori:** {category}"
            )

            info_col2.write(
                f"**Prioritas:** {priority}"
            )

            info_col3.write(
                f"**Tanggal:** {published_date}"
            )

            st.markdown("---")

            # ------------------------------------------------
            # KEYWORDS
            # ------------------------------------------------

            if keywords:

                st.write(
                    "**🔎 Kata Kunci Terdeteksi:**"
                )

                st.write(
                    ", ".join(
                        keywords
                    )
                )

            else:

                st.write(
                    "**🔎 Kata Kunci:** Tidak ada"
                )

            # ------------------------------------------------
            # PREVIEW
            # ------------------------------------------------

            if content:

                preview = content[:700]

                if len(content) > 700:

                    preview += "..."

                st.write(
                    preview
                )

            else:

                st.info(
                    "Isi berita tidak tersedia."
                )

            # ------------------------------------------------
            # LINK
            # ------------------------------------------------

            if url:

                st.markdown(
                    f"[🔗 Baca Berita Selengkapnya]({url})"
                )

            else:

                st.warning(
                    "Link berita tidak tersedia."
                )


# ============================================================
# FOOTER
# ============================================================

st.markdown("---")

st.caption(
    "Dashboard Patroli Siber 2026 "
    "— Kejaksaan Negeri Deli Serdang"
)

