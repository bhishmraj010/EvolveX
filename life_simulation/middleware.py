"""
Writes ?date=YYYY-MM-DD (from the header date-picker, or any date-nav
arrow link) into the session, so the chosen day carries across pages
without every view needing its own date-passing logic.
"""
from datetime import date as date_cls


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