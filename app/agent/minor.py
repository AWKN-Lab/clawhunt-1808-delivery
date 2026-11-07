"""Age calculation from ``birth_ym`` (YYYY-MM or YYYY)."""
from __future__ import annotations

from datetime import date


def _split(birth_ym: str) -> tuple[int, int | None]:
    parts = str(birth_ym).replace("/", "-").replace(".", "-").split("-")
    year = int(parts[0])
    month = int(parts[1]) if len(parts) > 1 and parts[1] else None
    return year, month


def age_at(birth_ym: str, today: date | None = None) -> int:
    today = today or date.today()
    year, month = _split(birth_ym)
    if month is None:
        return today.year - year
    age = today.year - year
    if today.month < month:
        age -= 1
    return age


def is_minor(birth_ym: str, today: date | None = None) -> bool:
    return age_at(birth_ym, today) < 18
