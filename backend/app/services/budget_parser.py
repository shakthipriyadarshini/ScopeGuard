"""Reads a budget straight from the description text. No AI here.

It only trusts what the text literally says. Currencies: USD and INR.
Nothing is ever converted between currencies.
"""
import re

# One number: 500, 1500.50, 40,000 (also Indian grouping like 1,50,000)
NUM = r"\d+(?:,\d{2,3})*(?:\.\d+)?"
# Currency marker BEFORE the number: $500, US$500, USD 500, ₹40,000, Rs. 40,000, INR 40000
PREFIX = r"(?P<pre>US\$|\$|₹|(?<![A-Za-z])(?:USD|INR|Rs\.?))"
# Currency marker AFTER the number: 500 USD, 500 US dollars, 40000 rupees, 40000 Rs
SUFFIX = r"(?P<post>USD|INR|US\s*dollars?|dollars?|rupees?|Rs)(?![A-Za-z])"
AMOUNT = rf"(?:{PREFIX}\s*)?(?P<num>{NUM})(?:\s*{SUFFIX})?"

# Small words allowed between "budget" and the amount: "budget is around $500"
LINK = r"(?:\s*(?:is|of|:|=|-|will be|would be|at|around|about|approximately|approx\.?|roughly|~|only|just|up to))*\s*"
BUDGET_THEN_AMOUNT = re.compile(rf"budget(?:ed)?{LINK}{AMOUNT}", re.IGNORECASE)  # "Budget is $500"
AMOUNT_THEN_BUDGET = re.compile(rf"{AMOUNT}\s*(?:total\s+|overall\s+|fixed\s+)?budget", re.IGNORECASE)  # "a $500 budget"
ANY_AMOUNT = re.compile(AMOUNT, re.IGNORECASE)

# "5k", "2 lakh", "1 million": unclear size, so we do not read them as a budget
SCALE_AFTER = re.compile(r"\s*(?:k|m)\b|\s*(?:lakhs?|lacs?|crores?|thousand|million)\b", re.IGNORECASE)
# "3 weeks", "20 pages": a plain number followed by these is not money
UNIT_AFTER = re.compile(r"\s*(?:days?|weeks?|months?|years?|hours?|pages?|screens?|%|percent)", re.IGNORECASE)

CURRENCIES = {
    "$": "USD", "us$": "USD", "usd": "USD", "dollar": "USD", "dollars": "USD",
    "usdollar": "USD", "usdollars": "USD",
    "₹": "INR", "rs": "INR", "inr": "INR", "rupee": "INR", "rupees": "INR",
}


def _currency_of(marker):
    """'Rs.' -> 'INR', 'US dollars' -> 'USD', None -> None."""
    if not marker:
        return None
    return CURRENCIES.get(re.sub(r"[\s.]", "", marker.lower()))


def _read_amount(match, text):
    """Return (value, currency or None) for a regex match, or None if it is not a usable amount."""
    marker = match.group("pre") or match.group("post")
    after = text[match.end():]
    if SCALE_AFTER.match(after):
        return None
    if not marker and UNIT_AFTER.match(after):
        return None
    value = float(match.group("num").replace(",", ""))
    if value <= 0:
        return None
    return value, _currency_of(marker)


def find_budget(text):
    """Return (amount, currency) if the text clearly states ONE budget, else None.

    A number with no currency marker means USD (the app's currency).
    If the text names two different budgets, we return None instead of guessing.
    """
    found = set()
    for pattern in (BUDGET_THEN_AMOUNT, AMOUNT_THEN_BUDGET):
        for match in pattern.finditer(text):
            amount = _read_amount(match, text)
            if amount:
                found.add((amount[0], amount[1] or "USD"))
    return found.pop() if len(found) == 1 else None


def explicit_currency(text, value):
    """Currency written next to this number in the text ($, ₹, USD...), or None."""
    for match in ANY_AMOUNT.finditer(text):
        amount = _read_amount(match, text)
        if amount and amount[1] and amount[0] == value:
            return amount[1]
    return None


def reconcile_budget(model_amount, text):
    """Decide the final (amount, currency) from the model's answer and the text.

    1. The text clearly states one budget -> use it (fixes a missed "$500" or a wrong currency).
    2. Otherwise keep the model's amount ONLY if that number is written with a currency
       marker in the text. Anything else is treated as invented -> (None, None).
    """
    found = find_budget(text)
    if found:
        return found
    if model_amount is not None:
        currency = explicit_currency(text, model_amount)
        if currency:
            return model_amount, currency
    return None, None