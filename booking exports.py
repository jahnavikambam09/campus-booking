"""CSV and Markdown rendering (pure functions)."""
import csv
import io

from .models import BOOKING_FIELDS


def csv_safe(value) -> str:
    """Neutralise spreadsheet formula injection (=, +, -, @ at the start of a cell)."""
    text = str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def bookings_to_csv(rows) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=BOOKING_FIELDS)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: csv_safe(v) for k, v in row.items()})
    return buffer.getvalue()


def stats_to_markdown(stats: dict, generated: str) -> str:
    lines = ["# Campus Booking Summary", f"_Generated {generated}_", "",
             "| Metric | Value |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in stats["kpis"].items()]
    lines += ["", "## Room occupancy", "", "| Room | Occupancy |", "|---|---|"]
    lines += [f"| {room} | {pct}% |" for room, pct in sorted(stats["occ"].items(), key=lambda kv: -kv[1])]
    lines += ["", "## Bookings per hour", "", "| Hour | Bookings |", "|---|---|"]
    lines += [f"| {hour} | {count} |" for hour, count in stats["hours"].items()]
    return "\n".join(lines) + "\n"