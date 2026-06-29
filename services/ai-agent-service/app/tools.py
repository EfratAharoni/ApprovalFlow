"""
Agent tools — callable by the LLM during the agent loop.
Each tool is defined as a Python function + a JSON schema dict for LiteLLM tool_calling.
"""
import json
from decimal import Decimal
from .policy import fetch_policy_clause as _fetch_rule

_FX_RATES: dict[str, Decimal] = {
    "USD": Decimal("1.00"),
    "EUR": Decimal("1.08"),
    "GBP": Decimal("1.27"),
}

# Known vendor set (mirrors submission-service's validation; used by agent tool)
_KNOWN_VENDORS: set[str] = {
    "bistro 19", "atlassian", "the rooftop grill", "dell", "trattoria verde",
    "office depot", "lakeside venue", "hotel adler", "logitech", "datadog",
    "pixelforge", "expoworks", "city cabs", "lufthansa", "rackspace supplies",
}


def fetch_policy_clause(rule_id: str) -> str:
    return _fetch_rule(rule_id)


def lookup_vendor(vendor_name: str) -> dict:
    known = vendor_name.lower().strip() in _KNOWN_VENDORS
    return {"vendor": vendor_name, "known": known, "status": "approved" if known else "unknown"}


def convert_currency(amount: float, from_currency: str) -> dict:
    rate = _FX_RATES.get(from_currency.upper(), Decimal("1.00"))
    usd = float(Decimal(str(amount)) * rate)
    return {"original_amount": amount, "currency": from_currency, "usd_amount": round(usd, 2)}


def execute_tool(name: str, arguments: dict) -> str:
    if name == "fetch_policy_clause":
        return fetch_policy_clause(arguments.get("rule_id", ""))
    if name == "lookup_vendor":
        return json.dumps(lookup_vendor(arguments.get("vendor_name", "")))
    if name == "convert_currency":
        return json.dumps(convert_currency(arguments.get("amount", 0), arguments.get("from_currency", "USD")))
    return f"Unknown tool: {name}"


# JSON schemas for LiteLLM tool_calling
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "fetch_policy_clause",
            "description": "Get the text of a specific expense policy rule by its rule_id (e.g. MEAL-01, SAAS-01, HW-02).",
            "parameters": {
                "type": "object",
                "properties": {
                    "rule_id": {"type": "string", "description": "The stable rule identifier, e.g. 'MEAL-01'"}
                },
                "required": ["rule_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_vendor",
            "description": "Check whether a vendor is known and approved in the company vendor list.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vendor_name": {"type": "string", "description": "The vendor name as submitted"}
                },
                "required": ["vendor_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "convert_currency",
            "description": "Convert an amount from a foreign currency to USD using the submission-date exchange rate.",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {"type": "number", "description": "Amount in the original currency"},
                    "from_currency": {"type": "string", "description": "ISO 4217 currency code, e.g. 'EUR'"},
                },
                "required": ["amount", "from_currency"],
            },
        },
    },
]
