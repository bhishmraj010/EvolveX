"""
Writes ?date=YYYY-MM-DD (from the header date-picker, or any date-nav
arrow link) into the session, so the chosen day carries across pages
without every view needing its own date-passing logic.
"""
from datetime import date as date_cls
import zoneinfo
from django.utils import timezone as dj_timezone

class SelectedDateMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        date_str = request.GET.get("date")
        if date_str:
            try:
                date_cls.fromisoformat(date_str)
                request.session["selected_date"] = date_str
            except ValueError:
                pass
        return self.get_response(request)

class UserTimezoneMiddleware:
    """
    Activates the correct timezone for every request so that timezone.now(),
    template {% now %}, and anything using Django's timezone-aware datetimes
    (streaks, daily resets, deadlines, etc.) are computed in the user's own
    local time instead of the server's fixed TIME_ZONE.
 
    Resolution order:
      1. Logged-in user's saved `timezone` field (set once via the
         `set_timezone` view below, called by tz-detect.js on every page load
         if it differs from what's stored).
      2. A `tz` cookie (set client-side by tz-detect.js) for anonymous users
         or before the DB value has been saved.
      3. Falls back to Django's default TIME_ZONE (settings.TIME_ZONE).
    """
 
    def __init__(self, get_response):
        self.get_response = get_response
 
    def __call__(self, request):
        tz_name = None
 
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            tz_name = getattr(user, "timezone", None)
 
        if not tz_name:
            tz_name = request.COOKIES.get("tz")
 
        if tz_name:
            try:
                dj_timezone.activate(zoneinfo.ZoneInfo(tz_name))
            except Exception:
                # Unknown/garbled tz string (bad cookie, tampered value, etc.)
                # — silently fall back to the server default rather than 500.
                dj_timezone.deactivate()
        else:
            dj_timezone.deactivate()  # uses settings.TIME_ZONE
 
        response = self.get_response(request)
        return response