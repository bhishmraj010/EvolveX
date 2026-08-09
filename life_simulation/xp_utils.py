"""
Single source of truth for `user.total_xp`.

IMPORTANT: total_xp must NEVER be incremented directly (`user.total_xp += ...`)
anywhere in the codebase. Every XP-affecting event (task complete/skip,
willpower, diet, roadmap mission/checkpoint) should end by calling
`recompute_total_xp(user)`, which rebuilds total_xp from scratch off the
real event tables. This makes the value idempotent — safe to call as many
times as you want, from as many places as you want, with no risk of
double-counting or drift.

Roadmap XP is computed from DailyMission / RoadmapCheckpoint completion
events directly (not from Roadmap.xp_earned), because a user can have
multiple Roadmap rows over time (old versions kept around after
"Regenerate Roadmap"). Summing Roadmap.xp_earned across all of them
double-counts anything that was already reflected in an older row.
Querying the actual completed mission/checkpoint rows is safe because
each event exists exactly once, regardless of how many Roadmap versions
the user has had.
"""
from django.db.models import Sum


def recompute_total_xp(user):
    """Recompute and set user.total_xp from real event data. Does NOT call
    user.save() — caller decides when to persist (matches existing
    update_user_xp() flow, which also runs check_level_up()/check_deadline_penalty()
    before saving)."""
    from tasks.models import DailyLog

    total = DailyLog.objects.filter(
        user=user, total_points__gt=0
    ).aggregate(Sum('total_points'))['total_points__sum'] or 0

    try:
        from roadmap.models import DailyMission, RoadmapCheckpoint

        total += DailyMission.objects.filter(
            roadmap__user=user, status='completed'
        ).aggregate(Sum('xp_reward'))['xp_reward__sum'] or 0

        total += RoadmapCheckpoint.objects.filter(
            phase__roadmap__user=user, is_completed=True
        ).aggregate(Sum('xp_reward'))['xp_reward__sum'] or 0
    except Exception:
        pass

    user.total_xp = total
    return total