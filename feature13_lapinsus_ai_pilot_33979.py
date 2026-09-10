import json
import os
from pathlib import Path

from database import get_supabase
from feature13_lapinsus_engine import build_lapinsus, make_pdf, TABLE

ARTICLE_ID = 33979
OUT = Path("LAPINSUS_33979_AI_V1_4_PILOT.pdf")
JSON_OUT = Path("LAPINSUS_33979_AI_V1_4_PILOT.json")


def main():
    rows = (
        get_supabase()
        .table(TABLE)
        .select("*")
        .eq("id", ARTICLE_ID)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        raise SystemExit(f"Article {ARTICLE_ID} tidak ditemukan di {TABLE}.")

    article = rows[0]
    data = build_lapinsus(article)
    pdf = make_pdf(data)
    OUT.write_bytes(pdf)

    # Do not store source text in the report artifact JSON.
    audit = {
        "article_id": ARTICLE_ID,
        "title": data.get("title"),
        "source": data.get("source"),
        "resolved_link": data.get("link"),
        "report_number": data.get("report_number"),
        "ai_model": data.get("ai_model"),
        "ai_version": data.get("ai_version"),
        "grounding": data.get("grounding"),
        "source_extraction_method": data.get("source_extraction_method"),
        "source_sentence_count": data.get("source_sentence_count"),
        "source_material_highlights": data.get("source_material_highlights"),
        "facts": data.get("facts"),
        "fact_evidence": data.get("fact_evidence"),
        "trend": data.get("trend"),
        "trend_evidence": data.get("trend_evidence"),
        "actions": data.get("actions"),
        "source_statement": data.get("source_statement"),
        "image_count": len(data.get("images") or []),
        "database_mutation": False,
        "telegram_sent": False,
    }
    JSON_OUT.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"PDF: {OUT}")
    print(f"Audit: {JSON_OUT}")
    print(f"AI model: {data.get('ai_model')}")
    print(f"Grounding: {data.get('grounding')}")
    print("Database mutation: NONE")
    print("Telegram: NONE")
    print("STATUS: PASS")


if __name__ == "__main__":
    main()
