import datetime
import html
import os
import re

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
    "Kejaksaan Negeri Deli Serdang",
)

TAHUN_TARGET = 2026


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
        background: linear-gradient(
            135deg,
            #7f1d1d 0%,
            #991b1b 50%,
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


    /* =====================================================
       BADGE
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
       BUTTON
       ===================================================== */

    .stButton > button,
    .stLinkButton > a {
        border-radius: 10px;
        font-weight: 650;
    }


    /* =====================================================
       INFO
       ===================================================== */

    .safe-info {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 12px 14px;
        color: #475569;
        font-size: 13px;
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
# SANITASI TEKS
# ============================================================

def clean_text(value):
    """
    Membersihkan teks dari:
    - HTML tag
    - HTML entity
    - script/style/iframe
    - HTML yang sudah di-escape
    - karakter invisible
    - whitespace berlebihan
    """

    if value is None:
        return ""

    if isinstance(value, float) and pd.isna(value):
        return ""

    text = str(value)

    # --------------------------------------------------------
    # 1. Decode entity berkali-kali
    #    Menangani:
    #    &lt;p&gt;
    #    &amp;lt;p&amp;gt;
    # --------------------------------------------------------

    for _ in range(5):
        decoded = html.unescape(text)

        if decoded == text:
            break

        text = decoded

    # --------------------------------------------------------
    # 2. Hapus script/style/iframe/noscript/object/embed
    # --------------------------------------------------------

    text = re.sub(
        r"<\s*(script|style|iframe|noscript|object|embed)"
        r"\b[^>]*>.*?"
        r"<\s*/\s*\1\s*>",
        " ",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # --------------------------------------------------------
    # 3. Hapus komentar HTML
    # --------------------------------------------------------

    text = re.sub(
        r"<!--.*?-->",
        " ",
        text,
        flags=re.DOTALL,
    )

    # --------------------------------------------------------
    # 4. Ubah beberapa tag pemisah menjadi spasi
    # --------------------------------------------------------

    text = re.sub(
        r"<\s*(br|p|div|li|tr|td|th|h1|h2|h3|h4|h5|h6)"
        r"\b[^>]*>",
        " ",
        text,
        flags=re.IGNORECASE,
    )

    # --------------------------------------------------------
    # 5. Hapus seluruh tag HTML tersisa
    # --------------------------------------------------------

    previous = None

    while previous != text:

        previous = text

        text = re.sub(
            r"<[^>]*>",
            " ",
            text,
            flags=re.DOTALL,
        )

    # --------------------------------------------------------
    # 6. Decode entity sekali lagi
    # --------------------------------------------------------

    text = html.unescape(text)

    # --------------------------------------------------------
    # 7. Jika hasil decode menghasilkan tag lagi,
    #    hapus kembali
    # --------------------------------------------------------

    text = re.sub(
        r"<[^>]*>",
        " ",
        text,
        flags=re.DOTALL,
    )

    # --------------------------------------------------------
    # 8. Karakter invisible
    # --------------------------------------------------------

    text = re.sub(
        r"[\xa0\u200b\u200c\u200d\ufeff]",
        " ",
        text,
    )

    # --------------------------------------------------------
    # 9. Hapus karakter kontrol
    # --------------------------------------------------------

    text = re.sub(
        r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]",
        " ",
        text,
    )

    # --------------------------------------------------------
    # 10. Rapikan whitespace
    # --------------------------------------------------------

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def clean_list(value):
    """
    Membersihkan field list dari database.
    """

    if value is None:
        return []

    if isinstance(value, (list, tuple, set)):

        result = []

        for item in value:

            cleaned = clean_text(item)

            if cleaned:
                result.append(cleaned)

        return result

    cleaned = clean_text(value)

    if cleaned:
        return [cleaned]

    return []


def clean_url(value):
    """
    Membersihkan URL dan memastikan hanya URL HTTP/HTTPS.
    """

    if not value:
        return ""

    url = str(value).strip()

    # Decode entity
    for _ in range(3):

        decoded = html.unescape(url)

        if decoded == url:
            break

        url = decoded

    # Jangan izinkan HTML sebagai URL
    if "<" in url or ">" in url:
        return ""

    # Hanya HTTP/HTTPS
    if not re.match(
        r"^https?://",
        url,
        flags=re.IGNORECASE,
    ):
        return ""

    return url


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
            <div style="
                text-align:center;
                color:#94a3b8;
                font-size:11px;
                margin-top:18px;
            ">
                🏛️ {html.escape(clean_text(NAMA_SATKER))}<br>
                Sistem Internal • Tahun {TAHUN_TARGET}
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.stop()


# ============================================================
# USER
# ============================================================

CURRENT_USERNAME = clean_text(
    st.session_state.username
)

CURRENT_ROLE = clean_text(
    st.session_state.role
).lower()

IS_ADMIN = CURRENT_ROLE == "admin"
IS_VIEWER = CURRENT_ROLE == "viewer"

if CURRENT_ROLE not in ["admin", "viewer"]:

    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.role = ""

    st.error(
        "Role pengguna tidak valid."
    )

    st.stop()


# ============================================================
# HEADER
# ============================================================

safe_satker_html = html.escape(
    clean_text(NAMA_SATKER)
)

st.markdown(
    f"""
    <div class="dashboard-header">

        <div class="dashboard-header-title">
            🛡️ Patroli Siber 2026
        </div>

        <div class="dashboard-header-subtitle">
            Sistem Monitoring dan Klasifikasi Awal Pemberitaan
            • {safe_satker_html}
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

    data = get_all_articles()

    if not data:
        return []

    cleaned_articles = []

    for item in data:

        article = dict(item)

        # ----------------------------------------------------
        # FIELD TEKS
        # ----------------------------------------------------

        article["title"] = clean_text(
            article.get("title", "")
        )

        article["snippet"] = clean_text(
            article.get("snippet", "")
        )

        article["content"] = clean_text(
            article.get("content", "")
        )

        article["category"] = clean_text(
            article.get("category", "Netral")
        )

        article["priority"] = clean_text(
            article.get("priority", "RENDAH")
        )

        # ----------------------------------------------------
        # FIELD LIST
        # ----------------------------------------------------

        article["detected_keywords"] = clean_list(
            article.get("detected_keywords")
        )

        article["strong_context"] = clean_list(
            article.get("strong_context")
        )

        article["handling_context"] = clean_list(
            article.get("handling_context")
        )

        article["satker_matches"] = clean_list(
            article.get("satker_matches")
        )

        # ----------------------------------------------------
        # LINK
        # ----------------------------------------------------

        article["link"] = clean_url(
            article.get("link")
        )

        cleaned_articles.append(article)

    return cleaned_articles


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
# HELPER TANGGAL
# ============================================================

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

        if getattr(dt, "tzinfo", None):

            dt = dt.tz_convert(None)

        return dt.to_pydatetime()

    except Exception:

        return None


def article_datetime(item):

    dt = parse_date(
        item.get("published_date")
    )

    if dt is None:
        return datetime.datetime.min

    return dt


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

        st.success("👑 ADMIN")

        st.caption(
            "Akses penuh sistem"
        )

    else:

        st.info("👁️ VIEWER")

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
        value=clean_text(NAMA_SATKER),
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
            list(bulan_options.values()),
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
        placeholder=(
            "Contoh: Kejaksaan, tersangka, penyidikan..."
        ),
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
            filter_mode,
        )
    ):
        continue

    if bulan_dipilih != "Semua Bulan":

        dt = parse_date(
            article.get("published_date")
        )

        if not dt:
            continue

        month_number = next(
            num
            for num, name in bulan_options.items()
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

    q = clean_text(
        search_text
    ).lower().strip()

    searched = []

    for item in filtered:

        searchable_text = " ".join(
            [
                clean_text(
                    item.get("title", "")
                ),

                clean_text(
                    item.get("snippet", "")
                ),

                clean_text(
                    item.get("content", "")
                ),

                " ".join(
                    clean_list(
                        item.get(
                            "detected_keywords"
                        )
                    )
                ),

                " ".join(
                    clean_list(
                        item.get(
                            "satker_matches"
                        )
                    )
                ),
            ]
        ).lower()

        if q in searchable_text:

            searched.append(item)

    filtered = searched


# ============================================================
# SORTING
# ============================================================

filtered.sort(
    key=article_datetime,
    reverse=(
        sort_order
        == "Terbaru → Terlama"
    ),
)


# ============================================================
# KATEGORI
# ============================================================

negative = [
    x for x in filtered
    if clean_text(
        x.get("category", "")
    ) == "Negatif Kuat"
]

handling = [
    x for x in filtered
    if clean_text(
        x.get("category", "")
    ) == "Perlu Penanganan"
]

neutral = [
    x for x in filtered
    if clean_text(
        x.get("category", "")
    ) == "Netral"
]

positive = [
    x for x in filtered
    if clean_text(
        x.get("category", "")
    ) == "Positif"
]

priority = [
    x for x in filtered
    if clean_text(
        x.get("category", "")
    )
    in [
        "Negatif Kuat",
        "Perlu Penanganan",
    ]
]


# ============================================================
# KPI
# ============================================================

st.markdown(
    '<div class="section-title">📊 Ringkasan Monitoring</div>',
    unsafe_allow_html=True,
)

safe_sort_order = html.escape(
    clean_text(sort_order)
)

st.markdown(
    f"""
    <div class="section-description">
        Menampilkan <b>{len(filtered)}</b> artikel.
        Urutan: <b>{safe_sort_order}</b>
    </div>
    """,
    unsafe_allow_html=True,
)

kpi_cols = st.columns(5)

kpis = [
    ("🔴", "Negatif Kuat", len(negative)),
    ("🟠", "Perlu Penanganan", len(handling)),
    ("🟡", "Netral", len(neutral)),
    ("🟢", "Positif", len(positive)),
    ("🚨", "Prioritas", len(priority)),
]

for col, (
    icon,
    label,
    value,
) in zip(kpi_cols, kpis):

    with col:

        safe_label = html.escape(
            clean_text(label)
        )

        st.markdown(
            f"""
            <div class="kpi-card">

                <div class="kpi-icon">
                    {icon}
                </div>

                <div class="kpi-label">
                    {safe_label}
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
# ARTICLE RENDERER
# ============================================================

def render_article(item):

    category = clean_text(
        item.get(
            "category",
            "Netral",
        )
    )

    priority_value = clean_text(
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

    title = clean_text(
        item.get(
            "title",
            "-",
        )
    )

    snippet = clean_text(
        item.get(
            "snippet",
            "",
        )
    )

    published_date = clean_text(
        item.get(
            "published_date",
            "-",
        )
    )

    keywords = clean_list(
        item.get(
            "detected_keywords"
        )
    )

    strong_context = clean_list(
        item.get(
            "strong_context"
        )
    )

    handling_context = clean_list(
        item.get(
            "handling_context"
        )
    )

    satker = clean_list(
        item.get(
            "satker_matches"
        )
    )

    article_link = clean_url(
        item.get("link")
    )

    # --------------------------------------------------------
    # KATEGORI
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # ARTICLE CONTAINER
    # --------------------------------------------------------

    with st.container(border=True):

        # ----------------------------------------------------
        # JUDUL
        # ----------------------------------------------------

        if title:

            st.markdown(
                f"### {icon} {title}"
            )

        else:

            st.markdown(
                f"### {icon} Tanpa Judul"
            )


        # ----------------------------------------------------
        # BADGES
        # ----------------------------------------------------

        safe_category = html.escape(
            category
        )

        safe_priority = html.escape(
            priority_value
        )

        badge_html = (
            f'<span class="badge {category_class}">'
            f'{safe_category}'
            f'</span>'

            f'<span class="badge badge-gray">'
            f'Prioritas: {safe_priority}'
            f'</span>'

            f'<span class="badge badge-gray">'
            f'Negative: {html.escape(str(negative_score))}'
            f'</span>'

            f'<span class="badge badge-gray">'
            f'Handling: {html.escape(str(handling_score))}'
            f'</span>'
        )

        st.markdown(
            badge_html,
            unsafe_allow_html=True,
        )


        # ----------------------------------------------------
        # TANGGAL
        # ----------------------------------------------------

        st.caption(
            f"📅 {published_date}"
        )


        # ----------------------------------------------------
        # SNIPPET
        # ----------------------------------------------------

        if snippet:

            st.markdown(
                "**📰 Ringkasan**"
            )

            # st.write digunakan agar data tidak
            # diproses sebagai HTML
            st.write(
                snippet
            )


        # ----------------------------------------------------
        # KEYWORDS
        # ----------------------------------------------------

        if keywords:

            st.markdown(
                "**🔎 Indikator**"
            )

            keyword_cols = st.columns(
                min(
                    max(
                        len(keywords[:12]),
                        1,
                    ),
                    4,
                )
            )

            for index, keyword in enumerate(
                keywords[:12]
            ):

                with keyword_cols[
                    index % len(keyword_cols)
                ]:

                    st.caption(
                        f"• {keyword}"
                    )


        # ----------------------------------------------------
        # KONTEKS NEGATIF
        # ----------------------------------------------------

        if strong_context:

            st.warning(
                "⚠️ **Konteks Negatif Kuat:** "
                + ", ".join(
                    strong_context
                )
            )


        # ----------------------------------------------------
        # KONTEKS PENANGANAN
        # ----------------------------------------------------

        if handling_context:

            st.info(
                "📌 **Konteks Penanganan:** "
                + ", ".join(
                    handling_context
                )
            )


        # ----------------------------------------------------
        # SATKER
        # ----------------------------------------------------

        if satker:

            st.caption(
                "🏢 Satker: "
                + ", ".join(
                    satker
                )
            )


        # ----------------------------------------------------
        # LINK
        # ----------------------------------------------------

        if article_link:

            st.link_button(
                "🔗 Buka Artikel",
                article_link,
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
# HELPER LIST
# ============================================================

def render_article_list(
    article_list,
    empty_message,
):

    if article_list:

        for item in article_list:

            render_article(item)

    else:

        st.info(
            empty_message
        )


# ============================================================
# PRIORITAS
# ============================================================

with tab_priority:

    st.markdown(
        '<div class="section-title">'
        '🚨 Artikel Prioritas Review'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="section-description">'
        'Artikel Negatif Kuat dan Perlu Penanganan '
        'yang membutuhkan perhatian lebih lanjut.'
        '</div>',
        unsafe_allow_html=True,
    )

    render_article_list(
        priority,
        "Tidak ada artikel prioritas.",
    )


# ============================================================
# NEGATIF
# ============================================================

with tab_negative:

    st.markdown(
        '<div class="section-title">'
        '🔴 Negatif Kuat'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="section-description">'
        'Pemberitaan yang terindikasi memiliki '
        'dampak negatif kuat terhadap satker.'
        '</div>',
        unsafe_allow_html=True,
    )

    render_article_list(
        negative,
        "Tidak ada artikel Negatif Kuat.",
    )


# ============================================================
# HANDLING
# ============================================================

with tab_handling:

    st.markdown(
        '<div class="section-title">'
        '🟠 Perlu Penanganan'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="section-description">'
        'Pemberitaan yang perlu dipantau '
        'atau diverifikasi lebih lanjut.'
        '</div>',
        unsafe_allow_html=True,
    )

    render_article_list(
        handling,
        "Tidak ada artikel Perlu Penanganan.",
    )


# ============================================================
# NETRAL
# ============================================================

with tab_neutral:

    st.markdown(
        '<div class="section-title">'
        '🟡 Netral'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="section-description">'
        'Pemberitaan yang tidak menunjukkan '
        'indikasi negatif kuat atau penanganan khusus.'
        '</div>',
        unsafe_allow_html=True,
    )

    render_article_list(
        neutral,
        "Tidak ada artikel Netral.",
    )


# ============================================================
# POSITIF
# ============================================================

with tab_positive:

    st.markdown(
        '<div class="section-title">'
        '🟢 Positif'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="section-description">'
        'Pemberitaan positif, keberhasilan penegakan hukum, '
        'kegiatan resmi, dan aktivitas kelembagaan.'
        '</div>',
        unsafe_allow_html=True,
    )

    render_article_list(
        positive,
        "Tidak ada artikel Positif.",
    )


# ============================================================
# ANALISIS
# ============================================================

with tab_analytics:

    st.markdown(
        '<div class="section-title">'
        '📊 Analisis Sentimen & Tren'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="section-description">'
        'Analisis distribusi kategori dan tren pemberitaan '
        'berdasarkan data yang sedang difilter.'
        '</div>',
        unsafe_allow_html=True,
    )

    if filtered:

        df = pd.DataFrame(
            filtered
        )

        col_chart1, col_chart2 = st.columns(2)


        # ----------------------------------------------------
        # PIE
        # ----------------------------------------------------

        with col_chart1:

            if "category" in df.columns:

                cat_counts = (
                    df["category"]
                    .fillna("Netral")
                    .astype(str)
                    .map(clean_text)
                    .value_counts()
                    .reset_index()
                )

                cat_counts.columns = [
                    "Kategori",
                    "Jumlah",
                ]

                fig_pie = px.pie(
                    cat_counts,
                    names="Kategori",
                    values="Jumlah",
                    title="Proporsi Kategori Pemberitaan",
                    hole=0.45,
                )

                fig_pie.update_layout(
                    margin=dict(
                        l=10,
                        r=10,
                        t=50,
                        b=10,
                    )
                )

                st.plotly_chart(
                    fig_pie,
                    use_container_width=True,
                )


        # ----------------------------------------------------
        # TREND
        # ----------------------------------------------------

        with col_chart2:

            if "published_date" in df.columns:

                df["date_parsed"] = (
                    df["published_date"]
                    .apply(parse_date)
                )

                df_valid_dates = (
                    df.dropna(
                        subset=["date_parsed"]
                    )
                    .copy()
                )

                if not df_valid_dates.empty:

                    df_valid_dates[
                        "date_only"
                    ] = (
                        df_valid_dates[
                            "date_parsed"
                        ]
                        .dt.date
                    )

                    timeline = (
                        df_valid_dates
                        .groupby("date_only")
                        .size()
                        .reset_index(
                            name="Jumlah"
                        )
                        .sort_values(
                            "date_only"
                        )
                    )

                    fig_line = px.line(
                        timeline,
                        x="date_only",
                        y="Jumlah",
                        title="Tren Volume Pemberitaan",
                        markers=True,
                    )

                    fig_line.update_layout(
                        margin=dict(
                            l=10,
                            r=10,
                            t=50,
                            b=10,
                        )
                    )

                    st.plotly_chart(
                        fig_line,
                        use_container_width=True,
                    )

    else:

        st.info(
            "Tidak ada data untuk ditampilkan "
            "pada grafik analisis."
        )


# ============================================================
# LOG ADMIN
# ============================================================

if IS_ADMIN and tab_logs is not None:

    with tab_logs:

        st.markdown(
            '<div class="section-title">'
            '📜 Log Riwayat Patroli'
            '</div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            '<div class="section-description">'
            'Riwayat proses patroli otomatis '
            'dan klasifikasi artikel.'
            '</div>',
            unsafe_allow_html=True,
        )

        if logs:

            df_logs = pd.DataFrame(
                logs
            )

            # Sanitasi kolom string pada log
            for column in df_logs.columns:

                if (
                    df_logs[column].dtype
                    == "object"
                ):

                    df_logs[column] = (
                        df_logs[column]
                        .apply(clean_text)
                    )

            st.dataframe(
                df_logs,
                use_container_width=True,
                hide_index=True,
            )

        else:

            st.info(
                "Tidak ada log eksekusi yang tersimpan."
            )


# ============================================================
# FOOTER
# ============================================================

st.divider()

safe_footer_satker = html.escape(
    clean_text(NAMA_SATKER)
)

safe_footer_user = html.escape(
    CURRENT_USERNAME
)

safe_footer_role = html.escape(
    CURRENT_ROLE.upper()
)

st.markdown(
    f"""
    <div style="
        text-align:center;
        color:#94a3b8;
        font-size:11px;
        line-height:1.7;
        padding:15px 0;
    ">

        🛡️ <b>Patroli Siber 2026</b><br>

        Sistem merupakan alat bantu monitoring dan
        klasifikasi awal.<br>

        Artikel <b>Negatif Kuat</b> dan
        <b>Perlu Penanganan</b> tetap perlu diverifikasi
        terhadap isi, sumber, dan fakta.<br><br>

        {safe_footer_satker}
        • Login: {safe_footer_user}
        ({safe_footer_role})

    </div>
    """,
    unsafe_allow_html=True,
)
