"""Approved customer message templates. Claude can pick one; it can never write free text.

Placeholders are filled by code from the invoice and customer records.
"""

TEMPLATES: dict[str, str] = {
    "friendly_reminder": (
        "Hi {first_name}, this is {company}. A quick reminder that invoice {invoice_id} "
        "for ${amount_due:,.2f} was due on {due}. You can reply to this message if you have "
        "any questions. Thank you!"
    ),
    "second_reminder": (
        "Hi {first_name}, {company} here. Invoice {invoice_id} for ${amount_due:,.2f} is now "
        "{days_overdue} days past due. Please arrange payment or reply so we can help. Thank you."
    ),
}


def render(template: str, **values) -> str:
    return TEMPLATES[template].format(**values)
