from decimal import Decimal

# FX rates are embedded in sample-invoices.json; in production these would
# come from a live feed. For now we use a static lookup matching the fixtures.
_FX_RATES: dict[str, Decimal] = {
    "USD": Decimal("1.00"),
    "EUR": Decimal("1.08"),
    "GBP": Decimal("1.27"),
}


def to_usd(amount: Decimal, currency: str) -> Decimal:
    rate = _FX_RATES.get(currency.upper())
    if rate is None:
        raise ValueError(f"Unknown currency: {currency}")
    return (amount * rate).quantize(Decimal("0.01"))
