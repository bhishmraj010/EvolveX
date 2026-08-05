"""
Shared "selected date" helper. The header date-picker (see base.html) is the
one global control for "which day am I looking at" — SelectedDateMiddleware
writes any incoming ?date=YYYY-MM-DD into the session, and every date-aware
view (To-Do, Willpower, Diet) reads it back via get_selected_date() instead
of each maintaining its own separate date-parsing logic. This means picking
a date once in the header carries across pages.
"""
from datetime import date as date_cls

from django.utils import timezone


def get_selected_date(request):
    date_str = request.session.get("selected_date")
    if date_str:
        try:
            return date_cls.fromisoformat(date_str)
        except ValueError:
            pass
    return timezone.localdate()