
import os
import datetime
import html

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
# CONFIG APLIKASI
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

    /* =====================================================
       GLOBAL
       ===================================================== */

    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
        max-width: 1500px;
    }

    [data-testid="stMetricValue"] {
        font-size: 28px;
        font-weight: 800;
    }

    [data-testid="stMetricLabel"] {
        font-weight: 600;
    }

    /* =====================================================
       HEADER
       ===================================================== */

    .hero {
        padding: 28px 32px;
        border-radius: 20px;
        margin-bottom: 24px;

        background:
            linear-gradient(
                135deg,
                #8b0000 0%,
                #b30000 48%,
                #f5f5f5 48%,
                #ffffff 100%
            );

        box-shadow:
            0 8px 30px rgba(0,0,0,0.10);

        position: relative;
        overflow: hidden;
    }

    .hero-content {
        position: relative;
        z-index: 2;
    }

    .hero-title {
        color: white;
        font-size: 34px;
        font-weight: 800;
        margin: 0;
        letter-spacing: -0.5px;
    }

    .hero-subtitle {
        color: rgba(255,255,255,0.92);
        font-size: 15px;
        margin-top: 6px;
    }

    .hero-satker {
        display: inline-block;
        margin-top: 14px;
        padding: 7px 14px;
        border-radius: 999px;
        background: rgba(255,255,255,0.16);
        color: white;
        font-size: 13px;
        font-weight: 600;
        border: 1px solid rgba(255,255,255,0.25);
    }

    /* =====================================================
       LOGIN CARD
       ===================================================== */

    .login-card {
        padding: 34px;
        border-radius: 22px;
        background: white;
        border: 1px solid #e5e7eb;
        box-shadow:
            0 15px 40px rgba(0,0,0,0.08);
    }

    .login-logo {
        font-size: 58px;
        text-align: center;
        margin-bottom: 8px;
    }

    .login-title {
        text-align: center;
        font-size: 28px;
        font-weight: 800;
        margin-bottom: 4px;
    }

    .login-subtitle {
        text-align: center;
        color: #6b7280;
        margin-bottom: 22px;
    }

    /* =====================================================
       SECTION TITLE
       ===================================================== */

    .section-title {
        font-size: 21px;
        font-weight: 800;
        margin-top: 8px;
        margin-bottom: 14px;
    }

    .section-description {
        color: #6b7280;
        font-size: 13px;
        margin-top: -8px;
        margin-bottom: 16px;
    }

    /* =====================================================
       ARTICLE CARD
       ===================================================== */

    .article-card {
        padding: 20px;
        border-radius: 16px;
        border: 1px solid #e5e7eb;
        background: white;
        margin-bottom: 14px;

        box-shadow:
            0 4px 14px rgba(0,0,0,0.045);

        transition:
            transform 0.15s ease,
            box-shadow 0.15s ease;
    }

    .article-card:hover {
        transform: translateY(-2px);
        box-shadow:
            0 8px 24px rgba(0,0,0,0.08);
    }

    .article-title {
        font-size: 17px;
        line-height: 1.45;
        font-weight: 750;
        color: #111827;
        margin-bottom: 10px;
    }

    .article-meta {
        color: #6b7280;
        font-size: 12px;
        margin-bottom: 12px;
    }

    .article-snippet {
        color: #374151;
        font-size: 14px;
        line-height: 1.65;
    }

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

    /* =====================================================
       INFO BOX
       ===================================================== */

    .info-box {
        padding: 12px 15px;
        border-radius: 12px;
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        margin-top: 10px;
        font-size: 13px;
    }

    .danger-box {
        padding: 12px 15px;
        border-radius: 12px;
        background: #fff1f2;
        border: 1px solid #fecdd3;
        color: #881337;
        margin-top: 10px;
        font-size: 13px;
    }

    .warning-box {
        padding: 12px 15px;
        border-radius: 12px;
        background: #fff7ed;
        border: 1px solid #fed7aa;
        color: #9a3412;
        margin-top: 10px;
        font-size: 13px;
    }

    /* =====================================================
       SIDEBAR
       ===================================================== */

    section[data-testid="stSidebar"] {
        border-right: 1px solid #e5e7eb;
    }

    /* =====================================================
       FOOTER
       ===================================================== */

    .footer {
        text-align: center;
        color: #9ca3af;
        font-size: 12px;
        padding: 20px 0 5px 0;
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
        "<br><br>",
        unsafe_allow_html=True
    )

    col1, col2, col3 = st.columns(
        [1, 2, 1]
    )

    with col2:

        st.markdown(
            """
            <div class="login-card">

                <div class="login-logo">
                    🛡️
                </div>

                <div class="login-title">
                    Patroli Siber 2026
                </div>

                <div class="login-subtitle">
                    Sistem Monitoring Pemberitaan
                </div>

            </div>
            """,
            unsafe_allow_html=True
        )

        st.divider()

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

            dt = dt.tz_convert(None)

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
            dt >= now - datetime.timedelta(hours=24)
            and dt <= now
        )

    if mode == "7 hari terakhir":

        return (
            dt >= now - datetime.timedelta(days=7)
            and dt <= now
        )

    if mode == "1 bulan terakhir":

        return (
            dt >= now - datetime.timedelta(days=30)
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
            and
            os.getenv("CHAT_ID")
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
# MAIN HEADER
# ============================================================

st.markdown(
    f"""
    <div class="hero">

        <div class="hero-content">

            <div class="hero-title">
                🛡️ Patroli Siber 2026
            </div>

            <div class="hero-subtitle">
                Sistem Monitoring dan Klasifikasi Pemberitaan
            </div>

            <div class="hero-satker">
                🏢 {html.escape(NAMA_SATKER)}
            </div>

        </div>

    </div>
    """,
    unsafe_allow_html=True
)


# ============================================================
# FILTER
# ============================================================

st.markdown(
    '<div class="section-title">🕒 Filter Monitoring</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="section-description">'
    'Gunakan filter untuk mempersempit pemberitaan yang ditampilkan.'
    '</div>',
    unsafe_allow_html=True
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
        list(bulan_options.values()),
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

    filtered.append(article)


# ============================================================
# SEARCH
# ============================================================

search_text = st.text_input(
    "🔎 Cari judul, indikator, satker, atau sumber",
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
            f"{' '.join(item.get('detected_keywords', []) or [])} "
            f"{' '.join(item.get('satker_matches', []) or [])}"
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
    if x.get("category") == "Negatif Kuat"
]

handling = [
    x for x in filtered
    if x.get("category") == "Perlu Penanganan"
]

neutral = [
    x for x in filtered
    if x.get("category") == "Netral"
]

positive = [
    x for x in filtered
    if x.get("category") == "Positif"
]

priority = [
    x for x in filtered
    if x.get("category") in [
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
# ARTICLE RENDER
# ============================================================

def safe_list(value):

    if not value:
        return []

    if isinstance(value, list):
        return value

    return [str(value)]


def render_article(item):

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
        category_class = "badge-red"

    elif category == "Perlu Penanganan":

        icon = "🟠"
        category_class = "badge-orange"

    elif category == "Positif":

        icon = "🟢"
        category_class = "badge-green"

    else:

        icon = "🟡"
        category_class = "badge-yellow"

    title = html.escape(
        str(
            item.get(
                "title",
                "-"
            )
        )
    )

    published = html.escape(
        str(
            item.get(
                "published_date",
                "-"
            )
        )
    )

    negative_score = item.get(
        "negative_score",
        0
    )

    handling_score = item.get(
        "handling_score",
        0
    )

    satker = safe_list(
        item.get(
            "satker_matches",
            []
        )
    )

    title_matches = safe_list(
        item.get(
            "satker_title_matches",
            []
        )
    )

    first_matches = safe_list(
        item.get(
            "satker_first_paragraph_matches",
            []
        )
    )

    location = item.get(
        "satker_match_location",
        ""
    )

    detected_keywords = safe_list(
        item.get(
            "detected_keywords",
            []
        )
    )

    strong_context = safe_list(
        item.get(
            "strong_context",
            []
        )
    )

    handling_context = safe_list(
        item.get(
            "handling_context",
            []
        )
    )

    first_paragraphs = safe_list(
        item.get(
            "first_paragraphs",
            []
        )
    )

    with st.container(
        border=True
    ):

        col1, col2 = st.columns(
            [6.5, 1]
        )

        with col1:

            st.markdown(
                f"""
                <div class="article-card">

                    <div class="article-title">
                        {icon} {title}
                    </div>

                    <span class="badge {category_class}">
                        {category}
                    </span>

                    <span class="badge badge-dark">
                        Prioritas {html.escape(str(priority_value))}
                    </span>

                    <span class="badge badge-dark">
                        Negatif {negative_score}
                    </span>

                    <span class="badge badge-dark">
                        Penanganan {handling_score}
                    </span>

                    <div class="article-meta">
                        📅 {published}
                    </div>

                </div>
                """,
                unsafe_allow_html=True
            )

            snippet = item.get(
                "snippet",
                ""
            )

            if snippet:

                st.write(
                    snippet
                )

            # =================================================
            # SATKER
            # =================================================

            if satker:

                st.markdown(
                    '<div class="info-box">'
                    '<b>🏢 SATKER TERDETEKSI</b><br>'
                    + html.escape(
                        ", ".join(
                            map(str, satker)
                        )
                    )
                    + (
                        "<br><small>Lokasi: "
                        + html.escape(
                            str(location)
                        )
                        + "</small>"
                        if location
                        else ""
                    )
                    + '</div>',
                    unsafe_allow_html=True
                )

            if title_matches:

                st.markdown(
                    '<div class="info-box">'
                    '<b>📰 SATKER PADA JUDUL</b><br>'
                    + html.escape(
                        ", ".join(
                            map(str, title_matches)
                        )
                    )
                    + '</div>',
                    unsafe_allow_html=True
                )

            if first_matches:

                st.markdown(
                    '<div class="info-box">'
                    '<b>📌 SATKER PADA 1–3 PARAGRAF AWAL</b><br>'
                    + html.escape(
                        ", ".join(
                            map(str, first_matches)
                        )
                    )
                    + '</div>',
                    unsafe_allow_html=True
                )

            # =================================================
            # KEYWORDS
            # =================================================

            if detected_keywords:

                st.markdown(
                    "**🔎 Indikator:** "
                    + ", ".join(
                        map(
                            str,
                            detected_keywords[:30]
                        )
                    )
                )

            # =================================================
            # CONTEXT
            # =================================================

            if strong_context:

                st.markdown(
                    '<div class="danger-box">'
                    '<b>⚠️ Konteks Negatif Kuat</b><br>'
                    + html.escape(
                        ", ".join(
                            map(
                                str,
                                strong_context
                            )
                        )
                    )
                    + '</div>',
                    unsafe_allow_html=True
                )

            if handling_context:

                st.markdown(
                    '<div class="warning-box">'
                    '<b>📌 Konteks Penanganan</b><br>'
                    + html.escape(
                        ", ".join(
                            map(
                                str,
                                handling_context
                            )
                        )
                    )
                    + '</div>',
                    unsafe_allow_html=True
                )

            # =================================================
            # FIRST PARAGRAPHS
            # =================================================

            if first_paragraphs:

                with st.expander(
                    "📄 Lihat 1–3 paragraf awal"
                ):

                    for paragraph in first_paragraphs[:3]:

                        st.write(
                            paragraph
                        )

        with col2:

            link = item.get(
                "link",
                ""
            )

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
    "🚨 PRIORITAS",
    "🔴 NEGATIF",
    "🟠 PENANGANAN",
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

    st.markdown(
        '<div class="section-title">'
        '🚨 Prioritas Review'
        '</div>',
        unsafe_allow_html=True
    )

    st.caption(
        "Artikel dengan risiko tertinggi ditampilkan terlebih dahulu."
    )

    if priority:

        for item in priority:

            render_article(
                item
            )

    else:

        st.success(
            "Tidak ada artikel prioritas."
        )


# ============================================================
# NEGATIVE
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
# HANDLING
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
# NEUTRAL
# ============================================================

with tab_neutral:

    st.markdown(
        '<div class="section-title">'
        '🟡 Artikel Netral'
        '</div>',
        unsafe_allow_html=True
    )

    st.caption(
        "Artikel tetap disimpan untuk kebutuhan monitoring dan audit klasifikasi."
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
# ANALYTICS
# ============================================================

with tab_analytics:

    st.markdown(
        '<div class="section-title">'
        '📊 Analisis Monitoring'
        '</div>',
        unsafe_allow_html=True
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
            hole=0.5,
            title="Distribusi Kategori"
        )

        fig.update_layout(
            margin=dict(
                t=60,
                l=10,
                r=10,
                b=10
            ),
            legend_title=""
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )

    st.divider()

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

    st.divider()

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
# ============================================================

if IS_ADMIN:

    with tab_logs:

        st.markdown(
            '<div class="section-title">'
            '📜 Log Patroli'
            '</div>',
            unsafe_allow_html=True
        )

        st.caption(
            "Log hanya dapat diakses oleh Admin."
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
    """
    <div class="footer">

        🛡️ <b>Patroli Siber 2026</b><br>

        Sistem merupakan alat bantu monitoring dan
        klasifikasi awal. Artikel Negatif Kuat dan
        Perlu Penanganan tetap perlu diverifikasi
        terhadap isi, sumber, dan fakta.

    </div>
    """,
    unsafe_allow_html=True
)

st.caption(
    f"👤 Login: {CURRENT_USERNAME} "
    f"• Role: {CURRENT_ROLE.upper()}"
)

