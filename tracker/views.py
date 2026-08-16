from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from .models import WillpowerTask, MealEntry, WILLPOWER_POINTS, WILLPOWER_DEDUCT
from datetime import date, timedelta
from life_simulation.date_utils import get_selected_date


# ─── Helpers ────────────────────────────────────────────────

def sync_willpower_to_daily(user, log_date=None):
    if log_date is None:
        log_date = timezone.localdate()
    try:
        from tasks.views import recalculate_daily_points
        recalculate_daily_points(user, log_date)
    except Exception:
        pass


def _blocked(request, is_ajax, msg, redirect_to, status=403):
    """Shared response for a date-guard rejection — JSON for AJAX callers,
    messages+redirect for normal link/form submissions."""
    if is_ajax:
        return JsonResponse({'ok': False, 'error': msg}, status=status)
    messages.error(request, msg)
    return redirect(redirect_to)


# ─── Willpower Views ─────────────────────────────────────────

@login_required
def willpower(request):
    today = timezone.localdate()
    selected_date = get_selected_date(request)

    # FIX: .isoformat() added — without it these were `date` objects, which
    # Django's template engine renders using DATE_FORMAT (e.g. "Aug. 16, 2026")
    # instead of ISO "YYYY-MM-DD". That broke every ?date= link on this page,
    # since fromisoformat() couldn't parse the resulting non-ISO query param.
    prev_date = (selected_date - timedelta(days=1)).isoformat()
    next_date = (selected_date + timedelta(days=1)).isoformat()
    is_today  = (selected_date == today)

    if request.method == 'POST':
        action = request.POST.get('action')
        title  = request.POST.get('title', '').strip()
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

        if action == 'add' and title:
            # Server-side guard: mirrors the frontend rule — can only add
            # challenges for today or a future (planning) date, never past.
            if selected_date < today:
                return _blocked(
                    request, is_ajax,
                    "Can't add challenges to a past date.",
                    f'/tracker/willpower/?date={selected_date}',
                )

            task = WillpowerTask.objects.create(
                user     = request.user,
                title    = title,
                due_date = selected_date,
            )
            messages.success(request, f'Challenge added: "{title}"')

            if is_ajax:
                tasks_qs = WillpowerTask.objects.filter(user=request.user, due_date=selected_date)
                wp_points = sum(
                    WILLPOWER_POINTS if t.status == 'completed' else
                    -WILLPOWER_DEDUCT if t.status == 'skipped' else 0
                    for t in tasks_qs
                )
                return JsonResponse({
                    'ok':              True,
                    'task_id':         task.id,
                    'title':           task.title,
                    'wp_points':       wp_points,
                    'completed_count': tasks_qs.filter(status='completed').count(),
                    'skipped_count':   tasks_qs.filter(status='skipped').count(),
                    'total_count':     tasks_qs.count(),
                })

        elif is_ajax:
            return JsonResponse({'ok': False, 'error': 'Title required.'}, status=400)

        return redirect(f'/tracker/willpower/?date={selected_date}')

    tasks     = WillpowerTask.objects.filter(user=request.user, due_date=selected_date)
    pending   = tasks.filter(status='pending')
    completed = tasks.filter(status='completed')
    skipped   = tasks.filter(status='skipped')

    wp_points = sum(
        WILLPOWER_POINTS if t.status == 'completed' else
        -WILLPOWER_DEDUCT if t.status == 'skipped' else 0
        for t in tasks
    )

    # ── Weekly summary strip (Mon..Sun dots) ──
    week_start = selected_date - timedelta(days=selected_date.weekday())
    weekly_summary = []
    for i in range(7):
        d = week_start + timedelta(days=i)
        day_tasks = WillpowerTask.objects.filter(user=request.user, due_date=d)
        has_activity = day_tasks.filter(status='completed').exists()
        weekly_summary.append({
            'label': d.strftime('%a')[0],
            'date': d,
            'is_today': d == today,
            'active': has_activity,
        })

    # ── Current streak (consecutive days ending today/selected_date with net-positive willpower) ──
    def _day_net(d):
        day_tasks = WillpowerTask.objects.filter(user=request.user, due_date=d)
        return sum(
            WILLPOWER_POINTS if t.status == 'completed' else
            -WILLPOWER_DEDUCT if t.status == 'skipped' else 0
            for t in day_tasks
        )

    current_streak = 0
    d = today
    while _day_net(d) > 0:
        current_streak += 1
        d -= timedelta(days=1)

    best_streak = current_streak
    run = 0
    for i in range(90):
        d = today - timedelta(days=i)
        if _day_net(d) > 0:
            run += 1
            best_streak = max(best_streak, run)
        else:
            run = 0

    # ── Points this week (Mon..today of this week) ──
    week_tasks = WillpowerTask.objects.filter(
        user=request.user, due_date__gte=week_start, due_date__lte=today
    )
    earned = week_tasks.filter(status='completed').count() * WILLPOWER_POINTS
    skipped_ct = week_tasks.filter(status='skipped').count()
    skipped_pts = skipped_ct * WILLPOWER_DEDUCT
    net_pts = earned - skipped_pts

    # ── AI Insight — reuse Analyzer's latest recommendation if available ──
    ai_insight_title = "Start your day with 1 small win."
    ai_insight_body = "Small wins build unstoppable momentum."
    try:
        from analyzer.models import AnalyzerReport
        latest = AnalyzerReport.objects.filter(user=request.user).order_by('-generated_at').first()
        if latest and latest.recommendations:
            ai_insight_title = latest.recommendations[0]
            ai_insight_body = latest.verdict[:120] if getattr(latest, 'verdict', '') else ai_insight_body
    except Exception:
        pass

    context = {
        'today':          today,
        'selected_date':  selected_date,
        'prev_date':      prev_date,
        'next_date':      next_date,
        'is_today':       is_today,
        'pending':        pending,
        'completed':      completed,
        'skipped':        skipped,
        'tasks':          tasks,
        'wp_points':      wp_points,
        'weekly_summary': weekly_summary,
        'current_streak': current_streak,
        'best_streak':    best_streak,
        'week_earned':    earned,
        'week_skipped':   skipped_pts,
        'week_net':       net_pts,
        'ai_insight_title': ai_insight_title,
        'ai_insight_body':  ai_insight_body,
    }
    return render(request, 'tracker/willpower.html', context)


def _wp_stats(user, log_date):
    tasks_qs = WillpowerTask.objects.filter(user=user, due_date=log_date)
    wp_points = sum(
        WILLPOWER_POINTS if t.status == 'completed' else
        -WILLPOWER_DEDUCT if t.status == 'skipped' else 0
        for t in tasks_qs
    )
    return {
        'wp_points':       wp_points,
        'completed_count': tasks_qs.filter(status='completed').count(),
        'skipped_count':   tasks_qs.filter(status='skipped').count(),
        'total_count':     tasks_qs.count(),
    }


@login_required
def complete_wp_task(request, task_id):
    task = get_object_or_404(WillpowerTask, id=task_id, user=request.user)
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if task.due_date != timezone.localdate():
        return _blocked(
            request, is_ajax,
            "This action is only allowed for today's entries.",
            f'/tracker/willpower/?date={task.due_date}',
        )

    if task.status == 'pending':
        task.status = 'completed'
        task.save()
        sync_willpower_to_daily(request.user, task.due_date)
    if is_ajax:
        return JsonResponse({'ok': True, **_wp_stats(request.user, task.due_date)})
    return redirect(f'/tracker/willpower/?date={task.due_date}')


@login_required
def skip_wp_task(request, task_id):
    task = get_object_or_404(WillpowerTask, id=task_id, user=request.user)
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if task.due_date != timezone.localdate():
        return _blocked(
            request, is_ajax,
            "This action is only allowed for today's entries.",
            f'/tracker/willpower/?date={task.due_date}',
        )

    if task.status == 'pending':
        task.status = 'skipped'
        task.save()
        sync_willpower_to_daily(request.user, task.due_date)
    if is_ajax:
        return JsonResponse({'ok': True, **_wp_stats(request.user, task.due_date)})
    return redirect(f'/tracker/willpower/?date={task.due_date}')


@login_required
def delete_wp_task(request, task_id):
    task     = get_object_or_404(WillpowerTask, id=task_id, user=request.user)
    due_date = task.due_date
    is_ajax  = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if due_date < timezone.localdate():
        return _blocked(
            request, is_ajax,
            "Past entries are read-only and can't be deleted.",
            f'/tracker/willpower/?date={due_date}',
        )

    task.delete()
    sync_willpower_to_daily(request.user, due_date)
    if is_ajax:
        return JsonResponse({'ok': True, **_wp_stats(request.user, due_date)})
    messages.success(request, 'Challenge deleted.')
    return redirect(f'/tracker/willpower/?date={due_date}')


@login_required
def undo_wp_task(request, task_id):
    task = get_object_or_404(WillpowerTask, id=task_id, user=request.user)
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if task.due_date != timezone.localdate():
        return _blocked(
            request, is_ajax,
            "This action is only allowed for today's entries.",
            f'/tracker/willpower/?date={task.due_date}',
        )

    if task.status != 'pending':
        task.status = 'pending'
        task.save()
        sync_willpower_to_daily(request.user, task.due_date)
    if is_ajax:
        return JsonResponse({'ok': True, **_wp_stats(request.user, task.due_date)})
    return redirect(f'/tracker/willpower/?date={task.due_date}')


# ─── Diet Views (legacy — MealEntry based, not the main diet/home.html app) ──

@login_required
def diet(request):
    today = timezone.localdate()

    if request.method == 'POST':
        meal_type   = request.POST.get('meal_type')
        description = request.POST.get('description', '').strip()
        is_healthy  = request.POST.get('is_healthy') == 'on'

        if description:
            MealEntry.objects.create(
                user=request.user, date=today,
                meal_type=meal_type, description=description,
                is_healthy=is_healthy,
            )
            messages.success(request, f'{meal_type.capitalize()} logged! {"🥗 Healthy" if is_healthy else "🍔 Treat"}')
        return redirect('diet')

    today_meals   = MealEntry.objects.filter(user=request.user, date=today)
    week_ago      = today - timedelta(days=7)
    week_meals    = MealEntry.objects.filter(user=request.user, date__gte=week_ago)
    total_meals   = week_meals.count()
    healthy_meals = week_meals.filter(is_healthy=True).count()
    healthy_pct   = round(healthy_meals / total_meals * 100) if total_meals else 0

    context = {
        'today': today, 'today_meals': today_meals,
        'total_meals': total_meals, 'healthy_pct': healthy_pct,
        'healthy_meals': healthy_meals,
    }
    return render(request, 'tracker/diet.html', context)