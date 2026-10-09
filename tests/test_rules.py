"""Rules tests: pure code, no Claude, no network. Every rule has a pass and a fail case."""
from datetime import date

import pytest

from summit_ops import rules
from summit_ops.templates import TEMPLATES

TODAY = date(2026, 10, 12)  # Monday

MIKE = {"id": "T1", "name": "Mike Ross", "working_days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
        "work_start": "08:00", "work_end": "17:00"}
CUSTOMER = {"id": "C1", "name": "Mark Johnson", "in_service_area": True}
FAR_CUSTOMER = {"id": "C2", "name": "Tom Becker", "in_service_area": False}
JOB = {"id": "J1", "customer_id": "C1", "tech_id": "T1", "date": "2026-10-13", "start": "10:00",
       "duration_hours": 1.5, "status": "scheduled"}
BUSY = {"id": "J2", "customer_id": "C9", "tech_id": "T1", "date": "2026-10-15", "start": "14:00",
        "duration_hours": 2, "status": "scheduled"}


def resched(new_date, new_start, job=JOB, customer=CUSTOMER, others=(BUSY,)):
    return rules.check_reschedule(job, MIKE, customer, [job, *others], new_date, new_start, TODAY)


# ------------------------------------------------------------------ reschedule
@pytest.mark.parametrize("new_date,new_start,rule", [
    ("2026-10-10", "10:00", "date_in_past"),
    ("2026-10-18", "10:00", "tech_not_working"),        # Sunday
    ("2026-10-17", "10:00", "tech_not_working"),        # Saturday
    ("2026-10-14", "07:00", "outside_working_hours"),   # before 8am
    ("2026-10-14", "16:00", "outside_working_hours"),   # 16:00 + 1.5h = 17:30
    ("2026-10-15", "15:00", "double_booking"),          # overlaps 14:00-16:00
    ("2026-10-15", "13:00", "double_booking"),          # 13:00-14:30 overlaps 14:00
    ("2026-10-13", "10:00", "no_change"),
    ("2026-13-01", "10:00", "invalid_date"),
    ("2026-10-14", "25:00", "invalid_time"),
    ("2026-10-14", "3pm", "invalid_time"),
])
def test_reschedule_refusals(new_date, new_start, rule):
    d = resched(new_date, new_start)
    assert not d.ok and d.rule == rule, d


@pytest.mark.parametrize("new_date,new_start", [
    ("2026-10-15", "12:00"),   # 12:00-13:30, ends before 14:00
    ("2026-10-15", "08:00"),   # same day as the busy job, morning
    ("2026-10-14", "15:30"),   # ends exactly 17:00
    ("2026-10-12", "15:00"),   # today is allowed
])
def test_reschedule_allowed(new_date, new_start):
    assert resched(new_date, new_start).ok


def test_reschedule_back_to_back_is_allowed():
    # 12:30-14:00 touches the 14:00 job but doesn't overlap
    assert resched("2026-10-15", "12:30").ok


def test_reschedule_ignores_cancelled_jobs():
    cancelled = dict(BUSY, status="cancelled")
    assert resched("2026-10-15", "14:00", others=(cancelled,)).ok


def test_reschedule_only_scheduled_jobs():
    d = resched("2026-10-14", "10:00", job=dict(JOB, status="done"))
    assert d.rule == "job_not_scheduled"


def test_reschedule_out_of_service_area():
    assert resched("2026-10-14", "10:00", customer=FAR_CUSTOMER).rule == "out_of_service_area"


def test_double_booking_message_names_the_conflict():
    d = resched("2026-10-15", "15:00")
    assert "Thu 2pm–4pm" in d.message and "J2" in d.message


# ------------------------------------------------------------------ discount
INV = {"id": "INV-1", "amount": 400.0, "status": "unpaid", "discount_pct": 0.0, "due": "2026-09-22"}


@pytest.mark.parametrize("invoice,percent,reason,rule", [
    (INV, 50, "goodwill", "discount_cap"),
    (INV, 10.5, "goodwill", "discount_cap"),
    (dict(INV, discount_pct=10.0), 1, "goodwill", "discount_cap"),
    (dict(INV, discount_pct=5.0), 6, "goodwill", "discount_cap"),
    (INV, 5, "", "reason_required"),
    (INV, 5, "   ", "reason_required"),
    (INV, 0, "goodwill", "invalid_percent"),
    (INV, -5, "goodwill", "invalid_percent"),
    (INV, "lots", "goodwill", "invalid_percent"),
    (dict(INV, status="paid"), 5, "goodwill", "invoice_not_unpaid"),
])
def test_discount_refusals(invoice, percent, reason, rule):
    d = rules.check_discount(invoice, percent, reason, 10)
    assert not d.ok and d.rule == rule, d


@pytest.mark.parametrize("invoice,percent", [(INV, 10), (INV, 5), (dict(INV, discount_pct=5.0), 5)])
def test_discount_allowed(invoice, percent):
    assert rules.check_discount(invoice, percent, "late arrival", 10).ok


def test_discount_message_says_what_is_left():
    d = rules.check_discount(dict(INV, discount_pct=4.0), 10, "goodwill", 10)
    assert "6% more" in d.message


# ------------------------------------------------------------------ reminders
@pytest.mark.parametrize("invoice,template,rule", [
    (INV, "angry_letter", "unknown_template"),
    (dict(INV, status="paid"), "friendly_reminder", "invoice_not_unpaid"),
    (dict(INV, due="2026-10-20"), "friendly_reminder", "not_overdue"),
    (dict(INV, due="2026-10-12"), "friendly_reminder", "not_overdue"),
    (dict(INV, last_reminder="2026-10-10"), "friendly_reminder", "reminder_too_soon"),
    (dict(INV, last_reminder="2026-10-06"), "friendly_reminder", "reminder_too_soon"),
])
def test_reminder_refusals(invoice, template, rule):
    d = rules.check_reminder(invoice, template, TEMPLATES, TODAY, 7)
    assert not d.ok and d.rule == rule, d


@pytest.mark.parametrize("invoice", [INV, dict(INV, last_reminder="2026-10-05"), dict(INV, last_reminder=None)])
def test_reminder_allowed(invoice):
    assert rules.check_reminder(invoice, "second_reminder", TEMPLATES, TODAY, 7).ok


# ------------------------------------------------------------------ helpers
def test_amount_due_and_days_overdue():
    assert rules.amount_due(dict(INV, discount_pct=10.0)) == 360.0
    assert rules.days_overdue(INV, TODAY) == 20


@pytest.mark.parametrize("hhmm,text", [("14:00", "2pm"), ("09:30", "9:30am"), ("00:00", "12am"), ("12:15", "12:15pm")])
def test_fmt_time(hhmm, text):
    assert rules.fmt_time(hhmm) == text
