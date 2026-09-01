import datetime
import os
from typing import Any, Dict, List, Optional

import pandas as pd
import plotly.express as px
import streamlit as st
import re
import html



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

try:
    TAHUN_TARGET = int(
        os.getenv("TAHUN_TARGET", "2026")
    )
except (TypeError, ValueError):
    TAHUN_TARGET = 2026


# ============================================================
# SESSION STATE
# ============================================================

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "username" not in st.session_state:
    st.session_state.username = ""

if "role" not in st.session_state:
    st.session_state.role = ""

def clean_html_text(value):
    """
    Membersihkan HTML dari teks yang berasal dari database/sumber berita.

    Contoh:
        <a href="https://...">Judul Berita</a>
        <font color="#6f6f6f">Media Online</font>

    Menjadi:
        Judul Berita Media Online
    """

    if value is None:
        return ""

    # Jika list, bersihkan setiap item
    if isinstance(value, list):
        cleaned = []

        for item in value:
            text = clean_html_text(item)

            if text:
                cleaned.append(text)

        return cleaned

    text = str(value)

    # Decode HTML entity:
    # &amp; -> &
    # &quot; -> "
    # &nbsp; -> spasi
    text = html.unescape(text)

    # Hapus tag <script>...</script>
    text = re.sub(
        r"<script\b[^>]*>.*?</script>",
        " ",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Hapus tag <style>...</style>
    text = re.sub(
        r"<style\b[^>]*>.*?</style>",
        " ",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # <br>, <p>, </p>, </div>, dll -> spasi
    text = re.sub(
        r"<[^>]+>",
        " ",
        text,
        flags=re.IGNORECASE,
    )

    # Hapus sisa pola HTML entity
    text = re.sub(
        r"&(?:[a-zA-Z][a-zA-Z0-9]+|#\d+|#x[0-9a-fA-F]+);",
        " ",
        text,
    )

    # Normalisasi whitespace
    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()
    
# ============================================================
# FUNGSI AUTHENTICATION
# ============================================================

def get_users() -> Dict[str, Dict[str, str]]:
    """
    Membaca daftar pengguna dari st.secrets.

    Format secrets yang didukung:

    [users.admin]
    username = "admin"
    password = "password"
    role = "admin"

    [users.viewer]
    username = "viewer"
    password = "password"
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
    """Memeriksa username dan password."""

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
# HALAMAN LOGIN
# ============================================================

def show_login_page() -> None:
    """Menampilkan halaman login."""

    st.title("🛡️ Patroli Siber")

    st.subheader(
        "Sistem Monitoring Pemberitaan"
    )

    st.caption(
        f"{NAMA_SATKER} • Tahun {TAHUN_TARGET}"
    )

    st.divider()

    left, center, right = st.columns(
        [1, 1.4, 1]
    )

    with center:

        with st.container(border=True):

            st.header("🔐 Login Sistem")

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

                    if (
                        not username
                        or not password
                    ):
                        st.error(
                            "Username dan password wajib diisi."
                        )
                        return

                    user = authenticate(
                        username,
                        password,
                    )

                    if user is None:
                        st.error(
                            "❌ Username atau password salah."
                        )
                        return

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
        "Sistem Internal • "
        f"{NAMA_SATKER} • "
        f"Tahun {TAHUN_TARGET}"
    )


# ============================================================
# HELPER DATA
# ============================================================

def parse_date(
    value: Any,
) -> Optional[datetime.datetime]:
    """
    Mengubah nilai tanggal menjadi datetime.
    Aman terhadap nilai kosong dan format tidak valid.
    """

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

            if pd.isna(dt):
                return None

            if isinstance(dt, pd.Timestamp):
                if dt.tzinfo is not None:
                    dt = dt.tz_convert(None)

                dt = dt.to_pydatetime()

        except Exception:
            return None

    return dt


def safe_list(value: Any) -> List[str]:
    """
    Memastikan nilai menjadi list string.
    """

    if value is None:
        return []

    if isinstance(value, list):
        return [
            str(item)
            for item in value
            if item is not None
        ]

    if isinstance(value, tuple):
        return [
            str(item)
            for item in value
            if item is not None
        ]

    if isinstance(value, set):
        return [
            str(item)
            for item in value
            if item is not None
        ]

    if isinstance(value, str):

        value = value.strip()

        if not value:
            return []

        return [value]

    return [str(value)]


def get_article_date(
    article: Dict[str, Any],
) -> Optional[datetime.datetime]:
    """Mengambil tanggal artikel."""

    return parse_date(
        article.get("published_date")
    )


def filter_date(
    article: Dict[str, Any],
    mode: str,
) -> bool:
    """
    Memfilter artikel berdasarkan periode.
    """

    dt = get_article_date(article)

    if dt is None:
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

    if mode == f"Tahun {TAHUN_TARGET}":

        return (
            dt.year == TAHUN_TARGET
            and dt <= now
        )

    return True

def clean_list(value):
    """
    Membersihkan semua item dalam list dari HTML.
    """

    if not value:
        return []

    if not isinstance(value, list):
        value = [value]

    result = []

    for item in value:

        cleaned = clean_html_text(item)

        if cleaned:
            result.append(cleaned)

    return result

def article_matches_search(
    article: Dict[str, Any],
    query: str,
) -> bool:
    """
    Mencari kata pada judul, snippet, content,
    indikator, dan satker.
    """

    if not query:
        return True

    q = query.lower().strip()

    keywords = clean_list(
        item.get("detected_keywords")
    )


    satker = clean_list(
        item.get("satker_matches")
    )

    searchable_text = " ".join(
        [
            str(article.get("title", "")),
            str(article.get("snippet", "")),
            str(article.get("content", "")),
            keywords,
            satker,
            str(article.get("source", "")),
        ]
    ).lower()

    return q in searchable_text


def article_datetime(
    article: Dict[str, Any],
) -> datetime.datetime:
    """
    Nilai tanggal untuk sorting.
    """

    dt = get_article_date(article)

    if dt is None:
        return datetime.datetime.min

    return dt


# ============================================================
# LOAD DATA
# ============================================================

@st.cache_data(ttl=60)
def load_articles() -> List[Dict[str, Any]]:
    """
    Mengambil seluruh artikel dari database.py.
    """

    try:
        data = get_all_articles()

        if data is None:
            return []

        if isinstance(data, list):
            return data

        return list(data)

    except Exception as exc:
        st.error(
            f"Gagal mengambil data artikel dari Supabase: {exc}"
        )
        return []


@st.cache_data(ttl=30)
def load_logs() -> List[Dict[str, Any]]:
    """
    Mengambil log patroli.
    """

    try:
        data = get_run_logs(300)

        if data is None:
            return []

        if isinstance(data, list):
            return data

        return list(data)

    except Exception:
        return []


# ============================================================
# SIDEBAR
# ============================================================

def show_sidebar(
    username: str,
    role: str,
) -> None:

    is_admin = role == "admin"

    with st.sidebar:

        st.title("🛡️ Patroli Siber")

        st.caption(
            f"Dashboard Monitoring {TAHUN_TARGET}"
        )

        st.divider()

        st.subheader("👤 Pengguna")

        st.write(
            f"**{username}**"
        )

        if is_admin:

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

        st.subheader(
            "ℹ️ Informasi Sistem"
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
        )

        telegram_chat_id = os.getenv(
            "TELEGRAM_CHAT_ID",
            "",
        )

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

        if is_admin:

            st.divider()

            st.subheader(
                "⚙️ Administrasi"
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
            "pengambilan dan klasifikasi berita "
            "melalui GitHub Actions."
        )


# ============================================================
# HEADER
# ============================================================

def show_header() -> None:

    st.title(
        f"🛡️ Patroli Siber {TAHUN_TARGET}"
    )

    st.subheader(
        "Sistem Monitoring dan Klasifikasi Awal Pemberitaan"
    )

    st.caption(
        f"{NAMA_SATKER} • "
        "📡 Monitoring Aktif • "
        f"📅 Tahun {TAHUN_TARGET}"
    )

    st.divider()


# ============================================================
# FILTER
# ============================================================

def show_filters(
    articles: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:

    st.header(
        "🔎 Filter & Pengurutan"
    )

    st.caption(
        "Saring pemberitaan berdasarkan periode, "
        "bulan, kata kunci, dan urutan tanggal."
    )

    with st.container(border=True):

        col1, col2, col3 = st.columns(3)

        with col1:

            filter_mode = st.selectbox(
                "📅 Periode",
                [
                    "24 jam terakhir",
                    "7 hari terakhir",
                    "1 bulan terakhir",
                    f"Tahun {TAHUN_TARGET}",
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
                f"🗓️ Bulan {TAHUN_TARGET}",
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
            "🔍 Pencarian",
            placeholder=(
                "Cari judul, indikator, satker, "
                "sumber, atau isi artikel..."
            ),
        )

    filtered: List[Dict[str, Any]] = []

    for article in articles:

        if (
            filter_mode != "Semua data"
            and not filter_date(
                article,
                filter_mode,
            )
        ):
            continue

        if (
            bulan_dipilih
            != "Semua Bulan"
        ):

            dt = get_article_date(article)

            if dt is None:
                continue

            month_number = next(
                (
                    number
                    for number, name
                    in bulan_options.items()
                    if name == bulan_dipilih
                ),
                0,
            )

            if (
                dt.year != TAHUN_TARGET
                or dt.month != month_number
            ):
                continue

        if not article_matches_search(
            article,
            search_text,
        ):
            continue

        filtered.append(article)

    filtered.sort(
        key=article_datetime,
        reverse=(
            sort_order
            == "Terbaru → Terlama"
        ),
    )

    return filtered


# ============================================================
# KATEGORI
# ============================================================

def split_categories(
    articles: List[Dict[str, Any]],
):

    negative = [
        article
        for article in articles
        if article.get("category")
        == "Negatif Kuat"
    ]

    handling = [
        article
        for article in articles
        if article.get("category")
        == "Perlu Penanganan"
    ]

    neutral = [
        article
        for article in articles
        if article.get("category")
        == "Netral"
    ]

    positive = [
        article
        for article in articles
        if article.get("category")
        == "Positif"
    ]

    priority = [
        article
        for article in articles
        if article.get("category")
        in {
            "Negatif Kuat",
            "Perlu Penanganan",
        }
    ]

    return (
        negative,
        handling,
        neutral,
        positive,
        priority,
    )


# ============================================================
# KPI
# ============================================================

def show_kpis(
    filtered: List[Dict[str, Any]],
) -> None:

    (
        negative,
        handling,
        neutral,
        positive,
        priority,
    ) = split_categories(filtered)

    st.header(
        "📊 Ringkasan Monitoring"
    )

    st.caption(
        f"Menampilkan {len(filtered)} artikel "
        "berdasarkan filter yang dipilih."
    )

    cols = st.columns(5)

    with cols[0]:
        st.metric(
            "🔴 Negatif Kuat",
            len(negative),
        )

    with cols[1]:
        st.metric(
            "🟠 Perlu Penanganan",
            len(handling),
        )

    with cols[2]:
        st.metric(
            "🟡 Netral",
            len(neutral),
        )

    with cols[3]:
        st.metric(
            "🟢 Positif",
            len(positive),
        )

    with cols[4]:
        st.metric(
            "🚨 Prioritas",
            len(priority),
        )

    st.divider()


# ============================================================
# ARTICLE RENDERER
# ============================================================

def render_article(
    item: Dict[str, Any],
) -> None:

    category = str(
        item.get(
            "category",
            "Netral",
        )
    )

    priority = str(
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

    title = str(
        item.get(
            "title",
            "-",
        )
    )

    snippet = str(
        item.get(
            "snippet",
            "",
        )
    )

    published_date = str(
        item.get(
            "published_date",
            "-",
        )
    )

    link = str(
        item.get(
            "link",
            "",
        )
    ).strip()

    if category == "Negatif Kuat":

        icon = "🔴"

    elif category == "Perlu Penanganan":

        icon = "🟠"

    elif category == "Positif":

        icon = "🟢"

    else:

        icon = "🟡"

    with st.container(border=True):

        st.subheader(
            f"{icon} {title}"
        )

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.write(
                f"**Kategori:** {category}"
            )

        with col2:
            st.write(
                f"**Prioritas:** {priority}"
            )

        with col3:
            st.write(
                f"**Negative Score:** {negative_score}"
            )

        with col4:
            st.write(
                f"**Handling Score:** {handling_score}"
            )

        st.caption(
            f"📅 {published_date}"
        )

        if snippet:
            st.write(snippet)

        keywords = safe_list(
            item.get(
                "detected_keywords"
            )
        )

        if keywords:

            st.write(
                "**🔎 Indikator:**"
            )

            st.write(
                ", ".join(
                    keywords[:15]
                )
            )

        strong_context = clean_html_text(
            item.get(
                "strong_context"
            )
        )

        context_html = ""

        if strong_context:
        
            context_html += (
                '<div class="info-box" style="margin-top:10px;">'
                "⚠️ <b>Konteks Negatif Kuat:</b> "
                + ", ".join(
                    html.escape(str(x))
                    for x in strong_context
                )
                + "</div>"
            )


        handling_context = clean_html_text(
            item.get(
                "handling_context"
            )
        )

        if handling_context:
        
            context_html += (
                '<div class="info-box" style="margin-top:10px;">'
                "📌 <b>Konteks Penanganan:</b> "
                + ", ".join(
                    html.escape(str(x))
                    for x in handling_context
                )
                + "</div>"
            )
        satker = clean_html_text(
            item.get(
                "satker_matches"
            )
        )

        if satker:

            st.caption(
                "🏢 Satker: "
                + ", ".join(satker)
            )

        if link:

            st.link_button(
                "🔗 Buka Artikel",
                link,
            )

    st.write("")


# ============================================================
# TAB ARTICLE LIST
# ============================================================

def show_article_list(
    articles: List[Dict[str, Any]],
    empty_message: str,
) -> None:

    if not articles:

        st.info(empty_message)
        return

    for article in articles:
        render_article(article)


# ============================================================
# ANALYTICS
# ============================================================

def show_analytics(
    filtered: List[Dict[str, Any]],
) -> None:

    st.header(
        "📊 Analisis Pemberitaan"
    )

    st.caption(
        "Visualisasi distribusi kategori "
        "dan tingkat prioritas."
    )

    (
        negative,
        handling,
        neutral,
        positive,
        priority,
    ) = split_categories(filtered)

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

    col1, col2 = st.columns(2)

    with col1:

        st.subheader(
            "Distribusi Kategori"
        )

        if chart_data["Jumlah"].sum() > 0:

            fig = px.pie(
                chart_data,
                names="Kategori",
                values="Jumlah",
                hole=0.5,
            )

            fig.update_layout(
                margin=dict(
                    l=10,
                    r=10,
                    t=20,
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
                "Belum ada data untuk ditampilkan."
            )

    with col2:

        st.subheader(
            "Distribusi Prioritas"
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
                        x
                        for x in filtered
                        if str(
                            x.get("priority", "")
                        ).upper()
                        == "KRITIS"
                    ]),
                    len([
                        x
                        for x in filtered
                        if str(
                            x.get("priority", "")
                        ).upper()
                        == "TINGGI"
                    ]),
                    len([
                        x
                        for x in filtered
                        if str(
                            x.get("priority", "")
                        ).upper()
                        == "SEDANG"
                    ]),
                    len([
                        x
                        for x in filtered
                        if str(
                            x.get("priority", "")
                        ).upper()
                        == "RENDAH"
                    ]),
                ],
            }
        )

        fig_priority = px.bar(
            priority_df,
            x="Prioritas",
            y="Jumlah",
            text="Jumlah",
        )

        fig_priority.update_layout(
            margin=dict(
                l=10,
                r=10,
                t=20,
                b=10,
            )
        )

        st.plotly_chart(
            fig_priority,
            use_container_width=True,
        )

    st.subheader(
        "📋 Rekapitulasi"
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

def show_logs(
    logs: List[Dict[str, Any]],
) -> None:

    st.header(
        "📜 Log Patroli"
    )

    st.caption(
        "Riwayat proses patroli otomatis "
        "dan klasifikasi artikel."
    )

    if not logs:

        st.info(
            "Belum ada log patroli."
        )
        return

    try:

        log_df = pd.DataFrame(logs)

        st.dataframe(
            log_df,
            use_container_width=True,
            hide_index=True,
        )

    except Exception as exc:

        st.error(
            f"Gagal menampilkan log: {exc}"
        )


# ============================================================
# FOOTER
# ============================================================

def show_footer(
    username: str,
    role: str,
) -> None:

    st.divider()

    st.caption(
        f"🛡️ Patroli Siber {TAHUN_TARGET}"
    )

    st.caption(
        "Sistem merupakan alat bantu monitoring "
        "dan klasifikasi awal. Artikel Negatif Kuat "
        "dan Perlu Penanganan tetap perlu diverifikasi "
        "terhadap isi, sumber, dan fakta."
    )

    st.caption(
        f"{NAMA_SATKER} • "
        f"Login: {username} "
        f"({role.upper()})"
    )


# ============================================================
# MAIN APPLICATION
# ============================================================

def main() -> None:

    # --------------------------------------------------------
    # LOGIN
    # --------------------------------------------------------

    if not st.session_state.logged_in:

        show_login_page()
        return

    # --------------------------------------------------------
    # USER
    # --------------------------------------------------------

    username = str(
        st.session_state.username
    )

    role = str(
        st.session_state.role
    ).lower()

    if role not in {
        "admin",
        "viewer",
    }:

        st.session_state.logged_in = False
        st.session_state.username = ""
        st.session_state.role = ""

        st.error(
            "Role pengguna tidak valid."
        )

        st.stop()

    is_admin = role == "admin"

    # --------------------------------------------------------
    # SIDEBAR
    # --------------------------------------------------------

    show_sidebar(
        username,
        role,
    )

    # --------------------------------------------------------
    # HEADER
    # --------------------------------------------------------

    show_header()

    # --------------------------------------------------------
    # DATA
    # --------------------------------------------------------

    articles = load_articles()

    if is_admin:
        logs = load_logs()
    else:
        logs = []

    # --------------------------------------------------------
    # STATUS DATABASE
    # --------------------------------------------------------

    st.caption(
        f"📚 Total artikel dari database: {len(articles)}"
    )

    # --------------------------------------------------------
    # FILTER
    # --------------------------------------------------------

    filtered = show_filters(
        articles
    )

    # --------------------------------------------------------
    # KPI
    # --------------------------------------------------------

    show_kpis(
        filtered
    )

    # --------------------------------------------------------
    # CATEGORY DATA
    # --------------------------------------------------------

    (
        negative,
        handling,
        neutral,
        positive,
        priority,
    ) = split_categories(
        filtered
    )

    # --------------------------------------------------------
    # TABS
    # --------------------------------------------------------

    if is_admin:

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

    # --------------------------------------------------------
    # PRIORITAS
    # --------------------------------------------------------

    with tab_priority:

        st.subheader(
            "🚨 Artikel Prioritas Review"
        )

        st.caption(
            "Artikel yang membutuhkan perhatian "
            "lebih lanjut."
        )

        show_article_list(
            priority,
            "Tidak ada artikel prioritas "
            "pada periode yang dipilih.",
        )

    # --------------------------------------------------------
    # NEGATIF KUAT
    # --------------------------------------------------------

    with tab_negative:

        st.subheader(
            "🔴 Negatif Kuat"
        )

        st.caption(
            "Pemberitaan yang terindikasi memiliki "
            "dampak negatif kuat terhadap satker "
            "dan perlu verifikasi."
        )

        show_article_list(
            negative,
            "Tidak ada artikel Negatif Kuat.",
        )

    # --------------------------------------------------------
    # PENANGANAN
    # --------------------------------------------------------

    with tab_handling:

        st.subheader(
            "🟠 Perlu Penanganan"
        )

        st.caption(
            "Pemberitaan yang perlu dipantau "
            "atau diverifikasi lebih lanjut."
        )

        show_article_list(
            handling,
            "Tidak ada artikel Perlu Penanganan.",
        )

    # --------------------------------------------------------
    # NETRAL
    # --------------------------------------------------------

    with tab_neutral:

        st.subheader(
            "🟡 Netral"
        )

        st.caption(
            "Pemberitaan yang tidak menunjukkan "
            "indikasi negatif kuat atau "
            "penanganan khusus."
        )

        show_article_list(
            neutral,
            "Tidak ada artikel Netral.",
        )

    # --------------------------------------------------------
    # POSITIF
    # --------------------------------------------------------

    with tab_positive:

        st.subheader(
            "🟢 Positif"
        )

        st.caption(
            "Pemberitaan positif, keberhasilan "
            "penegakan hukum, kegiatan resmi, "
            "dan aktivitas kelembagaan."
        )

        show_article_list(
            positive,
            "Tidak ada artikel Positif.",
        )

    # --------------------------------------------------------
    # ANALISIS
    # --------------------------------------------------------

    with tab_analytics:

        show_analytics(
            filtered
        )

    # --------------------------------------------------------
    # LOG ADMIN
    # --------------------------------------------------------

    if is_admin and tab_logs is not None:

        with tab_logs:

            show_logs(
                logs
            )

    # --------------------------------------------------------
    # FOOTER
    # --------------------------------------------------------

    show_footer(
        username,
        role,
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
