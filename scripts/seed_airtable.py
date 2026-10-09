"""Load data/seed.json into the Summit Ops Airtable base.

    python scripts/make_seed.py      # regenerate the seed for today first
    python scripts/seed_airtable.py           # refuses if tables already have records
    python scripts/seed_airtable.py --reset   # deletes ALL records in the 5 tables, then loads

--reset deletes data, so it asks you to type the base ID to confirm.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from summit_ops.schema import TABLE_KEYS  # noqa: E402
from summit_ops.store import AirtableStore  # noqa: E402


def main() -> None:
    from pyairtable import Api

    token, base_id = os.getenv("AIRTABLE_TOKEN"), os.getenv("AIRTABLE_BASE_ID")
    if not token or not base_id:
        sys.exit("Set AIRTABLE_TOKEN and AIRTABLE_BASE_ID in .env first.")
    api = Api(token)
    seed = json.loads((ROOT / "data" / "seed.json").read_text(encoding="utf-8"))
    reset = "--reset" in sys.argv

    tables = {key: api.table(base_id, name) for key, name in TABLE_KEYS.items()}
    non_empty = {k: len(t.all()) for k, t in tables.items()}
    if any(non_empty.values()):
        if not reset:
            sys.exit(f"Tables already have records {non_empty}. Re-run with --reset to wipe and reload.")
        typed = input(f"This deletes ALL records in {list(TABLE_KEYS.values())}. Type the base ID to confirm: ")
        if typed.strip() != base_id:
            sys.exit("Not confirmed. Nothing deleted.")
        for key, t in tables.items():
            ids = [r["id"] for r in t.all()]
            if ids:
                t.batch_delete(ids)
                print(f"deleted {len(ids)} records from {TABLE_KEYS[key]}")

    for key in ("customers", "techs", "jobs", "invoices"):
        rows = [AirtableStore._to_airtable(key, r) for r in seed[key]]
        tables[key].batch_create(rows)
        print(f"loaded {len(rows):3d} into {TABLE_KEYS[key]}")
    print(f"Seed anchored to {seed['anchor_date']}. Traps: {json.dumps(seed['traps'])}")


if __name__ == "__main__":
    main()
