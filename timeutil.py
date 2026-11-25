"""Small, strict time helpers (replace the old one-letter m() and hm())."""
import re

_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def to_minutes(text: str) -> int:
    """'09:30' -> 570. Raises ValueError for anything that is not a 24h HH:MM."""
    match = _TIME_RE.match(str(text).strip())
    if not match:
        raise ValueError(f"invalid time: {text!r}")
    return int(match.group(1)) * 60 + int(match.group(2))


def to_hhmm(minutes: int) -> str:
    """570 -> '09:30'."""
    return f"{minutes // 60:02d}:{minutes % 60:02d}"