"""The generated seed has exactly one overlapping pair of jobs: the planted Thursday trap."""
from datetime import date, timedelta

import pytest

from scripts.make_seed import build
from summit_ops.rules import job_window


def overlaps(jobs: list[dict]) -> set[frozenset[str]]:
    found = set()
    for i, a in enumerate(jobs):
        for b in jobs[i + 1:]:
            if a["tech_id"] == b["tech_id"] and a["date"] == b["date"]:
                (s1, e1), (s2, e2) = job_window(a), job_window(b)
                if s1 < e2 and s2 < e1:
                    found.add(frozenset((a["id"], b["id"])))
    return found


# the eval/test anchor plus every weekday position, so the filler is checked on many layouts
@pytest.mark.parametrize("anchor", [date(2026, 10, 12) + timedelta(days=n) for n in range(-3, 11)])
def test_only_the_planted_overlap(anchor):
    data = build(anchor)
    traps = data["traps"]
    assert overlaps(data["jobs"]) == {frozenset((traps["mike_thursday_busy"], traps["mike_thursday_overlap"]))}


def test_planted_overlap_shape():
    data = build(date(2026, 10, 12))
    jobs = {j["id"]: j for j in data["jobs"]}
    busy, planted = jobs[data["traps"]["mike_thursday_busy"]], jobs[data["traps"]["mike_thursday_overlap"]]
    assert (planted["tech_id"], planted["date"], planted["start"], planted["duration_hours"], planted["type"]) == \
        ("T1", busy["date"], "13:00", 1.5, "maintenance")
    assert (busy["start"], busy["duration_hours"]) == ("14:00", 2)
