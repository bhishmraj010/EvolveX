"""
Shared "selected date" helper. The header date-picker (see base.html) is the
one global control for "which day am I looking at" — SelectedDateMiddleware
writes any incoming ?date=YYYY-MM-DD into the session, and every date-aware
view (To-Do, Willpower, Diet) reads it back via get_selected_date() instead
of each maintaining its own separate date-parsing logic. This means picking
a date once in the header carries across pages.

Auto-reset behaviour: a manually picked date is only remembered for the rest
of that same real-world day. As soon as the wall-clock date changes (e.g. the
user comes back the next morning), the stale selection is dropped and today's
date is used automatically — without this, the app would keep showing
whatever day was last picked forever, forcing a manual date change every day.
"""
from datetime import date as date_cls

from django.utils import timezone

_LAST_SEEN_KEY = "_selected_date_last_seen"
_SELECTED_KEY = "selected_date"


def get_selected_date(request):
    today = timezone.localdate()
    today_str = today.isoformat()

    # 1. An explicit ?date= on THIS request always wins. This is what makes
    #    Prev/Next/date-picker links actually work, regardless of whether
    #    SelectedDateMiddleware already wrote it into the session — the view
    #    no longer depends solely on the middleware having run correctly.
    query_date = request.GET.get("date")
    if query_date:
        try:
            chosen = date_cls.fromisoformat(query_date)
            request.session[_SELECTED_KEY] = query_date
            request.session[_LAST_SEEN_KEY] = today_str
            return chosen
        except ValueError:
            pass  # garbage date param — fall through to normal logic

    # 2. No date on THIS request — auto-reset once per real-world day.
    last_seen = request.session.get(_LAST_SEEN_KEY)
    if last_seen != today_str:
        request.session[_LAST_SEEN_KEY] = today_str
        request.session.pop(_SELECTED_KEY, None)
        return today

    # 3. Otherwise fall back to whatever was picked earlier this session.
    date_str = request.session.get(_SELECTED_KEY)
    if date_str:
        try:
            return date_cls.fromisoformat(date_str)
        except ValueError:
            pass
    return today