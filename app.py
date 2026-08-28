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
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="Patroli Siber 2026",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
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
# MODERN CSS
# ============================================================

st.markdown(
    """
    <style>

    /* ========================================================
       GLOBAL
       ======================================================== */

    .block-container {
        max-width: 1500px;
        padding-top: 2rem;
        padding-bottom: 3rem;
    }

    body {
        background-color: #f8fafc;
    }

    /* ========================================================
       SIDEBAR
       ======================================================== */

    section[data-testid="stSidebar"] {
        border-right: 1px solid #e5e7eb;
    }

    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3 {
        font-weight: 800;
    }

    /* ========================================================
       LOGIN
       ======================================================== */

    .login-wrapper {
        max-width: 480px;
        margin: 50px auto 0 auto;
        padding: 40px;
        background: white;
        border-radius: 24px;
        border: 1px solid #e5e7eb;
        box-shadow: 0 15px 45px rgba(0, 0, 0, 0.08);
    }

    .login-icon {
        text-align: center;
        font-size: 60px;
        margin-bottom: 8px;
    }

    .login-heading {
        text-align: center;
        font-size: 30px;
        font-weight: 800;
        color: #8b0000;
        margin-bottom: 5px;
    }

    .login-description {
        text-align: center;
        color: #6b7280;
        font-size: 14px;
        margin-bottom: 28px;
    }

    .login-satker {
        text-align: center;
        color: #6b7280;
        font-size: 13px;
        margin-top: 20px;
        line-height: 1.6;
    }

    /* ========================================================
       DASHBOARD HEADER
       ======================================================== */

    .dashboard-header {
        padding: 30px 34px;
        border-radius: 22px;
        margin-bottom: 24px;
        background:
            linear-gradient(
                135deg,
                #7f0000 0%,
                #a90000 55%,
                #ffffff 55%,
                #f8fafc 100%
            );
        box-shadow:
            0 10px 30px rgba(0, 0, 0, 0.08);
        overflow: hidden;
    }

    .dashboard-header-title {
        font-size: 34px;
        font-weight: 800;
        color: white;
        line-height: 1.2;
    }

    .dashboard-header-subtitle {
        color: rgba(255,255,255,0.90);
        font-size: 14px;
        margin-top: 8px;
        max-width: 650px;
    }

    .satker-badge {
        display: inline-block;
        margin-top: 16px;
        padding: 7px 14px;
        border-radius: 999px;
        background: rgba(255,255,255,0.16);
        border: 1px solid rgba(255,255,255,0.25);
        color: white;
        font-size: 13px;
        font-weight: 600;
    }

    /* ========================================================
       SECTION
       ======================================================== */

    .section-title {
        font-size: 21px;
        font-weight: 800;
        color: #111827;
        margin-top: 10px;
        margin-bottom: 4px;
    }

    .section-description {
        color: #6b7280;
        font-size: 13px;
        margin-bottom: 15px;
    }

    /* ========================================================
       ARTICLE CARD
       ======================================================== */

    .article-card {
        background: white;
        border: 1px solid #e5e7eb;
        border-radius: 18px;
        padding: 20px;
        margin-bottom: 15px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.04);
    }

    .article-title {
        font-size: 17px;
        font-weight: 750;
        color: #111827;
        line-height: 1.45;
        margin-bottom: 10px;
    }

    .article-meta {
        color: #6b7280;
        font-size: 12px;
        margin-top: 10px;
        margin-bottom: 10px;
    }

    .article-snippet {
        color: #374151;
        font-size: 14px;
        line-height: 1.65;
    }

    /* ========================================================
       BADGES
       ======================================================== */

    .badge {
        display: inline-block;
        padding: 5px 10px;
        border-radius: 999px;
        font-size: 11px;
        font-weight: 700;
        margin-right: 5px;
        margin-bottom: 5px;
    }

    .badge-red {
        background: #fee2e2;
        color: #991b1b;
    }

    .badge-orange {
        background: #ffedd5;
        color: #9a3412;
    }

    .badge-yellow {
        background: #fef3c7;
        color: #92400e;
    }

    .badge-green {
        background: #dcfce7;
        color: #166534;
    }

    .badge-dark {
        background: #e5e7eb;
        color: #374151;
    }

    /* ========================================================
       CONTEXT BOX
       ======================================================== */

    .danger-box {
        background: #fff1f2;
        border: 1px solid #fecdd3;
        color: #881337;
        padding: 11px 14px;
        border-radius: 12px;
        margin-top: 10px;
        font-size: 13px;
    }

    .warning-box {
        background: #fff7ed;
        border: 1px solid #fed7aa;
        color: #9a3412;
        padding: 11px 14px;
        border-radius: 12px;
        margin-top: 10px;
        font-size: 13px;
    }

    .info-box {
        background: #eff6ff;
        border: 1px solid #bfdbfe;
        color: #1e40af;
        padding: 11px 14px;
        border-radius: 12px;
        margin-top: 10px;
        font-size: 13px;
    }

    /* ========================================================
       FOOTER
       ======================================================== */

    .footer {
        text-align: center;
        color: #9ca3af;
        font-size: 12px;
        line-height: 1.7;
        padding-top: 20px;
    }

    /* ========================================================
       METRIC
       ======================================================== */

    [data-testid="stMetricValue"] {
        font-size: 28px;
        font-weight: 800;
    }

    [data-testid="stMetricLabel"] {
        font-weight: 600;
    }

    </style>
    """,
    unsafe_allow_html=True
)


# ============================================================
# LOGIN CONFIG
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

    st.markdown(
        """
        <div class="login-wrapper">

            <div class="login-icon">
                🛡️
            </div>

            <div class="login-heading">
                Patroli Siber 2026
            </div>

            <div class="login-description">
                Sistem Monitoring Pemberitaan
            </div>

        </div>
        """,
        unsafe_allow_html=True
    )

    col_left, col_center, col_right = st.columns(
        [1, 2, 1]
    )

    with col_center:

        st.subheader(
            "🔐 Login Sistem"
        )

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
            "🔐 Masuk ke Dashboard",
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
            unsafe_allow_html=True
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

IS_ADMIN = (
    CURRENT_ROLE == "admin"
)

IS_VIEWER = (
    CURRENT_ROLE == "viewer"
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


# ============================================================
# LOAD DATA
# ============================================================

@st.cache_data(ttl=60)
def load_articles():

    try:

        return get_all_articles()

    except Exception as e:

        st.error(
            f"Gagal mengambil data artikel: {e}"
        )

        return []


@st.cache_data(ttl=30)
def load_logs():

    try:

        return get_run_logs(300)

    except Exception as e:

        st.error(
            f"Gagal mengambil log patroli: {e}"
        )

        return []


articles = load_articles()

logs = load_logs()


# ============================================================
# HELPER
# ============================================================

def safe_list(value):

    if not value:
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, tuple):
        return list(value)

    return [str(value)]


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

                dt = dt.tz_convert(
                    None
                )

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
            dt >= now - datetime.timedelta(
                hours=24
            )
            and dt <= now
        )

    if mode == "7 hari terakhir":

        return (
            dt >= now - datetime.timedelta(
                days=7
            )
            and dt <= now
        )

    if mode == "1 bulan terakhir":

        return (
            dt >= now - datetime.timedelta(
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
        disabled=True
    )

    st.text_input(
        "Database",
        value="Supabase",
        disabled=True
    )

    st.text_input(
        "Patroli Otomatis",
        value="GitHub Actions",
        disabled=True
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
        disabled=True
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
    f"""
    <div class="dashboard-header">

        <div class="dashboard-header-title">
            🛡️ Patroli Siber 2026
        </div>

        <div class="dashboard-header-subtitle">
            Monitoring dan klasifikasi awal pemberitaan
            untuk mendukung proses review informasi.
        </div>

        <div class="satker-badge">
            🏛️ {NAMA_SATKER}
        </div>

    </div>
    """,
    unsafe_allow_html=True
)


# ============================================================
# FILTER MONITORING
# ============================================================

st.markdown(
    '<div class="section-title">🕒 Filter Monitoring</div>',
    unsafe_allow_html=True
)

st.markdown(
    """
    <div class="section-description">
        Gunakan filter periode, bulan, dan pencarian
        untuk mempersempit data pemberitaan.
    </div>
    """,
    unsafe_allow_html=True
)

col_filter1, col_filter2 = st.columns(
    2
)


with col_filter1:

    filter_mode = st.selectbox(
        "Periode",
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
        "Bulan 2026",
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
            or dt.month != month_number
        ):

            continue

    filtered.append(
        article
    )


# ============================================================
# SEARCH
# ============================================================

search_text = st.text_input(
    "🔎 Cari judul, indikator, satker, atau sumber",
    placeholder="Contoh: Deli Serdang, korupsi, Kejari...",
    key="search_article"
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
            f"{' '.join(map(str, safe_list(item.get('satker_matches'))))}"

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
            str(
                x.get(
                    "priority",
                    "RENDAH"
                )
            ).upper(),
            4
        ),

        category_order.get(
            x.get(
                "category",
                "Netral"
            ),
            3
        ),

        -(float(
            x.get(
                "negative_score",
                0
            ) or 0
        ))

    )
)


# ============================================================
# CATEGORY DATA
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
# KPI
# ============================================================

st.divider()

st.markdown(
    '<div class="section-title">📊 Ringkasan Monitoring</div>',
    unsafe_allow_html=True
)

c1, c2, c3, c4, c5 = st.columns(5)


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
# ARTICLE RENDER
# ============================================================

def render_article(
    item
):

    category = item.get(
        "category",
        "Netral"
    )

    priority_value = str(
        item.get(
            "priority",
            "RENDAH"
        )
    ).upper()

    negative_score = item.get(
        "negative_score",
        0
    )

    handling_score = item.get(
        "handling_score",
        0
    )

    # --------------------------------------------------------
    # ICON
    # --------------------------------------------------------

    if category == "Negatif Kuat":

        icon = "🔴"
        badge_class = "badge-red"

    elif category == "Perlu Penanganan":

        icon = "🟠"
        badge_class = "badge-orange"

    elif category == "Positif":

        icon = "🟢"
        badge_class = "badge-green"

    else:

        icon = "🟡"
        badge_class = "badge-yellow"


    # --------------------------------------------------------
    # TITLE
    # --------------------------------------------------------

    title = str(
        item.get(
            "title",
            "-"
        )
    )


    # --------------------------------------------------------
    # DATE
    # --------------------------------------------------------

    published_date = str(
        item.get(
            "published_date",
            "-"
        )
    )


    # --------------------------------------------------------
    # SNIPPET
    # --------------------------------------------------------

    snippet = str(
        item.get(
            "snippet",
            ""
        )
    )


    # --------------------------------------------------------
    # KEYWORDS
    # --------------------------------------------------------

    keywords = safe_list(
        item.get(
            "detected_keywords"
        )
    )


    # --------------------------------------------------------
    # CONTEXT
    # --------------------------------------------------------

    strong_context = safe_list(
        item.get(
            "strong_context"
        )
    )


    handling_context = safe_list(
        item.get(
            "handling_context"
        )
    )


    satker = safe_list(
        item.get(
            "satker_matches"
        )
    )


    # --------------------------------------------------------
    # CARD
    # --------------------------------------------------------

    with st.container(
        border=True
    ):

        col1, col2 = st.columns(
            [6, 1]
        )


        # ====================================================
        # LEFT
        # ====================================================

        with col1:

            st.markdown(
                f"""
                <div class="article-title">
                    {icon} {title}
                </div>
                """,
                unsafe_allow_html=True
            )


            # ------------------------------------------------
            # BADGES
            # ------------------------------------------------

            st.markdown(
                f"""
                <span class="badge {badge_class}">
                    {category}
                </span>

                <span class="badge badge-dark">
                    Prioritas {priority_value}
                </span>

                <span class="badge badge-dark">
                    Negatif {negative_score}
                </span>

                <span class="badge badge-dark">
                    Penanganan {handling_score}
                </span>
                """,
                unsafe_allow_html=True
            )


            # ------------------------------------------------
            # DATE
            # ------------------------------------------------

            st.markdown(
                f"""
                <div class="article-meta">
                    📅 {published_date}
                </div>
                """,
                unsafe_allow_html=True
            )


            # ------------------------------------------------
            # SNIPPET
            # ------------------------------------------------

            if snippet:

                st.markdown(
                    f"""
                    <div class="article-snippet">
                        {snippet}
                    </div>
                    """,
                    unsafe_allow_html=True
                )


            # ------------------------------------------------
            # KEYWORDS
            # ------------------------------------------------

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


            # ------------------------------------------------
            # STRONG CONTEXT
            # ------------------------------------------------

            if strong_context:

                st.markdown(
                    f"""
                    <div class="danger-box">
                        ⚠️ <b>Konteks Negatif Kuat:</b><br>
                        {", ".join(map(str, strong_context))}
                    </div>
                    """,
                    unsafe_allow_html=True
                )


            # ------------------------------------------------
            # HANDLING CONTEXT
            # ------------------------------------------------

            if handling_context:

                st.markdown(
                    f"""
                    <div class="warning-box">
                        📌 <b>Konteks Penanganan:</b><br>
                        {", ".join(map(str, handling_context))}
                    </div>
                    """,
                    unsafe_allow_html=True
                )


            # ------------------------------------------------
            # SATKER
            # ------------------------------------------------

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


        # ====================================================
        # RIGHT
        # ====================================================

        with col2:

            link = str(
                item.get(
                    "link",
                    ""
                )
            ).strip()


            if link:

                st.link_button(
                    "🔗 Buka Artikel",
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


if IS_ADMIN:

    tabs.append(
        "📜 LOG"
    )


tab_objects = st.tabs(
    tabs
)


# ============================================================
# TAB REFERENCES
# ============================================================

tab_priority = tab_objects[0]

tab_negative = tab_objects[1]

tab_handling = tab_objects[2]

tab_neutral = tab_objects[3]

tab_positive = tab_objects[4]

tab_analytics = tab_objects[5]

tab_logs = None


if IS_ADMIN:

    tab_logs = tab_objects[6]


# ============================================================
# PRIORITY TAB
# ============================================================

with tab_priority:

    st.markdown(
        '<div class="section-title">'
        '🚨 Prioritas Review'
        '</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="section-description">'
        'Artikel dengan kategori Negatif Kuat dan '
        'Perlu Penanganan.'
        '</div>',
        unsafe_allow_html=True
    )

    if priority:

        for item in priority:

            render_article(
                item
            )

    else:

        st.success(
            "Tidak ada artikel prioritas pada filter yang dipilih."
        )


# ============================================================
# NEGATIVE TAB
# ============================================================

with tab_negative:

    st.markdown(
        '<div class="section-title">'
        '🔴 Negatif Kuat'
        '</div>',
        unsafe_allow_html=True
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
# HANDLING TAB
# ============================================================

with tab_handling:

    st.markdown(
        '<div class="section-title">'
        '🟠 Perlu Penanganan'
        '</div>',
        unsafe_allow_html=True
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
# NEUTRAL TAB
# ============================================================

with tab_neutral:

    st.markdown(
        '<div class="section-title">'
        '🟡 Artikel Netral'
        '</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="section-description">'
        'Artikel netral tetap tersedia untuk kebutuhan '
        'monitoring dan audit klasifikasi.'
        '</div>',
        unsafe_allow_html=True
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
# POSITIVE TAB
# ============================================================

with tab_positive:

    st.markdown(
        '<div class="section-title">'
        '🟢 Pemberitaan Positif'
        '</div>',
        unsafe_allow_html=True
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
# ANALYTICS TAB
# ============================================================

with tab_analytics:

    st.markdown(
        '<div class="section-title">'
        '📊 Analisis Pemberitaan'
        '</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="section-description">'
        'Ringkasan statistik berdasarkan data yang sedang difilter.'
        '</div>',
        unsafe_allow_html=True
    )


    # ========================================================
    # CATEGORY CHART
    # ========================================================

    chart_data = pd.DataFrame(
        {
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
        }
    )


    if chart_data["Jumlah"].sum() > 0:

        fig = px.pie(
            chart_data,
            names="Kategori",
            values="Jumlah",
            hole=0.45,
            title="Distribusi Kategori Pemberitaan"
        )

        fig.update_layout(
            margin=dict(
                t=60,
                b=20,
                l=20,
                r=20
            ),
            legend_title_text="Kategori"
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )

    else:

        st.info(
            "Belum ada data untuk ditampilkan."
        )


    # ========================================================
    # PRIORITY
    # ========================================================

    st.markdown(
        '<div class="section-title">'
        '📈 Distribusi Prioritas'
        '</div>',
        unsafe_allow_html=True
    )


    priority_df = pd.DataFrame(
        {
            "Prioritas": [
                "KRITIS",
                "TINGGI",
                "SEDANG",
                "RENDAH"
            ],

            "Jumlah": [

                len([
                    x for x in filtered
                    if str(
                        x.get(
                            "priority",
                            ""
                        )
                    ).upper() == "KRITIS"
                ]),

                len([
                    x for x in filtered
                    if str(
                        x.get(
                            "priority",
                            ""
                        )
                    ).upper() == "TINGGI"
                ]),

                len([
                    x for x in filtered
                    if str(
                        x.get(
                            "priority",
                            ""
                        )
                    ).upper() == "SEDANG"
                ]),

                len([
                    x for x in filtered
                    if str(
                        x.get(
                            "priority",
                            ""
                        )
                    ).upper() == "RENDAH"
                ])

            ]
        }
    )


    st.dataframe(
        priority_df,
        use_container_width=True,
        hide_index=True
    )


    # ========================================================
    # STATISTICS
    # ========================================================

    st.markdown(
        '<div class="section-title">'
        '📌 Statistik'
        '</div>',
        unsafe_allow_html=True
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
# LOG TAB - ADMIN ONLY
# ============================================================

if IS_ADMIN and tab_logs is not None:

    with tab_logs:

        st.markdown(
            '<div class="section-title">'
            '📜 Log Patroli'
            '</div>',
            unsafe_allow_html=True
        )

        st.markdown(
            '<div class="section-description">'
            'Riwayat proses patroli otomatis dan klasifikasi.'
            '</div>',
            unsafe_allow_html=True
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

st.markdown(
    f"""
    <div class="footer">

        🛡️ <b>Patroli Siber 2026</b><br>

        Sistem merupakan alat bantu monitoring dan
        klasifikasi awal. Artikel Negatif Kuat dan
        Perlu Penanganan tetap perlu diverifikasi
        terhadap isi, sumber, dan fakta.<br><br>

        {NAMA_SATKER} • Sistem Internal

    </div>
    """,
    unsafe_allow_html=True
)
