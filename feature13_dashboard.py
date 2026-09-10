import os
import json
import re
from datetime import datetime

import pandas as pd
import streamlit as st

try:
    from supabase import create_client
except Exception:
    create_client = None

try:
    import folium
    from folium.plugins import HeatMap
    from streamlit_folium import st_folium
except Exception:
    folium = None
    HeatMap = None
    st_folium = None

TABLE = "deli_serdang_location_articles"
TARGET_YEAR = 2026

# Approximate district-center coordinates for visualization only.
# They are intentionally treated as map anchors, not article-level coordinates.
DISTRICT_COORDS = {
    "bangun purba": (3.3667, 98.5833),
    "batang kuis": (3.6167, 98.8500),
    "sibiru-biru": (3.4333, 98.6500),
    "deli tua": (3.5000, 98.6667),
    "galang": (3.5000, 98.7833),
    "gunung meriah": (3.5667, 98.7000),
    "hamparan perak": (3.6833, 98.6000),
    "kutalimbaru": (3.5000, 98.5167),
    "labuhan deli": (3.7167, 98.6667),
    "lubuk pakam": (3.5667, 98.8667),
    "namorambe": (3.4833, 98.6500),
    "pagar merbau": (3.6167, 98.8500),
    "pancur batu": (3.5000, 98.5667),
    "pantai labu": (3.6000, 98.9500),
    "patumbak": (3.5000, 98.7000),
    "percut sei tuan": (3.6500, 98.7500),
    "sibolangit": (3.3500, 98.5833),
    "stm hilir": (3.5333, 98.7667),
    "stm hulu": (3.4667, 98.7500),
    "sunggal": (3.5833, 98.6000),
    "tanjung morawa": (3.5333, 98.7833),
}

AMBIGUOUS = {"bangun purba", "galang", "gunung meriah", "deli tua"}
REVIEW_IDS = {4284, 4292, 4356, 4358, 4523}


def norm(x):
    return re.sub(r"\s+", " ", str(x or "").strip().lower())


def get_client():
    if create_client is None:
        raise RuntimeError("supabase belum terpasang")
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL dan SUPABASE_SERVICE_ROLE_KEY/SUPABASE_KEY wajib diisi")
    return create_client(url, key)


def load_rows():
    client = get_client()
    rows = []
    offset = 0
    page = 1000
    while True:
        res = client.table(TABLE).select("*").range(offset, offset + page - 1).execute()
        batch = res.data or []
        rows.extend(batch)
        if len(batch) < page:
            break
        offset += page
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    if "published_date" in df:
        df["published_date"] = pd.to_datetime(df["published_date"], errors="coerce")
    if "matched_location_keywords" in df:
        df["matched_location_keywords"] = df["matched_location_keywords"].apply(parse_keywords)
    return df


def parse_keywords(value):
    if isinstance(value, list):
        return [norm(x) for x in value if norm(x)]
    if isinstance(value, str):
        s = value.strip()
        try:
            obj = json.loads(s.replace("'", '"'))
            if isinstance(obj, list):
                return [norm(x) for x in obj if norm(x)]
        except Exception:
            pass
        return [norm(x) for x in re.split(r"[,;|]", s) if norm(x)]
    return []


def clean_text(text):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text


def first_sentence(text, limit=600):
    text = clean_text(text)
    if not text:
        return ""
    m = re.split(r"(?<=[.!?])\s+", text)
    return " ".join(m[:3])[:limit]


def generate_lapinsus(row):
    title = clean_text(row.get("title"))
    content = clean_text(row.get("content"))
    source = clean_text(row.get("source") or row.get("publisher"))
    link = clean_text(row.get("link"))
    date = row.get("published_date")
    if pd.notna(date):
        date_str = pd.Timestamp(date).strftime("%d-%m-%Y")
    else:
        date_str = "Tidak tersedia"
    keywords = parse_keywords(row.get("matched_location_keywords"))
    valid = bool(row.get("location_context_valid"))

    return f"""LAPORAN INFORMASI KHUSUS (LAPINSUS)\n\nI. SUMBER INFORMASI\nMedia/Sumber : {source or 'Tidak tersedia'}\nTanggal      : {date_str}\nTautan       : {link or 'Tidak tersedia'}\n\nII. JUDUL INFORMASI\n{title or 'Tidak tersedia'}\n\nIII. LOKASI TERKAIT\nKabupaten Deli Serdang\nKata kunci lokasi terdeteksi: {', '.join(keywords) if keywords else 'Tidak tersedia'}\nValidasi konteks lokasi: {'VALID' if valid else 'REVIEW/INVALID'}\n\nIV. RINGKASAN INFORMASI\n{first_sentence(content) or 'Isi artikel tidak tersedia.'}\n\nV. URAIAN\n{content[:5000] if content else 'Isi artikel tidak tersedia.'}\n\nVI. ANALISIS AWAL\nInformasi ini berasal dari artikel yang masuk ke pipeline discovery lokasi Deli Serdang. Analisis substantif, identifikasi pihak, kronologi, dan penilaian risiko harus diverifikasi terhadap sumber primer sebelum digunakan sebagai bahan kedinasan.\n\nVII. REKOMENDASI TINDAK LANJUT\n1. Verifikasi artikel dan sumber primer.\n2. Verifikasi lokasi, waktu, pihak terkait, dan kronologi.\n3. Lakukan pendalaman apabila terdapat indikasi yang relevan dengan kewenangan satuan kerja.\n4. Simpan bukti sumber dan dokumentasi verifikasi.\n\nCatatan: Draft ini adalah bahan awal otomatis, bukan produk intelijen final.\n"""


def build_map(df):
    if folium is None or HeatMap is None or st_folium is None:
        st.warning("Komponen peta belum terpasang. Install requirements terlebih dahulu.")
        return
    points = []
    for _, row in df.iterrows():
        kws = parse_keywords(row.get("matched_location_keywords"))
        coords = None
        for kw in kws:
            if kw in DISTRICT_COORDS:
                coords = DISTRICT_COORDS[kw]
                break
        if coords:
            points.append([coords[0], coords[1], 1.0])
    m = folium.Map(location=[3.56, 98.72], zoom_start=10, tiles="OpenStreetMap")
    if points:
        HeatMap(points, radius=22, blur=18, min_opacity=0.25).add_to(m)
    st_folium(m, width=None, height=560)


st.set_page_config(page_title="Feature #13 — Deli Serdang Intelligence", layout="wide")
st.title("Feature #13 — Deli Serdang Intelligence")
st.caption("Read-only dashboard • source: deli_serdang_location_articles • target year 2026")

if "df" not in st.session_state:
    st.session_state.df = None

if st.button("Refresh data") or st.session_state.df is None:
    try:
        st.session_state.df = load_rows()
    except Exception as e:
        st.error(f"Gagal mengambil data Supabase: {e}")
        st.stop()

df = st.session_state.df.copy()
if df.empty:
    st.warning("Tidak ada data.")
    st.stop()

# Safety filter: this UI never displays non-target-year rows if they somehow exist.
df = df[pd.to_datetime(df.get("published_date"), errors="coerce").dt.year.eq(TARGET_YEAR) | df.get("published_date").isna()]

all_keywords = sorted({kw for kws in df["matched_location_keywords"] for kw in kws}) if "matched_location_keywords" in df else []
col1, col2, col3, col4 = st.columns(4)
col1.metric("Articles", len(df))
col2.metric("Valid", int(df["location_context_valid"].fillna(False).sum()))
col3.metric("Review IDs", len([x for x in REVIEW_IDS if x in set(df.get("id", []))]))
col4.metric("Keywords", len(all_keywords))

f1, f2, f3 = st.columns(3)
with f1:
    selected_kw = st.multiselect("Location", all_keywords)
with f2:
    status = st.selectbox("Context", ["ALL", "VALID", "INVALID/REVIEW"])
with f3:
    query = st.text_input("Search title/content")

filtered = df.copy()
if selected_kw:
    filtered = filtered[filtered["matched_location_keywords"].apply(lambda xs: bool(set(selected_kw) & set(xs)))]
if status == "VALID":
    filtered = filtered[filtered["location_context_valid"].fillna(False)]
elif status == "INVALID/REVIEW":
    filtered = filtered[~filtered["location_context_valid"].fillna(False)]
if query:
    q = norm(query)
    mask = filtered["title"].fillna("").map(norm).str.contains(q, regex=False) | filtered["content"].fillna("").map(norm).str.contains(q, regex=False)
    filtered = filtered[mask]

st.subheader(f"Daftar Artikel ({len(filtered)})")
display_cols = [c for c in ["id", "published_date", "title", "source", "location_context_valid", "matched_location_keywords", "link"] if c in filtered.columns]
st.dataframe(filtered[display_cols], use_container_width=True, hide_index=True)

st.subheader("Heatmap Isu / Lokasi")
st.info("Heatmap memakai titik jangkar tingkat kecamatan dari keyword lokasi. Ini bukan koordinat kejadian artikel secara presisi.")
build_map(filtered)

st.subheader("Generate LAPINSUS Draft")
if "id" not in filtered.columns:
    st.error("Kolom id tidak tersedia.")
else:
    options = filtered["id"].tolist()
    if options:
        selected_id = st.selectbox("Pilih artikel", options)
        row = filtered[filtered["id"] == selected_id].iloc[0]
        st.write(f"**{row.get('title', '')}**")
        if selected_id in REVIEW_IDS:
            st.warning("Artikel ini termasuk REVIEW. Draft tetap dapat dibuat sebagai bahan awal, tetapi wajib diverifikasi.")
        draft = generate_lapinsus(row)
        st.download_button(
            "Download LAPINSUS TXT",
            data=draft.encode("utf-8"),
            file_name=f"lapinsus_feature13_{selected_id}.txt",
            mime="text/plain",
        )
        st.text_area("Preview", draft, height=600)
    else:
        st.info("Tidak ada artikel sesuai filter.")
