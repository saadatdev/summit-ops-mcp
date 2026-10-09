"""Business rules. Pure functions: data in, Decision out. No I/O, no Claude.

Every write goes through these twice: when the preview is created and again
when it is confirmed. The prompt never carries a rule; if it isn't here, it
isn't enforced.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


@dataclass(frozen=True)
class Decision:
    ok: bool
    rule: str = ""
    message: str = ""

    @staticmethod
    def allow() -> "Decision":
        return Decision(True)

    @staticmethod
    def refuse(rule: str, message: str) -> "Decision":
        return Decision(False, rule, message)


# --- helpers ---------------------------------------------------------------

def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _valid_time(hhmm: str) -> bool:
    try:
        h, m = hhmm.split(":")
        return len(h) == 2 and len(m) == 2 and 0 <= int(h) < 24 and 0 <= int(m) < 60
    except ValueError:
        return False


def _valid_date(s: str) -> bool:
    try:
        date.fromisoformat(s)
        return True
    except (ValueError, TypeError):
        return False


def fmt_time(hhmm: str) -> str:
    """'14:00' -> '2pm', '09:30' -> '9:30am'. Works on Windows too (no %-I)."""
    h, m = (int(x) for x in hhmm.split(":"))
    suffix = "am" if h < 12 else "pm"
    h12 = h % 12 or 12
    return f"{h12}{suffix}" if m == 0 else f"{h12}:{m:02d}{suffix}"


def job_window(job: dict) -> tuple[int, int]:
    start = _minutes(job["start"])
    return start, start + int(round(float(job["duration_hours"]) * 60))


# --- reschedule --------------------------------------------------------------

def check_reschedule(
    job: dict,
    tech: dict,
    customer: dict,
    tech_jobs: list[dict],
    new_date: str,
    new_start: str,
    today: date,
) -> Decision:
    """tech_jobs = all jobs assigned to this tech (any date); the job itself is skipped."""
    if job.get("status") != "scheduled":
        return Decision.refuse("job_not_scheduled", f"Job {job['id']} is {job.get('status')}; only scheduled jobs can move.")
    if not _valid_date(new_date):
        return Decision.refuse("invalid_date", f"'{new_date}' is not a valid date (use YYYY-MM-DD).")
    if not _valid_time(new_start):
        return Decision.refuse("invalid_time", f"'{new_start}' is not a valid time (use HH:MM, 24-hour).")

    d = date.fromisoformat(new_date)
    if d < today:
        return Decision.refuse("date_in_past", "Can't schedule a job in the past.")
    if new_date == job["date"] and new_start == job["start"]:
        return Decision.refuse("no_change", "That's already the job's current date and time.")
    if not customer.get("in_service_area", True):
        return Decision.refuse("out_of_service_area", f"{customer['name']}'s address is outside the service area.")

    day = WEEKDAYS[d.weekday()]
    if day not in tech.get("working_days", []):
        return Decision.refuse("tech_not_working", f"{tech['name']} doesn't work on {day}.")

    moved = dict(job, date=new_date, start=new_start)
    start, end = job_window(moved)
    if start < _minutes(tech["work_start"]) or end > _minutes(tech["work_end"]):
        return Decision.refuse(
            "outside_working_hours",
            f"{tech['name']} works {fmt_time(tech['work_start'])}–{fmt_time(tech['work_end'])}; "
            f"this job would run {fmt_time(new_start)} for {job['duration_hours']}h.",
        )

    for other in tech_jobs:
        if other["id"] == job["id"] or other.get("status") != "scheduled" or other["date"] != new_date:
            continue
        o_start, o_end = job_window(other)
        if start < o_end and o_start < end:
            return Decision.refuse(
                "double_booking",
                f"{tech['name']} is already booked {day} {fmt_time(other['start'])}–"
                f"{fmt_time(_hhmm(o_end))} (job {other['id']}).",
            )
    return Decision.allow()


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


# --- discount ----------------------------------------------------------------

def check_discount(invoice: dict, percent: float, reason: str, cap_pct: float) -> Decision:
    if invoice.get("status") != "unpaid":
        return Decision.refuse("invoice_not_unpaid", f"Invoice {invoice['id']} is {invoice.get('status')}; discounts apply to unpaid invoices only.")
    try:
        percent = float(percent)
    except (TypeError, ValueError):
        return Decision.refuse("invalid_percent", "Discount must be a number.")
    if percent <= 0:
        return Decision.refuse("invalid_percent", "Discount must be more than 0%.")
    if not (reason or "").strip():
        return Decision.refuse("reason_required", "Add a reason for the discount.")
    current = float(invoice.get("discount_pct") or 0)
    if current + percent > cap_pct + 1e-9:
        left = max(cap_pct - current, 0)
        extra = f"this invoice already has {current:g}%" if current else f"{percent:g}% is over the cap"
        tail = f" (up to {left:g}% more is allowed)." if left > 0 else "."
        return Decision.refuse("discount_cap", f"Discounts are capped at {cap_pct:g}% per invoice; {extra}{tail}")
    return Decision.allow()


# --- payment reminder --------------------------------------------------------

def check_reminder(invoice: dict, template: str, templates: dict, today: date, spacing_days: int) -> Decision:
    if template not in templates:
        return Decision.refuse("unknown_template", f"Unknown template '{template}'. Allowed: {', '.join(sorted(templates))}.")
    if invoice.get("status") != "unpaid":
        return Decision.refuse("invoice_not_unpaid", f"Invoice {invoice['id']} is already {invoice.get('status')}.")
    if date.fromisoformat(invoice["due"]) >= today:
        return Decision.refuse("not_overdue", f"Invoice {invoice['id']} isn't due until {invoice['due']}.")
    last = invoice.get("last_reminder")
    if last:
        days = (today - date.fromisoformat(last)).days
        if days < spacing_days:
            return Decision.refuse(
                "reminder_too_soon",
                f"A reminder was sent {days} day{'s' if days != 1 else ''} ago; wait {spacing_days - days} more.",
            )
    return Decision.allow()


def days_overdue(invoice: dict, today: date) -> int:
    return max((today - date.fromisoformat(invoice["due"])).days, 0)


def amount_due(invoice: dict) -> float:
    return round(float(invoice["amount"]) * (1 - float(invoice.get("discount_pct") or 0) / 100), 2)


def next_weekday(start: date, weekday: int) -> date:
    """First date strictly after `start` falling on weekday (Mon=0)."""
    delta = (weekday - start.weekday()) % 7 or 7
    return start + timedelta(days=delta)
