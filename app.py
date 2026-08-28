import os
import datetime
import html

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
    "Kejaksaan Negeri Deli Serdang",
)

TAHUN_TARGET = 2026


# ============================================================
# CSS MODERN
# ============================================================

st.markdown(
    """
    <style>

    /* ======================================================
       GLOBAL
       ====================================================== */

    .block-container {
        max-width: 1500px;
        padding-top: 2rem;
        padding-bottom: 3rem;
    }

    body {
        background-color: #f8fafc;
    }

    /* Hilangkan elemen bawaan Streamlit yang tidak perlu */

    #MainMenu {
        visibility: hidden;
    }

    footer {
        visibility: hidden;
    }

    /* ======================================================
       HEADER DASHBOARD
       ====================================================== */

    .dashboard-header {
        background: linear-gradient(
            135deg,
            #7f0000 0%,
            #a40000 48%,
            #c1121f 100%
        );

        padding: 30px 34px;
        border-radius: 22px;

        box-shadow:
            0 12px 30px rgba(127, 0, 0, 0.18);

        margin-bottom: 25px;
    }

    .dashboard-header-title {
        color: white;
        font-size: 34px;
        font-weight: 800;
        line-height: 1.2;
        margin-bottom: 8px;
    }

    .dashboard-header-subtitle {
        color: rgba(255,255,255,0.90);
        font-size: 15px;
        margin-bottom: 18px;
    }

    .satker-badge {
        display: inline-block;
        padding: 8px 15px;
        border-radius: 999px;

        background: rgba(255,255,255,0.16);
        border: 1px solid rgba(255,255,255,0.25);

        color: white;
        font-size: 13px;
        font-weight: 600;
    }

    /* ======================================================
       LOGIN
       ====================================================== */

    .login-wrapper {
        max-width: 440px;
        margin: 70px auto 0 auto;
        padding: 36px 38px;

        background: white;

        border-radius: 24px;

        border: 1px solid #e5e7eb;

        box-shadow:
            0 20px 50px rgba(0,0,0,0.10);
    }

    .login-icon {
        width: 76px;
        height: 76px;

        margin: 0 auto 18px auto;

        display: flex;
        align-items: center;
        justify-content: center;

        border-radius: 22px;

        background: linear-gradient(
            135deg,
            #8b0000,
            #c1121f
        );

        color: white;

        font-size: 38px;

        box-shadow:
            0 10px 25px rgba(139,0,0,0.20);
    }

    .login-heading {
        text-align: center;

        font-size: 29px;
        font-weight: 800;

        color: #111827;

        margin-bottom: 6px;
    }

    .login-description {
        text-align: center;

        color: #6b7280;

        font-size: 14px;

        margin-bottom: 28px;
    }

    .login-info {
        text-align: center;

        color: #6b7280;

        font-size: 12px;

        margin-top: 20px;
    }

    /* ======================================================
       SECTION
       ====================================================== */

    .section-heading {
        font-size: 21px;
        font-weight: 800;
        color: #111827;

        margin-top: 8px;
        margin-bottom: 4px;
    }

    .section-subheading {
        color: #6b7280;
        font-size: 13px;

        margin-bottom: 18px;
    }

    /* ======================================================
       KPI
       ====================================================== */

    div[data-testid="stMetric"] {
        background: white;

        border: 1px solid #e5e7eb;

        border-radius: 17px;

        padding: 18px 20px;

        box-shadow:
            0 4px 15px rgba(0,0,0,0.045);
    }

    div[data-testid="stMetricLabel"] {
        font-weight: 600;
    }

    div[data-testid="stMetricValue"] {
        font-size: 29px;
        font-weight: 800;
    }

    /* ======================================================
       ARTICLE CARD
       ====================================================== */

    .article-box {
        background: white;

        border: 1px solid #e5e7eb;

        border-radius: 18px;

        padding: 22px;

        margin-bottom: 15px;

        box-shadow:
            0 5px 18px rgba(0,0,0,0.045);
    }

    .article-heading {
        font-size: 17px;
        font-weight: 750;

        color: #111827;

        line-height: 1.5;

        margin-bottom: 12px;
    }

    .article-date {
        color: #6b7280;

        font-size: 12px;

        margin-bottom: 12px;
    }

    .article-snippet {
        color: #374151;

        font-size: 14px;

        line-height: 1.65;

        margin-bottom: 12px;
    }

    .badge {
        display: inline-block;

        padding: 5px 10px;

        border-radius: 999px;

        font-size: 11px;

        font-weight: 700;

        margin-right: 5px;

        margin-bottom: 8px;
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

    .badge-gray {
        background: #f1f5f9;
        color: #475569;
    }

    .context-danger {
        background: #fff1f2;

        border-left: 4px solid #dc2626;

        padding: 11px 14px;

        border-radius: 10px;

        margin-top: 10px;

        color: #881337;

        font-size: 13px;
    }

    .context-warning {
        background: #fff7ed;

        border-left: 4px solid #f97316;

        padding: 11px 14px;

        border-radius: 10px;

        margin-top: 10px;

        color: #9a3412;

        font-size: 13px;
    }

    .keyword-box {
        background: #f8fafc;

        border: 1px solid #e2e8f0;

        border-radius: 10px;

        padding: 10px 13px;

        margin-top: 10px;

        font-size: 13px;

        color: #475569;
    }

    /* ======================================================
       SIDEBAR
       ====================================================== */

    section[data-testid="stSidebar"] {
        border-right: 1px solid #e5e7eb;
    }

    section[data-testid="stSidebar"] .block-container {
        padding-top: 1.5rem;
    }

    /* ======================================================
       FOOTER
       ====================================================== */

    .dashboard-footer {
        text-align: center;

        color: #9ca3af;

        font-size: 12px;

        padding: 25px 0 5px 0;
    }

    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# LOGIN - AMBIL USER DARI SECRETS
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
                    "",
                )
            ).strip()

            password = str(
                user_data.get(
                    "password",
                    "",
                )
            )

            role = str(
                user_data.get(
                    "role",
                    "viewer",
                )
            ).lower().strip()

            if role not in (
                "admin",
                "viewer",
            ):
                continue

            if not username or not password:
                continue

            users[username] = {
                "password": password,
                "role": role,
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
    password,
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
        "role": user["role"],
    }


# ============================================================
# SESSION
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
        '<div class="login-wrapper">',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="login-icon">🛡️</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="login-heading">'
        'Patroli Siber 2026'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="login-description">'
        'Sistem Monitoring Pemberitaan'
        '</div>',
        unsafe_allow_html=True,
    )

    username = st.text_input(
        "Username",
        placeholder="Masukkan username",
        key="login_username",
    )

    password = st.text_input(
        "Password",
        type="password",
        placeholder="Masukkan password",
        key="login_password",
    )

    login_button = st.button(
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
                password,
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

    st.markdown(
        f"""
        <div class="login-info">
            🏛️ {html.escape(NAMA_SATKER)}<br>
            Sistem Internal • Tahun {TAHUN_TARGET}
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        "</div>",
        unsafe_allow_html=True,
    )

    st.stop()


# ============================================================
# USER
# ============================================================

CURRENT_USERNAME = st.session_state.username
CURRENT_ROLE = st.session_state.role

IS_ADMIN = CURRENT_ROLE == "admin"
IS_VIEWER = CURRENT_ROLE == "viewer"


# ============================================================
# VALIDASI ROLE
# ============================================================

if CURRENT_ROLE not in (
    "admin",
    "viewer",
):

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
# HELPER
# ============================================================

def safe_list(value):

    if value is None:
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, tuple):
        return list(value)

    if isinstance(value, str):

        if not value.strip():
            return []

        return [value]

    return [str(value)]


def safe_text(value):

    if value is None:
        return ""

    return str(value)


def parse_date(value):

    if not value:
        return None

    try:

        dt = pd.to_datetime(
            value,
            errors="coerce",
        )

        if pd.isna(dt):
            return None

        if getattr(
            dt,
            "tzinfo",
            None,
        ):

            dt = dt.tz_convert(None)

        return dt.to_pydatetime()

    except Exception:

        return None


# ============================================================
# FILTER DATE
# ============================================================

def filter_date(
    article,
    mode,
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
        CURRENT_USERNAME
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
        use_container_width=True,
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

    telegram_active = (
        bool(
            os.getenv("TELEGRAM_TOKEN")
        )
        and
        bool(
            os.getenv("CHAT_ID")
        )
    )

    st.text_input(
        "Telegram",
        value=(
            "Aktif ✅"
            if telegram_active
            else
            "Tidak Aktif ❌"
        ),
        disabled=True,
    )

    if IS_ADMIN:

        st.divider()

        st.markdown(
            "### ⚙️ Administrasi"
        )

        if st.button(
            "🔄 Refresh Data",
            use_container_width=True,
        ):

            st.cache_data.clear()

            st.rerun()

    st.divider()

    st.caption(
        "Patroli otomatis menjalankan "
        "pengambilan dan klasifikasi berita."
    )


# ============================================================
# HEADER
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
            🏛️ {html.escape(NAMA_SATKER)}
        </div>

    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# FILTER
# ============================================================

st.markdown(
    '<div class="section-heading">'
    '🕒 Filter Monitoring'
    '</div>',
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="section-subheading">'
    'Gunakan filter periode, bulan, dan pencarian '
    'untuk menemukan pemberitaan yang diperlukan.'
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
# FILTER DATA
# ============================================================

filtered = []


for article in articles:

    if filter_mode != "Semua data":

        if not filter_date(
            article,
            filter_mode,
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

    filtered.append(article)


# ============================================================
# SEARCH
# ============================================================

search_text = st.text_input(
    "🔎 Cari judul, indikator, satker, atau sumber",
    placeholder="Ketik kata pencarian...",
)


if search_text:

    q = search_text.lower().strip()

    search_results = []

    for item in filtered:

        keywords = safe_list(
            item.get(
                "detected_keywords"
            )
        )

        satkers = safe_list(
            item.get(
                "satker_matches"
            )
        )

        searchable = " ".join(
            [
                safe_text(
                    item.get("title")
                ),
                safe_text(
                    item.get("snippet")
                ),
                safe_text(
                    item.get("content")
                ),
                " ".join(
                    map(str, keywords)
                ),
                " ".join(
                    map(str, satkers)
                ),
                safe_text(
                    item.get("source")
                ),
            ]
        ).lower()

        if q in searchable:

            search_results.append(item)

    filtered = search_results


# ============================================================
# SORT
# ============================================================

priority_order = {
    "KRITIS": 1,
    "TINGGI": 2,
    "SEDANG": 3,
    "RENDAH": 4,
}


category_order = {
    "Negatif Kuat": 1,
    "Perlu Penanganan": 2,
    "Netral": 3,
    "Positif": 4,
}


filtered.sort(
    key=lambda x: (
        priority_order.get(
            x.get(
                "priority",
                "RENDAH",
            ),
            4,
        ),

        category_order.get(
            x.get(
                "category",
                "Netral",
            ),
            3,
        ),

        float(
            x.get(
                "negative_score",
                0,
            )
            or 0
        ) * -1,
    )
)


# ============================================================
# KATEGORI
# ============================================================

negative = [
    x for x in filtered
    if x.get("category")
    == "Negatif Kuat"
]


handling = [
    x for x in filtered
    if x.get("category")
    == "Perlu Penanganan"
]


neutral = [
    x for x in filtered
    if x.get("category")
    == "Netral"
]


positive = [
    x for x in filtered
    if x.get("category")
    == "Positif"
]


priority = [
    x for x in filtered
    if x.get("category")
    in (
        "Negatif Kuat",
        "Perlu Penanganan",
    )
]


# ============================================================
# KPI
# ============================================================

st.markdown(
    '<div class="section-heading">'
    '📊 Ringkasan Monitoring'
    '</div>',
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="section-subheading">'
    'Ringkasan hasil klasifikasi berdasarkan filter aktif.'
    '</div>',
    unsafe_allow_html=True,
)

c1, c2, c3, c4, c5 = st.columns(5)


with c1:

    st.metric(
        "🔴 Negatif Kuat",
        len(negative),
    )


with c2:

    st.metric(
        "🟠 Penanganan",
        len(handling),
    )


with c3:

    st.metric(
        "🟡 Netral",
        len(neutral),
    )


with c4:

    st.metric(
        "🟢 Positif",
        len(positive),
    )


with c5:

    st.metric(
        "🚨 Prioritas",
        len(priority),
    )


# ============================================================
# ARTICLE RENDER
# ============================================================

def render_article(item):

    category = item.get(
        "category",
        "Netral",
    )

    priority_value = item.get(
        "priority",
        "RENDAH",
    )

    negative_score = item.get(
        "negative_score",
        0,
    )

    handling_score = item.get(
        "handling_score",
        0,
    )

    title = safe_text(
        item.get(
            "title",
            "-",
        )
    )

    published_date = safe_text(
        item.get(
            "published_date",
            "-",
        )
    )

    snippet = safe_text(
        item.get(
            "snippet",
            "",
        )
    )

    link = safe_text(
        item.get(
            "link",
            "",
        )
    )

    keywords = safe_list(
        item.get(
            "detected_keywords"
        )
    )

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
    # WARNA KATEGORI
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
    # ARTICLE CARD
    # --------------------------------------------------------

    st.markdown(
        '<div class="article-box">',
        unsafe_allow_html=True,
    )

    safe_title = html.escape(
        title
    )

    st.markdown(
        f"""
        <div class="article-heading">
            {icon} {safe_title}
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <span class="badge {badge_class}">
            {html.escape(str(category))}
        </span>

        <span class="badge badge-gray">
            Prioritas {html.escape(str(priority_value))}
        </span>

        <span class="badge badge-gray">
            Negatif {html.escape(str(negative_score))}
        </span>

        <span class="badge badge-gray">
            Penanganan {html.escape(str(handling_score))}
        </span>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class="article-date">
            📅 {html.escape(published_date)}
        </div>
        """,
        unsafe_allow_html=True,
    )

    if snippet:

        st.markdown(
            f"""
            <div class="article-snippet">
                {html.escape(snippet)}
            </div>
            """,
            unsafe_allow_html=True,
        )

    if keywords:

        keyword_text = ", ".join(
            html.escape(
                str(x)
            )
            for x in keywords[:30]
        )

        st.markdown(
            f"""
            <div class="keyword-box">
                🔎 <b>Indikator:</b> {keyword_text}
            </div>
            """,
            unsafe_allow_html=True,
        )

    if strong_context:

        context_text = ", ".join(
            html.escape(
                str(x)
            )
            for x in strong_context
        )

        st.markdown(
            f"""
            <div class="context-danger">
                ⚠️ <b>Konteks Negatif Kuat:</b>
                {context_text}
            </div>
            """,
            unsafe_allow_html=True,
        )

    if handling_context:

        context_text = ", ".join(
            html.escape(
                str(x)
            )
            for x in handling_context
        )

        st.markdown(
            f"""
            <div class="context-warning">
                📌 <b>Konteks Penanganan:</b>
                {context_text}
            </div>
            """,
            unsafe_allow_html=True,
        )

    if satker:

        satker_text = ", ".join(
            html.escape(
                str(x)
            )
            for x in satker
        )

        st.caption(
            f"🏢 Satker: {satker_text}"
        )

    if link:

        st.link_button(
            "🔗 Buka Artikel",
            link,
        )

    st.markdown(
        "</div>",
        unsafe_allow_html=True,
    )


# ============================================================
# TABS
# ============================================================

tab_priority, \
tab_negative, \
tab_handling, \
tab_neutral, \
tab_positive, \
tab_analytics = st.tabs(
    [
        "🚨 Prioritas Review",
        "🔴 Negatif Kuat",
        "🟠 Perlu Penanganan",
        "🟡 Netral",
        "🟢 Positif",
        "📊 Analisis",
    ]
)


# ============================================================
# PRIORITAS
# ============================================================

with tab_priority:

    st.markdown(
        '<div class="section-heading">'
        '🚨 Prioritas Review'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="section-subheading">'
        'Artikel dengan kategori Negatif Kuat '
        'dan Perlu Penanganan.'
        '</div>',
        unsafe_allow_html=True,
    )

    if priority:

        for item in priority:

            render_article(item)

    else:

        st.success(
            "Tidak ada artikel prioritas pada "
            "filter yang dipilih."
        )


# ============================================================
# NEGATIF
# ============================================================

with tab_negative:

    st.markdown(
        '<div class="section-heading">'
        '🔴 Negatif Kuat'
        '</div>',
        unsafe_allow_html=True,
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
        '<div class="section-heading">'
        '🟠 Perlu Penanganan'
        '</div>',
        unsafe_allow_html=True,
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
        '<div class="section-heading">'
        '🟡 Artikel Netral'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="section-subheading">'
        'Artikel netral tetap ditampilkan untuk '
        'kebutuhan monitoring dan audit klasifikasi.'
        '</div>',
        unsafe_allow_html=True,
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
        '<div class="section-heading">'
        '🟢 Pemberitaan Positif'
        '</div>',
        unsafe_allow_html=True,
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
        '<div class="section-heading">'
        '📊 Analisis Pemberitaan'
        '</div>',
        unsafe_allow_html=True,
    )

    # --------------------------------------------------------
    # DISTRIBUSI KATEGORI
    # --------------------------------------------------------

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

    if chart_data["Jumlah"].sum() > 0:

        fig = px.pie(
            chart_data,
            names="Kategori",
            values="Jumlah",
            hole=0.48,
            title="Distribusi Kategori",
        )

        fig.update_layout(
            margin=dict(
                l=20,
                r=20,
                t=60,
                b=20,
            ),
        )

        st.plotly_chart(
            fig,
            use_container_width=True,
        )

    # --------------------------------------------------------
    # PRIORITAS
    # --------------------------------------------------------

    st.markdown(
        '<div class="section-heading">'
        '📌 Distribusi Prioritas'
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
                len([
                    x for x in filtered
                    if x.get("priority")
                    == "KRITIS"
                ]),
                len([
                    x for x in filtered
                    if x.get("priority")
                    == "TINGGI"
                ]),
                len([
                    x for x in filtered
                    if x.get("priority")
                    == "SEDANG"
                ]),
                len([
                    x for x in filtered
                    if x.get("priority")
                    == "RENDAH"
                ]),
            ],
        }
    )

    st.dataframe(
        priority_df,
        use_container_width=True,
        hide_index=True,
    )

    # --------------------------------------------------------
    # STATISTIK
    # --------------------------------------------------------

    st.markdown(
        '<div class="section-heading">'
        '📈 Statistik'
        '</div>',
        unsafe_allow_html=True,
    )

    a1, a2, a3 = st.columns(3)

    with a1:

        st.metric(
            "Total Artikel",
            len(filtered),
        )

    with a2:

        st.metric(
            "Prioritas Review",
            len(priority),
        )

    with a3:

        st.metric(
            "Artikel Positif",
            len(positive),
        )


# ============================================================
# LOG ADMIN
# ============================================================

if IS_ADMIN:

    st.divider()

    st.markdown(
        '<div class="section-heading">'
        '📜 Log Patroli'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="section-subheading">'
        'Log eksekusi patroli otomatis dan proses sistem.'
        '</div>',
        unsafe_allow_html=True,
    )

    if logs:

        df_logs = pd.DataFrame(
            logs
        )

        st.dataframe(
            df_logs,
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

st.markdown(
    f"""
    <div class="dashboard-footer">

        🛡️ <b>Patroli Siber 2026</b><br>

        {html.escape(NAMA_SATKER)}<br><br>

        Sistem merupakan alat bantu monitoring dan
        klasifikasi awal. Artikel Negatif Kuat dan
        Perlu Penanganan tetap perlu diverifikasi
        terhadap isi, sumber, dan fakta.

    </div>
    """,
    unsafe_allow_html=True,
)

st.caption(
    f"👤 Login: {CURRENT_USERNAME} "
    f"• Role: {CURRENT_ROLE.upper()}"
)
