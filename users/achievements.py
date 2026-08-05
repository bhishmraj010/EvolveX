"""
users/achievements.py

Single source of truth for the badge list (used by profile_view for the
"3/8 Unlocked" grid) AND for triggering the global "Achievement Unlocked"
popup (see life_simulation/context_processors.py -> pending_popup) the
first time each badge's condition becomes true.

Badges are recomputed live from current stats every time — there's no
persistent "progress" model for them, only a persistent record of which
ones have ALREADY had their popup shown (UnlockedBadge), so re-checking
on every task completion is cheap and never re-fires a popup twice.
"""

from .models import UnlockedBadge


def get_badges(user, win_days, tasks_completed, max_streak):
    """Every badge needs a stable 'key' (used by UnlockedBadge) — don't
    rename existing keys later, that would let already-seen badges pop
    again for everyone."""
    return [
        {'key': 'first_blood', 'icon': 'swords',   'name': 'First Blood', 'desc': 'Complete your first task', 'unlocked': tasks_completed >= 1},
        {'key': 'win_streak',  'icon': 'trophy',    'name': 'Win Streak',  'desc': '3 Win days in a row',      'unlocked': max_streak >= 3},
        {'key': 'on_fire',     'icon': 'flame',     'name': 'On Fire',     'desc': '7 day streak',             'unlocked': max_streak >= 7},
        {'key': 'warrior',     'icon': 'dumbbell',  'name': 'Warrior',     'desc': '10 Win days total',        'unlocked': win_days >= 10},
        {'key': 'grinder',     'icon': 'zap',       'name': 'Grinder',     'desc': 'Complete 50 tasks',        'unlocked': tasks_completed >= 50},
        {'key': 'legend',      'icon': 'crown',     'name': 'Legend',      'desc': 'Reach Level 5',            'unlocked': user.level >= 5},
        {'key': 'night_owl',   'icon': 'moon',      'name': 'Night Owl',   'desc': '30 days active',           'unlocked': (win_days + getattr(user, '_survive_days', 0)) >= 30},
        {'key': 'diet_master', 'icon': 'apple',     'name': 'Diet Master', 'desc': 'Setup diet profile',       'unlocked': hasattr(user, 'diet_profile')},
    ]


def _current_stats(user):
    from tasks.models import DailyLog, Task
    all_logs = DailyLog.objects.filter(user=user)
    win_days = all_logs.filter(day_status='win').count()
    survive_days = all_logs.filter(day_status='survive').count()
    tasks_completed = Task.objects.filter(user=user, status='completed').count()
    streak_list = list(all_logs.order_by('date').values_list('streak', flat=True))
    max_streak = max(streak_list) if streak_list else 0
    user._survive_days = survive_days
    return win_days, tasks_completed, max_streak


def check_and_queue_achievement_popup(user, request):
    """Call this after anything that could change badge-relevant stats
    (task completed, level-up, streak update, etc). Queues at most ONE
    newly-unlocked badge's popup per call — if several unlock in the same
    request, the rest will simply get picked up (and popped) the next
    time this runs, since UnlockedBadge is only written for the one shown.

    Skips entirely if something else already queued a popup this request
    (e.g. a level-up popup) — one popup per page load, level-up wins.
    """
    if request is None or not getattr(request, 'session', None):
        return
    if request.session.get('pending_popup'):
        return  # something else already claimed this request's popup slot

    win_days, tasks_completed, max_streak = _current_stats(user)
    badges = get_badges(user, win_days, tasks_completed, max_streak)

    already_seen = set(
        UnlockedBadge.objects.filter(user=user).values_list('badge_key', flat=True)
    )

    for b in badges:
        if b['unlocked'] and b['key'] not in already_seen:
            UnlockedBadge.objects.create(user=user, badge_key=b['key'])
            request.session['pending_popup'] = {
                'type': 'achievement',
                'name': b['name'],
                'desc': b['desc'],
            }
            return