import ast
import os
import re

import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium

from feature13_lapinsus_engine import (
    get_location_articles,
    build_lapinsus,
    make_pdf,
    mark_generated,
    clean_article_content,
    classify_issues,
    extract_issue_topics,
    get_article_source_text,
)

FEATURE13_TABLE = "deli_serdang_location_articles"
FEATURE13_YEAR = int(os.getenv("TAHUN_TARGET", "2026"))
FEATURE13_REVIEW_IDS = {4284, 4292, 4356, 4358, 4523}

# Approximate district anchors only; not incident-level geocoding.
FEATURE13_COORDS = {
    "bangun purba": (3.442, 98.775), "batang kuis": (3.601, 98.873),
    "sibiru-biru": (3.443, 98.682), "deli tua": (3.507, 98.675),
    "galang": (3.423, 98.718), "gunung meriah": (3.457, 98.590),
    "hamparan perak": (3.706, 98.623), "kutalimbaru": (3.449, 98.510),
    "labuhan deli": (3.719, 98.666), "lubuk pakam": (3.558, 98.862),
    "namorambe": (3.472, 98.676), "pagar merbau": (3.600, 98.874),
    "pancur batu": (3.469, 98.603), "pantai labu": (3.659, 98.935),
    "patumbak": (3.522, 98.715), "percut sei tuan": (3.625, 98.790),
    "sibolangit": (3.303, 98.554), "stm hilir": (3.508, 98.805),
    "stm hulu": (3.432, 98.756), "sunggal": (3.603, 98.616),
    "tanjung morawa": (3.523, 98.790),
}


def _f13_keywords(row):
    value = row.get("matched_location_keywords") or []
    if isinstance(value, str):
        try:
            value = ast.literal_eval(value)
        except Exception:
            value = [x.strip() for x in value.split(",") if x.strip()]
    return [str(x).strip().lower() for x in value if str(x).strip()]


@st.cache_data(ttl=60)
def load_feature13_articles():
    return get_location_articles(limit=1000)


def _article_text(row):
    return clean_article_content(row.get("content") or "")


@st.cache_data(ttl=1800, show_spinner=False)
def _cached_source_text(article_id, title, content, link, article_images):
    article = {
        "id": article_id,
        "title": title,
        "content": content,
        "link": link,
        "article_images": article_images or [],
    }
    return get_article_source_text(article)


def render_feature13_panel(is_admin=False):
    st.header("📍 Feature #13 — Deli Serdang Location Intelligence")
    st.caption("Location discovery → artikel wilayah → peta isu → LAPINSUS")

    articles = load_feature13_articles()
    articles = [
        a for a in articles
        if str(a.get("published_date", "")).startswith(str(FEATURE13_YEAR))
    ]

    valid = [a for a in articles if bool(a.get("location_context_valid"))]
    review = [a for a in articles if not bool(a.get("location_context_valid"))]

    c = st.columns(4)
    c[0].metric("Total artikel", len(articles))
    c[1].metric("Valid", len(valid))
    c[2].metric("Perlu review", len(review))
    c[3].metric("Tahun", FEATURE13_YEAR)

    f1, f2, f3 = st.columns(3)
    with f1:
        search = st.text_input("🔎 Cari artikel", key="f13_search")
    with f2:
        status = st.selectbox(
            "Konteks lokasi", ["SEMUA", "VALID", "PERLU REVIEW"], key="f13_status"
        )
    with f3:
        allkw = sorted({k for a in articles for k in _f13_keywords(a)})
        kw = st.selectbox(
            "Kecamatan / keyword", ["SEMUA"] + allkw, key="f13_kw"
        )

    filtered = []
    for a in articles:
        text = (
            str(a.get("title") or "")
            + " "
            + _article_text(a)
        ).lower()
        kws = _f13_keywords(a)
        if search and search.lower() not in text:
            continue
        if status == "VALID" and not a.get("location_context_valid"):
            continue
        if status == "PERLU REVIEW" and a.get("location_context_valid"):
            continue
        if kw != "SEMUA" and kw not in kws:
            continue
        filtered.append(a)

    st.write(f"Menampilkan **{len(filtered)}** artikel")

    tab_list, tab_map, tab_lap = st.tabs(
        ["📋 Artikel", "🗺️ Peta Isu", "📄 LAPINSUS"]
    )

    with tab_list:
        for a in filtered[:100]:
            with st.container(border=True):
                st.subheader(str(a.get("title") or "Tanpa judul"))
                st.write(
                    f"**Tanggal:** {a.get('published_date') or '-'}  | "
                    f"**Lokasi:** {', '.join(_f13_keywords(a)) or '-'}"
                )
                st.write(
                    f"**Status konteks:** "
                    f"{'VALID' if a.get('location_context_valid') else 'PERLU REVIEW'}"
                )
                if a.get("publisher") or a.get("source"):
                    st.caption(f"Sumber: {a.get('publisher') or a.get('source')}")
                if a.get("link"):
                    st.markdown(f"[Buka sumber artikel]({a['link']})")

                with st.expander("Lihat isi artikel"):
                    clean = _article_text(a)
                    if clean:
                        st.write(clean[:12000])
                    else:
                        st.info(
                            "Isi artikel belum tersedia pada data tersimpan. "
                            "Gunakan Buka sumber artikel untuk melihat pemberitaan asli."
                        )

    with tab_map:
        st.subheader("🗺️ Peta Isu per Kecamatan")
        st.caption(
            "Isu diambil dari judul/konten berita dan, bila konten tersimpan berupa wrapper Google News atau terlalu pendek, "
            "sistem mengambil ulang isi dari link sumber berita. Satu artikel dihitung sekali per kecamatan."
        )

        source_key = f"f13_issue_source_{FEATURE13_YEAR}"
        if source_key not in st.session_state:
            st.session_state[source_key] = True

        col_a, col_b = st.columns([1, 3])
        with col_a:
            analyze_source = st.button(
                "🔄 Analisis dari link berita",
                key="f13_analyze_source",
                help="Mengambil isi sumber berita jika konten tersimpan tidak cukup untuk klasifikasi isu.",
            )
        if analyze_source:
            st.session_state[source_key] = True
            st.cache_data.clear()

        issue_by_location = {}
        article_issue_rows = []
        for a in valid:
            base_text = _article_text(a)
            use_source = (
                st.session_state[source_key]
                and (
                    "news.google.com" in str(a.get("link") or "").lower()
                    or len(base_text) < 350
                )
            )
            if use_source:
                try:
                    grounded = _cached_source_text(
                        a.get("id"), str(a.get("title") or ""), str(a.get("content") or ""),
                        str(a.get("link") or ""), a.get("article_images") or [],
                    )
                    issue_text = grounded.get("text") or base_text
                except Exception:
                    issue_text = base_text
            else:
                issue_text = base_text

            issues = extract_issue_topics(str(a.get("title") or ""), issue_text)
            locations = [k for k in _f13_keywords(a) if k in FEATURE13_COORDS]
            for k in locations:
                if issues:
                    issue_by_location.setdefault(k, set()).update(issues)
                for issue in issues:
                    article_issue_rows.append({
                        "Lokasi": k.title(),
                        "Isu": issue,
                        "Artikel": str(a.get("title") or "Tanpa judul"),
                        "ID": a.get("id"),
                    })

        if issue_by_location:
            center = (3.55, 98.73)
            m = folium.Map(location=center, zoom_start=10)
            max_issues = max(len(v) for v in issue_by_location.values()) or 1

            for k, issues in sorted(
                issue_by_location.items(),
                key=lambda x: (-len(x[1]), x[0]),
            ):
                lat, lon = FEATURE13_COORDS[k]
                issue_list = sorted(issues)
                n = len(issue_list)
                radius = 9 + 10 * (n / max_issues)
                popup_html = (
                    f"<b>{k.title()}</b><br>"
                    f"<b>Isu terdeteksi ({n}):</b><br>"
                    + "<br>".join(f"• {x}" for x in issue_list)
                )
                folium.CircleMarker(
                    [lat, lon],
                    radius=radius,
                    tooltip=f"{k.title()}: {n} jenis isu",
                    popup=folium.Popup(popup_html, max_width=420),
                    fill=True,
                ).add_to(m)

            st_folium(m, width=None, height=520, key="f13_map")

            table = [
                {
                    "Kecamatan": k.title(),
                    "Jumlah Isu": len(issues),
                    "Isu": ", ".join(sorted(issues)),
                }
                for k, issues in sorted(
                    issue_by_location.items(),
                    key=lambda x: (-len(x[1]), x[0]),
                )
            ]
            st.dataframe(
                pd.DataFrame(table),
                width="stretch",
                hide_index=True,
            )

            st.markdown("**Daftar isu berdasarkan artikel sumber:**")
            if article_issue_rows:
                issue_df = pd.DataFrame(article_issue_rows).drop_duplicates(
                    subset=["Lokasi", "Isu", "ID"]
                )
                st.dataframe(
                    issue_df[["Lokasi", "Isu", "Artikel", "ID"]],
                    width="stretch",
                    hide_index=True,
                )
            st.info(
                "Peta menampilkan JENIS ISU spesifik yang ditemukan pada berita, misalnya Narkotika, "
                "Penganiayaan, Pencurian, Korupsi, Infrastruktur, dan Kesehatan. "
                "Satu artikel tidak dihitung sebagai jumlah artikel pada marker. Koordinat merupakan anchor kecamatan perkiraan."
            )
        else:
            st.info("Belum ada data VALID yang dapat dipetakan.")

    with tab_lap:
        st.subheader("📄 LAPINSUS — Daftar Artikel")
        st.caption(
            "Setiap artikel VALID ditampilkan sebagai card. Generate hanya dilakukan untuk artikel yang tombolnya ditekan."
        )
        choices = [a for a in filtered if a.get("location_context_valid")]
        if not choices:
            st.info("Tidak ada artikel VALID pada filter saat ini.")
        else:
            page_size = st.selectbox(
                "Jumlah card per halaman", [10, 20, 50], index=1, key="f13_lap_page_size"
            )
            total_pages = max(1, (len(choices) + page_size - 1) // page_size)
            page_no = st.number_input(
                "Halaman", min_value=1, max_value=total_pages, value=1, step=1, key="f13_lap_page_no"
            )
            start_idx = (int(page_no) - 1) * page_size
            page_choices = choices[start_idx:start_idx + page_size]
            st.caption(f"Menampilkan card {start_idx + 1}–{min(start_idx + page_size, len(choices))} dari {len(choices)} artikel VALID.")

            for a in page_choices:
                article_id = a.get("id")
                title = str(a.get("title") or "Tanpa judul")
                locations = ", ".join(_f13_keywords(a)) or "-"
                source = a.get("publisher") or a.get("source") or "-"
                issue_labels = extract_issue_topics(title, _article_text(a))
                status_label = str(a.get("lapinsus_status") or "BELUM DIGENERATE")

                with st.container(border=True):
                    h1, h2 = st.columns([5, 1])
                    with h1:
                        st.markdown(f"### #{article_id} — {title}")
                    with h2:
                        st.caption(status_label)
                    st.write(
                        f"**Tanggal:** {a.get('published_date') or '-'}  | "
                        f"**Kecamatan:** {locations}"
                    )
                    st.write(f"**Sumber:** {source}")
                    st.write("**Isu:** " + ", ".join(issue_labels))
                    if a.get("link"):
                        st.markdown(f"[🔗 Buka sumber artikel]({a['link']})")

                    if is_admin:
                        if st.button(
                            "📄 Generate LAPINSUS",
                            key=f"f13_generate_card_{article_id}",
                            width="stretch",
                        ):
                            with st.spinner("Mengambil sumber artikel dan membuat LAPINSUS..."):
                                try:
                                    data = build_lapinsus(a)
                                    pdf = make_pdf(data)
                                    # Explicit button click is the only persistence path.
                                    mark_generated(article_id, pdf, data)
                                    st.session_state[f"f13_pdf_{article_id}"] = pdf
                                    st.session_state[f"f13_data_{article_id}"] = data
                                    st.success("LAPINSUS berhasil dibuat dan metadata lifecycle disimpan.")
                                except Exception as exc:
                                    st.error(f"Gagal membuat LAPINSUS: {type(exc).__name__}: {exc}")

                    pdf = st.session_state.get(f"f13_pdf_{article_id}")
                    data = st.session_state.get(f"f13_data_{article_id}")
                    if data:
                        with st.expander("🔎 Preview hasil LAPINSUS", expanded=True):
                            st.markdown(f"**Nomor:** {data['report_number']}")
                            st.markdown(f"**Perihal:** {data['title']}")
                            st.markdown(f"**Sumber:** {data['source']}")
                            if data.get("resolved_link"):
                                st.markdown(f"[Buka sumber artikel asli]({data['resolved_link']})")
                            st.markdown("**I. INFORMASI YANG DIPEROLEH:**")
                            for fact in data["facts"]:
                                st.write("• " + fact)
                            st.markdown("**III. TREND PERKEMBANGAN / PERKIRAAN:**")
                            for item in data["trend"]:
                                st.write("• " + item)
                            st.caption(
                                f"Dokumentasi sumber: {len(data.get('images') or [])} gambar ditemukan."
                            )
                            if pdf:
                                st.download_button(
                                    "⬇️ Download LAPINSUS PDF",
                                    pdf,
                                    file_name=f"LAPINSUS_{article_id}.pdf",
                                    mime="application/pdf",
                                    key=f"f13_dl_card_{article_id}",
                                    width="stretch",
                                )

