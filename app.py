import os
import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

from database import (
    get_all_articles,
    get_run_logs
)

st.set_page_config(
    page_title="Dashboard Patroli Siber 2026",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.write("VERSI APP.PY TERBARU - 28 AGUSTUS 2026")


# ============================================================
# CONFIG APLIKASI
# ============================================================

NAMA_SATKER = os.getenv(
    "NAMA_SATKER",
    "Kejaksaan Negeri Deli Serdang"
)

TAHUN_TARGET = 2026


# ============================================================
# LOGIN CONFIG
# ============================================================

def get_users():
    """
    Membaca konfigurasi user dari Streamlit Secrets.

    Format secrets:

    [users.admin]
    username = "admin"
    password = "password_admin"
    role = "admin"

    [users.viewer]
    username = "viewer"
    password = "password_viewer"
    role = "viewer"
    """

    users = {}

    try:

        if "users" not in st.secrets:
            return users

        secret_users = st.secrets["users"]

        for user_key in secret_users:

            user_data = secret_users[user_key]

            username = str(
                user_data.get(
                    "username",
                    ""
                )
            ).strip()

            password = str(
                user_data.get(
                    "password",
                    ""
                )
            )

            role = str(
                user_data.get(
                    "role",
                    "viewer"
                )
            ).lower().strip()

            # Hanya menerima 2 role
            if role not in [
                "admin",
                "viewer"
            ]:
                continue

            if not username or not password:
                continue

            users[username] = {
                "password": password,
                "role": role
            }

    except Exception as e:

        st.error(
            f"Gagal membaca konfigurasi login: {e}"
        )

    return users


# ============================================================
# AUTHENTICATION
# ============================================================

def authenticate(
    username,
    password
):

    users = get_users()

    username = str(
        username
    ).strip()

    password = str(
        password
    )

    if not users:
        return None

    user = users.get(
        username
    )

    if not user:
        return None

    if str(
        user["password"]
    ) != password:

        return None

    return {
        "username": username,
        "role": user["role"]
    }


# ============================================================
# SESSION STATE
# ============================================================

if "logged_in" not in st.session_state:

    st.session_state.logged_in = False


if "username" not in st.session_state:

    st.session_state.username = ""


if "role" not in st.session_state:

    st.session_state.role = ""


# ============================================================
# LOGIN PAGE
# ============================================================
if not st.session_state.logged_in:

    st.markdown("<br><br>", unsafe_allow_html=True)

    col_left, col_center, col_right = st.columns([1, 2, 1])

    with col_center:

        st.title("🛡️ Dashboard Patroli Siber 2026")

        st.write("Sistem Monitoring Pemberitaan")

        st.divider()

        st.subheader("🔐 Login Sistem")

        username = st.text_input(
            "Username",
            placeholder="Masukkan username",
            key="login_username"
        )

        password = st.text_input(
            "Password",
            type="password",
            placeholder="Masukkan password",
            key="login_password"
        )

        login_button = st.button(
            "🔐 Masuk",
            type="primary",
            use_container_width=True
        )

        if login_button:

            if not username or not password:

                st.error(
                    "Username dan password wajib diisi."
                )

            else:

                user = authenticate(
                    username,
                    password
                )

                if user is None:

                    st.error(
                        "❌ Username atau password salah."
                    )

                else:

                    st.session_state.logged_in = True
                    st.session_state.username = user["username"]
                    st.session_state.role = user["role"]

                    st.rerun()

        st.divider()

        st.caption(
            f"{NAMA_SATKER} • Sistem Internal"
        )

    st.stop()
# ============================================================
# CURRENT USER
# ============================================================

CURRENT_USERNAME = (
    st.session_state.username
)

CURRENT_ROLE = (
    st.session_state.role
)


# ============================================================
# ROLE VALIDATION
# ============================================================

if CURRENT_ROLE not in [
    "admin",
    "viewer"
]:

    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.role = ""

    st.error(
        "Role pengguna tidak valid."
    )

    st.stop()


IS_ADMIN = (
    CURRENT_ROLE == "admin"
)

IS_VIEWER = (
    CURRENT_ROLE == "viewer"
)


# ============================================================
# LOAD DATA
# ============================================================

@st.cache_data(ttl=60)
def load_articles():

    return get_all_articles()


@st.cache_data(ttl=30)
def load_logs():

    return get_run_logs(300)


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
# FILTER DATE
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
            dt >= now - datetime.timedelta(
                hours=24
            )
            and
            dt <= now
        )

    if mode == "7 hari terakhir":

        return (
            dt >= now - datetime.timedelta(
                days=7
            )
            and
            dt <= now
        )

    if mode == "1 bulan terakhir":

        return (
            dt >= now - datetime.timedelta(
                days=30
            )
            and
            dt <= now
        )

    if mode == "Tahun 2026":

        return (
            dt.year == TAHUN_TARGET
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

    # ========================================================
    # USER
    # ========================================================

    st.subheader(
        "👤 Pengguna"
    )

    st.write(
        f"**Username:** {CURRENT_USERNAME}"
    )

    if IS_ADMIN:

        st.success(
            "👑 Role: ADMIN"
        )

        st.caption(
            "Akses penuh sistem"
        )

    else:

        st.info(
            "👁️ Role: VIEWER"
        )

        st.caption(
            "Akses monitoring"
        )

    # ========================================================
    # LOGOUT
    # ========================================================

    if st.button(
        "🚪 Logout",
        use_container_width=True
    ):

        st.session_state.logged_in = False
        st.session_state.username = ""
        st.session_state.role = ""

        st.cache_data.clear()

        st.rerun()

    st.divider()

    # ========================================================
    # INFORMASI SISTEM
    # ========================================================

    st.subheader(
        "ℹ️ Informasi Sistem"
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

    # ========================================================
    # REFRESH
    # ADMIN ONLY
    # ========================================================

    if IS_ADMIN:

        st.subheader(
            "⚙️ Administrasi"
        )

        if st.button(
            "🔄 Refresh Data",
            use_container_width=True
        ):

            st.cache_data.clear()

            st.rerun()

    else:

        st.caption(
            "🔒 Refresh Data hanya tersedia "
            "untuk Admin."
        )


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

        month_number = next(

            number

            for number, name
            in bulan_options.items()

            if name == bulan_dipilih

        )

        if (
            dt.year != TAHUN_TARGET
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

    if x.get(
        "category"
    ) in [
        "Negatif Kuat",
        "Perlu Penanganan"
    ]

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
# RENDER ARTICLE
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

tabs = [

    "🚨 PRIORITAS REVIEW",
    "🔴 NEGATIF KUAT",
    "🟠 PERLU PENANGANAN",
    "🟡 NETRAL",
    "🟢 POSITIF",
    "📊 ANALISIS"
]


# ============================================================
# ADMIN ONLY TAB
# ============================================================

if IS_ADMIN:

    tabs.append(
        "📜 LOG"
    )


tab_objects = st.tabs(
    tabs
)


tab_priority = tab_objects[0]
tab_negative = tab_objects[1]
tab_handling = tab_objects[2]
tab_neutral = tab_objects[3]
tab_positive = tab_objects[4]
tab_analytics = tab_objects[5]

if IS_ADMIN:

    tab_logs = tab_objects[6]


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

    st.subheader(
        "📊 Distribusi Prioritas"
    )

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

    # --------------------------------------------------------
    # STATISTIK TAMBAHAN
    # --------------------------------------------------------

    st.subheader(
        "📈 Statistik"
    )

    a1, a2, a3 = st.columns(3)

    with a1:

        st.metric(
            "Total Artikel",
            len(filtered)
        )

    with a2:

        st.metric(
            "Prioritas Review",
            len(priority)
        )

    with a3:

        st.metric(
            "Artikel Positif",
            len(positive)
        )


# ============================================================
# LOG
# ADMIN ONLY
# ============================================================

if IS_ADMIN:

    with tab_logs:

        st.subheader(
            "📜 Log Patroli"
        )

        st.caption(
            "Log patroli hanya dapat diakses "
            "oleh pengguna dengan role ADMIN."
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
    "terhadap isi, sumber, dan fakta."
)

st.caption(
    f"👤 Login: {CURRENT_USERNAME} "
    f"• Role: {CURRENT_ROLE.upper()}"
)
