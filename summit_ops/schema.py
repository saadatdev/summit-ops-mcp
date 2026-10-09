"""One place that describes every table and field.

Used by the Airtable setup script (to create tables) and by the Airtable store
(to convert lists/JSON/booleans to and from Airtable's field formats).

Field kinds:
  text      single line text (also used for dates as YYYY-MM-DD and times as HH:MM)
  longtext  long text
  number    number with 2 decimals
  bool      checkbox
  list      list of strings, stored in Airtable as comma-separated text
  json      dict/list, stored in Airtable as JSON in long text

v1 keeps relations as text IDs (customer_id = "C001") instead of Airtable linked
records. That keeps the store simple; switching to linked records is a v2 option.
"""

TABLES: dict[str, list[tuple[str, str]]] = {
    "Customers": [
        ("id", "text"),
        ("name", "text"),
        ("phone", "text"),
        ("email", "text"),
        ("address", "text"),
        ("in_service_area", "bool"),
        ("notes", "longtext"),
    ],
    "Techs": [
        ("id", "text"),
        ("name", "text"),
        ("role", "text"),
        ("skills", "list"),
        ("working_days", "list"),   # e.g. ["Mon","Tue","Wed","Thu","Fri"]
        ("work_start", "text"),     # "08:00"
        ("work_end", "text"),       # "17:00"
    ],
    "Jobs": [
        ("id", "text"),
        ("customer_id", "text"),
        ("tech_id", "text"),
        ("type", "text"),           # repair | install | maintenance
        ("date", "text"),           # YYYY-MM-DD
        ("start", "text"),          # HH:MM
        ("duration_hours", "number"),
        ("status", "text"),         # scheduled | done | cancelled
        ("price", "number"),
    ],
    "Invoices": [
        ("id", "text"),
        ("job_id", "text"),
        ("customer_id", "text"),
        ("amount", "number"),
        ("issued", "text"),         # YYYY-MM-DD
        ("due", "text"),            # YYYY-MM-DD
        ("status", "text"),         # unpaid | paid
        ("discount_pct", "number"),
        ("payment_ref", "text"),
        ("last_reminder", "text"),  # YYYY-MM-DD or empty
    ],
    "Audit Log": [
        ("id", "text"),
        ("ts", "text"),             # ISO timestamp, UTC
        ("actor", "text"),
        ("tool", "text"),
        ("summary", "longtext"),
        ("action_id", "text"),
        ("status", "text"),         # read | previewed | confirmed | refused | expired
        ("rule", "text"),
        ("before", "json"),
        ("after", "json"),
        ("action", "json"),         # the pending action a preview created
    ],
}

TABLE_KEYS = {
    "customers": "Customers",
    "techs": "Techs",
    "jobs": "Jobs",
    "invoices": "Invoices",
    "audit": "Audit Log",
}


def field_kinds(table: str) -> dict[str, str]:
    return dict(TABLES[table])
