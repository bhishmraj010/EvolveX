"""
subscriptions/decorators.py

Usage in any app's views.py:

    from subscriptions.decorators import premium_required

    @login_required
    @premium_required("AI Roadmap")
    def roadmap_home(request):
        ...

Order matters: keep @login_required on top (outer) so anonymous users
hit the normal login redirect instead of the locked screen.
"""

from functools import wraps
from django.shortcuts import render

from .access import user_can_access_premium


def premium_required(feature_name):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not user_can_access_premium(request.user):
                return render(request, "subscriptions/locked.html", {
                    "feature_name": feature_name,
                })
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator