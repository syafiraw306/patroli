import os
import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

from database import (
    get_all_articles,
    get_run_logs
)


# ============================================================
# CONFIG
# ============================================================

st.set_page_config(

    page_title=
        "Dashboard Patroli Siber 2026",

    page_icon=
        "🛡️",

    layout=
        "wide",

    initial_sidebar_state=
        "expanded"

)


# ============================================================
# STYLE
# ============================================================

st.markdown(
    """
    <style>

    [data-testid="stMetricValue"] {
        font-size: 26px;
        font-weight: 700;
    }

    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
    }

    </style>
    """,
    unsafe_allow_html=True
)


# ============================================================
# CONFIG
# ============================================================

NAMA_SATKER = os.getenv(
    "NAMA_SATKER",
    "Kejaksaan Negeri Deli Serdang"
)


TAHUN_TARGET = 2026


# ============================================================
# LOAD
# ============================================================

@st.cache_data(
    ttl=60
)
def load_articles():

    return get_all_articles()


@st.cache_data(
    ttl=30
)
def load_logs():

    return get_run_logs(
        300
    )


articles = load_articles()

logs = load_logs()


# ============================================================
# DATE
# ============================================================

def parse_date(value):

    if not value:
        return None

    try:

        dt = pd.to_datetime(
            value,
            errors="coerce"
        )

        if pd.isna(dt):
            return None

        if getattr(
            dt,
            "tzinfo",
            None
        ):

            dt = dt.tz_convert(
                None
            )

        return dt.to_pydatetime()

    except Exception:

        return None


# ============================================================
# FILTER
# ============================================================

def filter_date(
    article,
    mode
):

    dt = parse_date(
        article.get(
            "published_date"
        )
    )

    if not dt:
        return False


    now = datetime.datetime.now()


    if mode == "24 jam terakhir":

        return (
            dt >=
            now - datetime.timedelta(
                hours=24
            )
            and
            dt <= now
        )


    if mode == "7 hari terakhir":

        return (
            dt >=
            now - datetime.timedelta(
                days=7
            )
            and
            dt <= now
        )


    if mode == "1 bulan terakhir":

        return (
            dt >=
            now - datetime.timedelta(
                days=30
            )
            and
            dt <= now
        )


    if mode == "Tahun 2026":

        return (
            dt.year == 2026
            and
            dt <= now
        )


    return True


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.title(
        "🛡️ Panel Kontrol"
    )

    st.caption(
        "Patroli Siber 2026"
    )

    st.divider()


    st.subheader(
        "Informasi"
    )


    st.text_input(
        "Satker",
        value=NAMA_SATKER,
        disabled=True
    )


    st.text_input(
        "Database",
        value="Supabase",
        disabled=True
    )


    st.text_input(
        "Patroli",
        value="GitHub Actions",
        disabled=True
    )


    telegram_status = (

        "Aktif ✅"

        if (
            os.getenv(
                "TELEGRAM_TOKEN"
            )
            and
            os.getenv(
                "CHAT_ID"
            )
        )

        else

        "Tidak Aktif ❌"

    )


    st.text_input(
        "Telegram",
        value=telegram_status,
        disabled=True
    )


    st.divider()


    if st.button(
        "🔄 Refresh Data",
        use_container_width=True
    ):

        st.cache_data.clear()

        st.rerun()


# ============================================================
# HEADER
# ============================================================

st.title(
    "🛡️ Dashboard Patroli Siber 2026"
)

st.subheader(
    NAMA_SATKER
)

st.caption(
    "Monitoring pemberitaan berbasis "
    "contextual classification + prioritas review."
)


# ============================================================
# FILTER UTAMA
# ============================================================

st.divider()

st.subheader(
    "🕒 Filter Periode"
)


col_filter1, col_filter2 = st.columns(
    2
)


with col_filter1:

    filter_mode = st.selectbox(

        "Periode cepat",

        [

            "24 jam terakhir",
            "7 hari terakhir",
            "1 bulan terakhir",
            "Tahun 2026",
            "Semua data"

        ],

        index=1

    )


with col_filter2:

    bulan_options = {

        0: "Semua Bulan",
        1: "Januari",
        2: "Februari",
        3: "Maret",
        4: "April",
        5: "Mei",
        6: "Juni",
        7: "Juli",
        8: "Agustus",
        9: "September",
        10: "Oktober",
        11: "November",
        12: "Desember"

    }


    bulan_dipilih = st.selectbox(

        "Pilih bulan 2026",

        list(
            bulan_options.values()
        ),

        index=0

    )


# ============================================================
# FILTER ARTICLE
# ============================================================

filtered = []


for article in articles:

    if filter_mode != "Semua data":

        if not filter_date(
            article,
            filter_mode
        ):

            continue


    if bulan_dipilih != "Semua Bulan":

        dt = parse_date(
            article.get(
                "published_date"
            )
        )

        if not dt:
            continue

        month_number = [
            name
            for name, value in bulan_options.items()
            if value == bulan_dipilih
        ][0]


        if (
            dt.year != 2026
            or
            dt.month != month_number
        ):

            continue


    filtered.append(
        article
    )


# ============================================================
# SEARCH
# ============================================================

search_text = st.text_input(
    "🔎 Cari judul / indikator / sumber",
    ""
)


if search_text:

    q = search_text.lower().strip()

    filtered = [

        item

        for item in filtered

        if q in (
            f"{item.get('title', '')} "
            f"{item.get('snippet', '')} "
            f"{item.get('content', '')} "
            f"{' '.join(item.get('detected_keywords', []) or [])}"
        ).lower()

    ]


# ============================================================
# SORT
# ============================================================

priority_order = {

    "KRITIS": 1,
    "TINGGI": 2,
    "SEDANG": 3,
    "RENDAH": 4

}


category_order = {

    "Negatif Kuat": 1,
    "Perlu Penanganan": 2,
    "Netral": 3,
    "Positif": 4

}


filtered.sort(

    key=lambda x: (

        priority_order.get(
            x.get(
                "priority",
                "RENDAH"
            ),
            4
        ),

        category_order.get(
            x.get(
                "category",
                "Netral"
            ),
            3
        ),

        x.get(
            "negative_score",
            0
        ) * -1

    )

)


# ============================================================
# CATEGORIES
# ============================================================

negative = [

    x for x in filtered

    if x.get(
        "category"
    ) == "Negatif Kuat"

]


handling = [

    x for x in filtered

    if x.get(
        "category"
    ) == "Perlu Penanganan"

]


neutral = [

    x for x in filtered

    if x.get(
        "category"
    ) == "Netral"

]


positive = [

    x for x in filtered

    if x.get(
        "category"
    ) == "Positif"

]


priority = [

    x for x in filtered

    if (
        x.get(
            "category"
        )
        in [
            "Negatif Kuat",
            "Perlu Penanganan"
        ]
    )

]


# ============================================================
# METRICS
# ============================================================

st.divider()

st.subheader(
    "📊 Ringkasan"
)


c1, c2, c3, c4, c5 = st.columns(
    5
)


with c1:

    st.metric(
        "🔴 Negatif Kuat",
        len(negative)
    )


with c2:

    st.metric(
        "🟠 Perlu Penanganan",
        len(handling)
    )


with c3:

    st.metric(
        "🟡 Netral",
        len(neutral)
    )


with c4:

    st.metric(
        "🟢 Positif",
        len(positive)
    )


with c5:

    st.metric(
        "🚨 Prioritas Review",
        len(priority)
    )


# ============================================================
# RENDER
# ============================================================

def render_article(
    item
):

    category = item.get(
        "category",
        "Netral"
    )

    priority_value = item.get(
        "priority",
        "RENDAH"
    )


    if category == "Negatif Kuat":

        icon = "🔴"

    elif category == "Perlu Penanganan":

        icon = "🟠"

    elif category == "Positif":

        icon = "🟢"

    else:

        icon = "🟡"


    with st.container(
        border=True
    ):

        col1, col2 = st.columns(
            [6, 1]
        )


        with col1:

            st.markdown(
                f"### {icon} "
                f"{item.get('title', '-')}"
            )


            st.markdown(

                f"**Kategori:** "
                f"{category}  |  "

                f"**Prioritas:** "
                f"{priority_value}  |  "

                f"**Negative Score:** "
                f"{item.get('negative_score', 0)}  |  "

                f"**Handling Score:** "
                f"{item.get('handling_score', 0)}"

            )


            st.caption(
                "📅 "
                + str(
                    item.get(
                        "published_date",
                        "-"
                    )
                )
            )


            snippet = item.get(
                "snippet",
                ""
            )

            if snippet:

                st.write(
                    snippet
                )


            keywords = (
                item.get(
                    "detected_keywords",
                    []
                )
                or []
            )


            if keywords:

                st.markdown(
                    "**🔎 Indikator:** "
                    + ", ".join(
                        keywords[:30]
                    )
                )


            strong_context = (
                item.get(
                    "strong_context",
                    []
                )
                or []
            )


            if strong_context:

                st.warning(
                    "⚠️ Konteks Negatif Kuat: "
                    + ", ".join(
                        strong_context
                    )
                )


            handling_context = (
                item.get(
                    "handling_context",
                    []
                )
                or []
            )


            if handling_context:

                st.info(
                    "📌 Konteks Penanganan: "
                    + ", ".join(
                        handling_context
                    )
                )


            satker = (
                item.get(
                    "satker_matches",
                    []
                )
                or []
            )


            if satker:

                st.caption(
                    "🏢 Satker: "
                    + ", ".join(
                        satker
                    )
                )


        with col2:

            link = item.get(
                "link",
                ""
            )


            if link:

                st.link_button(
                    "🔗 Buka",
                    link,
                    use_container_width=True
                )


# ============================================================
# TABS
# ============================================================

(
    tab_priority,
    tab_negative,
    tab_handling,
    tab_neutral,
    tab_positive,
    tab_analytics,
    tab_logs
) = st.tabs(

    [

        "🚨 PRIORITAS REVIEW",
        "🔴 NEGATIF KUAT",
        "🟠 PERLU PENANGANAN",
        "🟡 NETRAL",
        "🟢 POSITIF",
        "📊 ANALISIS",
        "📜 LOG"

    ]

)


# ============================================================
# PRIORITY
# ============================================================

with tab_priority:

    st.subheader(
        "🚨 Prioritas Review"
    )

    st.caption(
        "Artikel paling berisiko ditempatkan "
        "di bagian atas."
    )


    if priority:

        for item in priority:

            render_article(
                item
            )

    else:

        st.success(
            "Tidak ada artikel prioritas "
            "pada filter yang dipilih."
        )


# ============================================================
# NEGATIVE
# ============================================================

with tab_negative:

    st.subheader(
        "🔴 Negatif Kuat"
    )


    if negative:

        for item in negative:

            render_article(
                item
            )

    else:

        st.info(
            "Tidak ada artikel Negatif Kuat."
        )


# ============================================================
# HANDLING
# ============================================================

with tab_handling:

    st.subheader(
        "🟠 Perlu Penanganan"
    )


    if handling:

        for item in handling:

            render_article(
                item
            )

    else:

        st.info(
            "Tidak ada artikel Perlu Penanganan."
        )


# ============================================================
# NEUTRAL
# ============================================================

with tab_neutral:

    st.subheader(
        "🟡 Artikel Netral"
    )

    st.caption(
        "Tetap tersedia untuk audit klasifikasi."
    )


    if neutral:

        for item in neutral:

            render_article(
                item
            )

    else:

        st.info(
            "Tidak ada artikel Netral."
        )


# ============================================================
# POSITIVE
# ============================================================

with tab_positive:

    st.subheader(
        "🟢 Pemberitaan Positif"
    )


    if positive:

        for item in positive:

            render_article(
                item
            )

    else:

        st.info(
            "Tidak ada artikel Positif."
        )


# ============================================================
# ANALYTICS
# ============================================================

with tab_analytics:

    st.subheader(
        "📊 Analisis"
    )


    chart_data = pd.DataFrame({

        "Kategori": [

            "Negatif Kuat",
            "Perlu Penanganan",
            "Netral",
            "Positif"

        ],

        "Jumlah": [

            len(negative),
            len(handling),
            len(neutral),
            len(positive)

        ]

    })


    if chart_data["Jumlah"].sum() > 0:

        fig = px.pie(

            chart_data,

            names="Kategori",

            values="Jumlah",

            hole=0.45,

            title="Distribusi Kategori"

        )


        st.plotly_chart(
            fig,
            use_container_width=True
        )


    # --------------------------------------------------------
    # PRIORITY
    # --------------------------------------------------------

    priority_df = pd.DataFrame({

        "Prioritas": [

            "KRITIS",
            "TINGGI",
            "SEDANG",
            "RENDAH"

        ],

        "Jumlah": [

            len([
                x for x in filtered
                if x.get("priority") == "KRITIS"
            ]),

            len([
                x for x in filtered
                if x.get("priority") == "TINGGI"
            ]),

            len([
                x for x in filtered
                if x.get("priority") == "SEDANG"
            ]),

            len([
                x for x in filtered
                if x.get("priority") == "RENDAH"
            ])

        ]

    })


    st.dataframe(
        priority_df,
        use_container_width=True,
        hide_index=True
    )


# ============================================================
# LOG
# ============================================================

with tab_logs:

    st.subheader(
        "📜 Log Patroli"
    )


    if logs:

        df_logs = pd.DataFrame(
            logs
        )

        st.dataframe(
            df_logs,
            use_container_width=True,
            hide_index=True
        )

    else:

        st.info(
            "Belum ada log patroli."
        )


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "⚠️ Sistem merupakan alat bantu monitoring "
    "dan klasifikasi awal. Artikel Negatif Kuat "
    "dan Perlu Penanganan tetap perlu diverifikasi "
    "terhadap isi, sumber, konteks, dan fakta."
)
