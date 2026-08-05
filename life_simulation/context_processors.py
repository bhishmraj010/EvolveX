from django.conf import settings
from .date_utils import get_selected_date


def header_date(request):
    """Exposes header_selected_date + header_today to every template so the
    header date-picker in base.html can render on any page, not just the
    date-aware ones."""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}
    from django.utils import timezone
    return {
        "header_selected_date": get_selected_date(request),
        "header_today": timezone.localdate(),
    }


def firebase_config(request):
    """Exposes the Firebase web config (public, non-secret) to login.html
    for the Google Sign-In button, pre-serialized as JSON for safe embedding
    in a <script> tag."""
    import json
    return {"firebase_web_config": json.dumps(settings.FIREBASE_WEB_CONFIG)}


def pending_popup(request):
    """
    Global popup queue -- any view can push ONE popup onto
    request.session['pending_popup'] (a plain dict with a 'type' key), and
    it will render automatically on whichever page the user next loads
    (base.html reads pending_popup_json and shows the matching animated
    popup), then clears itself so it never shows twice.

    Supported 'type' values (see base.html for markup):
      - 'level'         {'type': 'level', 'level': int, 'title': str, 'xp': int|None}
      - 'achievement'   {'type': 'achievement', 'name': str, 'desc': str, 'xp': int|None, 'willpower': int|None}
      - 'subscription'  {'type': 'subscription', 'plan_name': str, 'is_lifetime': bool}

    Usage from any view, right before a redirect/render:
        request.session['pending_popup'] = {'type': 'level', 'level': user.level, 'title': user.title}
    """
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {"pending_popup_json": None}

    data = request.session.pop("pending_popup", None)
    if not data:
        return {"pending_popup_json": None}

    import json
    return {"pending_popup_json": json.dumps(data)}