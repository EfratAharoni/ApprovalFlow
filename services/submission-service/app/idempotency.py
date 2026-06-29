import hashlib
from decimal import Decimal


# Idempotency key = SHA256(vendor + amount_cents + invoiceNumber + date)
# Server-side hash: no client coordination needed; works for re-submissions
# of the same real-world invoice even from different clients.
def compute_idempotency_key(
    vendor: str,
    amount: Decimal,
    invoice_number: str,
    date: str,
) -> str:
    amount_cents = str(int(amount * 100))
    raw = f"{vendor.strip().lower()}|{amount_cents}|{invoice_number.strip()}|{date.strip()}"
    return hashlib.sha256(raw.encode()).hexdigest()
