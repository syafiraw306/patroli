import datetime
import html
import os
from typing import Any, Dict, List, Optional

import pandas as pd
import plotly.express as px
import streamlit as st

from database import (
    get_all_articles,
    get_run_logs,
)


# ============================================================
# KONFIGURASI APLIKASI
# ============================================================

st.set_page_config(
    page_title="Patroli Siber 2026",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

NAMA_SATKER = (
    os.getenv(
        "NAMA_SATKER",
        "Kejaksaan Negeri Deli Serdang",
    ).strip()
    or "Kejaksaan Negeri Deli Serdang"
)

try:
    TAHUN_TARGET = int(
        os.getenv("TAHUN_TARGET", "2026")
    )
except (TypeError, ValueError):
    TAHUN_TARGET = 2026


# ============================================================
# KONSTANTA
# ============================================================

CATEGORY_NEGATIVE = "Negatif Kuat"
CATEGORY_HANDLING = "Perlu Penanganan"
CATEGORY_NEUTRAL = "Netral"
CATEGORY_POSITIVE = "Positif"

CATEGORIES = [
    CATEGORY_NEGATIVE,
    CATEGORY_HANDLING,
    CATEGORY_NEUTRAL,
    CATEGORY_POSITIVE,
]

PRIORITY_CATEGORIES = [
    CATEGORY_NEGATIVE,
    CATEGORY_HANDLING,
]

MONTHS = {
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

DATE_FILTERS = [
    "24 jam terakhir",
    "7 hari terakhir",
    "1 bulan terakhir",
    f"Tahun {TAHUN_TARGET}",
    "Semua data",
]

SORT_OPTIONS = [
    "Terbaru → Terlama",
    "Terlama → Terbaru",
]


# ============================================================
# CSS
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
       KPI
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
       ARTICLE
       ===================================================== */

    .article-card {
        background: #ffffff;

        border: 1px solid #e5e7eb;
        border-radius: 16px;

        padding: 20px;
        margin-bottom: 10px;

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
        margin-top: 10px;
        margin-bottom: 10px;
    }

    .article-snippet {
        color: #374151;
        font-size: 13px;
        line-height: 1.6;
        margin-top: 10px;
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

        margin-top: 10px;
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
       TABS
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
        line-height: 1.6;
    }

    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# SESSION STATE
# ============================================================

def initialize_session_state() -> None:
    defaults = {
        "logged_in": False,
        "username": "",
        "role": "",
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


initialize_session_state()


# ============================================================
# AUTHENTICATION
# ============================================================

def get_users() -> Dict[str, Dict[str, str]]:
    """
    Membaca konfigurasi user dari st.secrets.

    Format:
        [users.admin]
        username = "admin"
        password = "..."
        role = "admin"

        [users.viewer]
        username = "viewer"
        password = "..."
        role = "viewer"
    """

    users: Dict[str, Dict[str, str]] = {}

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
            ).strip().lower()

            if (
                username
                and password
                and role in {"admin", "viewer"}
            ):
                users[username] = {
                    "password": password,
                    "role": role,
                }

    except Exception as exc:
        st.error(
            f"Gagal membaca konfigurasi login: {exc}"
        )

    return users


def authenticate(
    username: str,
    password: str,
) -> Optional[Dict[str, str]]:

    users = get_users()

    username = str(username).strip()

    user = users.get(username)

    if not user:
        return None

    if str(user["password"]) != str(password):
        return None

    return {
        "username": username,
        "role": user["role"],
    }


# ============================================================
# LOGIN PAGE
# ============================================================

def render_login_page() -> None:

    left, center, right = st.columns(
        [1, 1.3, 1]
    )

    with center:

        st.markdown(
            """
            <div style="
                text-align:center;
                margin-top:50px;
                margin-bottom:25px;
            ">
                <div style="font-size:55px;">
                    🛡️
                </div>

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
                    Sistem Monitoring Pemberitaan
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
                clear_on_submit=False,
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
                            password,
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
            <div style="
                text-align:center;
                color:#94a3b8;
                font-size:11px;
                margin-top:18px;
                line-height:1.6;
            ">
                🏛️ {html.escape(NAMA_SATKER)}<br>
                Sistem Internal • Tahun {TAHUN_TARGET}
            </div>
            """,
            unsafe_allow_html=True,
        )


if not st.session_state.logged_in:

    render_login_page()

    st.stop()


# ============================================================
# USER & ROLE
# ============================================================

CURRENT_USERNAME = str(
    st.session_state.get(
        "username",
        "",
    )
)

CURRENT_ROLE = str(
    st.session_state.get(
        "role",
        "",
    )
).lower()

IS_ADMIN = CURRENT_ROLE == "admin"
IS_VIEWER = CURRENT_ROLE == "viewer"

if CURRENT_ROLE not in {"admin", "viewer"}:

    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.role = ""

    st.error(
        "Role pengguna tidak valid."
    )

    st.stop()


# ============================================================
# DATA LOADING
# ============================================================

@st.cache_data(ttl=60)
def load_articles() -> List[Dict[str, Any]]:
    return get_all_articles()


@st.cache_data(ttl=30)
def load_logs() -> List[Dict[str, Any]]:
    return get_run_logs(300)


def load_application_data():
    articles: List[Dict[str, Any]] = []
    logs: List[Dict[str, Any]] = []

    try:
        articles = load_articles()

    except Exception as exc:

        st.error(
            f"Gagal mengambil data artikel: {exc}"
        )

    if IS_ADMIN:

        try:
            logs = load_logs()

        except Exception as exc:

            st.warning(
                f"Gagal mengambil log patroli: {exc}"
            )

    return articles, logs


articles, logs = load_application_data()


# ============================================================
# HELPER: HTML SAFE
# ============================================================

def safe_text(
    value: Any,
    default: str = "",
) -> str:
    """
    Mengubah nilai menjadi teks aman untuk HTML.
    """

    if value is None:
        return default

    text = str(value).strip()

    if not text:
        return default

    return html.escape(
        text,
        quote=True,
    )


def safe_list(
    value: Any,
) -> List[Any]:
    """
    Menormalkan nilai list dari Supabase.
    """

    if value is None:
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, tuple):
        return list(value)

    if isinstance(value, set):
        return list(value)

    if isinstance(value, str):

        value = value.strip()

        if not value:
            return []

        return [value]

    return [value]


# ============================================================
# HELPER: DATE
# ============================================================

def parse_date(
    value: Any,
) -> Optional[datetime.datetime]:

    if value is None:
        return None

    if isinstance(value, datetime.datetime):

        dt = value

    else:

        try:

            dt = pd.to_datetime(
                value,
                errors="coerce",
            )

        except Exception:
            return None

        if pd.isna(dt):
            return None

        try:
            dt = dt.to_pydatetime()

        except AttributeError:
            return None

    if dt.tzinfo is not None:

        try:
            dt = dt.astimezone(
                datetime.timezone.utc
            ).replace(
                tzinfo=None
            )

        except Exception:
            dt = dt.replace(
                tzinfo=None
            )

    return dt


def article_datetime(
    article: Dict[str, Any],
) -> datetime.datetime:

    dt = parse_date(
        article.get("published_date")
    )

    if dt is None:
        return datetime.datetime.min

    return dt


# ============================================================
# DATE FILTER
# ============================================================

def filter_date(
    article: Dict[str, Any],
    mode: str,
) -> bool:

    dt = parse_date(
        article.get("published_date")
    )

    if dt is None:
        return False

    now = datetime.datetime.now()

    if mode == "24 jam terakhir":

        return (
            now - datetime.timedelta(hours=24)
            <= dt
            <= now
        )

    if mode == "7 hari terakhir":

        return (
            now - datetime.timedelta(days=7)
            <= dt
            <= now
        )

    if mode == "1 bulan terakhir":

        return (
            now - datetime.timedelta(days=30)
            <= dt
            <= now
        )

    if mode == f"Tahun {TAHUN_TARGET}":

        return (
            dt.year == TAHUN_TARGET
            and dt <= now
        )

    return True


# ============================================================
# SEARCH TEXT
# ============================================================

def article_search_text(
    article: Dict[str, Any],
) -> str:

    keyword_text = " ".join(
        str(value)
        for value in safe_list(
            article.get("detected_keywords")
        )
    )

    satker_text = " ".join(
        str(value)
        for value in safe_list(
            article.get("satker_matches")
        )
    )

    return " ".join(
        [
            str(article.get("title", "")),
            str(article.get("snippet", "")),
            str(article.get("content", "")),
            keyword_text,
            satker_text,
            str(article.get("source", "")),
        ]
    ).lower()


def apply_filters(
    source_articles: List[Dict[str, Any]],
    filter_mode: str,
    selected_month: str,
    search_text: str,
) -> List[Dict[str, Any]]:

    result: List[Dict[str, Any]] = []

    month_number = next(
        (
            number
            for number, name
            in MONTHS.items()
            if name == selected_month
        ),
        0,
    )

    query = (
        search_text
        or ""
    ).strip().lower()

    for article in source_articles:

        if (
            filter_mode != "Semua data"
            and not filter_date(
                article,
                filter_mode,
            )
        ):
            continue

        if selected_month != "Semua Bulan":

            dt = parse_date(
                article.get("published_date")
            )

            if dt is None:
                continue

            if (
                dt.year != TAHUN_TARGET
                or dt.month != month_number
            ):
                continue

        if query:

            if query not in article_search_text(
                article
            ):
                continue

        result.append(article)

    return result


# ============================================================
# SIDEBAR
# ============================================================

def render_sidebar() -> None:

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
                    Dashboard Monitoring
                </div>

            </div>
            """,
            unsafe_allow_html=True,
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

        telegram_token = os.getenv(
            "TELEGRAM_BOT_TOKEN",
            "",
        ).strip()

        telegram_chat_id = os.getenv(
            "TELEGRAM_CHAT_ID",
            "",
        ).strip()

        telegram_status = (
            "Aktif ✅"
            if telegram_token
            and telegram_chat_id
            else "Tidak Aktif ❌"
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
                use_container_width=True,
            ):

                st.cache_data.clear()

                st.rerun()

        st.divider()

        st.caption(
            "Patroli otomatis menjalankan "
            "pengambilan, deduplikasi, dan "
            "klasifikasi awal pemberitaan."
        )


render_sidebar()


# ============================================================
# HEADER
# ============================================================

st.markdown(
    f"""
    <div class="dashboard-header">

        <div class="dashboard-header-title">
            🛡️ Patroli Siber {TAHUN_TARGET}
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
            DATE_FILTERS,
            index=1,
        )

    with col2:

        selected_month = st.selectbox(
            f"🗓️ Bulan {TAHUN_TARGET}",
            list(MONTHS.values()),
            index=0,
        )

    with col3:

        sort_order = st.selectbox(
            "↕️ Urutan Artikel",
            SORT_OPTIONS,
            index=0,
        )

    search_text = st.text_input(
        "🔍 Cari judul, indikator, satker, sumber, atau isi artikel",
        "",
        placeholder=(
            "Contoh: Kejaksaan, tersangka, penyidikan..."
        ),
    )


# ============================================================
# APPLY FILTER
# ============================================================

filtered = apply_filters(
    articles,
    filter_mode,
    selected_month,
    search_text,
)


# ============================================================
# SORT
# ============================================================

filtered.sort(
    key=article_datetime,
    reverse=(
        sort_order == "Terbaru → Terlama"
    ),
)


# ============================================================
# CATEGORY DATA
# ============================================================

negative = [
    item
    for item in filtered
    if item.get("category")
    == CATEGORY_NEGATIVE
]

handling = [
    item
    for item in filtered
    if item.get("category")
    == CATEGORY_HANDLING
]

neutral = [
    item
    for item in filtered
    if item.get("category")
    == CATEGORY_NEUTRAL
]

positive = [
    item
    for item in filtered
    if item.get("category")
    == CATEGORY_POSITIVE
]

priority = [
    item
    for item in filtered
    if item.get("category")
    in PRIORITY_CATEGORIES
]


# ============================================================
# KPI
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
        Urutan:
        <b>{html.escape(sort_order)}</b>
    </div>
    """,
    unsafe_allow_html=True,
)

kpi_columns = st.columns(5)

kpis = [
    (
        "🔴",
        CATEGORY_NEGATIVE,
        len(negative),
    ),
    (
        "🟠",
        CATEGORY_HANDLING,
        len(handling),
    ),
    (
        "🟡",
        CATEGORY_NEUTRAL,
        len(neutral),
    ),
    (
        "🟢",
        CATEGORY_POSITIVE,
        len(positive),
    ),
    (
        "🚨",
        "Prioritas",
        len(priority),
    ),
]

for column, (
    icon,
    label,
    value,
) in zip(kpi_columns, kpis):

    with column:

        st.markdown(
            f"""
            <div class="kpi-card">

                <div class="kpi-icon">
                    {icon}
                </div>

                <div class="kpi-label">
                    {html.escape(label)}
                </div>

                <div class="kpi-value">
                    {value}
                </div>

            </div>
            """,
            unsafe_allow_html=True,
        )


st.markdown(
    "<br>",
    unsafe_allow_html=True,
)


# ============================================================
# ARTICLE HELPERS
# ============================================================

def category_visual(
    category: str,
):
    if category == CATEGORY_NEGATIVE:
        return (
            "🔴",
            "badge-red",
        )

    if category == CATEGORY_HANDLING:
        return (
            "🟠",
            "badge-orange",
        )

    if category == CATEGORY_POSITIVE:
        return (
            "🟢",
            "badge-green",
        )

    return (
        "🟡",
        "badge-yellow",
    )


def build_badges(
    item: Dict[str, Any],
) -> str:

    category = str(
        item.get(
            "category",
            CATEGORY_NEUTRAL,
        )
    )

    priority_value = str(
        item.get(
            "priority",
            "RENDAH",
        )
    )

    negative_score = item.get(
        "negative_score",
        0,
    )

    handling_score = item.get(
        "handling_score",
        0,
    )

    icon, category_class = category_visual(
        category
    )

    return f"""
        <span class="badge {category_class}">
            {icon} {safe_text(category)}
        </span>

        <span class="badge badge-gray">
            Prioritas: {safe_text(priority_value)}
        </span>

        <span class="badge badge-gray">
            Negative: {safe_text(negative_score, "0")}
        </span>

        <span class="badge badge-gray">
            Handling: {safe_text(handling_score, "0")}
        </span>
    """


def build_keyword_html(
    item: Dict[str, Any],
) -> str:

    keywords = safe_list(
        item.get(
            "detected_keywords"
        )
    )

    if not keywords:
        return ""

    badges = []

    for keyword in keywords[:15]:

        badges.append(
            f"""
            <span class="badge badge-gray">
                {safe_text(keyword)}
            </span>
            """
        )

    return (
        '<div style="margin-top:12px;">'
        '<span style="'
        'font-size:11px;'
        'font-weight:700;'
        'color:#64748b;'
        '">🔎 INDIKATOR</span>'
        '<br>'
        + "".join(badges)
        + "</div>"
    )


def build_context_html(
    item: Dict[str, Any],
) -> str:

    output = []

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

    if strong_context:

        values = ", ".join(
            safe_text(value)
            for value in strong_context
        )

        output.append(
            f"""
            <div class="info-box">
                ⚠️ <b>Konteks Negatif Kuat:</b>
                {values}
            </div>
            """
        )

    if handling_context:

        values = ", ".join(
            safe_text(value)
            for value in handling_context
        )

        output.append(
            f"""
            <div class="info-box">
                📌 <b>Konteks Penanganan:</b>
                {values}
            </div>
            """
        )

    return "".join(output)


def build_satker_html(
    item: Dict[str, Any],
) -> str:

    satker = safe_list(
        item.get(
            "satker_matches"
        )
    )

    if not satker:
        return ""

    values = ", ".join(
        safe_text(value)
        for value in satker
    )

    return f"""
        <div style="
            font-size:11px;
            color:#64748b;
            margin-top:10px;
        ">
            🏢 {values}
        </div>
    """


# ============================================================
# ARTICLE RENDERER
# ============================================================

def render_article(
    item: Dict[str, Any],
) -> None:

    title = safe_text(
        item.get(
            "title",
            "-",
        ),
        "-",
    )

    snippet = safe_text(
        item.get(
            "snippet",
            "",
        )
    )

    published_date = safe_text(
        item.get(
            "published_date",
            "-",
        ),
        "-",
    )

    link = str(
        item.get(
            "link",
            "",
        )
        or ""
    ).strip()

    badges = build_badges(
        item
    )

    keyword_html = build_keyword_html(
        item
    )

    context_html = build_context_html(
        item
    )

    satker_html = build_satker_html(
        item
    )

    snippet_html = ""

    if snippet:

        snippet_html = f"""
            <div class="article-snippet">
                {snippet}
            </div>
        """

    st.markdown(
        f"""
        <div class="article-card">

            <div class="article-title">
                {title}
            </div>

            <div>
                {badges}
            </div>

            <div class="article-date">
                📅 {published_date}
            </div>

            {snippet_html}

            {keyword_html}

            {context_html}

            {satker_html}

        </div>
        """,
        unsafe_allow_html=True,
    )

    if link:

        try:

            st.link_button(
                "🔗 Buka Artikel",
                link,
            )

        except Exception:

            st.write(
                f"🔗 {link}"
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
        '<div class="section-title">'
        '🚨 Artikel Prioritas Review'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="section-description">
            Artikel yang membutuhkan perhatian
            dan verifikasi lebih lanjut.
        </div>
        """,
        unsafe_allow_html=True,
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
# TAB NEGATIF
# ============================================================

with tab_negative:

    st.markdown(
        '<div class="section-title">'
        '🔴 Negatif Kuat'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="section-description">
            Pemberitaan yang terindikasi memiliki
            dampak negatif kuat terhadap satker
            dan perlu diverifikasi.
        </div>
        """,
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
        '<div class="section-title">'
        '🟠 Perlu Penanganan'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="section-description">
            Pemberitaan yang perlu dipantau
            atau diverifikasi lebih lanjut.
        </div>
        """,
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
        '<div class="section-title">'
        '🟡 Netral'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="section-description">
            Pemberitaan yang tidak menunjukkan
            indikasi negatif kuat atau penanganan khusus.
        </div>
        """,
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
        '<div class="section-title">'
        '🟢 Positif'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="section-description">
            Pemberitaan positif, keberhasilan penegakan
            hukum, kegiatan resmi, dan aktivitas kelembagaan.
        </div>
        """,
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
        '<div class="section-title">'
        '📊 Analisis Pemberitaan'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="section-description">
            Visualisasi distribusi kategori
            dan tingkat prioritas.
        </div>
        """,
        unsafe_allow_html=True,
    )

    chart_data = pd.DataFrame(
        {
            "Kategori": [
                CATEGORY_NEGATIVE,
                CATEGORY_HANDLING,
                CATEGORY_NEUTRAL,
                CATEGORY_POSITIVE,
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
                "Belum ada data untuk dianalisis."
            )

    with col_chart2:

        priority_values = [
            "KRITIS",
            "TINGGI",
            "SEDANG",
            "RENDAH",
        ]

        priority_counts = []

        for priority_name in priority_values:

            count = len(
                [
                    item
                    for item in filtered
                    if str(
                        item.get(
                            "priority",
                            "",
                        )
                    ).upper()
                    == priority_name
                ]
            )

            priority_counts.append(
                count
            )

        priority_df = pd.DataFrame(
            {
                "Prioritas": priority_values,
                "Jumlah": priority_counts,
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
                f"🔴 {CATEGORY_NEGATIVE}",
                f"🟠 {CATEGORY_HANDLING}",
                f"🟡 {CATEGORY_NEUTRAL}",
                f"🟢 {CATEGORY_POSITIVE}",
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
            '<div class="section-title">'
            '📜 Log Patroli'
            '</div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            """
            <div class="section-description">
                Riwayat proses patroli otomatis,
                reklasifikasi, dan statistik proses.
            </div>
            """,
            unsafe_allow_html=True,
        )

        if logs:

            log_df = pd.DataFrame(
                logs
            )

            st.dataframe(
                log_df,
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

        🛡️ <b>Patroli Siber {TAHUN_TARGET}</b><br>

        Sistem merupakan alat bantu monitoring
        dan klasifikasi awal. Artikel
        <b>Negatif Kuat</b> dan
        <b>Perlu Penanganan</b> tetap perlu
        diverifikasi terhadap isi, sumber,
        dan fakta.<br><br>

        {html.escape(NAMA_SATKER)}
        • Login:
        {html.escape(CURRENT_USERNAME)}
        ({html.escape(CURRENT_ROLE.upper())})

    </div>
    """,
    unsafe_allow_html=True,
)
