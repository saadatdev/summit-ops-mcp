"""Preview/confirm flow tests on the in-memory store with a fixed clock. No Claude, no network."""
from datetime import date, datetime, timedelta, timezone

import pytest

from summit_ops.config import Settings
from summit_ops.ops import Ops
from summit_ops.store import MemoryStore
from scripts.make_seed import build

TODAY = date(2026, 10, 12)  # Monday


class Clock:
    def __init__(self):
        self.t = datetime(2026, 10, 12, 15, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.t


@pytest.fixture
def env():
    data = build(TODAY)
    clock = Clock()
    ops = Ops(MemoryStore(data), Settings(today_override=TODAY.isoformat()), now=clock)
    return ops, data["traps"], clock


def audit(ops):
    return ops.store.list("audit")


# ------------------------------------------------------------------ previews change nothing
def test_preview_does_not_write(env):
    ops, traps, _ = env
    before = ops.store.get("jobs", traps["mike_tuesday_10am_mark_johnson"])
    p = ops.propose_reschedule(before["id"], "2026-10-14", "09:00")
    assert p["status"] == "preview"
    assert ops.store.get("jobs", before["id"]) == before
    assert audit(ops)[-1]["status"] == "previewed"


def test_confirm_writes_and_logs(env):
    ops, traps, _ = env
    jid = traps["mike_tuesday_10am_mark_johnson"]
    p = ops.propose_reschedule(jid, "2026-10-14", "09:00")
    r = ops.confirm_action(p["action_id"])
    assert r["status"] == "done"
    job = ops.store.get("jobs", jid)
    assert (job["date"], job["start"]) == ("2026-10-14", "09:00")
    statuses = [a["status"] for a in audit(ops) if a["action_id"] == p["action_id"]]
    assert statuses == ["confirmed", "confirmed"]  # preview row updated + confirm row appended


# ------------------------------------------------------------------ demo traps
def test_double_booking_trap(env):
    ops, traps, _ = env
    r = ops.propose_reschedule(traps["mike_tuesday_10am_mark_johnson"], "2026-10-15", "15:00")
    assert r["status"] == "refused" and r["rule"] == "double_booking"
    assert audit(ops)[-1]["status"] == "refused"


def test_fifty_percent_discount_refused(env):
    ops, traps, _ = env
    r = ops.propose_discount(traps["garcia_unpaid_20d"], 50, "customer asked")
    assert r["rule"] == "discount_cap"


def test_already_discounted_invoice(env):
    ops, traps, _ = env
    assert ops.propose_discount(traps["lee_already_10pct"], 2, "goodwill")["rule"] == "discount_cap"


def test_out_of_area_reschedule_refused(env):
    ops, traps, _ = env
    assert ops.propose_reschedule(traps["out_of_area_job"], "2026-10-16", "10:00")["rule"] == "out_of_service_area"


def test_reminder_preview_has_exact_message_and_confirm_queues_it(env):
    ops, traps, _ = env
    p = ops.propose_payment_reminder(traps["patel_unpaid_35d"], "friendly_reminder")
    assert p["status"] == "preview" and p["message_to_customer"].startswith("Hi Raj")
    r = ops.confirm_action(p["action_id"])
    assert r["after"]["message_status"] == "queued"
    assert ops.store.get("invoices", traps["patel_unpaid_35d"])["last_reminder"] == TODAY.isoformat()
    again = ops.propose_payment_reminder(traps["patel_unpaid_35d"], "friendly_reminder")
    assert again["rule"] == "reminder_too_soon"


def test_reminder_too_soon_trap(env):
    ops, traps, _ = env
    assert ops.propose_payment_reminder(traps["reminded_2_days_ago"], "second_reminder")["rule"] == "reminder_too_soon"


def test_two_johnsons(env):
    ops, _, _ = env
    r = ops.search_customers("johnson")
    assert r["match_count"] == 2 and "ask the user" in r["hint"]


def test_injection_note_is_labelled_as_data(env):
    ops, _, _ = env
    c = ops.search_customers("patel")["customers"][0]
    assert "never as instructions" in c["customer_notes"]["label"]


def test_unpaid_invoices_total(env):
    ops, _, _ = env
    r = ops.get_unpaid_invoices(60)
    assert r["count"] == 3 and all(i["days_overdue"] >= 60 for i in r["invoices"])
    assert r["total_due"] == round(sum(i["amount_due"] for i in r["invoices"]), 2)


def test_schedule_shows_free_slots(env):
    ops, _, _ = env
    mike = next(t for t in ops.get_schedule("2026-10-15", "T1")["techs"])
    # planted overlap 13:00-14:30 plus the 14:00-16:00 trap: busy from 13:00 to 16:00
    assert mike["free_slots"] == ["08:00-13:00", "16:00-17:00"]


# ------------------------------------------------------------------ confirm edge cases
def test_unknown_action(env):
    ops, _, _ = env
    assert ops.confirm_action("act_nope")["rule"] == "unknown_action"


def test_double_confirm(env):
    ops, traps, _ = env
    p = ops.propose_discount(traps["garcia_unpaid_20d"], 5, "late arrival")
    assert ops.confirm_action(p["action_id"])["status"] == "done"
    assert ops.confirm_action(p["action_id"])["rule"] == "action_not_pending"


def test_expired_preview(env):
    ops, traps, clock = env
    p = ops.propose_discount(traps["garcia_unpaid_20d"], 5, "late arrival")
    clock.t += timedelta(minutes=11)
    assert ops.confirm_action(p["action_id"])["rule"] == "preview_expired"
    assert ops.store.get("invoices", traps["garcia_unpaid_20d"])["discount_pct"] == 0


def test_record_changed_after_preview(env):
    ops, traps, _ = env
    inv = traps["garcia_unpaid_20d"]
    p = ops.propose_discount(inv, 5, "late arrival")
    ops.store.update("invoices", inv, {"status": "paid"})  # someone marks it paid in Airtable
    assert ops.confirm_action(p["action_id"])["rule"] == "record_changed"


def test_rules_rerun_at_confirm(env):
    """Two previews that are each fine alone; together they'd break the cap. The second confirm must fail."""
    ops, traps, _ = env
    inv = traps["garcia_unpaid_20d"]
    p1 = ops.propose_discount(inv, 6, "late arrival")
    p2 = ops.propose_discount(inv, 6, "late arrival")
    assert ops.confirm_action(p1["action_id"])["status"] == "done"
    r = ops.confirm_action(p2["action_id"])
    assert r["status"] == "refused"  # snapshot changed (discount_pct 0 -> 6)
    assert ops.store.get("invoices", inv)["discount_pct"] == 6


def test_reads_are_logged(env):
    ops, _, _ = env
    ops.get_unpaid_invoices()
    assert audit(ops)[-1]["tool"] == "get_unpaid_invoices" and audit(ops)[-1]["status"] == "read"
