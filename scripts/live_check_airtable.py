"""Live check of the Airtable store against the memory store. Not part of pytest (needs network).

    python scripts/seed_airtable.py            # base must hold the same seed as data/seed.json
    python scripts/live_check_airtable.py

What it does (writes to the real base; reset afterwards with seed_airtable.py --reset):
  1. every read tool returns the same result from Airtable and from memory
  2. one reschedule: preview, confirm, job changed in Airtable, audit rows present
  3. one refused action (50% discount on the Garcia invoice): refused row, invoice unchanged
  4. confirm with an unknown action ID and with an expired preview is refused
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from summit_ops.config import Settings, utcnow  # noqa: E402
from summit_ops.ops import Ops  # noqa: E402
from summit_ops.store import AirtableStore, MemoryStore  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail and not ok else ''}")
    return ok


def first_diff(a, b, path="") -> str:
    if type(a) is not type(b) and not (isinstance(a, (int, float)) and isinstance(b, (int, float))):
        return f"{path}: {a!r} != {b!r}"
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if (d := first_diff(a.get(k), b.get(k), f"{path}.{k}")):
                return d
        return ""
    if isinstance(a, list):
        if len(a) != len(b):
            return f"{path}: length {len(a)} != {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            if (d := first_diff(x, y, f"{path}[{i}]")):
                return d
        return ""
    return "" if a == b else f"{path}: {a!r} != {b!r}"


def audit_rows(store: AirtableStore, action_id: str) -> list[dict]:
    return store.find("audit", "action_id", action_id)


def main() -> None:
    token, base_id = os.getenv("AIRTABLE_TOKEN"), os.getenv("AIRTABLE_BASE_ID")
    if not token or not base_id:
        sys.exit("Set AIRTABLE_TOKEN and AIRTABLE_BASE_ID in .env first.")
    seed = json.loads((ROOT / "data" / "seed.json").read_text(encoding="utf-8"))
    settings = Settings(today_override=seed["anchor_date"])
    mem = Ops(MemoryStore(seed), settings)
    air_store = AirtableStore(token, base_id)
    air = Ops(air_store, settings)
    traps = seed["traps"]
    started = time.time()

    # 1. read parity ---------------------------------------------------------
    anchor = seed["anchor_date"]
    days = sorted({j["date"] for j in seed["jobs"] if j["date"] >= anchor})[:6]
    reads = [
        ("search_customers", {"query": q}) for q in ("johnson", "patel", "becker", "555-0103", "nobody")
    ] + [
        ("get_jobs", {}),
        ("get_jobs", {"tech_id": "T1"}),
        ("get_jobs", {"customer_id": "C001"}),
        ("get_jobs", {"date_from": days[0], "date_to": days[-1], "status": "scheduled"}),
    ] + [
        ("get_unpaid_invoices", {"min_days_overdue": n}) for n in (0, 30, 60)
    ] + [
        ("get_schedule", {"day": d}) for d in days
    ] + [("get_schedule", {"day": days[0], "tech_id": "T1"})]
    for tool, args in reads:
        a, b = getattr(mem, tool)(**args), getattr(air, tool)(**args)
        check(f"parity {tool}({args})", a == b, first_diff(a, b))

    # 2. reschedule J002 (Mark Johnson, Mike) into a free slot of Mike's ---------
    job_id = traps["mike_tuesday_10am_mark_johnson"]
    job_before = air_store.get("jobs", job_id)
    target = None
    for d in days:
        if d == job_before["date"]:
            continue
        sched = air.get_schedule(d, "T1")["techs"][0]
        for slot in sched["free_slots"]:
            s, e = slot.split("-")
            if int(e[:2]) * 60 + int(e[3:]) - (int(s[:2]) * 60 + int(s[3:])) >= job_before["duration_hours"] * 60:
                target = (d, s)
                break
        if target:
            break
    check("found a free slot for the reschedule", target is not None)
    prev = air.propose_reschedule(job_id, *target)
    check("reschedule preview", prev.get("status") == "preview", json.dumps(prev))
    job_mid = AirtableStore(token, base_id).get("jobs", job_id)
    check("job unchanged after preview", (job_mid["date"], job_mid["start"]) == (job_before["date"], job_before["start"]))
    done = air.confirm_action(prev["action_id"])
    check("reschedule confirm", done.get("status") == "done", json.dumps(done))
    fresh = AirtableStore(token, base_id)  # no cached record IDs
    job_after = fresh.get("jobs", job_id)
    check("job changed in Airtable", (job_after["date"], job_after["start"]) == target,
          f"{job_after['date']} {job_after['start']}")
    rows = audit_rows(fresh, prev["action_id"])
    p_rows = [r for r in rows if r["tool"] == "propose_reschedule"]
    c_rows = [r for r in rows if r["tool"] == "confirm_action"]
    check("audit: preview row (now marked confirmed, action stored)",
          len(p_rows) == 1 and p_rows[0]["status"] == "confirmed" and p_rows[0]["action"]["type"] == "reschedule",
          json.dumps(p_rows))
    check("audit: confirm row with before/after",
          len(c_rows) == 1 and c_rows[0]["status"] == "confirmed"
          and c_rows[0]["before"] == {"date": job_before["date"], "start": job_before["start"]}
          and c_rows[0]["after"] == {"date": target[0], "start": target[1]}, json.dumps(c_rows))
    again = air.confirm_action(prev["action_id"])
    check("second confirm of same action refused", again.get("rule") == "action_not_pending", json.dumps(again))

    # 3. refused: 50% discount on the Garcia invoice --------------------------
    inv_id = traps["garcia_unpaid_20d"]
    inv_before = air_store.get("invoices", inv_id)
    n_audit = len(air_store.list("audit"))
    ref = air.propose_discount(inv_id, 50, "great customer")
    check("50% discount refused", ref.get("status") == "refused", json.dumps(ref))
    fresh = AirtableStore(token, base_id)
    new_rows = fresh.list("audit")[n_audit:]  # Airtable lists in creation order by default
    refused = [r for r in fresh.list("audit") if r["tool"] == "propose_discount" and inv_id in r["summary"]]
    check("audit: refused row for the discount",
          any(r["status"] == "refused" and r["rule"] == ref.get("rule") for r in refused), json.dumps(refused))
    check("invoice unchanged", fresh.get("invoices", inv_id) == inv_before,
          first_diff(inv_before, fresh.get("invoices", inv_id)))
    check("no action_id issued for the refusal", not any(r["action_id"] for r in refused), json.dumps(new_rows))

    # 4. unknown and expired action IDs ---------------------------------------
    unk = air.confirm_action("act_doesnotexist")
    check("unknown action ID refused", unk.get("rule") == "unknown_action", json.dumps(unk))
    past = Ops(air_store, settings, now=lambda: utcnow() - timedelta(minutes=settings.preview_expiry_minutes + 5))
    old = past.propose_discount(inv_id, 5, "loyalty")
    check("old preview created", old.get("status") == "preview", json.dumps(old))
    exp = air.confirm_action(old["action_id"])
    check("expired preview refused", exp.get("rule") == "preview_expired", json.dumps(exp))
    fresh = AirtableStore(token, base_id)
    check("invoice still unchanged after expired confirm", fresh.get("invoices", inv_id) == inv_before)
    exp_rows = audit_rows(fresh, old["action_id"])
    check("audit: preview row marked expired",
          any(r["tool"] == "propose_discount" and r["status"] == "expired" for r in exp_rows), json.dumps(exp_rows))

    n_ok = sum(ok for _, ok, _ in results)
    print(f"\n{n_ok}/{len(results)} checks passed in {time.time() - started:.1f}s")
    sys.exit(0 if n_ok == len(results) else 1)


if __name__ == "__main__":
    main()
