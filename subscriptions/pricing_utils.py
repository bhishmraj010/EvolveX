"""
subscriptions/pricing_utils.py

Detect whether to show INR or USD pricing.

Priority order:
  1. Phone number country code (if the User model ever gets a phone field —
     safe no-op today since none exists yet)
  2. Cached value in session (avoid hitting the geo-IP API every request)
  3. IP geolocation (ip-api.com — free, no API key, ~45 req/min limit)
  4. settings.PRICING_DEFAULT_CURRENCY, or "USD" if not set
"""

import requests
from django.conf import settings


def _currency_from_phone(phone_number):
    if not phone_number:
        return None
    p = str(phone_number).strip().replace(" ", "").replace("-", "")
    if p.startswith("+91"):
        return "INR"
    if p.startswith("91") and len(p) in (12, 13):
        return "INR"
    return None


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def _currency_from_ip(request):
    ip = _client_ip(request)
    if not ip or ip in ("127.0.0.1", "::1") or ip.startswith("192.168.") or ip.startswith("10."):
        return None  # local/private IP — no useful geo data (dev environment)

    try:
        resp = requests.get(
            f"http://ip-api.com/json/{ip}",
            params={"fields": "status,countryCode"},
            timeout=2,
        )
        data = resp.json()
        if data.get("status") == "success":
            return "INR" if data.get("countryCode") == "IN" else "USD"
    except Exception as e:
        print(f"[WARN] IP geolocation failed for pricing: {e}")

    return None


def get_pricing_currency(request, phone_number=None):
    from_phone = _currency_from_phone(phone_number)
    if from_phone:
        return from_phone

    cached = request.session.get("pricing_currency")
    if cached:
        return cached

    detected = _currency_from_ip(request)
    if detected:
        # Only cache a SUCCESSFUL detection. If the geo-IP lookup failed
        # (network hiccup, rate limit, etc.) we fall through to the default
        # below without caching it, so the next request gets to retry
        # instead of being stuck on the fallback for the whole session.
        request.session["pricing_currency"] = detected
        return detected

    return getattr(settings, "PRICING_DEFAULT_CURRENCY", "USD")