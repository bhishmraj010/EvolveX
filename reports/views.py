from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from datetime import date, timedelta
from collections import defaultdict
import json


@login_required
def reports_home(request):
    user  = request.user
    today = timezone.localdate()

    # ── Date range selector ───────────────────────────────────────────────
    range_str = request.GET.get('range', '30')
    try:
        days = int(range_str)
    except ValueError:
        days = 30
    if days not in [7, 30, 90]:
        days = 30

    start_date = today - timedelta(days=days - 1)

    # ── Tasks points (DailyLog) ───────────────────────────────────────────
    from tasks.models import DailyLog, Task, PRIORITY_POINTS, SKIP_DEDUCTION
    from tasks.views import get_or_create_daily_log

    daily_logs = DailyLog.objects.filter(
        user=user, date__gte=start_date, date__lte=today
    ).order_by('date')

    # ── Today's Day Status card — uses the same get_or_create_daily_log()
    # helper the Dashboard/To-Do pages use, so thresholds (win/survive
    # points) are computed with the user's actual per-level criteria, not
    # a hardcoded number. Safe even if today has no activity yet (creates
    # the row on the fly, same as everywhere else in the app). ──
    today_log = get_or_create_daily_log(user, today)
    today_status = today_log.day_status

    # Pure task-only points per day — NOT DailyLog.total_points, since that
    # field already has willpower points synced into it (see tracker app's
    # "Synced to daily total!" behavior). Computing straight from Task
    # objects here keeps "Task Points" and "Willpower Pts" from double-
    # counting the same points under two different labels.
    task_pts_by_date = defaultdict(int)
    day_tasks = Task.objects.filter(
        user=user, due_date__gte=start_date, due_date__lte=today
    )
    for t in day_tasks:
        d = str(t.due_date)
        if t.status == 'completed':
            task_pts_by_date[d] += t.get_points()
        elif t.status == 'skipped':
            task_pts_by_date[d] -= SKIP_DEDUCTION

    # ── Willpower points ──────────────────────────────────────────────────
    wp_by_date = defaultdict(int)
    try:
        from tracker.models import WillpowerTask, WILLPOWER_POINTS, WILLPOWER_DEDUCT
        wp_tasks = WillpowerTask.objects.filter(
            user=user, due_date__gte=start_date, due_date__lte=today
        )
        for wt in wp_tasks:
            d = str(wt.due_date)
            if wt.status == 'completed':
                wp_by_date[d] += WILLPOWER_POINTS
            elif wt.status == 'skipped':
                wp_by_date[d] -= WILLPOWER_DEDUCT
    except Exception:
        pass

    # ── Diet points ───────────────────────────────────────────────────────
    diet_by_date = defaultdict(int)
    try:
        from diet.models import DietLog
        diet_logs = DietLog.objects.filter(
            user=user, date__gte=start_date, date__lte=today
        )
        for dl in diet_logs:
            diet_by_date[str(dl.date)] = dl.points_earned
    except Exception:
        pass

    # ── Roadmap XP ───────────────────────────────────────────────────────
    # Two sources feed user.total_xp from the Roadmap app:
    #   1. DailyMission.toggle_task() — awards mission.xp_reward once every
    #      sub-task in that day's mission is completed (dated by `.date`).
    #   2. RoadmapCheckpoint.clear() — awards checkpoint.xp_reward when a
    #      phase's checkpoint is cleared (dated by `.completed_at`).
    # Both are summed into the same by-date bucket so the daily trend line
    # and the "Roadmap XP" totals reflect everything the roadmap contributed.
    roadmap_by_date = defaultdict(int)
    try:
        from roadmap.models import DailyMission, RoadmapCheckpoint

        completed_missions = DailyMission.objects.filter(
            roadmap__user=user, status='completed',
            date__gte=start_date, date__lte=today,
        )
        for m in completed_missions:
            roadmap_by_date[str(m.date)] += m.xp_reward

        cleared_checkpoints = RoadmapCheckpoint.objects.filter(
            phase__roadmap__user=user, is_completed=True,
            completed_at__date__gte=start_date, completed_at__date__lte=today,
        )
        for cp in cleared_checkpoints:
            roadmap_by_date[str(cp.completed_at.date())] += cp.xp_reward
    except Exception:
        pass

    # ── Build date series ─────────────────────────────────────────────────
    date_labels   = []
    task_pts      = []
    wp_pts        = []
    diet_pts      = []
    roadmap_pts   = []
    total_pts     = []
    day_statuses  = []
    streak_data   = []

    log_map = {str(l.date): l for l in daily_logs}

    for i in range(days):
        d     = start_date + timedelta(days=i)
        d_str = str(d)
        date_labels.append(d.strftime('%d %b'))

        log    = log_map.get(d_str)
        t_pts  = task_pts_by_date.get(d_str, 0)
        w_pts  = wp_by_date.get(d_str, 0)
        di_pts = diet_by_date.get(d_str, 0)
        rd_pts = roadmap_by_date.get(d_str, 0)

        task_pts.append(t_pts)
        wp_pts.append(w_pts)
        diet_pts.append(di_pts)
        roadmap_pts.append(rd_pts)
        total_pts.append(t_pts + w_pts + di_pts + rd_pts)
        day_statuses.append(log.day_status if log else 'none')
        streak_data.append(log.streak if log else 0)

    # ── Summary stats ─────────────────────────────────────────────────────
    total_task_pts    = sum(p for p in task_pts    if p > 0)
    total_wp_pts       = sum(p for p in wp_pts       if p > 0)
    total_diet_pts     = sum(p for p in diet_pts     if p > 0)
    total_roadmap_pts  = sum(p for p in roadmap_pts  if p > 0)
    grand_total        = total_task_pts + total_wp_pts + total_diet_pts + total_roadmap_pts

    win_days     = sum(1 for s in day_statuses if s == 'win')
    survive_days = sum(1 for s in day_statuses if s == 'survive')
    lose_days    = sum(1 for s in day_statuses if s == 'lose')
    active_days  = win_days + survive_days + lose_days

    max_streak   = max(streak_data) if streak_data else 0
    cur_streak   = streak_data[-1]  if streak_data else 0

    # Pie chart — points breakdown
    pie_data = [total_task_pts, total_wp_pts, total_diet_pts, total_roadmap_pts]

    # Day status donut
    donut_data = [win_days, survive_days, lose_days]

    # Best day
    if total_pts:
        best_idx  = total_pts.index(max(total_pts))
        best_day  = date_labels[best_idx]
        best_pts  = total_pts[best_idx]
    else:
        best_day, best_pts = '-', 0

    # Avg per active day
    avg_pts = round(grand_total / active_days, 1) if active_days else 0

    context = {
        'days':           days,
        'start_date':     start_date,
        'today':          today,
        'today_status':   today_status,
        # Chart data (JSON)
        'date_labels':    json.dumps(date_labels),
        'task_pts':       json.dumps(task_pts),
        'wp_pts':         json.dumps(wp_pts),
        'diet_pts':       json.dumps(diet_pts),
        'roadmap_pts':    json.dumps(roadmap_pts),
        'total_pts':      json.dumps(total_pts),
        'pie_data':       json.dumps(pie_data),
        'donut_data':     json.dumps(donut_data),
        'streak_data':    json.dumps(streak_data),
        # Summary
        'total_task_pts':     total_task_pts,
        'total_wp_pts':       total_wp_pts,
        'total_diet_pts':     total_diet_pts,
        'total_roadmap_pts':  total_roadmap_pts,
        'roadmap_xp':         total_roadmap_pts,
        'grand_total':        grand_total,
        'win_days':        win_days,
        'survive_days':    survive_days,
        'lose_days':       lose_days,
        'active_days':     active_days,
        'max_streak':      max_streak,
        'cur_streak':      cur_streak,
        'best_day':        best_day,
        'best_pts':        best_pts,
        'avg_pts':         avg_pts,
        # User
        'user_level':      user.level,
        'user_xp':         user.total_xp,
    }

    context['range_options'] = [(7, '7 Days'), (30, '30 Days'), (90, '90 Days')]

    # ── Cumulative "Total XP" trend line (spec: rising line, not daily delta) ──
    # grand_total now includes roadmap XP, so this baseline is correct even
    # for users earning XP from the Roadmap app during the selected window.
    baseline_xp = max(user.total_xp - grand_total, 0)
    cumulative_xp = []
    running = baseline_xp
    for p in total_pts:
        running += p
        cumulative_xp.append(running)

    # ── Points Distribution radar (0-100 scores derived from real data) ──
    def _pct(numerator, denom):
        return min(100, round(numerator / denom * 100)) if denom else 0

    roadmap_active_days = sum(1 for p in roadmap_pts if p > 0)

    radar_scores = {
        'task_points':  _pct(total_task_pts, active_days * 40) if active_days else 0,
        'willpower':    _pct(total_wp_pts, active_days * 7) if active_days else 0,
        'diet_points':  _pct(total_diet_pts, active_days * 10) if active_days else 0,
        'roadmap':      _pct(roadmap_active_days, days),
        'focus':        _pct(win_days, active_days) if active_days else 0,
        'consistency':  _pct(active_days, days),
    }

    # ── Points by Source (percentages) ──
    def _source_pct(v):
        return round(v / grand_total * 100) if grand_total else 0
    source_breakdown = {
        'tasks':     {'value': total_task_pts,    'pct': _source_pct(total_task_pts)},
        'willpower': {'value': total_wp_pts,       'pct': _source_pct(total_wp_pts)},
        'diet':      {'value': total_diet_pts,     'pct': _source_pct(total_diet_pts)},
        'roadmap':   {'value': total_roadmap_pts,  'pct': _source_pct(total_roadmap_pts)},
    }

    # ── Activity Heatmap — weeks x weekdays grid, intensity 0-4 ──
    def _intensity(status):
        return {'win': 4, 'survive': 2, 'lose': 1}.get(status, 0)

    heatmap_weeks = []
    week_row = [None] * 7  # Mon..Sun
    for i in range(days):
        d = start_date + timedelta(days=i)
        wd = d.weekday()  # 0=Mon
        week_row[wd] = _intensity(day_statuses[i])
        if wd == 6 or i == days - 1:
            heatmap_weeks.append(list(week_row))
            week_row = [None] * 7
    heatmap_weeks = heatmap_weeks[-6:]  # cap to last 6 weeks for layout sanity

    # ── Weekly Consistency bars (% active days per week, last up to 5 weeks) ──
    weekly_consistency = []
    for wk in heatmap_weeks:
        vals = [v for v in wk if v is not None]
        active_in_week = sum(1 for v in vals if v and v > 0)
        weekly_consistency.append(round(active_in_week / len(vals) * 100) if vals else 0)
    weekly_consistency = weekly_consistency[-5:]

    # ── Achievements — computed live from real activity, not a fabricated list ──
    total_tasks_completed = Task.objects.filter(user=user, status='completed').count()
    achievements = []
    if max_streak >= 7:
        achievements.append({'icon': 'flame', 'title': 'Consistency King', 'desc': f'Reached a {max_streak}-day streak'})
    if total_wp_pts >= 500:
        achievements.append({'icon': 'zap', 'title': 'Willpower Warrior', 'desc': f'Earned {total_wp_pts} willpower points'})
    if total_diet_pts >= 100:
        achievements.append({'icon': 'apple', 'title': 'Diet Champion', 'desc': f'Earned {total_diet_pts} diet points'})
    if total_roadmap_pts >= 100:
        achievements.append({'icon': 'map', 'title': 'Roadmap Explorer', 'desc': f'Earned {total_roadmap_pts} roadmap XP'})
    if total_tasks_completed >= 50:
        achievements.append({'icon': 'award', 'title': 'Task Master', 'desc': f'Completed {total_tasks_completed} tasks total'})
    if win_days >= 10:
        achievements.append({'icon': 'trophy', 'title': 'Win Streaker', 'desc': f'{win_days} WIN days in this period'})

    context.update({
        'cumulative_xp':      json.dumps(cumulative_xp),
        'radar_scores':       radar_scores,
        'radar_scores_json':  json.dumps(radar_scores),
        'source_breakdown':   source_breakdown,
        'heatmap_weeks':      heatmap_weeks,
        'weekly_consistency': weekly_consistency,
        'weekly_consistency_json': json.dumps(weekly_consistency),
        'achievements':       achievements,
        'win_pct':            _source_pct(win_days) if active_days else 0,
    })
    # Recompute win/survive/lose pct against active_days, not grand_total
    context['win_pct']     = round(win_days / active_days * 100) if active_days else 0
    context['survive_pct'] = round(survive_days / active_days * 100) if active_days else 0
    context['lose_pct']    = round(lose_days / active_days * 100) if active_days else 0

    return render(request, 'reports/home.html', context)