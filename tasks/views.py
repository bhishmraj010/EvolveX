from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.contrib import messages
from .models import (
    Task, DailyLog, PRIORITY_POINTS, SKIP_DEDUCTION, LOSE_PUNISHMENT,
    Boss, BossChallenge, BossChallengeProgress, BossDefeat,
    get_pending_boss, get_auto_verify_info, sync_auto_challenges,
)
from datetime import date, timedelta

try:
    from subscriptions.decorators import premium_required
except ImportError:  # subscriptions app not installed yet — no-op gate
    def premium_required(feature_name):
        def decorator(view_func):
            return view_func
        return decorator


# ─── Helpers ─────────────────────────────────────────────────────────────────

def get_or_create_daily_log(user, log_date=None):
    if log_date is None:
        log_date = timezone.localdate()

    log, created = DailyLog.objects.get_or_create(user=user, date=log_date)

    if created:
        log.win_threshold     = user.get_win_pts()
        log.survive_threshold = user.get_survive_min()

        yesterday = log_date - timedelta(days=1)
        try:
            y_log = DailyLog.objects.get(user=user, date=yesterday)
            if y_log.day_status == 'lose':
                log.total_points = -LOSE_PUNISHMENT
                log.punishment   = True
        except DailyLog.DoesNotExist:
            pass
        log.save()

    return log


def recalculate_daily_points(user, log_date=None, request=None):
    """
    request is optional — pass it in from any view that wants the global
    "Level Complete" popup (see life_simulation/context_processors.py ->
    pending_popup) to fire automatically when this recalculation causes a
    level-up. Safe to omit (e.g. for background/management-command calls).
    """
    if log_date is None:
        log_date = timezone.localdate()

    log    = get_or_create_daily_log(user, log_date)
    points = -LOSE_PUNISHMENT if log.punishment else 0

    for task in Task.objects.filter(user=user, due_date=log_date):
        if task.status == 'completed':
            points += task.get_points()
        elif task.status == 'skipped':
            points -= SKIP_DEDUCTION

    try:
        from tracker.models import WillpowerTask, WILLPOWER_POINTS, WILLPOWER_DEDUCT
        for wt in WillpowerTask.objects.filter(user=user, due_date=log_date):
            if wt.status == 'completed':
                points += WILLPOWER_POINTS
            elif wt.status == 'skipped':
                points -= WILLPOWER_DEDUCT
    except Exception:
        pass

    log.total_points      = points
    log.win_threshold     = user.get_win_pts()
    log.survive_threshold = user.get_survive_min()
    log.save()

    update_streak(user, log)
    leveled_up, _penalized = update_user_xp(user, request=request)
    if request is not None and not leveled_up:
        from users.achievements import check_and_queue_achievement_popup
        check_and_queue_achievement_popup(user, request)
    return log


def update_user_xp(user, request=None):
    from django.db.models import Sum
    total = DailyLog.objects.filter(
        user=user, total_points__gt=0
    ).aggregate(Sum('total_points'))['total_points__sum'] or 0

    # Roadmap XP (DailyMission / RoadmapCheckpoint) is tracked on
    # Roadmap.xp_earned, NOT via DailyLog — so without this it gets wiped
    # out every time this function overwrites user.total_xp from the
    # DailyLog aggregate above (e.g. on the very next normal task
    # complete/skip). Fold it in here so the recompute stays idempotent
    # AND roadmap XP survives.
    try:
        from roadmap.models import Roadmap
        roadmap_total = Roadmap.objects.filter(user=user).aggregate(
            Sum('xp_earned')
        )['xp_earned__sum'] or 0
        total += roadmap_total
    except Exception:
        pass

    user.total_xp  = total
    penalized      = user.check_deadline_penalty()
    leveled_up     = user.check_level_up()

    if not leveled_up and not penalized:
        user.save()

    # Queue the global "Level Complete" popup (rendered from base.html on
    # whatever page the user next loads — see pending_popup() context
    # processor). Only fires when we actually have a request to stash the
    # session flag on (e.g. not during a bare management-command call).
    if leveled_up and request is not None:
        request.session['pending_popup'] = {
            'type':  'level',
            'level': user.level,
            'title': user.title,
        }

    return leveled_up, penalized


def update_streak(user, today_log):
    yesterday = today_log.date - timedelta(days=1)
    try:
        y_log = DailyLog.objects.get(user=user, date=yesterday)
        if today_log.day_status == 'win':
            today_log.streak = y_log.streak + 1
        elif today_log.day_status == 'lose':
            today_log.streak = 0
        else:
            today_log.streak = y_log.streak
    except DailyLog.DoesNotExist:
        today_log.streak = 1 if today_log.day_status == 'win' else 0
    DailyLog.objects.filter(pk=today_log.pk).update(streak=today_log.streak)


# ─── Views ───────────────────────────────────────────────────────────────────

DAILY_QUOTES = [
    "Discipline today, freedom tomorrow.",
    "You are stronger than yesterday.",
    "Small actions today, big changes tomorrow.",
    "The grind you're avoiding is the growth you're seeking.",
    "Level up in real life, one task at a time.",
    "Consistency beats intensity.",
    "Your future self is watching — make them proud.",
]


@login_required
def dashboard(request):
    """
    Mission Control — NOT a task manager, NOT an analytics page. One
    screen that answers: how's my day going, what's my level, which boss
    am I fighting, what's next. Full task list lives on /dashboard/todo/;
    charts/trends live on Reports; deep AI analysis lives on Analyzer.
    """
    import random
    from life_simulation.date_utils import get_selected_date

    today = timezone.localdate()
    selected_date = get_selected_date(request)
    is_today = (selected_date == today)

    penalized = request.user.check_deadline_penalty()
    if penalized:
        messages.warning(request, f'⏰ Level deadline missed! Extra time given!')

    log = get_or_create_daily_log(request.user, selected_date)
    tasks = Task.objects.filter(user=request.user, due_date=selected_date)
    tasks_total = tasks.count()
    tasks_done = tasks.filter(status='completed').count()
    tasks_pending = tasks.filter(status='pending').count()
    high_priority_pending = tasks.filter(status='pending', priority__gte=4).count()
    completion_pct = round(tasks_done / tasks_total * 100) if tasks_total else 0

    user = request.user
    cur = user.current_level_data()
    nxt = user.next_level_data()

    pending_boss = get_pending_boss(user, user.level) if user.boss_pending else None

    # ── Current Boss (whichever boss the user is actively working toward,
    # not just the one blocking level-up) ──
    current_boss = pending_boss
    boss_progress_pct = 0
    if current_boss:
        total_ch = current_boss.challenges.count()
        done_ch = BossChallengeProgress.objects.filter(
            user=user, challenge__boss=current_boss, completed=True
        ).count()
        boss_progress_pct = round(done_ch / total_ch * 100) if total_ch else 0

    # ── Willpower score (today's completion rate) ──
    willpower_score = None
    try:
        from tracker.models import WillpowerTask
        wp_qs = WillpowerTask.objects.filter(user=user, due_date=selected_date)
        if wp_qs.exists():
            wp_done = wp_qs.filter(status='completed').count()
            willpower_score = round(wp_done / wp_qs.count() * 100)
    except Exception:
        pass

    # ── Diet status (today) ──
    diet_status = None
    try:
        from diet.models import DietLog
        diet_log = DietLog.objects.filter(user=user, date=selected_date).first()
        if diet_log:
            diet_status = diet_log.day_status
    except Exception:
        pass

    # ── Daily Challenge: clear every 5-star task today ──
    five_star_qs = tasks.filter(priority=5)
    five_star_total = five_star_qs.count()
    five_star_done = five_star_qs.filter(status='completed').count()
    daily_challenge_complete = five_star_total > 0 and five_star_done == five_star_total

    # ── AI Daily Insight — one line, pulled from the latest Analyzer report
    # if fresh enough, otherwise a sensible default (never triggers a new
    # Gemini call from the dashboard — that's the Analyzer page's job) ──
    ai_insight = None
    try:
        from analyzer.models import AnalyzerReport
        latest_report = AnalyzerReport.objects.filter(user=user).order_by('-generated_at').first()
        if latest_report and latest_report.recommendations:
            ai_insight = latest_report.recommendations[0]
        elif latest_report and latest_report.insights:
            ai_insight = latest_report.insights[0]
    except Exception:
        pass
    if not ai_insight:
        ai_insight = "Complete your highest-priority task first to build early momentum."

    # ── Current AI Roadmap (if the user has generated one) ──
    current_roadmap = None
    try:
        from roadmap.models import Roadmap
        current_roadmap = (
            Roadmap.objects
            .filter(user=user, status="active")
            .exclude(generation_failed=True)
            .order_by("-created_at")
            .first()
        )
    except Exception:
        pass

    day_status_copy = {
        'win':     ("🟢", "You are dominating today. Keep going."),
        'survive': ("🟡", "You're still in the fight. Complete your priority tasks."),
        'lose':    ("🔴", "The day isn't over yet. Finish an important mission to recover."),
    }
    status_icon, status_message = day_status_copy.get(log.day_status, ("🟡", ""))

    context = {
        'log':                    log,
        'today':                  today,
        'selected_date':          selected_date,
        'is_today':               is_today,
        'cur_level':              cur,
        'nxt_level':              nxt,
        'xp_pct':                 user.xp_progress_pct(),
        'xp_to_next':             user.xp_to_next_level(),
        'days_left':              user.days_left(),
        'pending_boss':           pending_boss,
        'current_boss':           current_boss,
        'boss_progress_pct':      boss_progress_pct,
        'tasks_total':            tasks_total,
        'tasks_done':             tasks_done,
        'tasks_pending':          tasks_pending,
        'high_priority_pending':  high_priority_pending,
        'completion_pct':         completion_pct,
        'status_icon':            status_icon,
        'status_message':         status_message,
        'willpower_score':        willpower_score,
        'diet_status':            diet_status,
        'daily_challenge_complete': daily_challenge_complete,
        'five_star_total':        five_star_total,
        'five_star_done':         five_star_done,
        'ai_insight':             ai_insight,
        'current_roadmap':        current_roadmap,
        'daily_quote':            random.choice(DAILY_QUOTES),
    }
    return render(request, 'tasks/dashboard.html', context)


@login_required
def todo_list(request):
    """Full task management page — date navigation, add/complete/skip/delete.
    This used to be the entire /dashboard/ page; it moved here so Dashboard
    could become a slim overview instead of a duplicate task table."""
    from life_simulation.date_utils import get_selected_date

    today = timezone.localdate()
    selected_date = get_selected_date(request)

    prev_date = (selected_date - timedelta(days=1)).isoformat()
    next_date = (selected_date + timedelta(days=1)).isoformat()
    is_today  = (selected_date == today)

    penalized = request.user.check_deadline_penalty()
    if penalized:
        messages.warning(request, f'⏰ Level deadline missed! Extra time given!')

    log   = get_or_create_daily_log(request.user, selected_date)
    tasks = Task.objects.filter(user=request.user, due_date=selected_date)

    pending   = tasks.filter(status='pending')
    completed = tasks.filter(status='completed')
    skipped   = tasks.filter(status='skipped')

    user = request.user
    cur = user.current_level_data()
    nxt = user.next_level_data()
    pending_boss = get_pending_boss(user, user.level) if user.boss_pending else None

    tasks_done_ct = completed.count()

    context = {
        'log':            log,
        'tasks':          tasks,
        'pending':        pending,
        'completed':      completed,
        'skipped':        skipped,
        'today':          today,
        'selected_date':  selected_date,
        'prev_date':      prev_date,
        'next_date':      next_date,
        'is_today':       is_today,
        'win_pts':        log.win_threshold,
        'survive_pts':    log.survive_threshold,
        'pending_boss':   pending_boss,
        'cur_level':      cur,
        'nxt_level':      nxt,
        'xp_pct':         user.xp_progress_pct(),
        'xp_to_next':     user.xp_to_next_level(),
        'tasks_done_ct':  tasks_done_ct,
        'tasks_total_ct': tasks.count(),
    }
    return render(request, 'tasks/todo.html', context)


@login_required
def add_task(request):
    if request.method == 'POST':
        title    = request.POST.get('title', '').strip()
        priority = int(request.POST.get('priority', 3))
        date_str = request.POST.get('selected_date')
        try:
            due_date = date.fromisoformat(date_str) if date_str else timezone.localdate()
        except ValueError:
            due_date = timezone.localdate()

        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

        if title:
            task = Task.objects.create(
                user=request.user, title=title,
                priority=priority, due_date=due_date,
            )
            log = recalculate_daily_points(request.user, due_date, request=request)
            user = request.user
            messages.success(request, f'Task "{title}" added!')

            if is_ajax:
                return JsonResponse({
                    'ok':         True,
                    'task_id':    task.id,
                    'title':      task.title,
                    'priority':   task.priority,
                    'stars':      task.stars(),
                    'points':     task.get_points(),
                    'points_total':   log.total_points,
                    'day_status':     log.day_status,
                    'streak':         log.streak,
                    'total_xp':       user.total_xp,
                    'level':          user.level,
                    'xp_pct':         user.xp_progress_pct(),
                    'win_pts':        log.win_threshold,
                })
        elif is_ajax:
            return JsonResponse({'ok': False, 'error': 'Title required.'}, status=400)

    return redirect(f'/dashboard/todo/?date={due_date.isoformat()}')


@login_required
def complete_task(request, task_id):
    task = get_object_or_404(Task, id=task_id, user=request.user)
    if task.status == 'pending':
        task.status = 'completed'
        task.save()
        log  = recalculate_daily_points(request.user, task.due_date, request=request)
        user = request.user
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'status':     'completed',
                'points':     log.total_points,
                'day_status': log.day_status,
                'streak':     log.streak,
                'earned':     task.get_points(),
                'total_xp':   user.total_xp,
                'level':      user.level,
                'xp_pct':     user.xp_progress_pct(),
                'xp_to_next': user.xp_to_next_level(),
                'win_pts':    log.win_threshold,
            })
    return redirect(f'/dashboard/todo/?date={task.due_date.isoformat()}')


@login_required
def skip_task(request, task_id):
    task = get_object_or_404(Task, id=task_id, user=request.user)
    if task.status == 'pending':
        task.status = 'skipped'
        task.save()
        log  = recalculate_daily_points(request.user, task.due_date, request=request)
        user = request.user
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'status':     'skipped',
                'points':     log.total_points,
                'day_status': log.day_status,
                'streak':     log.streak,
                'deducted':   SKIP_DEDUCTION,
                'total_xp':   user.total_xp,
                'level':      user.level,
                'xp_pct':     user.xp_progress_pct(),
                'win_pts':    log.win_threshold,
            })
    return redirect(f'/dashboard/todo/?date={task.due_date.isoformat()}')


@login_required
def delete_task(request, task_id):
    task     = get_object_or_404(Task, id=task_id, user=request.user)
    due_date = task.due_date
    task.delete()
    recalculate_daily_points(request.user, due_date, request=request)
    messages.success(request, 'Task deleted.')
    return redirect(f'/dashboard/todo/?date={due_date.isoformat()}')


@login_required
def undo_task(request, task_id):
    task = get_object_or_404(Task, id=task_id, user=request.user)
    if task.status != 'pending':
        task.status = 'pending'
        task.save()
        log = recalculate_daily_points(request.user, task.due_date, request=request)
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'points':     log.total_points,
                'day_status': log.day_status,
                'streak':     log.streak,
                'win_pts':    log.win_threshold,
            })
    return redirect(f'/dashboard/todo/?date={task.due_date.isoformat()}')


# ─── Boss Battle Views ────────────────────────────────────────────────────

@login_required
@premium_required("Boss Fights")
def boss_battle(request):
    from users.models import LEVELS

    user = request.user
    boss = get_pending_boss(user, user.level)

    if boss is None and user.boss_pending:
        # Everything for this level was already defeated but the flag
        # wasn't cleared yet — clear it and let check_level_up() run.
        user.boss_pending = False
        user.save()
        user.check_level_up()

    # ── XP gate: the boss only becomes fightable once the user has fully
    # earned this level's required XP (i.e. they're right at the doorstep
    # of leveling up). Until then it's shown as a locked preview instead
    # of an active fight — see xp_current/xp_needed/next_boss below. ──
    levels_by_number = {lvl['level']: lvl for lvl in LEVELS}
    next_level_req = levels_by_number.get(user.level + 1, {}).get('pts_required')

    xp_current = user.total_xp
    xp_needed = next_level_req  # None at max level — never locks in that case

    boss_unlocked = True
    next_boss = None
    if boss is not None and xp_needed is not None and xp_current < xp_needed:
        boss_unlocked = False
        next_boss = boss  # keep a reference so the locked card can still show name/image
        boss = None

    challenge_data = []
    all_done = False
    hp_pct = 100
    fusion_names = []
    challenges_total = 0

    if boss is not None:
        challenges = boss.challenges.all()
        challenges_total = challenges.count()

        # Sync any auto-verifiable (e.g. "Reach N total XP") challenges against
        # real stats before building the display list, so it's never stale.
        sync_auto_challenges(boss, user)

        progress_map = {
            p.challenge_id: p.completed
            for p in BossChallengeProgress.objects.filter(user=user, challenge__boss=boss)
        }

        def classify_icon(desc):
            d = desc.lower()
            if 'xp' in d:
                return 'star'
            if 'streak' in d or 'row' in d or 'straight' in d:
                return 'flame'
            if 'pts' in d or 'win' in d or 'score' in d:
                return 'target'
            if 'diet' in d or 'meal' in d:
                return 'apple'
            return 'swords'

        for i, c in enumerate(challenges):
            is_auto, is_met, auto_label = get_auto_verify_info(c.description, user)
            completed = is_met if is_auto else progress_map.get(c.id, False)
            challenge_data.append({
                'challenge':   c,
                'completed':   completed,
                'icon':        classify_icon(c.description),
                'index':       i + 1,
                'is_auto':     is_auto,
                'auto_label':  auto_label,
            })
        all_done = challenges.exists() and all(cd['completed'] for cd in challenge_data)

        completed_count = sum(1 for cd in challenge_data if cd['completed'])
        hp_pct = 100 if challenges_total == 0 else round(
            max(0, (challenges_total - completed_count) / challenges_total * 100)
        )

        # Level 10 (LUST) gets a special "fusion" intro — small glowing orbs for
        # each of the previous 9 bosses converge into the final form.
        if boss.level_number == 10:
            fusion_names = list(
                Boss.objects.filter(level_number__lt=10, boss_type='final')
                .order_by('level_number').values_list('name', flat=True)
            )

    # The level to anchor the Journey roadmap / upcoming-bosses query on,
    # whether or not there's an active fight right now.
    anchor_level = boss.level_number if boss is not None else (next_boss.level_number if next_boss else user.level)

    # ── Boss Journey roadmap (levels 1-10 circles: defeated/current/locked) ──
    defeated_levels = set(
        BossDefeat.objects.filter(user=user, boss__boss_type='final')
        .values_list('boss__level_number', flat=True)
    )
    journey = []
    for lvl_num in range(1, 11):
        journey.append({
            'level': lvl_num,
            'defeated': lvl_num in defeated_levels,
            'current': lvl_num == anchor_level and (boss is not None or next_boss is not None),
            'locked': lvl_num > anchor_level,
        })

    def _reward_for_level(lvl_num):
        cur_req = levels_by_number.get(lvl_num, {}).get('pts_required', 0)
        nxt_req = levels_by_number.get(lvl_num + 1, {}).get('pts_required', cur_req + 500)
        return max(nxt_req - cur_req, 100)

    def _difficulty_for(boss_obj):
        n = boss_obj.challenges.count()
        if boss_obj.boss_type == 'final' or n >= 4:
            return 'Hard'
        if n >= 2:
            return 'Medium'
        return 'Easy'

    # ── Defeated Bosses history ──
    defeats_qs = BossDefeat.objects.filter(user=user).select_related('boss').order_by('defeated_at')
    defeated_bosses = []
    for i, d in enumerate(defeats_qs):
        defeated_bosses.append({
            'index': i + 1,
            'boss': d.boss,
            'reward_xp': _reward_for_level(d.boss.level_number),
            'defeated_at': d.defeated_at,
            'difficulty': _difficulty_for(d.boss),
        })

    # ── Upcoming (locked) bosses — next 2 beyond the anchor level ──
    upcoming_bosses = list(
        Boss.objects.filter(level_number__gt=anchor_level)
        .order_by('level_number', 'order')[:2]
    )

    # ── Quick Stats ──
    bosses_defeated_ct = defeats_qs.count()
    total_bosses_ct = Boss.objects.filter(level_number__lte=10).count() or 1
    win_rate = round(bosses_defeated_ct / total_bosses_ct * 100)
    total_xp_from_bosses = sum(d['reward_xp'] for d in defeated_bosses)

    today_log = DailyLog.objects.filter(user=user, date=timezone.localdate()).first()
    current_streak_val = today_log.streak if today_log else 0

    context = {
        'boss':             boss,
        'boss_unlocked':    boss_unlocked,
        'next_boss':        next_boss,
        'xp_current':       xp_current,
        'xp_needed':        xp_needed,
        'challenge_data':   challenge_data,
        'all_done':         all_done,
        'user_level':       user.level,
        'hp_pct':           hp_pct,
        'fusion_names':     fusion_names,
        'journey':          journey,
        'defeated_bosses':  list(reversed(defeated_bosses)),
        'upcoming_bosses':  upcoming_bosses,
        'current_reward_xp': _reward_for_level(anchor_level),
        'current_difficulty': _difficulty_for(boss) if boss else None,
        'bosses_defeated_ct': bosses_defeated_ct,
        'total_xp_from_bosses': total_xp_from_bosses,
        'win_rate':         win_rate,
        'current_streak':   current_streak_val,
    }
    return render(request, 'tasks/boss_battle.html', context)


@login_required
@premium_required("Boss Fights")
def complete_challenge(request, challenge_id):
    challenge = get_object_or_404(BossChallenge, id=challenge_id)
    progress, _ = BossChallengeProgress.objects.get_or_create(
        user=request.user, challenge=challenge
    )
    if not progress.completed:
        progress.mark_complete()
        messages.success(request, f'✅ Challenge cleared: {challenge.description}')
    return redirect('boss_battle')


@login_required
@premium_required("Boss Fights")
def defeat_boss(request, boss_id):
    """Called once all of a boss's challenges are marked complete."""
    boss = get_object_or_404(Boss, id=boss_id)
    user = request.user
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if not boss.challenges_completed_by(user):
        if is_ajax:
            return JsonResponse({'ok': False, 'error': 'Complete all challenges first.'}, status=400)
        messages.error(request, 'Complete all challenges before facing the boss!')
        return redirect('boss_battle')

    BossDefeat.objects.get_or_create(user=user, boss=boss)
    messages.success(request, f'🏆 {boss.name} defeated!')

    # Re-run the gate: if this was the last boss for the level, this will
    # actually perform the level up now.
    leveled_up = user.check_level_up()
    if leveled_up:
        messages.success(request, f'🎉 Level Up! Welcome to Level {user.level}!')
        # Global popup queue (base.html) reads and clears this on the next
        # page load — see life_simulation/context_processors.py -> pending_popup.
        request.session['pending_popup'] = {
            'type':  'level',
            'level': user.level,
            'title': user.title,
        }
        redirect_url = '/dashboard/'
    else:
        redirect_url = '/dashboard/boss/'

    if is_ajax:
        return JsonResponse({'ok': True, 'leveled_up': leveled_up, 'redirect': redirect_url})

    return redirect('dashboard') if leveled_up else redirect('boss_battle')