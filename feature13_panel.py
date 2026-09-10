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
        # Peta ini sengaja TIDAK memakai jumlah artikel sebagai bobot.
        # Satu kecamatan dinilai dari jumlah/jenis isu unik yang terdeteksi.
        issue_by_location = {}
        for a in valid:
            issues = classify_issues(
                str(a.get("title") or ""),
                _article_text(a),
            )
            for k in _f13_keywords(a):
                if k in FEATURE13_COORDS:
                    issue_by_location.setdefault(k, set()).update(issues)

        if issue_by_location:
            center = (3.55, 98.73)
            m = folium.Map(location=center, zoom_start=10)
            max_issues = max(len(v) for v in issue_by_location.values()) or 1

            for k, issues in sorted(
                issue_by_location.items(),
                key=lambda x: (-len(x[1]), x[0]),
            ):
                lat, lon = FEATURE13_COORDS[k]
                issue_list = sorted(issues) or ["Isu belum terklasifikasi"]
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
                    tooltip=f"{k.title()}: {n} isu",
                    popup=folium.Popup(popup_html, max_width=420),
                    fill=True,
                ).add_to(m)

            st_folium(m, width=None, height=520, key="f13_map")

            table = [
                {
                    "Lokasi": k.title(),
                    "Jumlah Isu Unik": len(issues),
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
            st.info(
                "Peta ini berbasis JENIS ISU unik per kecamatan, bukan jumlah artikel. "
                "Koordinat merupakan anchor kecamatan perkiraan, bukan koordinat kejadian presisi."
            )
        else:
            st.info("Belum ada data VALID yang dapat dipetakan.")

    with tab_lap:
        choices = [a for a in filtered if a.get("location_context_valid")]
        if not choices:
            st.info("Tidak ada artikel VALID pada filter saat ini.")
        else:
            labels = {
                f"#{a.get('id')} — {str(a.get('title') or 'Tanpa judul')[:100]}": a
                for a in choices
            }
            label = st.selectbox("Pilih artikel", list(labels), key="f13_lap_article")
            a = labels[label]
            data = build_lapinsus(a)

            st.markdown(f"**Nomor:** {data['report_number']}")
            st.markdown(f"**Perihal:** {data['title']}")
            st.markdown(f"**Sumber:** {data['source']}")
            if data.get("resolved_link"):
                st.markdown(f"[Buka sumber artikel asli]({data['resolved_link']})")

            st.markdown("**Fakta yang diekstrak:**")
            for fact in data["facts"]:
                st.write("• " + fact)

            st.markdown("**Trend perkembangan / perkiraan:**")
            for item in data["trend"]:
                st.write("• " + item)

            if data.get("images"):
                st.caption(f"Dokumentasi artikel ditemukan: {len(data['images'])} gambar.")
            else:
                st.caption("Tidak ditemukan gambar artikel yang dapat diambil.")

            if is_admin:
                if st.button(
                    "Generate LAPINSUS PDF",
                    key=f"f13_generate_{a.get('id')}",
                    width="stretch",
                ):
                    pdf = make_pdf(data)
                    mark_generated(a.get("id"), pdf, data)
                    st.session_state["f13_pdf"] = (a.get("id"), pdf)
                    st.success(
                        "Draft LAPINSUS berhasil dibuat. Tetap memerlukan verifikasi analis."
                    )

                if (
                    "f13_pdf" in st.session_state
                    and st.session_state["f13_pdf"][0] == a.get("id")
                ):
                    st.download_button(
                        "⬇️ Download LAPINSUS PDF",
                        st.session_state["f13_pdf"][1],
                        file_name=f"LAPINSUS_{a.get('id')}.pdf",
                        mime="application/pdf",
                        key=f"f13_dl_{a.get('id')}",
                        width="stretch",
                    )
            else:
                st.info(
                    "Generate LAPINSUS tersedia untuk ADMIN. "
                    "Viewer dapat membaca dan meninjau data."
                )
