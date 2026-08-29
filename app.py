
import datetime
import os

import pandas as pd
import plotly.express as px
import streamlit as st

from database import (
    get_all_articles,
    get_run_logs,
)


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="Patroli Siber 2026",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# KONFIGURASI
# ============================================================

NAMA_SATKER = os.getenv(
    "NAMA_SATKER",
    "Kejaksaan Negeri Deli Serdang"
).strip()

TAHUN_TARGET = 2026


# ============================================================
# CSS
# ============================================================

st.markdown(
    """
    <style>

    .block-container {
        max-width: 1450px;
        padding-top: 2rem;
        padding-bottom: 3rem;
    }

    section[data-testid="stSidebar"] {
        border-right: 1px solid #e5e7eb;
    }

    .section-title {
        font-size: 21px;
        font-weight: 800;
        color: #111827;
        margin-top: 10px;
        margin-bottom: 5px;
    }

    .section-description {
        color: #6b7280;
        font-size: 13px;
        margin-bottom: 16px;
    }

    .login-box {
        padding-top: 60px;
    }

    .login-icon {
        text-align: center;
        font-size: 60px;
        margin-bottom: 10px;
    }

    .login-heading {
        text-align: center;
        font-size: 32px;
        font-weight: 800;
        color: #8b0000;
        margin-bottom: 5px;
    }

    .login-description {
        text-align: center;
        color: #6b7280;
        font-size: 14px;
        margin-bottom: 30px;
    }

    .login-satker {
        text-align: center;
        color: #6b7280;
        font-size: 12px;
        margin-top: 20px;
    }

    .dashboard-title {
        font-size: 30px;
        font-weight: 800;
        color: #8b0000;
        margin-bottom: 4px;
    }

    .dashboard-subtitle {
        color: #6b7280;
        font-size: 14px;
        margin-bottom: 8px;
    }

    .satker-badge {
        display: inline-block;
        background: #fef2f2;
        color: #8b0000;
        border: 1px solid #fecaca;
        border-radius: 999px;
        padding: 5px 12px;
        font-size: 12px;
        font-weight: 600;
        margin-bottom: 20px;
    }

    [data-testid="stMetricValue"] {
        font-size: 28px;
        font-weight: 800;
    }

    [data-testid="stMetricLabel"] {
        font-weight: 600;
    }

    </style>
    """,
    unsafe_allow_html=True,
)


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
# AUTHENTICATION
# ============================================================

def get_users():
    users = {}

    try:

        if "users" not in st.secrets:
            return users

        secret_users = st.secrets["users"]

        for user_key in secret_users:

            user_data = secret_users[user_key]

            username = str(
                user_data.get("username", "")
            ).strip()

            password = str(
                user_data.get("password", "")
            )

            role = str(
                user_data.get("role", "viewer")
            ).lower().strip()

            if (
                role in ["admin", "viewer"]
                and username
                and password
            ):
                users[username] = {
                    "password": password,
                    "role": role,
                }

    except Exception as e:

        st.error(
            f"Gagal membaca konfigurasi login: {e}"
        )

    return users


def authenticate(username, password):

    users = get_users()

    username = str(username).strip()

    user = users.get(username)

    if user:

        if str(user["password"]) == str(password):

            return {
                "username": username,
                "role": user["role"],
            }

    return None


# ============================================================
# LOGIN PAGE
# ============================================================

if not st.session_state.logged_in:

    left, center, right = st.columns(
        [1, 2, 1]
    )

    with center:

        st.markdown(
            '<div class="login-box"></div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            """
            <div class="login-icon">
                🛡️
            </div>

            <div class="login-heading">
                Patroli Siber 2026
            </div>

            <div class="login-description">
                Sistem Monitoring Pemberitaan
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.form(
            "login_form",
            clear_on_submit=False
        ):

            username = st.text_input(
                "Username",
                placeholder="Masukkan username",
            )

            password = st.text_input(
                "Password",
                type="password",
                placeholder="Masukkan password",
            )

            login_button = st.form_submit_button(
                "🔐 Masuk ke Dashboard",
                type="primary",
                use_container_width=True,
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
                        st.session_state.username = (
                            user["username"]
                        )
                        st.session_state.role = (
                            user["role"]
                        )

                        st.rerun()

        st.markdown(
            f"""
            <div class="login-satker">
                🏛️ {NAMA_SATKER}<br>
                Sistem Internal • Tahun {TAHUN_TARGET}
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.stop()


# ============================================================
# USER SESSION
# ============================================================

CURRENT_USERNAME = (
    st.session_state.username
)

CURRENT_ROLE = (
    st.session_state.role
)

IS_ADMIN = CURRENT_ROLE == "admin"

IS_VIEWER = CURRENT_ROLE == "viewer"


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


# ============================================================
# LOAD DATA
# ============================================================

@st.cache_data(ttl=60)
def load_articles():

    return get_all_articles()


@st.cache_data(ttl=30)
def load_logs():

    return get_run_logs(300)


try:

    articles = load_articles()

except Exception as e:

    articles = []

    st.error(
        f"Gagal mengambil data artikel: {e}"
    )


try:

    logs = (
        load_logs()
        if IS_ADMIN
        else []
    )

except Exception as e:

    logs = []

    if IS_ADMIN:

        st.warning(
            f"Gagal mengambil log patroli: {e}"
        )


# ============================================================
# HELPER
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

            try:

                dt = dt.tz_convert(None)

            except Exception:

                dt = dt.replace(
                    tzinfo=None
                )

        return dt.to_pydatetime()

    except Exception:

        return None


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
            dt >= now
            - datetime.timedelta(
                hours=24
            )
            and dt <= now
        )

    if mode == "7 hari terakhir":

        return (
            dt >= now
            - datetime.timedelta(
                days=7
            )
            and dt <= now
        )

    if mode == "1 bulan terakhir":

        return (
            dt >= now
            - datetime.timedelta(
                days=30
            )
            and dt <= now
        )

    if mode == "Tahun 2026":

        return (
            dt.year == TAHUN_TARGET
            and dt <= now
        )

    return True


def safe_list(value):

    if not value:
        return []

    if isinstance(
        value,
        list
    ):

        return value

    return [str(value)]


def article_sort_key(article):

    dt = parse_date(
        article.get(
            "published_date"
        )
    )

    if dt is None:

        return datetime.datetime.min

    return dt


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.markdown(
        "## 🛡️ Patroli Siber"
    )

    st.caption(
        "Dashboard Monitoring 2026"
    )

    st.divider()

    st.markdown(
        "### 👤 Pengguna"
    )

    st.write(
        f"**{CURRENT_USERNAME}**"
    )

    if IS_ADMIN:

        st.success(
            "👑 ADMIN"
        )

        st.caption(
            "Akses penuh sistem"
        )

    else:

        st.info(
            "👁️ VIEWER"
        )

        st.caption(
            "Akses monitoring"
        )

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

    st.markdown(
        "### ℹ️ Informasi Sistem"
    )

    st.text_input(
        "Satker",
        value=NAMA_SATKER,
        disabled=True,
    )

    st.text_input(
        "Database",
        value="Supabase",
        disabled=True,
    )

    st.text_input(
        "Patroli Otomatis",
        value="GitHub Actions",
        disabled=True,
    )

    telegram_status = (
        "Aktif ✅"
        if (
            os.getenv("TELEGRAM_TOKEN")
            and os.getenv("CHAT_ID")
        )
        else
        "Tidak Aktif ❌"
    )

    st.text_input(
        "Telegram",
        value=telegram_status,
        disabled=True,
    )

    if IS_ADMIN:

        st.divider()

        st.markdown(
            "### ⚙️ Administrasi"
        )

        if st.button(
            "🔄 Refresh Data",
            use_container_width=True
        ):

            st.cache_data.clear()

            st.rerun()

    st.divider()

    st.caption(
        "Patroli otomatis menjalankan "
        "pengambilan dan klasifikasi berita."
    )


# ============================================================
# DASHBOARD HEADER
# ============================================================

st.markdown(
    """
    <div class="dashboard-title">
        🛡️ Patroli Siber 2026
    </div>

    <div class="dashboard-subtitle">
        Monitoring dan klasifikasi awal pemberitaan
        untuk mendukung proses review informasi.
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    f"""
    <div class="satker-badge">
        🏛️ {NAMA_SATKER}
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# FILTER MONITORING
# ============================================================

st.markdown(
    '<div class="section-title">🕒 Filter Monitoring</div>',
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="section-description">'
    'Gunakan filter untuk mempersempit pemberitaan yang ditampilkan.'
    '</div>',
    unsafe_allow_html=True,
)


col_filter1, col_filter2 = st.columns(2)


with col_filter1:

    filter_mode = st.selectbox(
        "Periode",
        [
            "24 jam terakhir",
            "7 hari terakhir",
            "1 bulan terakhir",
            "Tahun 2026",
            "Semua data",
        ],
        index=1,
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
        12: "Desember",

    }

    bulan_dipilih = st.selectbox(
        "Bulan 2026",
        list(
            bulan_options.values()
        ),
        index=0,
    )


# ============================================================
# SORTING
# ============================================================

sort_order = st.selectbox(
    "📅 Urutan Artikel",
    [
        "Terbaru → Terlama",
        "Terlama → Terbaru",
    ],
    index=0,
    help=(
        "Pengurutan berdasarkan tanggal "
        "publikasi artikel."
    ),
)


sort_ascending = (
    sort_order == "Terlama → Terbaru"
)


# ============================================================
# FILTER DATA
# ============================================================

filtered = []


for article in articles:

    if (
        filter_mode != "Semua data"
        and not filter_date(
            article,
            filter_mode
        )
    ):

        continue

    if (
        bulan_dipilih
        != "Semua Bulan"
    ):

        dt = parse_date(
            article.get(
                "published_date"
            )
        )

        if not dt:
            continue

        month_number = next(
            num
            for num, name
            in bulan_options.items()
            if name == bulan_dipilih
        )

        if (
            dt.year != TAHUN_TARGET
            or dt.month
            != month_number
        ):

            continue

    filtered.append(article)


# ============================================================
# SEARCH
# ============================================================

search_text = st.text_input(
    "🔎 Cari judul, indikator, satker, atau sumber",
    "",
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
            f"{' '.join(map(str, safe_list(item.get('detected_keywords'))))} "
            f"{' '.join(map(str, safe_list(item.get('satker_matches'))))} "
            f"{item.get('source', '')}"
        ).lower()

    ]


# ============================================================
# SORTING FINAL
# ============================================================

filtered.sort(
    key=article_sort_key,
    reverse=not sort_ascending,
)


# ============================================================
# KATEGORI
# ============================================================

negative = [

    x

    for x in filtered

    if x.get(
        "category"
    ) == "Negatif Kuat"

]


handling = [

    x

    for x in filtered

    if x.get(
        "category"
    ) == "Perlu Penanganan"

]


neutral = [

    x

    for x in filtered

    if x.get(
        "category"
    ) == "Netral"

]


positive = [

    x

    for x in filtered

    if x.get(
        "category"
    ) == "Positif"

]


priority = [

    x

    for x in filtered

    if x.get(
        "category"
    )
    in [
        "Negatif Kuat",
        "Perlu Penanganan",
    ]

]


# ============================================================
# KPI
# ============================================================

st.divider()

st.markdown(
    '<div class="section-title">📊 Ringkasan Monitoring</div>',
    unsafe_allow_html=True,
)


c1, c2, c3, c4, c5 = st.columns(5)


with c1:

    st.metric(
        "🔴 Negatif Kuat",
        len(negative)
    )


with c2:

    st.metric(
        "🟠 Penanganan",
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
        "🚨 Prioritas",
        len(priority)
    )


# ============================================================
# ARTICLE RENDERER
# ============================================================

def render_article(item):

    category = item.get(
        "category",
        "Netral"
    )

    priority_value = item.get(
        "priority",
        "RENDAH"
    )

    negative_score = item.get(
        "negative_score",
        0
    )

    handling_score = item.get(
        "handling_score",
        0
    )

    positive_score = item.get(
        "positive_score",
        0
    )

    icon = (

        "🔴"

        if category == "Negatif Kuat"

        else (

            "🟠"

            if category == "Perlu Penanganan"

            else (

                "🟢"

                if category == "Positif"

                else "🟡"

            )

        )

    )


    with st.container(
        border=True
    ):

        left, right = st.columns(
            [6, 1]
        )


        with left:

            st.markdown(
                f"### {icon} "
                f"{item.get('title', '-')}"
            )


            info1, info2, info3, info4 = st.columns(4)


            with info1:

                st.caption(
                    "Kategori"
                )

                st.write(
                    category
                )


            with info2:

                st.caption(
                    "Prioritas"
                )

                st.write(
                    priority_value
                )


            with info3:

                st.caption(
                    "Negative Score"
                )

                st.write(
                    negative_score
                )


            with info4:

                st.caption(
                    "Handling Score"
                )

                st.write(
                    handling_score
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


            if item.get(
                "snippet"
            ):

                st.write(
                    item.get(
                        "snippet"
                    )
                )


            keywords = safe_list(
                item.get(
                    "detected_keywords"
                )
            )


            if keywords:

                st.markdown(
                    "**🔎 Indikator:** "
                    + ", ".join(
                        map(
                            str,
                            keywords[:30]
                        )
                    )
                )


            strong_context = safe_list(
                item.get(
                    "strong_context"
                )
            )


            if strong_context:

                st.warning(
                    "⚠️ Konteks Negatif Kuat: "
                    + ", ".join(
                        map(
                            str,
                            strong_context
                        )
                    )
                )


            handling_context = safe_list(
                item.get(
                    "handling_context"
                )
            )


            if handling_context:

                st.info(
                    "📌 Konteks Penanganan: "
                    + ", ".join(
                        map(
                            str,
                            handling_context
                        )
                    )
                )


            positive_context = safe_list(
                item.get(
                    "positive_context"
                )
            )


            if positive_context:

                st.success(
                    "✅ Konteks Positif: "
                    + ", ".join(
                        map(
                            str,
                            positive_context
                        )
                    )
                )


            satker = safe_list(
                item.get(
                    "satker_matches"
                )
            )


            if satker:

                st.caption(
                    "🏢 Satker: "
                    + ", ".join(
                        map(
                            str,
                            satker
                        )
                    )
                )


            source = item.get(
                "source"
            )

            if source:

                st.caption(
                    "📰 Sumber: "
                    + str(source)
                )


        with right:

            if item.get(
                "link"
            ):

                st.link_button(
                    "🔗 Buka Artikel",
                    item.get(
                        "link"
                    ),
                    use_container_width=True,
                )


# ============================================================
# TABS
# ============================================================

if IS_ADMIN:

    (
        tab_priority,
        tab_negative,
        tab_handling,
        tab_neutral,
        tab_positive,
        tab_analytics,
        tab_logs,
    ) = st.tabs(
        [
            "🚨 PRIORITAS",
            "🔴 NEGATIF KUAT",
            "🟠 PENANGANAN",
            "🟡 NETRAL",
            "🟢 POSITIF",
            "📊 ANALISIS",
            "📜 LOG",
        ]
    )

else:

    (
        tab_priority,
        tab_negative,
        tab_handling,
        tab_neutral,
        tab_positive,
        tab_analytics,
    ) = st.tabs(
        [
            "🚨 PRIORITAS",
            "🔴 NEGATIF KUAT",
            "🟠 PENANGANAN",
            "🟡 NETRAL",
            "🟢 POSITIF",
            "📊 ANALISIS",
        ]
    )

    tab_logs = None


# ============================================================
# PRIORITAS
# ============================================================

with tab_priority:

    st.markdown(
        '<div class="section-title">'
        '🚨 Prioritas Review'
        '</div>',
        unsafe_allow_html=True,
    )

    st.caption(
        f"Urutan: {sort_order}"
    )

    if priority:

        for item in priority:

            render_article(item)

    else:

        st.success(
            "Tidak ada artikel prioritas "
            "pada periode yang dipilih."
        )


# ============================================================
# NEGATIF KUAT
# ============================================================

with tab_negative:

    st.markdown(
        '<div class="section-title">'
        '🔴 Negatif Kuat'
        '</div>',
        unsafe_allow_html=True,
    )

    st.caption(
        f"Urutan: {sort_order}"
    )

    if negative:

        for item in negative:

            render_article(item)

    else:

        st.info(
            "Tidak ada artikel Negatif Kuat."
        )


# ============================================================
# PENANGANAN
# ============================================================

with tab_handling:

    st.markdown(
        '<div class="section-title">'
        '🟠 Perlu Penanganan'
        '</div>',
        unsafe_allow_html=True,
    )

    st.caption(
        f"Urutan: {sort_order}"
    )

    if handling:

        for item in handling:

            render_article(item)

    else:

        st.info(
            "Tidak ada artikel Perlu Penanganan."
        )


# ============================================================
# NETRAL
# ============================================================

with tab_neutral:

    st.markdown(
        '<div class="section-title">'
        '🟡 Artikel Netral'
        '</div>',
        unsafe_allow_html=True,
    )

    st.caption(
        f"Urutan: {sort_order}"
    )

    if neutral:

        for item in neutral:

            render_article(item)

    else:

        st.info(
            "Tidak ada artikel Netral."
        )


# ============================================================
# POSITIF
# ============================================================

with tab_positive:

    st.markdown(
        '<div class="section-title">'
        '🟢 Pemberitaan Positif'
        '</div>',
        unsafe_allow_html=True,
    )

    st.caption(
        f"Urutan: {sort_order}"
    )

    if positive:

        for item in positive:

            render_article(item)

    else:

        st.info(
            "Tidak ada artikel Positif."
        )


# ============================================================
# ANALISIS
# ============================================================

with tab_analytics:

    st.markdown(
        '<div class="section-title">'
        '📊 Analisis Pemberitaan'
        '</div>',
        unsafe_allow_html=True,
    )


    chart_data = pd.DataFrame(
        {
            "Kategori": [
                "Negatif Kuat",
                "Perlu Penanganan",
                "Netral",
                "Positif",
            ],

            "Jumlah": [
                len(negative),
                len(handling),
                len(neutral),
                len(positive),
            ],
        }
    )


    if chart_data[
        "Jumlah"
    ].sum() > 0:

        fig = px.pie(
            chart_data,
            names="Kategori",
            values="Jumlah",
            hole=0.45,
            title="Distribusi Kategori",
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )

    else:

        st.info(
            "Belum ada data untuk dianalisis."
        )


    st.markdown(
        '<div class="section-title">'
        '📊 Distribusi Prioritas'
        '</div>',
        unsafe_allow_html=True,
    )


    priority_df = pd.DataFrame(
        {
            "Prioritas": [
                "KRITIS",
                "TINGGI",
                "SEDANG",
                "RENDAH",
            ],

            "Jumlah": [

                len(
                    [
                        x
                        for x in filtered
                        if x.get(
                            "priority"
                        )
                        == "KRITIS"
                    ]
                ),

                len(
                    [
                        x
                        for x in filtered
                        if x.get(
                            "priority"
                        )
                        == "TINGGI"
                    ]
                ),

                len(
                    [
                        x
                        for x in filtered
                        if x.get(
                            "priority"
                        )
                        == "SEDANG"
                    ]
                ),

                len(
                    [
                        x
                        for x in filtered
                        if x.get(
                            "priority"
                        )
                        == "RENDAH"
                    ]
                ),

            ],
        }
    )


    st.dataframe(
        priority_df,
        use_container_width=True,
        hide_index=True,
    )


# ============================================================
# LOG ADMIN
# ============================================================

if (
    IS_ADMIN
    and tab_logs is not None
):

    with tab_logs:

        st.markdown(
            '<div class="section-title">'
            '📜 Log Patroli'
            '</div>',
            unsafe_allow_html=True,
        )


        if logs:

            logs_df = pd.DataFrame(
                logs
            )

            st.dataframe(
                logs_df,
                use_container_width=True,
                hide_index=True,
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
    f"🛡️ Patroli Siber 2026 • "
    f"{NAMA_SATKER} • "
    f"Login: {CURRENT_USERNAME} "
    f"({CURRENT_ROLE.upper()})"
)
