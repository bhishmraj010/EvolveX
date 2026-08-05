"""
subscription/access.py

Single source of truth for "can this user use a premium (locked) feature?"

Rule (as decided): Level 1 is a free trial of the whole app — every
feature works with no subscription. The moment a user crosses into
Level 2+, AI Analyzer / AI Roadmap / Diet Tracker / Boss Fights all
require an active subscription (monthly, 3-month, or lifetime).
"""

from .models import UserSubscription

# Users at or below this level get every feature for free, no exceptions.
FREE_LEVEL_CAP = 1


def user_can_access_premium(user):
    """
    True  -> user may use locked features (AI Analyzer, AI Roadmap,
             Diet Tracker, Boss Fights)
    False -> show the upsell/locked screen instead
    """
    if not user.is_authenticated:
        return False

    # Level 1 users always pass, regardless of subscription status.
    if getattr(user, "level", 1) <= FREE_LEVEL_CAP:
        return True

    # Level 2+ needs a currently-active subscription (monthly/quarterly
    # both expire via expires_at; yearly-turned-lifetime never expires).
    return UserSubscription.get_active_for_user(user) is not None