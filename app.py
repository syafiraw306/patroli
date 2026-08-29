
import datetime
import os
import html

import pandas as pd
import plotly.express as px
import streamlit as st

from database import (
    get_all_articles,
    get_run_logs,
)

# ============================================================
# KONFIGURASI
# ============================================================

st.set_page_config(
    page_title="Patroli Siber 2026",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

NAMA_SATKER = os.getenv(
    "NAMA_SATKER",
    "Kejaksaan Negeri Deli Serdang"
)

TAHUN_TARGET = 2026


# ============================================================
# CSS MODERN
# ============================================================

st.markdown(
    """
    <style>

    /* =====================================================
       GLOBAL
       ===================================================== */

    .stApp {
        background: #f5f7fb;
    }

    .block-container {
        max-width: 1500px;
        padding-top: 1.5rem;
        padding-bottom: 3rem;
    }

    section[data-testid="stSidebar"] {
        background: #ffffff;
        border-right: 1px solid #e5e7eb;
    }

    section[data-testid="stSidebar"] > div {
        padding-top: 1.5rem;
    }

    /* =====================================================
       HEADER
       ===================================================== */

    .dashboard-header {
        background:
            linear-gradient(
                135deg,
                #7f1d1d 0%,
                #991b1b 45%,
                #b91c1c 100%
            );

        padding: 28px 32px;
        border-radius: 18px;
        margin-bottom: 24px;

        box-shadow:
            0 10px 30px rgba(127, 29, 29, 0.18);

        color: white;
    }

    .dashboard-header-title {
        font-size: 30px;
        font-weight: 800;
        letter-spacing: -0.5px;
    }

    .dashboard-header-subtitle {
        margin-top: 6px;
        font-size: 14px;
        opacity: 0.90;
    }

    .dashboard-header-badge {
        display: inline-block;
        margin-top: 16px;
        padding: 6px 12px;
        border-radius: 999px;

        background: rgba(255,255,255,0.15);
        border: 1px solid rgba(255,255,255,0.25);

        font-size: 12px;
        font-weight: 600;
    }

    /* =====================================================
       SECTION
       ===================================================== */

    .section-title {
        font-size: 21px;
        font-weight: 800;
        color: #111827;
        margin-top: 8px;
        margin-bottom: 4px;
    }

    .section-description {
        color: #6b7280;
        font-size: 13px;
        margin-bottom: 16px;
    }

    /* =====================================================
       KPI CARD
       ===================================================== */

    .kpi-card {
        background: #ffffff;

        border: 1px solid #e5e7eb;
        border-radius: 16px;

        padding: 18px 20px;

        min-height: 120px;

        box-shadow:
            0 4px 14px rgba(15, 23, 42, 0.05);

        transition: all 0.2s ease;
    }

    .kpi-card:hover {
        transform: translateY(-2px);
        box-shadow:
            0 8px 22px rgba(15, 23, 42, 0.09);
    }

    .kpi-icon {
        font-size: 22px;
    }

    .kpi-label {
        color: #6b7280;
        font-size: 12px;
        font-weight: 600;
        margin-top: 8px;
    }

    .kpi-value {
        color: #111827;
        font-size: 29px;
        font-weight: 800;
        margin-top: 2px;
    }

    /* =====================================================
       ARTICLE CARD
       ===================================================== */

    .article-card {
        background: #ffffff;

        border: 1px solid #e5e7eb;
        border-radius: 16px;

        padding: 20px;
        margin-bottom: 14px;

        box-shadow:
            0 3px 12px rgba(15, 23, 42, 0.04);

        transition: all 0.2s ease;
    }

    .article-card:hover {
        border-color: #cbd5e1;
        box-shadow:
            0 8px 22px rgba(15, 23, 42, 0.08);
        transform: translateY(-1px);
    }

    .article-title {
        font-size: 17px;
        font-weight: 750;
        color: #111827;
        line-height: 1.45;
        margin-bottom: 10px;
    }

    .article-date {
        color: #6b7280;
        font-size: 12px;
        margin-bottom: 10px;
    }

    .article-snippet {
        color: #374151;
        font-size: 13px;
        line-height: 1.6;
        margin-bottom: 12px;
    }

    /* =====================================================
       BADGES
       ===================================================== */

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
        background: #fef9c3;
        color: #854d0e;
    }

    .badge-green {
        background: #dcfce7;
        color: #166534;
    }

    .badge-gray {
        background: #f3f4f6;
        color: #374151;
    }

    /* =====================================================
       FILTER BOX
       ===================================================== */

    .filter-box {
        background: #ffffff;

        border: 1px solid #e5e7eb;
        border-radius: 16px;

        padding: 18px 20px;
        margin-bottom: 20px;

        box-shadow:
            0 3px 12px rgba(15, 23, 42, 0.04);
    }

    /* =====================================================
       INFO BOX
       ===================================================== */

    .info-box {
        background: #f8fafc;

        border: 1px solid #e2e8f0;

        border-radius: 14px;

        padding: 14px 16px;

        color: #475569;

        font-size: 13px;
        line-height: 1.6;
    }

    /* =====================================================
       SIDEBAR
       ===================================================== */

    .sidebar-brand {
        text-align: center;
        padding: 5px 5px 18px 5px;
    }

    .sidebar-logo {
        font-size: 42px;
    }

    .sidebar-title {
        font-size: 18px;
        font-weight: 800;
        color: #111827;
    }

    .sidebar-subtitle {
        color: #6b7280;
        font-size: 12px;
        margin-top: 3px;
    }

    /* =====================================================
       TAB
       ===================================================== */

    button[data-baseweb="tab"] {
        font-weight: 700;
    }

    /* =====================================================
       METRIC
       ===================================================== */

    [data-testid="stMetricValue"] {
        font-size: 27px;
        font-weight: 800;
    }

    [data-testid="stMetricLabel"] {
        font-weight: 650;
    }

    /* =====================================================
       BUTTON
       ===================================================== */

    .stButton > button,
    .stLinkButton > a {
        border-radius: 10px;
        font-weight: 650;
    }

    /* =====================================================
       FOOTER
       ===================================================== */

    .footer {
        text-align: center;
        color: #94a3b8;
        font-size: 11px;
        padding-top: 12px;
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

    user = users.get(
        str(username).strip()
    )

    if (
        user
        and str(user["password"]) == str(password)
    ):
        return {
            "username": username,
            "role": user["role"],
        }

    return None


# ============================================================
# LOGIN
# ============================================================

if not st.session_state.logged_in:

    left, center, right = st.columns([1, 1.3, 1])

    with center:

        st.markdown(
            """
            <div style="
                text-align:center;
                margin-top:50px;
                margin-bottom:25px;
            ">
                <div style="font-size:55px;">🛡️</div>

                <div style="
                    font-size:28px;
                    font-weight:800;
                    color:#111827;
                ">
                    Patroli Siber
                </div>

                <div style="
                    color:#6b7280;
                    font-size:13px;
                    margin-top:5px;
                ">
                    Sistem Monitoring Pemberitaan 2026
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.container(border=True):

            st.markdown(
                "### 🔐 Login Sistem"
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

                login_button = (
                    st.form_submit_button(
                        "🔐 Masuk ke Dashboard",
                        type="primary",
                        use_container_width=True,
                    )
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

        st.markdown(
            f"""
            <div style="
                text-align:center;
                color:#94a3b8;
                font-size:11px;
                margin-top:18px;
            ">
                🏛️ {html.escape(NAMA_SATKER)}<br>
                Sistem Internal • Tahun {TAHUN_TARGET}
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.stop()


# ============================================================
# USER INFO
# ============================================================

CURRENT_USERNAME = st.session_state.username
CURRENT_ROLE = st.session_state.role

IS_ADMIN = CURRENT_ROLE == "admin"
IS_VIEWER = CURRENT_ROLE == "viewer"

if CURRENT_ROLE not in ["admin", "viewer"]:

    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.role = ""

    st.error("Role pengguna tidak valid.")

    st.stop()


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
            Sistem Monitoring dan Klasifikasi Awal Pemberitaan
            • {html.escape(NAMA_SATKER)}
        </div>

        <div class="dashboard-header-badge">
            ● SISTEM INTERNAL
            &nbsp;&nbsp;|&nbsp;&nbsp;
            📡 MONITORING AKTIF
            &nbsp;&nbsp;|&nbsp;&nbsp;
            📅 {TAHUN_TARGET}
        </div>

    </div>
    """,
    unsafe_allow_html=True,
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

        if getattr(dt, "tzinfo", None):

            dt = dt.tz_convert(None)

        return dt.to_pydatetime()

    except Exception:

        return None


def filter_date(article, mode):

    dt = parse_date(
        article.get("published_date")
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


def safe_list(value):

    if not value:
        return []

    if isinstance(value, list):
        return value

    return [str(value)]


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.markdown(
        """
        <div class="sidebar-brand">

            <div class="sidebar-logo">
                🛡️
            </div>

            <div class="sidebar-title">
                Patroli Siber
            </div>

            <div class="sidebar-subtitle">
                Dashboard Monitoring 2026
            </div>

        </div>
        """,
        unsafe_allow_html=True,
    )

    st.divider()

    st.markdown("### 👤 Pengguna")

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
# FILTER
# ============================================================

st.markdown(
    '<div class="section-title">🔎 Filter & Pengurutan</div>',
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="section-description">
        Saring pemberitaan berdasarkan periode,
        bulan, kata kunci, dan urutan tanggal.
    </div>
    """,
    unsafe_allow_html=True,
)

with st.container(border=True):

    col1, col2, col3 = st.columns(
        [1.2, 1.2, 1.2]
    )

    with col1:

        filter_mode = st.selectbox(
            "📅 Periode",
            [
                "24 jam terakhir",
                "7 hari terakhir",
                "1 bulan terakhir",
                "Tahun 2026",
                "Semua data",
            ],
            index=1,
        )

    with col2:

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
            "🗓️ Bulan 2026",
            list(
                bulan_options.values()
            ),
            index=0,
        )

    with col3:

        sort_order = st.selectbox(
            "↕️ Urutan Artikel",
            [
                "Terbaru → Terlama",
                "Terlama → Terbaru",
            ],
            index=0,
        )

    search_text = st.text_input(
        "🔍 Cari judul, indikator, satker, sumber, atau isi artikel",
        "",
        placeholder="Contoh: Kejaksaan, tersangka, penyidikan...",
    )


# ============================================================
# FILTER PROCESSING
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
            article.get("published_date")
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
            or dt.month != month_number
        ):
            continue

    filtered.append(article)


# ============================================================
# SEARCH
# ============================================================

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
# SORTING
# ============================================================

def article_datetime(item):

    dt = parse_date(
        item.get("published_date")
    )

    if dt is None:

        return datetime.datetime.min

    return dt


filtered.sort(
    key=article_datetime,
    reverse=(
        sort_order
        == "Terbaru → Terlama"
    ),
)


# ============================================================
# KPI
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
    in [
        "Negatif Kuat",
        "Perlu Penanganan",
    ]
]


# ============================================================
# KPI HEADER
# ============================================================

st.markdown(
    '<div class="section-title">📊 Ringkasan Monitoring</div>',
    unsafe_allow_html=True,
)

st.markdown(
    f"""
    <div class="section-description">
        Menampilkan <b>{len(filtered)}</b> artikel
        berdasarkan filter yang dipilih.
        Urutan: <b>{html.escape(sort_order)}</b>
    </div>
    """,
    unsafe_allow_html=True,
)

kpi_cols = st.columns(5)

kpis = [
    (
        "🔴",
        "Negatif Kuat",
        len(negative),
    ),
    (
        "🟠",
        "Perlu Penanganan",
        len(handling),
    ),
    (
        "🟡",
        "Netral",
        len(neutral),
    ),
    (
        "🟢",
        "Positif",
        len(positive),
    ),
    (
        "🚨",
        "Prioritas",
        len(priority),
    ),
]

for col, (
    icon,
    label,
    value,
) in zip(kpi_cols, kpis):

    with col:

        st.markdown(
            f"""
            <div class="kpi-card">

                <div class="kpi-icon">
                    {icon}
                </div>

                <div class="kpi-label">
                    {label}
                </div>

                <div class="kpi-value">
                    {value}
                </div>

            </div>
            """,
            unsafe_allow_html=True,
        )


st.markdown("<br>", unsafe_allow_html=True)


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

    title = html.escape(
        str(
            item.get(
                "title",
                "-"
            )
        )
    )

    snippet = html.escape(
        str(
            item.get(
                "snippet",
                ""
            )
        )
    )

    published_date = html.escape(
        str(
            item.get(
                "published_date",
                "-"
            )
        )
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

    keyword_html = ""

    if keywords:

        keyword_html = (
            '<div style="margin-top:8px;">'
            '<span style="'
            'font-size:11px;'
            'font-weight:700;'
            'color:#64748b;'
            '">🔎 INDIKATOR</span><br>'
            + "".join(
                f'<span class="badge badge-gray">'
                f'{html.escape(str(k))}'
                f'</span>'
                for k in keywords[:15]
            )
            + "</div>"
        )

    context_html = ""

    if strong_context:

        context_html += (
            '<div class="info-box" '
            'style="margin-top:10px;">'
            "⚠️ <b>Konteks Negatif Kuat:</b> "
            + ", ".join(
                html.escape(str(x))
                for x in strong_context
            )
            + "</div>"
        )

    if handling_context:

        context_html += (
            '<div class="info-box" '
            'style="margin-top:10px;">'
            "📌 <b>Konteks Penanganan:</b> "
            + ", ".join(
                html.escape(str(x))
                for x in handling_context
            )
            + "</div>"
        )

    satker_html = ""

    if satker:

        satker_html = (
            '<div style="'
            'font-size:11px;'
            'color:#64748b;'
            'margin-top:10px;'
            '">'
            "🏢 "
            + ", ".join(
                html.escape(str(x))
                for x in satker
            )
            + "</div>"
        )

    st.markdown(
        f"""
        <div class="article-card">

            <div class="article-title">
                {icon} {title}
            </div>

            <div>
                <span class="badge {category_class}">
                    {html.escape(category)}
                </span>

                <span class="badge badge-gray">
                    Prioritas: {html.escape(str(priority_value))}
                </span>

                <span class="badge badge-gray">
                    Negative: {negative_score}
                </span>

                <span class="badge badge-gray">
                    Handling: {handling_score}
                </span>
            </div>

            <div class="article-date">
                📅 {published_date}
            </div>

            {
                f'<div class="article-snippet">{snippet}</div>'
                if snippet
                else ""
            }

            {keyword_html}

            {context_html}

            {satker_html}

        </div>
        """,
        unsafe_allow_html=True,
    )

    if item.get("link"):

        st.link_button(
            "🔗 Buka Artikel",
            item.get("link"),
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
# TAB PRIORITAS
# ============================================================

with tab_priority:

    st.markdown(
        '<div class="section-title">🚨 Artikel Prioritas Review</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="section-description">'
        'Artikel yang membutuhkan perhatian lebih lanjut.'
        '</div>',
        unsafe_allow_html=True,
    )

    if priority:

        for item in priority:

            render_article(item)

    else:

        st.success(
            "Tidak ada artikel prioritas pada periode yang dipilih."
        )


# ============================================================
# TAB NEGATIF
# ============================================================

with tab_negative:

    st.markdown(
        '<div class="section-title">🔴 Negatif Kuat</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="section-description">'
        'Pemberitaan yang terindikasi memiliki dampak negatif kuat '
        'terhadap satker dan perlu verifikasi.'
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
# TAB HANDLING
# ============================================================

with tab_handling:

    st.markdown(
        '<div class="section-title">🟠 Perlu Penanganan</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="section-description">'
        'Pemberitaan yang perlu dipantau atau diverifikasi lebih lanjut.'
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
# TAB NETRAL
# ============================================================

with tab_neutral:

    st.markdown(
        '<div class="section-title">🟡 Netral</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="section-description">'
        'Pemberitaan yang tidak menunjukkan indikasi negatif kuat '
        'atau penanganan khusus.'
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
# TAB POSITIF
# ============================================================

with tab_positive:

    st.markdown(
        '<div class="section-title">🟢 Positif</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="section-description">'
        'Pemberitaan positif, keberhasilan penegakan hukum, '
        'kegiatan resmi, dan aktivitas kelembagaan.'
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
# ANALYTICS
# ============================================================

with tab_analytics:

    st.markdown(
        '<div class="section-title">📊 Analisis Pemberitaan</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="section-description">'
        'Visualisasi distribusi kategori dan tingkat prioritas.'
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

    col_chart1, col_chart2 = st.columns(2)

    with col_chart1:

        if chart_data["Jumlah"].sum() > 0:

            fig = px.pie(
                chart_data,
                names="Kategori",
                values="Jumlah",
                hole=0.50,
                title="Distribusi Kategori",
            )

            fig.update_layout(
                margin=dict(
                    l=10,
                    r=10,
                    t=50,
                    b=10,
                ),
                legend_title_text="",
            )

            st.plotly_chart(
                fig,
                use_container_width=True,
            )

        else:

            st.info(
                "Belum ada data."
            )

    with col_chart2:

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

        fig_priority = px.bar(
            priority_df,
            x="Prioritas",
            y="Jumlah",
            title="Distribusi Prioritas",
            text="Jumlah",
        )

        fig_priority.update_layout(
            margin=dict(
                l=10,
                r=10,
                t=50,
                b=10,
            )
        )

        st.plotly_chart(
            fig_priority,
            use_container_width=True,
        )

    st.markdown(
        "### 📋 Rekapitulasi"
    )

    summary_df = pd.DataFrame(
        {
            "Kategori": [
                "🔴 Negatif Kuat",
                "🟠 Perlu Penanganan",
                "🟡 Netral",
                "🟢 Positif",
            ],

            "Jumlah": [
                len(negative),
                len(handling),
                len(neutral),
                len(positive),
            ],
        }
    )

    st.dataframe(
        summary_df,
        use_container_width=True,
        hide_index=True,
    )


# ============================================================
# LOG ADMIN
# ============================================================

if IS_ADMIN and tab_logs is not None:

    with tab_logs:

        st.markdown(
            '<div class="section-title">📜 Log Patroli</div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            '<div class="section-description">'
            'Riwayat proses patroli otomatis dan klasifikasi artikel.'
            '</div>',
            unsafe_allow_html=True,
        )

        if logs:

            st.dataframe(
                pd.DataFrame(logs),
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
    <div class="footer">

        🛡️ <b>Patroli Siber 2026</b><br>

        Sistem merupakan alat bantu monitoring dan
        klasifikasi awal. Artikel <b>Negatif Kuat</b> dan
        <b>Perlu Penanganan</b> tetap perlu diverifikasi
        terhadap isi, sumber, dan fakta.<br><br>

        {html.escape(NAMA_SATKER)}
        • Login: {html.escape(CURRENT_USERNAME)}
        ({html.escape(CURRENT_ROLE.upper())})

    </div>
    """,
    unsafe_allow_html=True,
)

