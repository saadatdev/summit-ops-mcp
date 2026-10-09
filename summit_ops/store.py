"""Data access. Two interchangeable stores with the same small interface:

  MemoryStore   - loads data/seed.json into memory. Used by tests, evals and
                  offline demos. Every process starts from a clean copy.
  AirtableStore - reads and writes the "Summit Ops" Airtable base.

Records are plain dicts with an "id" key (our ID like "J014", not Airtable's
record ID). Table names are the keys in schema.TABLE_KEYS:
customers, techs, jobs, invoices, audit.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Protocol

from .schema import TABLE_KEYS, field_kinds


class Store(Protocol):
    def list(self, table: str) -> list[dict]: ...
    def get(self, table: str, record_id: str) -> dict | None: ...
    def find(self, table: str, field: str, value: str) -> list[dict]: ...
    def update(self, table: str, record_id: str, fields: dict) -> dict: ...
    def append(self, table: str, record: dict) -> dict: ...


class MemoryStore:
    def __init__(self, data: dict[str, list[dict]]):
        self._data = {k: copy.deepcopy(data.get(k, [])) for k in TABLE_KEYS}

    @classmethod
    def from_seed(cls, path: str | Path) -> "MemoryStore":
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f))

    def list(self, table: str) -> list[dict]:
        return copy.deepcopy(self._data[table])

    def get(self, table: str, record_id: str) -> dict | None:
        for r in self._data[table]:
            if r["id"] == record_id:
                return copy.deepcopy(r)
        return None

    def find(self, table: str, field: str, value: str) -> list[dict]:
        return [copy.deepcopy(r) for r in self._data[table] if r.get(field) == value]

    def update(self, table: str, record_id: str, fields: dict) -> dict:
        for r in self._data[table]:
            if r["id"] == record_id:
                r.update(copy.deepcopy(fields))
                return copy.deepcopy(r)
        raise KeyError(f"{table}/{record_id} not found")

    def append(self, table: str, record: dict) -> dict:
        self._data[table].append(copy.deepcopy(record))
        return copy.deepcopy(record)


class AirtableStore:
    """Thin wrapper over pyairtable. Converts list/json/bool fields both ways.

    Needs AIRTABLE_TOKEN (scopes: data.records:read, data.records:write) and
    AIRTABLE_BASE_ID. Run scripts/setup_airtable.py first to create the tables.
    """

    def __init__(self, token: str, base_id: str):
        from pyairtable import Api

        self._api = Api(token)
        self._base_id = base_id
        self._rec_ids: dict[tuple[str, str], str] = {}  # (table, our id) -> Airtable record id

    def _table(self, table: str):
        return self._api.table(self._base_id, TABLE_KEYS[table])

    # --- conversion ---------------------------------------------------------
    @staticmethod
    def _to_airtable(table: str, record: dict) -> dict:
        kinds = field_kinds(TABLE_KEYS[table])
        out = {}
        for k, v in record.items():
            kind = kinds.get(k)
            if kind is None:
                continue
            if kind == "list":
                out[k] = ",".join(v or [])
            elif kind == "json":
                out[k] = json.dumps(v) if v is not None else ""
            elif kind == "bool":
                out[k] = bool(v)
            elif v is None:
                out[k] = None
            else:
                out[k] = v
        return out

    @staticmethod
    def _from_airtable(table: str, fields: dict) -> dict:
        kinds = field_kinds(TABLE_KEYS[table])
        out = {}
        for k, kind in kinds.items():
            v = fields.get(k)
            if kind == "list":
                out[k] = [s.strip() for s in v.split(",") if s.strip()] if v else []
            elif kind == "json":
                out[k] = json.loads(v) if v else None
            elif kind == "bool":
                out[k] = bool(v)
            elif kind == "number":
                out[k] = v if v is not None else 0
            else:
                out[k] = v if v is not None else ""
        return out

    # --- interface ----------------------------------------------------------
    def list(self, table: str) -> list[dict]:
        rows = []
        for rec in self._table(table).all():
            row = self._from_airtable(table, rec["fields"])
            self._rec_ids[(table, row["id"])] = rec["id"]
            rows.append(row)
        return rows

    def _rec_id(self, table: str, record_id: str) -> str | None:
        key = (table, record_id)
        if key not in self._rec_ids:
            safe = record_id.replace("'", "\\'")
            match = self._table(table).first(formula=f"{{id}}='{safe}'")
            if not match:
                return None
            self._rec_ids[key] = match["id"]
        return self._rec_ids[key]

    def get(self, table: str, record_id: str) -> dict | None:
        rid = self._rec_id(table, record_id)
        if not rid:
            return None
        return self._from_airtable(table, self._table(table).get(rid)["fields"])

    def find(self, table: str, field: str, value: str) -> list[dict]:
        """Records where field == value, filtered by Airtable (no full-table read)."""
        from pyairtable.formulas import match

        rows = []
        for rec in self._table(table).all(formula=match({field: value})):
            row = self._from_airtable(table, rec["fields"])
            self._rec_ids[(table, row["id"])] = rec["id"]
            rows.append(row)
        return rows

    def update(self, table: str, record_id: str, fields: dict) -> dict:
        rid = self._rec_id(table, record_id)
        if not rid:
            raise KeyError(f"{table}/{record_id} not found")
        rec = self._table(table).update(rid, self._to_airtable(table, fields))
        return self._from_airtable(table, rec["fields"])

    def append(self, table: str, record: dict) -> dict:
        rec = self._table(table).create(self._to_airtable(table, record))
        self._rec_ids[(table, record["id"])] = rec["id"]
        return self._from_airtable(table, rec["fields"])


def make_store(settings) -> Store:
    if settings.store == "airtable":
        token, base = os.getenv("AIRTABLE_TOKEN"), os.getenv("AIRTABLE_BASE_ID")
        if not token or not base:
            raise RuntimeError("STORE=airtable needs AIRTABLE_TOKEN and AIRTABLE_BASE_ID in .env")
        return AirtableStore(token, base)
    return MemoryStore.from_seed(settings.seed_path)
