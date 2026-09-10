import ast
import html
import json
import os
import re
from collections import Counter, defaultdict
from urllib.parse import urlparse

import folium
import pandas as pd
import requests
import streamlit as st
from streamlit_folium import st_folium

from feature13_lapinsus_engine import (
    build_lapinsus,
    clean_article_content,
    extract_issue_topics,
    get_article_source_text,
    get_location_articles,
    make_pdf,
    mark_generated,
)

FEATURE13_TABLE = "deli_serdang_location_articles"
FEATURE13_YEAR = int(os.getenv("TAHUN_TARGET", "2026"))
FEATURE13_REVIEW_IDS = {4284, 4292, 4356, 4358, 4523}

# 22 kecamatan Deli Serdang; anchors are only used for labels/icons.
FEATURE13_COORDS = {
    "bangun purba": (3.442, 98.775), "batang kuis": (3.601, 98.873),
    "beringin": (3.590, 98.890), "sibiru-biru": (3.443, 98.682),
    "deli tua": (3.507, 98.675), "galang": (3.423, 98.718),
    "gunung meriah": (3.457, 98.590), "hamparan perak": (3.706, 98.623),
    "kutalimbaru": (3.449, 98.510), "labuhan deli": (3.719, 98.666),
    "lubuk pakam": (3.558, 98.862), "namorambe": (3.472, 98.676),
    "pagar merbau": (3.600, 98.874), "pancur batu": (3.469, 98.603),
    "pantai labu": (3.659, 98.935), "patumbak": (3.522, 98.715),
    "percut sei tuan": (3.625, 98.790), "sibolangit": (3.303, 98.554),
    "stm hilir": (3.508, 98.805), "stm hulu": (3.432, 98.756),
    "sunggal": (3.603, 98.616), "tanjung morawa": (3.523, 98.790),
}

ISSUE_META = {
    "Narkotika": ("💉", "#dc2626"),
    "Penganiayaan": ("⚔️", "#7c3aed"),
    "Pencurian": ("🕵️", "#d97706"),
    "Pembunuhan": ("☠️", "#991b1b"),
    "Penipuan": ("💳", "#b45309"),
    "Korupsi": ("🏛️", "#ea580c"),
    "Suap / Gratifikasi": ("💰", "#ca8a04"),
    "Judi": ("🎰", "#9333ea"),
    "Kekerasan Seksual": ("⚠️", "#be185d"),
    "KDRT": ("🏠", "#db2777"),
    "Kecelakaan": ("🚗", "#f97316"),
    "Banjir": ("🌊", "#0284c7"),
    "Longsor": ("⛰️", "#92400e"),
    "Karhutla": ("🔥", "#b91c1c"),
    "Kebakaran": ("🔥", "#ef4444"),
    "Infrastruktur": ("🏗️", "#f59e0b"),
    "Kesehatan": ("🏥", "#2563eb"),
    "Pendidikan": ("🎓", "#7c3aed"),
    "Lingkungan": ("🌿", "#16a34a"),
    "Konflik / Kamtibmas": ("👥", "#0f766e"),
    "Pertanahan / Sengketa": ("⚖️", "#64748b"),
    "Anggaran / Pemerintahan": ("🏢", "#0891b2"),
}
ISSUE_ORDER = list(ISSUE_META)
GEOJSON_URL = os.getenv(
    "FEATURE13_GEOJSON_URL",
    "https://raw.githubusercontent.com/fahadh4ilyas/indonesia-geojson-archive/master/Indonesia_subdistricts.geojson",
)


def _keywords(row):
    value = row.get("matched_location_keywords") or []
    if isinstance(value, str):
        try:
            value = ast.literal_eval(value)
        except Exception:
            value = [x.strip() for x in value.split(",") if x.strip()]
    return [str(x).strip().lower() for x in value if str(x).strip()]


def _district(row):
    kws = _keywords(row)
    preferred = [k for k in kws if k in FEATURE13_COORDS and k not in {"deli serdang", "kabupaten deli serdang", "kabupaten deliserdang", "deliserdang"}]
    return preferred[0] if preferred else ("deli serdang" if any("deli serdang" in k for k in kws) else "")


def _source_domain(row):
    source = str(row.get("publisher") or row.get("source") or "").strip()
    if source:
        return source
    try:
        return urlparse(str(row.get("link") or "")).netloc.replace("www.", "")
    except Exception:
        return "Sumber"


@st.cache_data(ttl=60, show_spinner=False)
def load_feature13_articles():
    rows = get_location_articles(limit=1000)
    return [r for r in rows if str(r.get("published_date", "")).startswith(str(FEATURE13_YEAR))]


@st.cache_data(ttl=1800, show_spinner=False)
def _source_data_cached(article_id, link, content, title, images):
    return get_article_source_text({"id": article_id, "link": link, "content": content, "title": title, "article_images": images})


@st.cache_data(ttl=86400, show_spinner=False)
def _load_deli_serdang_geojson():
    """Load only Deli Serdang district polygons and normalize common GeoJSON schemas."""
    urls = [GEOJSON_URL]
    env_url = os.getenv("FEATURE13_GEOJSON_URL", "").strip()
    if env_url and env_url not in urls:
        urls.insert(0, env_url)
    for url in urls:
        try:
            response = requests.get(
                url, timeout=30,
                headers={"User-Agent": "Feature13-DeliSerdang/1.1"},
            )
            response.raise_for_status()
            data = response.json()
            raw_features = data.get("features") or []
            features = []
            for feature in raw_features:
                props = feature.get("properties") or {}
                vals = {str(k).lower(): str(v).strip().lower() for k, v in props.items() if v is not None}
                kab = vals.get("name_2") or vals.get("kabupaten") or vals.get("kab_kota") or vals.get("kabupaten_kota") or ""
                prov = vals.get("name_1") or vals.get("provinsi") or ""
                # Accept Deli Serdang even when province metadata is absent.
                is_ds = kab in {"deli serdang", "deliserdang", "kabupaten deli serdang", "kabupaten deliserdang"}
                if not is_ds:
                    joined = " ".join(vals.values())
                    is_ds = "deli serdang" in joined or "deliserdang" in joined
                if is_ds:
                    features.append(feature)
            if features:
                return {"type": "FeatureCollection", "features": features, "source_url": url}
        except Exception:
            continue
    return None


def _geo_bounds(geo):
    coords = []
    def walk(value):
        if isinstance(value, (list, tuple)):
            if len(value) >= 2 and all(isinstance(x, (int, float)) for x in value[:2]):
                coords.append((float(value[1]), float(value[0])))
            else:
                for item in value:
                    walk(item)
    for feature in (geo or {}).get("features", []):
        walk((feature.get("geometry") or {}).get("coordinates"))
    if not coords:
        return None
    lats = [x[0] for x in coords]
    lons = [x[1] for x in coords]
    return [[min(lats), min(lons)], [max(lats), max(lons)]]


def _geo_district_name(feature):
    props = feature.get("properties") or {}
    for key in ("NAME_3", "name_3", "KECAMATAN", "kecamatan", "WADMKC", "NAMOBJ"):
        value = props.get(key)
        if value:
            return str(value).strip().lower().replace("kec. ", "").replace("kecamatan ", "")
    return ""

def _topics_for_article(row, allow_source=False):
    title = str(row.get("title") or "")
    content = clean_article_content(row.get("content"))
    topics = extract_issue_topics(title, content)
    if allow_source and ("news.google.com" in str(row.get("link") or "") or len(content) < 350):
        data = _source_data_cached(row.get("id"), row.get("link"), row.get("content"), row.get("title"), row.get("article_images") or [])
        topics = extract_issue_topics(title, data.get("text") or content)
    return topics


def _excerpt(row):
    text = clean_article_content(row.get("content"))
    if len(text) < 220:
        data = _source_data_cached(row.get("id"), row.get("link"), row.get("content"), row.get("title"), row.get("article_images") or [])
        text = data.get("text") or text
    return text[:260] + ("..." if len(text) > 260 else "")


def _image_for_card(row):
    images = row.get("article_images") or []
    if isinstance(images, str):
        try: images = json.loads(images)
        except Exception: images = []
    if images:
        return images[0]
    return None


def _render_image(url, height=145):
    if url:
        st.image(url, use_container_width=True, output_format="auto")
    else:
        st.markdown(
            f"<div style='height:{height}px;border-radius:12px;background:#171923;display:flex;align-items:center;justify-content:center;font-size:42px'>📰</div>",
            unsafe_allow_html=True,
        )


def _render_issue_badges(topics):
    if not topics:
        st.caption("Belum ada isu spesifik yang terdeteksi dari konten tersimpan.")
        return
    html_badges = []
    for topic in topics[:5]:
        icon, color = ISSUE_META.get(topic, ("•", "#64748b"))
        html_badges.append(
            f"<span style='display:inline-block;background:{color};color:white;border-radius:999px;padding:4px 10px;margin:2px 4px 2px 0;font-size:12px'>{icon} {html.escape(topic)}</span>"
        )
    st.markdown("".join(html_badges), unsafe_allow_html=True)


def _generate_lapinsus(a, is_admin):
    if not is_admin:
        st.info("Generate LAPINSUS hanya tersedia untuk ADMIN.")
        return
    article_id = a.get("id")
    if st.button("📄 Generate LAPINSUS", key=f"f13_generate_{article_id}", type="primary", use_container_width=True):
        try:
            with st.spinner("Mengambil berita asli → menganalisis dengan AI → memvalidasi evidence → menyusun PDF..."):
                data = build_lapinsus(a)
                pdf = make_pdf(data)
                mark_generated(article_id, pdf, data)
                st.session_state[f"f13_pdf_{article_id}"] = pdf
                st.session_state[f"f13_data_{article_id}"] = data
            st.success("Draft LAPINSUS AI berhasil dibuat. Tetap memerlukan verifikasi analis.")
        except Exception as exc:
            mark_failed(article_id, exc)
            st.error(f"LAPINSUS AI gagal dibuat: {type(exc).__name__}: {exc}")
            st.caption("PDF tidak dibuat karena validasi sumber/AI gagal. Tidak ada fakta generik yang dimasukkan sebagai pengganti.")
    pdf = st.session_state.get(f"f13_pdf_{article_id}")
    if pdf:
        data = st.session_state.get(f"f13_data_{article_id}") or {}
        model = data.get("ai_model") or "AI"
        grounding = data.get("grounding") or {}
        st.caption(f"AI: {model} · Grounding: {'PASS' if grounding.get('passed') else 'REVIEW'}")
        st.download_button("⬇️ Download LAPINSUS PDF", pdf, file_name=f"LAPINSUS_{article_id}.pdf", mime="application/pdf", key=f"f13_dl_{article_id}", use_container_width=True)


def _render_article_card(a, is_admin):
    article_id = a.get("id")
    topics = _topics_for_article(a, allow_source=False)
    image_url = _image_for_card(a)
    district = _district(a)
    valid = bool(a.get("location_context_valid"))
    status = "VALID" if valid else "PERLU REVIEW"
    status_color = "#16a34a" if valid else "#f59e0b"
    with st.container(border=True):
        cols = st.columns([1.05, 4.0, 0.72])
        with cols[0]:
            _render_image(image_url)
        with cols[1]:
            st.markdown(f"### {html.escape(str(a.get('title') or 'Tanpa judul'))}")
            date = str(a.get("published_date") or "-")[:10]
            st.caption(f"📅 {date}   |   📍 {district.title() if district else 'Deli Serdang'}   |   📰 {_source_domain(a)}")
            _render_issue_badges(topics)
            st.write(_excerpt(a))
            b1, b2 = st.columns([1, 1.35])
            with b1:
                if a.get("link"):
                    st.link_button("↗️ Buka Berita", a["link"], use_container_width=True)
            with b2:
                _generate_lapinsus(a, is_admin)
        with cols[2]:
            st.markdown(
                f"<div style='text-align:center'><span style='background:{status_color};color:white;padding:5px 9px;border-radius:999px;font-size:12px'>{status}</span><br><br><span style='color:#9ca3af'>#{article_id}</span></div>",
                unsafe_allow_html=True,
            )
            with st.expander("Isi"):
                st.write(clean_article_content(a.get("content"))[:5000] or "Konten tersimpan tidak tersedia.")
        generated_data = st.session_state.get(f"f13_data_{article_id}")
        if generated_data:
            st.markdown("**Preview LAPINSUS**")
            st.markdown("**I. INFORMASI YANG DIPEROLEH**")
            for fact in generated_data["facts"][:5]: st.write("• " + fact)
            st.markdown("**III. TREND PERKEMBANGAN / PERKIRAAN**")
            for trend in generated_data["trend"][:5]: st.write("• " + trend)
            st.caption(
                f"Dokumentasi sumber: {len(generated_data.get('images') or [])} gambar · "
                f"Evidence fakta: {len(generated_data.get('fact_evidence') or [])} · "
                f"Evidence trend: {len(generated_data.get('trend_evidence') or [])}"
            )


def _map_issue_data(rows, source_refresh=False):
    district_topics = defaultdict(set)
    district_articles = defaultdict(list)
    for row in rows:
        district = _district(row)
        if not district:
            continue
        topics = _topics_for_article(row, allow_source=source_refresh)
        for topic in topics:
            district_topics[district].add(topic)
            district_articles[district].append((topic, row.get("id"), row.get("title")))
    return district_topics, district_articles


def _render_issue_map(valid_rows, source_refresh=False):
    st.markdown("### 🗺️ Peta Isu per Kecamatan")
    st.caption("Batas kecamatan Deli Serdang ditampilkan sebagai poligon. Warna dan marker menunjukkan isu spesifik yang terdeteksi dari berita.")
    refresh_col, issue_col = st.columns([1.4, 2.6])
    with refresh_col:
        if st.button("🔄 Analisis dari link berita", key="f13_map_refresh"):
            st.session_state["f13_map_source_refresh"] = True
            _source_data_cached.clear()
            st.rerun()
    source_refresh = bool(st.session_state.get("f13_map_source_refresh", source_refresh))
    with issue_col:
        available = sorted({topic for row in valid_rows for topic in _topics_for_article(row, allow_source=False)}, key=lambda x: ISSUE_ORDER.index(x) if x in ISSUE_ORDER else 999)
        issue_filter = st.selectbox("Filter isu", ["SEMUA ISU"] + available, key="f13_issue_filter")

    district_topics, district_articles = _map_issue_data(valid_rows, source_refresh=source_refresh)
    if issue_filter != "SEMUA ISU":
        district_topics = {d: {t for t in topics if t == issue_filter} for d, topics in district_topics.items()}
        district_topics = {d: t for d, t in district_topics.items() if t}

    geo = _load_deli_serdang_geojson()
    if geo is None:
        st.warning("Batas poligon kecamatan Deli Serdang belum berhasil dimuat. Marker kecamatan tetap ditampilkan; posisi peta tetap dikunci ke Deli Serdang.")
    else:
        st.caption("Base map: OpenStreetMap • Polygon: Deli Serdang • tanpa CARTO API key")

    # OpenStreetMap is used deliberately: no CARTO API key is required.
    m = folium.Map(
        location=[3.52, 98.72],
        zoom_start=10,
        tiles="OpenStreetMap",
        control_scale=True,
        prefer_canvas=True,
    )
    style_by_name = {}
    for district, topics in district_topics.items():
        dominant = next((x for x in ISSUE_ORDER if x in topics), None)
        color = ISSUE_META.get(dominant, ("•", "#64748b"))[1]
        style_by_name[district] = color

    if geo:
        def style_function(feature):
            district_name = _geo_district_name(feature)
            color = style_by_name.get(district_name, "#475569")
            active = district_name in style_by_name
            return {
                "fillColor": color if active else "#334155",
                "color": color if active else "#64748b",
                "weight": 1.5,
                "fillOpacity": 0.62 if active else 0.12,
            }

        tooltip_fields = []
        if geo.get("features"):
            props = geo["features"][0].get("properties") or {}
            for candidate in ("NAME_3", "name_3", "KECAMATAN", "kecamatan", "WADMKC", "NAMOBJ"):
                if candidate in props:
                    tooltip_fields = [candidate]
                    break

        kwargs = {
            "name": "Kecamatan Deli Serdang",
            "style_function": style_function,
        }
        if tooltip_fields:
            kwargs["tooltip"] = folium.GeoJsonTooltip(fields=tooltip_fields, aliases=["Kecamatan"])
        folium.GeoJson(geo, **kwargs).add_to(m)

        bounds = _geo_bounds(geo)
        if bounds:
            m.fit_bounds(bounds, padding=(12, 12))
    else:
        # Safe fallback: keep the map centered on Deli Serdang, never on another regency.
        m.location = [3.52, 98.72]
        m.zoom_start = 10

    for district, topics in sorted(district_topics.items()):
        if district not in FEATURE13_COORDS:
            continue
        lat, lon = FEATURE13_COORDS[district]
        topic_list = [t for t in ISSUE_ORDER if t in topics]
        if not topic_list:
            continue
        first = topic_list[0]
        icon, color = ISSUE_META[first]
        rows_html = "".join(f"<li>{html.escape(t)}</li>" for t in topic_list)
        count = len(district_articles.get(district, []))
        popup = folium.Popup(f"<b>{html.escape(district.title())}</b><br><b>Isu:</b><ul>{rows_html}</ul><small>{count} relasi artikel</small>", max_width=330)
        folium.Marker(
            [lat, lon], popup=popup,
            tooltip=f"{district.title()} — {', '.join(topic_list)}",
            icon=folium.DivIcon(html=f"<div style='width:34px;height:34px;border-radius:50%;background:{color};border:3px solid white;display:flex;align-items:center;justify-content:center;font-size:17px;box-shadow:0 2px 8px rgba(0,0,0,.5)'>{icon}</div>"),
        ).add_to(m)

    left, right = st.columns([4.2, 1.4])
    with left:
        st_folium(m, width=None, height=600, key="f13_real_issue_map")
    with right:
        st.markdown("**Legenda isu**")
        if issue_filter != "SEMUA ISU":
            legend_topics = [issue_filter] if any(issue_filter in topics for topics in district_topics.values()) else []
        else:
            legend_topics = [topic for topic in ISSUE_ORDER if any(topic in topics for topics in district_topics.values())]
        if not legend_topics:
            st.caption("Tidak ada isu spesifik yang cocok dengan filter saat ini.")
        for topic in legend_topics:
            icon, color = ISSUE_META[topic]
            st.markdown(f"<div style='margin:6px 0'><span style='display:inline-flex;width:25px;height:25px;border-radius:50%;background:{color};align-items:center;justify-content:center'>{icon}</span> &nbsp; {html.escape(topic)}</div>", unsafe_allow_html=True)
        st.divider()
        st.caption("Klik marker untuk melihat isu dan artikel yang terkait dengan kecamatan tersebut.")


def render_feature13_panel(is_admin=False):
    st.header("📍 Feature #13 — Deli Serdang Location Intelligence")
    st.caption("Location discovery → artikel wilayah → peta isu (berdasarkan isi berita)")
    articles = load_feature13_articles()
    valid = [a for a in articles if bool(a.get("location_context_valid"))]
    review = [a for a in articles if not bool(a.get("location_context_valid"))]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📄 Total artikel", len(articles)); c2.metric("✅ Valid", len(valid)); c3.metric("⚠️ Perlu review", len(review)); c4.metric("🏘️ Kecamatan terdeteksi", f"{len({ _district(a) for a in valid if _district(a) })} / 22")

    f1, f2, f3, f4 = st.columns([1.7, 1.0, 1.0, 1.0])
    with f1: search = st.text_input("🔎 Cari artikel", placeholder="Ketik judul, kata kunci, atau sumber...", key="f13_search_v5")
    with f2: status = st.selectbox("Konteks lokasi", ["SEMUA", "VALID", "PERLU REVIEW"], key="f13_status_v5")
    with f3:
        districts = sorted({k for a in articles for k in _keywords(a) if k in FEATURE13_COORDS})
        district_filter = st.selectbox("Kecamatan", ["SEMUA"] + districts, key="f13_district_v5")
    with f4:
        sources = sorted({_source_domain(a) for a in articles})
        source_filter = st.selectbox("Sumber", ["SEMUA"] + sources[:150], key="f13_source_v5")
    if st.button("↻ Reset filter", key="f13_reset_v5"):
        for key in ("f13_search_v5", "f13_status_v5", "f13_district_v5", "f13_source_v5"):
            st.session_state.pop(key, None)
        st.rerun()

    filtered=[]
    q = search.lower().strip()
    for a in articles:
        hay = " ".join([str(a.get("title") or ""), clean_article_content(a.get("content")), _source_domain(a)]).lower()
        kws = _keywords(a)
        if q and q not in hay: continue
        if status == "VALID" and not a.get("location_context_valid"): continue
        if status == "PERLU REVIEW" and a.get("location_context_valid"): continue
        if district_filter != "SEMUA" and district_filter not in kws: continue
        if source_filter != "SEMUA" and _source_domain(a) != source_filter: continue
        filtered.append(a)

    st.write(f"Menampilkan **{len(filtered)}** artikel")
    left, right = st.columns([1.03, 0.97], gap="large")
    with left:
        h1, h2 = st.columns([2.2, 1.0])
        with h1:
            st.subheader("📰 Daftar Artikel")
            st.caption(f"Menampilkan {len(filtered)} artikel ({FEATURE13_YEAR})")
        with h2:
            sort = st.selectbox("Urutkan", ["Terbaru", "Terlama"], key="f13_sort_v5")
            page_size = st.selectbox("Tampilkan", [10, 20, 50], index=1, key="f13_page_size_v5")
        filtered.sort(key=lambda x: str(x.get("published_date") or ""), reverse=(sort == "Terbaru"))
        total_pages = max(1, (len(filtered) + page_size - 1) // page_size)
        page = st.number_input("Halaman", min_value=1, max_value=total_pages, value=min(int(st.session_state.get("f13_page_v5", 1)), total_pages), step=1, key="f13_page_v5")
        start = (page - 1) * page_size
        for a in filtered[start:start+page_size]:
            _render_article_card(a, is_admin)
        if total_pages > 1:
            st.caption(f"Halaman {page} dari {total_pages}")
    with right:
        _render_issue_map(valid, source_refresh=False)
