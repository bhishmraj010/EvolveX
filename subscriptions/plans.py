"""
subscriptions/plans.py

Single source of truth for plan pricing, in both USD and INR, plus the
launch-promo logic (buy before 19 Aug 2026 -> bonus duration / lifetime).
"""

from datetime import date

PROMO_CUTOFF_DATE = date(2026, 8, 19)

# Backward-compat alias — some older views (e.g. home/views.py) import this
# name instead of PROMO_CUTOFF_DATE. Keep both in sync.
PROMO_DEADLINE = PROMO_CUTOFF_DATE

PLANS = {
    "monthly": {
        "name": "Monthly Plan",
        "tagline": "Perfect for short term",
        "icon": "calendar-days",
        "duration_days": 30,
        "is_lifetime": False,
        # Monthly has no launch promo — always billed as-is.
        "promo_duration_days": None,
        "promo_is_lifetime": False,
        "prices": {"USD": 7.99, "INR": 499},
    },
    "quarterly": {
        "name": "3 Months Plan",
        "tagline": "Great for consistent growth",
        "icon": "clock",
        "duration_days": 90,
        "is_lifetime": False,
        "promo_duration_days": 365,   # buy before cutoff -> 1 full year
        "promo_is_lifetime": False,
        "prices": {"USD": 14.99, "INR": 999},
    },
    "yearly": {
        "name": "Annual Plan",
        "tagline": "Best for long term success",
        "icon": "crown",
        "duration_days": 365,
        "is_lifetime": False,
        "promo_duration_days": None,
        "promo_is_lifetime": True,    # buy before cutoff -> lifetime
        "prices": {"USD": 49.00, "INR": 2999},
    },
}

CURRENCY_SYMBOLS = {"USD": "$", "INR": "₹"}


def promo_is_active():
    return date.today() < PROMO_CUTOFF_DATE


def get_plan_context(plan_code, currency="USD"):
    """Everything needed to (a) display a plan card and (b) create a
    payment order for it, in one dict."""
    cfg = PLANS[plan_code]
    active = promo_is_active()
    price = cfg["prices"].get(currency, cfg["prices"]["USD"])

    effective_is_lifetime = cfg["is_lifetime"] or (active and cfg["promo_is_lifetime"])
    effective_duration_days = cfg["duration_days"]
    if active and cfg["promo_duration_days"]:
        effective_duration_days = cfg["promo_duration_days"]

    return {
        "code": plan_code,
        "name": cfg["name"],
        "tagline": cfg["tagline"],
        "icon": cfg["icon"],
        "price": price,
        "currency": currency,
        "currency_symbol": CURRENCY_SYMBOLS.get(currency, "$"),
        "promo_active": active and bool(cfg["promo_duration_days"] or cfg["promo_is_lifetime"]),
        "effective_is_lifetime": effective_is_lifetime,
        "effective_duration_days": None if effective_is_lifetime else effective_duration_days,
    }


def all_plans_context(currency="USD"):
    return [get_plan_context(code, currency) for code in PLANS]