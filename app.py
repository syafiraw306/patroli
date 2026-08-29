import streamlit as st
import pandas as pd
from database import get_filtered_articles, clean_html

# Konfigurasi Halaman
st.set_page_config(
    page_title="Dashboard Patroli Siber 2026",
    page_icon="⚖️",
    layout="wide"
)

# Custom Styling (CSS dibungkus rapat dalam multiline string)
st.markdown("""
<style>
    .main-header {
        font-size: 2rem;
        font-weight: bold;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        color: #6c757d;
        margin-bottom: 1.5rem;
    }
    .badge-negatif {
        background-color: #ff4d4f;
        color: white;
        padding: 3px 8px;
        border-radius: 4px;
        font-weight: bold;
    }
    .badge-penanganan {
        background-color: #faad14;
        color: white;
        padding: 3px 8px;
        border-radius: 4px;
        font-weight: bold;
    }
    .badge-positif {
        background-color: #52c41a;
        color: white;
        padding: 3px 8px;
        border-radius: 4px;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# Judul Utama
st.markdown('<div class="main-header">⚖️ Dashboard Patroli Siber - Kejaksaan Negeri Deli Serdang</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Sistem Pemantauan dan Klasifikasi Media Berita Otomatis</div>', unsafe_allow_html=True)

# Sidebar Filter
st.sidebar.header("🔍 Filter Data")
category_filter = st.sidebar.selectbox("Kategori", ["Semua Kategori", "Negatif Kuat", "Perlu Penanganan", "Positif", "Netral"])
priority_filter = st.sidebar.selectbox("Prioritas", ["Semua Prioritas", "TINGGI", "SEDANG", "RENDAH"])
search_query = st.sidebar.text_input("Cari Judul Berita")

# Ambil data dari database
articles = get_filtered_articles(
    category=category_filter,
    priority=priority_filter,
    search_query=search_query
)

# Hitung statistik ringkas
total_art = len(articles)
neg_count = sum(1 for a in articles if a.get("category") == "Negatif Kuat")
hand_count = sum(1 for a in articles if a.get("category") == "Perlu Penanganan")
pos_count = sum(1 for a in articles if a.get("category") == "Positif")

# Tampilan KPI Ringkas
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Berita", total_art)
col2.metric("🔴 Negatif Kuat", neg_count)
col3.metric("🟡 Perlu Penanganan", hand_count)
col4.metric("🟢 Positif", pos_count)

st.markdown("---")

# Tampilan Utama Berita
if not articles:
    st.info("Tidak ada berita yang sesuai dengan filter.")
else:
    for art in articles:
        # Bersihkan sisa tag HTML dari judul dan konten
        clean_title = clean_html(art.get("title", "Tanpa Judul"))
        clean_content = clean_html(art.get("content", ""))
        
        category = art.get("category", "Netral")
        badge = "🔴" if category == "Negatif Kuat" else "🟡" if category == "Perlu Penanganan" else "🟢"
        
        with st.expander(f"{badge} {clean_title}"):
            st.write(f"**Kategori:** {category} | **Prioritas:** {art.get('priority', 'RENDAH')} | **Tanggal:** {art.get('published_date', '-')}")
            
            keywords = art.get("keywords")
            if keywords and isinstance(keywords, list):
                st.write(f"**Kata Kunci Terdeteksi:** {', '.join(keywords)}")
            
            # Tampilkan ringkasan konten yang bersih dari tag HTML
            preview_text = clean_content[:400] + ("..." if len(clean_content) > 400 else "")
            st.write(preview_text)
            
            st.markdown(f"[🔗 Baca Berita Selengkapnya]({art.get('url')})")
