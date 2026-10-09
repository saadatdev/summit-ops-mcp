"""Settings for the Summit Ops MCP server.

Business limits live here, not in prompts and not scattered through the code,
so they can change without touching the rules.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    # Business rules
    discount_cap_pct: float = 10.0          # max total discount per invoice
    reminder_spacing_days: int = 7          # min days between reminders on one invoice
    preview_expiry_minutes: int = 10        # a preview must be confirmed within this window

    # Runtime
    store: str = "memory"                   # "memory" (seed.json) or "airtable"
    seed_path: str = "data/seed.json"
    actor: str = "owner"                    # who is using the server (v1: one role)
    company_name: str = "Summit Heating & Air"
    today_override: str | None = None       # YYYY-MM-DD, for demos and evals

    def today(self) -> date:
        if self.today_override:
            return date.fromisoformat(self.today_override)
        return date.today()


def load_settings() -> Settings:
    return Settings(
        discount_cap_pct=float(os.getenv("DISCOUNT_CAP_PCT", "10")),
        reminder_spacing_days=int(os.getenv("REMINDER_SPACING_DAYS", "7")),
        preview_expiry_minutes=int(os.getenv("PREVIEW_EXPIRY_MINUTES", "10")),
        store=os.getenv("STORE", "memory"),
        seed_path=os.getenv("SEED_PATH", "data/seed.json"),
        actor=os.getenv("ACTOR", "owner"),
        company_name=os.getenv("COMPANY_NAME", "Summit Heating & Air"),
        today_override=os.getenv("TODAY") or None,
    )


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
