import csv
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from database import get_supabase


# ==========================================================
# ID ARTIKEL YANG SUDAH DIVERIFIKASI UNTUK DIHAPUS
# ==========================================================

DELETE_IDS = [
    4409,
    #4356,
    #4353,
    #4376,
    #4357,
    #4408,
    #4355,
    #4396,
    #4361,
    #4395,
    #4358,
    #4394,
    #4831,
    #4397,
    #4390,
    #4398,
    #4655,
    #4360,
    #4362,
    #4404,
    #4405,
    #4363,
    #4399,
    #4354,
    #4359,
    #4393,
    #4391,
    #4392,
    #4418,
    #4383,
    #4402,
    #4365,
    #4403,
    #4400,
    #4364,
    #4378,
    #4386,
    #4368,
    #4385,
    #4389,
    #4407,
    #4373,
    #4380,
    #4370,
    #4388,
    #4384,
    #4366,
    #4382,
    #4367,
    #4381,
    #4377,
    #4372,
    #4387,
    #4374,
    #4675,
    #4401,
    #4375,
    #4369,
    #4379,
    #4406,
    #4371,
]


# ==========================================================
# KONFIGURASI
# ==========================================================

REPORT_CSV = "dedupe_delete_report.csv"
REPORT_JSON = "dedupe_delete_report.json"


# ==========================================================
# UTILITAS
# ==========================================================

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_target_ids() -> List[int]:
    """
    Menghilangkan ID duplikat dari daftar.
    """

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
# AMBIL DATA ARTIKEL
# ==========================================================

def get_articles_by_ids(
    article_ids: List[int],
) -> List[Dict[str, Any]]:

    if not article_ids:
        return []

    client = get_supabase()

    try:
        response = (
            client
            .table("articles")
            .select("*")
            .in_("id", article_ids)
            .execute()
        )

        return response.data or []

    except Exception as exc:

        print(
            "[SUPABASE ERROR] "
            f"Gagal mengambil artikel: {exc}"
        )

        return []


# ==========================================================
# BUAT LAPORAN
# ==========================================================

def create_report(
    requested_ids: List[int],
    found_articles: List[Dict[str, Any]],
    deleted_ids: List[int],
    failed_ids: List[int],
) -> None:

    found_map = {
        int(article["id"]): article
        for article in found_articles
        if article.get("id") is not None
    }

    report_rows = []

    for article_id in requested_ids:

        article = found_map.get(article_id)

        if article_id in deleted_ids:
            status = "DELETED"

        elif article_id in failed_ids:
            status = "DELETE_FAILED"

        elif article is None:
            status = "NOT_FOUND"

        else:
            status = "NOT_DELETED"

        report_rows.append(
            {
                "article_id": article_id,
                "status": status,
                "title": (
                    article.get("title", "")
                    if article
                    else ""
                ),
                "link": (
                    article.get("link", "")
                    if article
                    else ""
                ),
                "category": (
                    article.get("category", "")
                    if article
                    else ""
                ),
                "priority": (
                    article.get("priority", "")
                    if article
                    else ""
                ),
                "published_date": (
                    article.get("published_date", "")
                    if article
                    else ""
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
        ) as csv_file:

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
                csv_file,
                fieldnames=fields,
            )

            writer.writeheader()
            writer.writerows(report_rows)

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

    json_data = {
        "generated_at": now_iso(),
        "requested_count": len(requested_ids),
        "found_count": len(found_articles),
        "deleted_count": len(deleted_ids),
        "failed_count": len(failed_ids),
        "not_found_count": (
            len(requested_ids)
            - len(deleted_ids)
            - len(failed_ids)
            - (
                len(requested_ids)
                - len(found_articles)
            )
        ),
        "requested_ids": requested_ids,
        "deleted_ids": deleted_ids,
        "failed_ids": failed_ids,
        "rows": report_rows,
    }

    try:

        with open(
            REPORT_JSON,
            "w",
            encoding="utf-8",
        ) as json_file:

            json.dump(
                json_data,
                json_file,
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
# PROSES DEDUPE
# ==========================================================

def run_dedupe() -> bool:

    print("=" * 70)
    print("DEDUPE DATABASE")
    print("MENGHAPUS ID ARTIKEL YANG SUDAH DIVERIFIKASI")
    print("=" * 70)

    requested_ids = get_target_ids()

    print()
    print(
        f"[TARGET] Jumlah ID yang akan diproses: "
        f"{len(requested_ids)}"
    )

    print()
    print("ID TARGET:")
    print(", ".join(str(x) for x in requested_ids))

    # ======================================================
    # AMBIL DATA SEBELUM DELETE
    # ======================================================

    print()
    print("=" * 70)
    print("VERIFIKASI DATA SEBELUM DELETE")
    print("=" * 70)

    found_articles = get_articles_by_ids(
        requested_ids
    )

    found_ids = {
        int(article["id"])
        for article in found_articles
        if article.get("id") is not None
    }

    not_found_ids = [
        article_id
        for article_id in requested_ids
        if article_id not in found_ids
    ]

    print(
        f"[DATABASE] ID ditemukan : "
        f"{len(found_ids)}"
    )

    print(
        f"[DATABASE] ID tidak ditemukan : "
        f"{len(not_found_ids)}"
    )

    if not_found_ids:

        print()
        print("ID TIDAK DITEMUKAN:")

        print(
            ", ".join(
                str(x)
                for x in not_found_ids
            )
        )

    # ======================================================
    # TAMPILKAN DATA YANG AKAN DIHAPUS
    # ======================================================

    print()
    print("=" * 70)
    print("DATA YANG AKAN DIHAPUS")
    print("=" * 70)

    for article in found_articles:

        print(
            f"ID={article.get('id')} | "
            f"{str(article.get('title') or '')[:120]}"
        )

    # ======================================================
    # DELETE
    # ======================================================

    if not found_ids:

        print()
        print(
            "[DEDUPE] Tidak ada ID yang ditemukan."
        )

        create_report(
            requested_ids,
            found_articles,
            [],
            [],
        )

        return False

    print()
    print("=" * 70)
    print("MENGHAPUS DATA")
    print("=" * 70)

    deleted_ids = []
    failed_ids = []

    client = get_supabase()

    for article_id in sorted(found_ids):

        try:

            response = (
                client
                .table("articles")
                .delete()
                .eq("id", article_id)
                .execute()
            )

            rows = response.data or []

            if rows:

                deleted_ids.append(
                    article_id
                )

                print(
                    f"[DELETE OK] "
                    f"ID={article_id}"
                )

            else:

                failed_ids.append(
                    article_id
                )

                print(
                    f"[DELETE GAGAL] "
                    f"ID={article_id} "
                    f"tidak mengembalikan data."
                )

        except Exception as exc:

            failed_ids.append(
                article_id
            )

            print(
                f"[DELETE ERROR] "
                f"ID={article_id} -> {exc}"
            )

    # ======================================================
    # REPORT
    # ======================================================

    create_report(
        requested_ids,
        found_articles,
        deleted_ids,
        failed_ids,
    )

    # ======================================================
    # SUMMARY
    # ======================================================

    print()
    print("=" * 70)
    print("HASIL DEDUPE")
    print("=" * 70)

    print(
        f"ID diminta          : "
        f"{len(requested_ids)}"
    )

    print(
        f"ID ditemukan        : "
        f"{len(found_ids)}"
    )

    print(
        f"Berhasil dihapus    : "
        f"{len(deleted_ids)}"
    )

    print(
        f"Gagal dihapus       : "
        f"{len(failed_ids)}"
    )

    print(
        f"Tidak ditemukan     : "
        f"{len(not_found_ids)}"
    )

    print("=" * 70)

    if failed_ids:

        print()
        print("ID GAGAL DIHAPUS:")

        print(
            ", ".join(
                str(x)
                for x in failed_ids
            )
        )

    if deleted_ids:

        print()
        print(
            "[DEDUPE] Penghapusan selesai."
        )

    print()
    print(
        f"[REPORT] {REPORT_CSV}"
    )

    print(
        f"[REPORT] {REPORT_JSON}"
    )

    print("=" * 70)

    return len(failed_ids) == 0


# ==========================================================
# MAIN
# ==========================================================

if __name__ == "__main__":

    success = run_dedupe()

    if not success:
        raise SystemExit(1)
