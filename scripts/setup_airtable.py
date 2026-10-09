"""Create the five Summit Ops tables in an EMPTY Airtable base.

1. In Airtable, create a new base called "Summit Ops" (blank). Copy its ID (starts with "app")
   from the URL into .env as AIRTABLE_BASE_ID.
2. Create a personal access token with scopes:
     data.records:read, data.records:write, schema.bases:read, schema.bases:write
   and access to that base. Put it in .env as AIRTABLE_TOKEN.
3. python scripts/setup_airtable.py
4. python scripts/seed_airtable.py

Tables that already exist are skipped. Airtable creates a default "Table 1" in a new base;
delete it by hand afterwards.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from summit_ops.schema import TABLES  # noqa: E402


def airtable_field(name: str, kind: str) -> dict:
    if kind == "number":
        return {"name": name, "type": "number", "options": {"precision": 2}}
    if kind == "bool":
        return {"name": name, "type": "checkbox", "options": {"icon": "check", "color": "greenBright"}}
    if kind in ("longtext", "json"):
        return {"name": name, "type": "multilineText"}
    return {"name": name, "type": "singleLineText"}  # text, list, dates and times


def main() -> None:
    from pyairtable import Api

    token, base_id = os.getenv("AIRTABLE_TOKEN"), os.getenv("AIRTABLE_BASE_ID")
    if not token or not base_id:
        sys.exit("Set AIRTABLE_TOKEN and AIRTABLE_BASE_ID in .env first.")
    base = Api(token).base(base_id)
    existing = {t.name for t in base.tables(force=True)}
    for name, fields in TABLES.items():
        if name in existing:
            print(f"skip   {name} (already exists)")
            continue
        # the first field becomes the primary field, so "id" must come first
        base.create_table(name, [airtable_field(n, k) for n, k in fields])
        print(f"create {name} ({len(fields)} fields)")
    print("Done. Delete Airtable's default 'Table 1' if it's still there, then run scripts/seed_airtable.py.")


if __name__ == "__main__":
    main()
