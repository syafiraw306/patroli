
import csv
import json
from datetime import datetime, timezone
from typing import Any, Dict, List

from database import get_supabase


# ==========================================================
# KONFIGURASI
# ==========================================================

REPORT_CSV = "dedupe_diagnostic_report.csv"
REPORT_JSON = "dedupe_diagnostic_report.json"

TABLE_NAME = "articles"


# ==========================================================
# ID DUPLICATE YANG SUDAH DIVERIFIKASI
# ==========================================================

DELETE_IDS = [
    4356,
    4353,
    4376,
    4357,
    4408,
    4355,
    4396,
    4361,
    4395,
    4358,
    4394,
    4831,
    4397,
    4390,
    4398,
    4655,
    4360,
    4362,
    4404,
    4405,
    4363,
    4399,
    4354,
    4359,
    4393,
    4391,
    4392,
    4418,
    4383,
    4402,
    4365,
    4403,
    4400,
    4364,
    4378,
    4386,
    4368,
    4385,
    4389,
    4407,
    4373,
    4380,
    4370,
    4388,
    4384,
    4366,
    4382,
    4367,
    4381,
    4377,
    4372,
    4387,
    4374,
    4675,
    4401,
    4375,
    4369,
    4379,
    4406,
    4371,
]


# ==========================================================
# UTILITAS
# ==========================================================

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_target_ids() -> List[int]:
    """Membersihkan dan menghapus ID duplicate dari daftar target."""

    result = []

    for article_id in DELETE_IDS:

        try:
            article_id = int(article_id)

            if article_id not in result:
                result.append(article_id)

        except (TypeError, ValueError):

            print(
                f"[WARNING] ID tidak valid: {article_id}"
            )

    return result


# ==========================================================
# KONEKSI SUPABASE
# ==========================================================

def get_client():

    try:

        client = get_supabase()

        print("[SUPABASE] Client berhasil dibuat.")

        return client

    except Exception as exc:

        print(
            f"[SUPABASE ERROR] Gagal membuat client: {exc}"
        )

        return None


# ==========================================================
# CEK DATABASE
# ==========================================================

def check_database(client) -> bool:

    print()
    print("=" * 70)
    print("DIAGNOSTIK DATABASE")
    print("=" * 70)

    try:

        response = (
            client
            .table(TABLE_NAME)
            .select("id")
            .limit(10)
            .execute()
        )

        rows = response.data or []

        print(
            f"[DATABASE] Tabel        : {TABLE_NAME}"
        )

        print(
            f"[DATABASE] Sample data  : {len(rows)}"
        )

        if not rows:

            print(
                "[WARNING] Tidak ada data yang dikembalikan."
            )

            return True

        print()
        print("10 ID PERTAMA DARI DATABASE:")

        for row in rows:

            print(
                f"  ID = {row.get('id')!r} "
                f"(tipe={type(row.get('id')).__name__})"
            )

        return True

    except Exception as exc:

        print(
            f"[DATABASE ERROR] {exc}"
        )

        return False


# ==========================================================
# AMBIL SAMPLE ARTIKEL LENGKAP
# ==========================================================

def get_sample_articles(client) -> List[Dict[str, Any]]:

    try:

        response = (
            client
            .table(TABLE_NAME)
            .select("*")
            .order("id", desc=True)
            .limit(10)
            .execute()
        )

        rows = response.data or []

        return rows

    except Exception as exc:

        print(
            f"[DATABASE ERROR] Gagal mengambil sample artikel: {exc}"
        )

        return []


# ==========================================================
# CEK TARGET ID
# ==========================================================

def check_target_ids(
    client,
    target_ids: List[int],
) -> Dict[int, Dict[str, Any]]:

    print()
    print("=" * 70)
    print("VERIFIKASI TARGET ID")
    print("=" * 70)

    found_map: Dict[int, Dict[str, Any]] = {}

    if not target_ids:

        print("[TARGET] Tidak ada target ID.")

        return found_map

    # ------------------------------------------------------
    # Query per batch
    # ------------------------------------------------------

    batch_size = 50

    for start in range(
        0,
        len(target_ids),
        batch_size,
    ):

        batch = target_ids[
            start:start + batch_size
        ]

        print()
        print(
            f"[CHECK] Memeriksa batch "
            f"{start + 1}-{start + len(batch)}..."
        )

        try:

            response = (
                client
                .table(TABLE_NAME)
                .select("*")
                .in_("id", batch)
                .execute()
            )

            rows = response.data or []

            print(
                f"[CHECK] Data ditemukan: {len(rows)}"
            )

            for row in rows:

                raw_id = row.get("id")

                try:

                    article_id = int(raw_id)

                    found_map[article_id] = row

                except (
                    TypeError,
                    ValueError,
                ):

                    print(
                        "[WARNING] ID database "
                        f"tidak dapat dikonversi: {raw_id!r}"
                    )

        except Exception as exc:

            print(
                f"[SUPABASE ERROR] Batch gagal: {exc}"
            )

    return found_map


# ==========================================================
# CEK TARGET DENGAN STRING
# ==========================================================

def check_target_ids_as_strings(
    client,
    target_ids: List[int],
) -> Dict[str, Dict[str, Any]]:

    """
    Pemeriksaan tambahan.

    Jika kolom ID ternyata bertipe text/varchar,
    query integer sebelumnya bisa tidak cocok.
    """

    print()
    print("=" * 70)
    print("PEMERIKSAAN ID SEBAGAI STRING")
    print("=" * 70)

    found_map: Dict[str, Dict[str, Any]] = {}

    target_strings = [
        str(x)
        for x in target_ids
    ]

    batch_size = 50

    for start in range(
        0,
        len(target_strings),
        batch_size,
    ):

        batch = target_strings[
            start:start + batch_size
        ]

        try:

            response = (
                client
                .table(TABLE_NAME)
                .select("*")
                .in_("id", batch)
                .execute()
            )

            rows = response.data or []

            print(
                f"[STRING CHECK] "
                f"Batch menemukan {len(rows)} data."
            )

            for row in rows:

                raw_id = row.get("id")

                if raw_id is not None:

                    found_map[
                        str(raw_id)
                    ] = row

        except Exception as exc:

            print(
                "[STRING CHECK ERROR] "
                f"{exc}"
            )

    return found_map


# ==========================================================
# BUAT REPORT
# ==========================================================

def create_report(
    target_ids: List[int],
    found_map: Dict[int, Dict[str, Any]],
    string_found_map: Dict[str, Dict[str, Any]],
    sample_articles: List[Dict[str, Any]],
) -> None:

    rows = []

    for article_id in target_ids:

        article = found_map.get(article_id)

        string_article = string_found_map.get(
            str(article_id)
        )

        if article:

            status = "FOUND_INTEGER_QUERY"

            data = article

        elif string_article:

            status = "FOUND_STRING_QUERY"

            data = string_article

        else:

            status = "NOT_FOUND"

            data = {}

        rows.append(
            {
                "article_id": article_id,
                "status": status,
                "title": data.get("title", ""),
                "link": data.get("link", ""),
                "category": data.get("category", ""),
                "priority": data.get("priority", ""),
                "published_date": data.get(
                    "published_date",
                    "",
                ),
            }
        )

    # ------------------------------------------------------
    # CSV
    # ------------------------------------------------------

    try:

        with open(
            REPORT_CSV,
            "w",
            newline="",
            encoding="utf-8",
        ) as file:

            fields = [
                "article_id",
                "status",
                "title",
                "link",
                "category",
                "priority",
                "published_date",
            ]

            writer = csv.DictWriter(
                file,
                fieldnames=fields,
            )

            writer.writeheader()

            writer.writerows(rows)

        print()
        print(
            f"[REPORT] CSV berhasil dibuat: "
            f"{REPORT_CSV}"
        )

    except Exception as exc:

        print(
            f"[REPORT ERROR] CSV: {exc}"
        )

    # ------------------------------------------------------
    # JSON
    # ------------------------------------------------------

    integer_found = len(found_map)

    string_found = len(
        string_found_map
    )

    not_found = sum(
        1
        for row in rows
        if row["status"] == "NOT_FOUND"
    )

    json_data = {
        "generated_at": now_iso(),
        "mode": "DIAGNOSTIC_ONLY",
        "delete_executed": False,
        "table": TABLE_NAME,
        "target_count": len(target_ids),
        "integer_query_found": integer_found,
        "string_query_found": string_found,
        "not_found_count": not_found,
        "target_ids": target_ids,
        "rows": rows,
        "database_sample": sample_articles,
    }

    try:

        with open(
            REPORT_JSON,
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                json_data,
                file,
                ensure_ascii=False,
                indent=2,
                default=str,
            )

        print(
            f"[REPORT] JSON berhasil dibuat: "
            f"{REPORT_JSON}"
        )

    except Exception as exc:

        print(
            f"[REPORT ERROR] JSON: {exc}"
        )


# ==========================================================
# DIAGNOSTIK UTAMA
# ==========================================================

def run_diagnostic() -> bool:

    print("=" * 70)
    print("DEDUPE DATABASE - MODE DIAGNOSTIK")
    print("=" * 70)

    print()
    print(
        "!!! MODE AMAN !!!"
    )

    print(
        "!!! TIDAK ADA DATA YANG AKAN DIHAPUS !!!"
    )

    print("=" * 70)

    # ------------------------------------------------------
    # TARGET
    # ------------------------------------------------------

    target_ids = get_target_ids()

    print()
    print(
        f"[TARGET] Jumlah ID: {len(target_ids)}"
    )

    print()
    print("ID TARGET:")

    print(
        ", ".join(
            str(x)
            for x in target_ids
        )
    )

    # ------------------------------------------------------
    # CLIENT
    # ------------------------------------------------------

    client = get_client()

    if client is None:

        return False

    # ------------------------------------------------------
    # CEK DATABASE
    # ------------------------------------------------------

    database_ok = check_database(
        client
    )

    if not database_ok:

        return False

    # ------------------------------------------------------
    # SAMPLE ARTIKEL
    # ------------------------------------------------------

    print()
    print("=" * 70)
    print("SAMPLE ARTIKEL TERBARU")
    print("=" * 70)

    sample_articles = get_sample_articles(
        client
    )

    if sample_articles:

        for article in sample_articles:

            print(
                f"ID={article.get('id')!r} | "
                f"{str(article.get('title') or '')[:100]}"
            )

    else:

        print(
            "[DATABASE] Tidak ada sample artikel."
        )

    # ------------------------------------------------------
    # CEK INTEGER
    # ------------------------------------------------------

    found_map = check_target_ids(
        client,
        target_ids,
    )

    # ------------------------------------------------------
    # CEK STRING
    # ------------------------------------------------------

    string_found_map = (
        check_target_ids_as_strings(
            client,
            target_ids,
        )
    )

    # ------------------------------------------------------
    # HASIL
    # ------------------------------------------------------

    found_integer_ids = set(
        found_map.keys()
    )

    found_string_ids = {
        int(x)
        for x in string_found_map.keys()
        if str(x).isdigit()
    }

    all_found_ids = (
        found_integer_ids
        | found_string_ids
    )

    not_found_ids = [
        article_id
        for article_id in target_ids
        if article_id not in all_found_ids
    ]

    print()
    print("=" * 70)
    print("HASIL DIAGNOSTIK")
    print("=" * 70)

    print(
        f"ID target             : {len(target_ids)}"
    )

    print(
        f"Ditemukan integer     : "
        f"{len(found_integer_ids)}"
    )

    print(
        f"Ditemukan string      : "
        f"{len(found_string_ids)}"
    )

    print(
        f"Tidak ditemukan      : "
        f"{len(not_found_ids)}"
    )

    if found_integer_ids:

        print()
        print("ID DITEMUKAN:")

        print(
            ", ".join(
                str(x)
                for x in sorted(found_integer_ids)
            )
        )

    if found_string_ids:

        print()
        print(
            "ID DITEMUKAN MELALUI STRING:"
        )

        print(
            ", ".join(
                str(x)
                for x in sorted(found_string_ids)
            )
        )

    if not_found_ids:

        print()
        print(
            "ID TIDAK DITEMUKAN:"
        )

        print(
            ", ".join(
                str(x)
                for x in not_found_ids
            )
        )

    # ------------------------------------------------------
    # REPORT
    # ------------------------------------------------------

    create_report(
        target_ids,
        found_map,
        string_found_map,
        sample_articles,
    )

    # ------------------------------------------------------
    # KEAMANAN
    # ------------------------------------------------------

    print()
    print("=" * 70)
    print("KEAMANAN")
    print("=" * 70)

    print(
        "[SAFE MODE] DELETE TIDAK DIJALANKAN."
    )

    print(
        "[SAFE MODE] Tidak ada artikel yang dihapus."
    )

    print(
        "[SAFE MODE] Silakan periksa hasil diagnostik."
    )

    print("=" * 70)

    # Diagnostic berhasil jika koneksi database berhasil.
    return True


# ==========================================================
# MAIN
# ==========================================================

if __name__ == "__main__":

    success = run_diagnostic()

    if not success:

        raise SystemExit(1)

    raise SystemExit(0)

