"""
Risk Engine - Patroli Siber

Tahap 1:
- Tidak mengakses database.
- Tidak mengubah artikel.
- Menggunakan field klasifikasi yang sudah tersedia.
- Menghasilkan skor risiko 0-100 yang explainable.

Bobot:
    Sentiment Severity : 25
    Issue Severity     : 25
    Media Spread       : 20
    Recurrence         : 15
    Trend              : 15

Level:
    0-30   LOW
    31-60  MEDIUM
    61-80  HIGH
    81-100 CRITICAL
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List


WEIGHTS = {
    "sentiment_severity": 25,
    "issue_severity": 25,
    "media_spread": 20,
    "recurrence": 15,
    "trend": 15,
}

RISK_LEVELS = (
    (80, "CRITICAL"),
    (60, "HIGH"),
    (30, "MEDIUM"),
    (-1, "LOW"),
)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _clamp(value: float, minimum: float, maximum: float) -> int:
    return int(round(max(minimum, min(maximum, value))))


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set)):
        return list(value)
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    return [value]


def get_risk_level(score: int) -> str:
    """Konversi skor 0-100 menjadi LOW/MEDIUM/HIGH/CRITICAL."""
    score = _clamp(score, 0, 100)

    for minimum, level in RISK_LEVELS:
        if score > minimum:
            return level

    return "LOW"


def calculate_sentiment_severity(article: Dict[str, Any]) -> Dict[str, Any]:
    """
    Maksimum 25.

    Dasar:
    - category Negatif Kuat
    - negative_score
    - category Perlu Penanganan
    - handling_score

    Positif/Netral tidak diberi penalti.
    """
    category = str(article.get("category") or "Netral").strip()
    negative_score = _safe_int(article.get("negative_score"))
    handling_score = _safe_int(article.get("handling_score"))

    if category == "Negatif Kuat":
        # negative_score saat ini memiliki rentang sampai 40.
        score = 15 + round(min(negative_score, 40) / 40 * 10)
        score = _clamp(score, 0, 25)
        reason = "Kategori Negatif Kuat dengan sinyal negatif langsung."
    elif category == "Perlu Penanganan":
        # Handling maksimal 30; risikonya lebih rendah daripada negatif kuat.
        score = 5 + round(min(handling_score, 30) / 30 * 10)
        score = _clamp(score, 0, 15)
        reason = "Kategori Perlu Penanganan dengan sinyal isu yang perlu dipantau."
    else:
        score = 0
        reason = "Tidak ada kategori negatif/penanganan."

    return {
        "score": score,
        "max_score": 25,
        "reason": reason,
    }


def calculate_issue_severity(article: Dict[str, Any]) -> Dict[str, Any]:
    """
    Maksimum 25.

    Menggabungkan kekuatan konteks negatif/handling dan indikator
    yang sudah dihasilkan classifier.
    """
    category = str(article.get("category") or "Netral").strip()
    negative_score = _safe_int(article.get("negative_score"))
    handling_score = _safe_int(article.get("handling_score"))
    strong_context = _as_list(article.get("strong_context"))
    handling_context = _as_list(article.get("handling_context"))
    negative_hits = _as_list(article.get("negative_hits"))

    if category == "Negatif Kuat":
        base = 12
        base += round(min(negative_score, 40) / 40 * 8)
        base += min(len(strong_context), 2) * 2
        base += min(len(negative_hits), 1)
        reason = "Terdapat konteks negatif kuat yang berkaitan dengan satker."
    elif category == "Perlu Penanganan":
        base = 7
        base += round(min(handling_score, 30) / 30 * 8)
        base += min(len(handling_context), 2) * 2
        reason = "Terdapat konteks yang memerlukan pemantauan/penanganan."
    else:
        base = 0
        reason = "Tidak ditemukan indikator isu prioritas."

    score = _clamp(base, 0, 25)

    return {
        "score": score,
        "max_score": 25,
        "reason": reason,
    }


def calculate_media_spread(
    article: Dict[str, Any],
    media_count: int | None = None,
    media_sources: Iterable[Any] | None = None,
) -> Dict[str, Any]:
    """
    Maksimum 20.

    Tahap 1 belum melakukan clustering lintas-media secara otomatis.
    Karena itu nilai media_count/media_sources dapat diberikan oleh
    caller. Default 1 media agar tidak mengarang spread.
    """
    if media_sources is not None:
        sources = {
            str(item).strip().lower()
            for item in media_sources
            if str(item).strip()
        }
        count = len(sources)
    elif media_count is not None:
        count = max(1, _safe_int(media_count, 1))
    else:
        source = article.get("publisher") or article.get("source")
        count = 1 if str(source or "").strip() else 1

    # 1 media = 0; 2 = 5; 3 = 10; 4 = 15; 5+ = 20.
    score = _clamp((count - 1) * 5, 0, 20)

    if count <= 1:
        reason = "Belum ada indikasi penyebaran lintas media."
    else:
        reason = f"Indikasi artikel/event muncul pada {count} media."

    return {
        "score": score,
        "max_score": 20,
        "media_count": count,
        "reason": reason,
    }


def calculate_recurrence(
    article: Dict[str, Any],
    recurrence_count: int | None = None,
) -> Dict[str, Any]:
    """
    Maksimum 15.

    recurrence_count = jumlah kejadian/artikel terkait sebelumnya.
    Jika belum tersedia, default 0 agar tidak mengarang recurrence.
    """
    if recurrence_count is None:
        recurrence_count = _safe_int(
            article.get("recurrence_count"),
            0,
        )

    count = max(0, recurrence_count)

    # 0=0, 1=5, 2=8, 3=11, 4+=15
    if count <= 0:
        score = 0
    elif count == 1:
        score = 5
    elif count == 2:
        score = 8
    elif count == 3:
        score = 11
    else:
        score = 15

    reason = (
        "Belum ada kejadian terkait sebelumnya."
        if count == 0
        else f"Ditemukan {count} kejadian/artikel terkait sebelumnya."
    )

    return {
        "score": score,
        "max_score": 15,
        "recurrence_count": count,
        "reason": reason,
    }


def calculate_trend(
    article: Dict[str, Any],
    trend_score: int | None = None,
) -> Dict[str, Any]:
    """
    Maksimum 15.

    trend_score dapat diberikan langsung 0-15 setelah analisis tren.
    Jika belum tersedia, default 0 agar tidak mengarang kenaikan tren.
    """
    if trend_score is None:
        trend_score = _safe_int(article.get("trend_score"), 0)

    score = _clamp(trend_score, 0, 15)

    if score == 0:
        reason = "Belum ada indikasi kenaikan tren."
    elif score <= 5:
        reason = "Ada indikasi tren rendah."
    elif score <= 10:
        reason = "Ada indikasi tren meningkat."
    else:
        reason = "Ada indikasi tren meningkat kuat."

    return {
        "score": score,
        "max_score": 15,
        "reason": reason,
    }


def calculate_risk_score(
    article: Dict[str, Any],
    *,
    media_count: int | None = None,
    media_sources: Iterable[Any] | None = None,
    recurrence_count: int | None = None,
    trend_score: int | None = None,
) -> Dict[str, Any]:
    """
    Fungsi utama Risk Engine.

    Tidak mengubah object article.
    Mengembalikan breakdown lengkap agar skor dapat dijelaskan.
    """
    sentiment = calculate_sentiment_severity(article)
    issue = calculate_issue_severity(article)
    media = calculate_media_spread(
        article,
        media_count=media_count,
        media_sources=media_sources,
    )
    recurrence = calculate_recurrence(
        article,
        recurrence_count=recurrence_count,
    )
    trend = calculate_trend(
        article,
        trend_score=trend_score,
    )

    factors = {
        "sentiment_severity": sentiment,
        "issue_severity": issue,
        "media_spread": media,
        "recurrence": recurrence,
        "trend": trend,
    }

    score = sum(
        int(factor["score"])
        for factor in factors.values()
    )
    score = _clamp(score, 0, 100)

    level = get_risk_level(score)

    reasons = [
        factor["reason"]
        for factor in factors.values()
        if factor["score"] > 0
    ]

    return {
        "risk_score": score,
        "risk_level": level,
        "factors": factors,
        "reasons": reasons,
    }


def enrich_article_with_risk(
    article: Dict[str, Any],
    *,
    media_count: int | None = None,
    media_sources: Iterable[Any] | None = None,
    recurrence_count: int | None = None,
    trend_score: int | None = None,
) -> Dict[str, Any]:
    """
    Menghasilkan copy article + field risk.

    Article asli tidak dimodifikasi.
    """
    result = dict(article)

    risk = calculate_risk_score(
        article,
        media_count=media_count,
        media_sources=media_sources,
        recurrence_count=recurrence_count,
        trend_score=trend_score,
    )

    result["risk_score"] = risk["risk_score"]
    result["risk_level"] = risk["risk_level"]
    result["risk_factors"] = risk["factors"]
    result["risk_reasons"] = risk["reasons"]

    return result


def calculate_risk_batch(
    articles: Iterable[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Menghitung risk untuk banyak artikel tanpa mengubah artikel asli."""
    return [
        enrich_article_with_risk(article)
        for article in articles
    ]


def format_risk_explanation(risk_result: Dict[str, Any]) -> str:
    """Format singkat yang siap dipakai dashboard/log."""
    score = risk_result.get("risk_score", 0)
    level = risk_result.get("risk_level", "LOW")
    factors = risk_result.get("factors", {})

    lines = [
        f"Risk Score : {score}/100",
        f"Risk Level : {level}",
    ]

    labels = {
        "sentiment_severity": "Sentiment Severity",
        "issue_severity": "Issue Severity",
        "media_spread": "Media Spread",
        "recurrence": "Recurrence",
        "trend": "Trend",
    }

    for key, label in labels.items():
        factor = factors.get(key, {})
        lines.append(
            f"{label:20}: "
            f"{factor.get('score', 0)}/"
            f"{factor.get('max_score', WEIGHTS[key])}"
        )

    reasons = risk_result.get("reasons") or []
    if reasons:
        lines.append("")
        lines.append("Alasan:")
        lines.extend(f"- {reason}" for reason in reasons)

    return "\n".join(lines)


def _self_test() -> None:
    """Tes internal sederhana untuk memastikan engine aman."""
    positive = {
        "category": "Positif",
        "negative_score": 0,
        "handling_score": 0,
    }
    assert calculate_risk_score(positive)["risk_score"] == 0

    neutral = {
        "category": "Netral",
        "negative_score": 0,
        "handling_score": 0,
    }
    assert calculate_risk_score(neutral)["risk_score"] == 0

    negative = {
        "category": "Negatif Kuat",
        "negative_score": 40,
        "handling_score": 0,
        "strong_context": [
            "Kajari dilaporkan...",
            "Kejari diadukan..."
        ],
        "negative_hits": ["pattern"],
    }
    result = calculate_risk_score(
        negative,
        media_count=5,
        recurrence_count=4,
        trend_score=15,
    )
    assert result["risk_score"] == 100
    assert result["risk_level"] == "CRITICAL"

    handling = {
        "category": "Perlu Penanganan",
        "negative_score": 0,
        "handling_score": 30,
        "handling_context": ["Ada pengaduan..."],
    }
    result = calculate_risk_score(handling)
    assert 0 < result["risk_score"] <= 40
    assert result["risk_level"] in {"LOW", "MEDIUM"}

    original = dict(negative)
    enrich_article_with_risk(negative)
    assert negative == original

    print("RISK ENGINE SELF-TEST: PASS")


if __name__ == "__main__":
    _self_test()
