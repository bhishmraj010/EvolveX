import threading
from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Roadmap, RoadmapDraft, RoadmapPhase, PhaseTest
from . import gemini_service
from .chart_utils import build_growth_chart

try:
    from subscriptions.decorators import premium_required
except ImportError:  # subscription app not installed yet — no-op gate
    def premium_required(feature_name):
        def decorator(view_func):
            return view_func
        return decorator


def _kick_prefetch_next_mission(roadmap):
    """Fire-and-forget: warm phase.next_mission_cache in a background
    thread so it doesn't block the request/response. Safe no-op if a fresh
    cache already exists (see gemini_service.prefetch_next_mission)."""
    threading.Thread(
        target=gemini_service.prefetch_next_mission, args=(roadmap,), daemon=True
    ).start()


def _parse_deadline(raw):
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def _safe_int(raw, default=None):
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _onboarding_context(**extra):
    ctx = {
        "skill_levels": Roadmap.SKILL_LEVELS,
        "learning_preferences": Roadmap.LEARNING_PREFERENCES,
        "budget_choices": Roadmap.BUDGET_CHOICES,
    }
    ctx.update(extra)
    return ctx


def _generate_final_roadmap(user, draft):
    """Turn a RoadmapDraft (+ any clarifying answers) into a real, generated
    Roadmap. Returns the new Roadmap and whether generation succeeded."""
    roadmap = Roadmap.objects.create(
        user=user,
        goal=draft.goal,
        current_skill_level=draft.current_skill_level,
        daily_minutes=draft.daily_minutes,
        target_deadline=draft.target_deadline,
        learning_preference=draft.learning_preference,
        existing_skills=draft.existing_skills,
        preferred_language=draft.preferred_language,
        budget=draft.budget,
    )

    # A new active roadmap replaces any previously active one for the
    # dashboard (keep history — just archive, don't delete).
    Roadmap.objects.filter(user=user, status="active").exclude(pk=roadmap.pk).update(status="archived")

    ok = gemini_service.generate_roadmap(roadmap, carry_forward_note=draft.to_context_note())
    return roadmap, ok


@login_required
@premium_required("AI Roadmap")
def onboarding(request):
    """Step 1: collect Goal / Skill Level / Daily Time / Deadline /
    Preference / Existing Skills / Language / Budget. Instead of generating
    the roadmap immediately, we create a RoadmapDraft and ask the AI if the
    goal needs disambiguating (e.g. "Full Stack Dev" -> which stack?)."""
    if request.method == "POST":
        draft = RoadmapDraft.objects.create(
            user=request.user,
            goal=request.POST.get("goal", "").strip()[:200],
            current_skill_level=request.POST.get("current_skill_level", "beginner"),
            daily_minutes=_safe_int(request.POST.get("daily_minutes"), 60),
            target_deadline=_parse_deadline(request.POST.get("target_deadline", "")),
            learning_preference=request.POST.get("learning_preference", "mixed"),
            existing_skills=request.POST.get("existing_skills", "").strip(),
            preferred_language=request.POST.get("preferred_language", "English").strip() or "English",
            budget=request.POST.get("budget", "free"),
        )

        questions = gemini_service.generate_clarifying_questions(draft)
        if questions:
            draft.clarifying_questions = [{"question": q, "answer": ""} for q in questions]
            draft.save(update_fields=["clarifying_questions"])
            return render(request, "roadmap/clarify.html", {"draft": draft})

        # Goal was already unambiguous — skip straight to generation.
        roadmap, ok = _generate_final_roadmap(request.user, draft)
        draft.delete()
        if not ok:
            messages.error(request, "AI Roadmap generation failed — please try again.")
            return redirect("roadmap_onboarding")
        messages.success(request, f"Your roadmap for \"{roadmap.goal}\" is ready! 🎯")
        return redirect("roadmap_home")

    # All of the user's roadmaps, grouped by status, for the "My Roadmaps"
    # side panel on the onboarding page. Roadmap.Meta.ordering = ["-created_at"]
    # so each queryset already comes back newest-first.
    user_roadmaps = request.user.roadmaps.all()

    return render(request, "roadmap/onboarding.html", _onboarding_context(
        active_roadmaps=user_roadmaps.filter(status="active"),
        completed_roadmaps=user_roadmaps.filter(status="completed"),
        archived_roadmaps=user_roadmaps.filter(status="archived"),
    ))


@login_required
@premium_required("AI Roadmap")
@require_POST
def submit_clarifying_answers(request, draft_id):
    """Step 2: user answered the AI's clarifying questions — finalize and
    generate the real roadmap using those answers as extra prompt context."""
    draft = get_object_or_404(RoadmapDraft, pk=draft_id, user=request.user)

    answered = []
    for i, q in enumerate(draft.clarifying_questions):
        answered.append({
            "question": q["question"],
            "answer": request.POST.get(f"answer_{i}", "").strip(),
        })
    draft.clarifying_questions = answered
    draft.save(update_fields=["clarifying_questions"])

    roadmap, ok = _generate_final_roadmap(request.user, draft)
    draft.delete()

    if not ok:
        messages.error(request, "AI Roadmap generation failed — please try again.")
        return redirect("roadmap_onboarding")

    messages.success(request, f"Your roadmap for \"{roadmap.goal}\" is ready! 🎯")
    return redirect("roadmap_home")


@login_required
@premium_required("AI Roadmap")
def roadmap_home(request):
    """The AI Roadmap dashboard — growth roadmap timeline, phases, today's
    missions, progress ring, XP/streak, predictions, resources."""
    roadmap = Roadmap.objects.filter(user=request.user, status="active").first()
    if roadmap is None:
        return redirect("roadmap_onboarding")

    if roadmap.generation_failed or roadmap.phases.count() == 0:
        return render(request, "roadmap/onboarding.html", {
            "skill_levels": Roadmap.SKILL_LEVELS,
            "learning_preferences": Roadmap.LEARNING_PREFERENCES,
            "budget_choices": Roadmap.BUDGET_CHOICES,
            "generation_failed": True,
            "goal": roadmap.goal,
        })

    mission, _ = gemini_service.get_or_create_daily_mission(roadmap)

    if mission and mission.status != "completed":
        # Get a head start on tomorrow's mission while the learner is still
        # working through today's — so finishing the last task reveals the
        # next day instantly instead of waiting on an AI call.
        _kick_prefetch_next_mission(roadmap)

    phases = list(roadmap.phases_ordered().prefetch_related("daily_missions", "checkpoint"))
    resources = roadmap.resources.select_related("phase").all()[:12]
    growth_chart = build_growth_chart(roadmap, phases)

    today_pct = mission.completion_pct() if mission else 0
    today_done = sum(1 for t in (mission.tasks if mission else []) if t.get("completed"))
    today_total = len(mission.tasks) if mission else 0

    return render(request, "roadmap/home.html", {
        "roadmap": roadmap,
        "phases": phases,
        "current_phase": roadmap.current_phase(),
        "resources": resources,
        "mission": mission,
        "today": timezone.localdate(),
        "today_pct": today_pct,
        "today_done": today_done,
        "today_total": today_total,
        "days_left": roadmap.days_left(),
        "growth_chart": growth_chart,
    })


@login_required
@premium_required("AI Roadmap")
@require_POST
def switch_roadmap(request, roadmap_id):
    """Make a different (completed/archived) roadmap the active one so the
    user can jump back into it from the 'My Roadmaps' panel."""
    target = get_object_or_404(Roadmap, pk=roadmap_id, user=request.user)

    if target.status == "completed":
        messages.info(request, f'"{target.goal}" is already completed — you can still view its history.')
        return redirect("roadmap_home")

    if target.status != "active":
        # archive whichever roadmap is currently active, then promote target
        Roadmap.objects.filter(user=request.user, status="active").exclude(pk=target.pk).update(status="archived")
        target.status = "active"
        target.save(update_fields=["status"])

    messages.success(request, f'Switched to "{target.goal}" 🔄')
    return redirect("roadmap_home")


@login_required
@premium_required("AI Roadmap")
@require_POST
def regenerate(request, roadmap_id):
    old_roadmap = get_object_or_404(Roadmap, pk=roadmap_id, user=request.user)

    daily_minutes = _safe_int(request.POST.get("daily_minutes"))

    deadline_raw = request.POST.get("target_deadline", "").strip()
    target_deadline = None
    if deadline_raw:
        try:
            target_deadline = datetime.strptime(deadline_raw, "%Y-%m-%d").date()
        except ValueError:
            pass

    learning_preference = request.POST.get("learning_preference") or None
    extra_notes = request.POST.get("extra_notes", "").strip()

    new_roadmap, ok = gemini_service.regenerate_roadmap(
        old_roadmap,
        daily_minutes=daily_minutes,
        target_deadline=target_deadline,
        learning_preference=learning_preference,
        extra_notes=extra_notes,
    )

    if ok:
        messages.success(request, "Roadmap regenerated based on your progress! 🔄")
    else:
        messages.error(request, "Regeneration failed — your previous roadmap is safe and still active.")
        old_roadmap.status = "active"
        old_roadmap.save(update_fields=["status"])

    return redirect("roadmap_home")


@login_required
@premium_required("AI Roadmap")
@require_POST
def toggle_mission_task(request, mission_id):
    from .models import DailyMission
    mission = get_object_or_404(DailyMission, pk=mission_id, roadmap__user=request.user)
    task_id = request.POST.get("task_id")
    ok = mission.toggle_task(task_id)

    if mission.status != "completed":
        _kick_prefetch_next_mission(mission.roadmap)

    return JsonResponse({
        "ok": ok,
        "status": mission.status,
        "completion_pct": mission.completion_pct(),
        "xp": request.user.total_xp,
        "level": request.user.level,
    })


@login_required
@premium_required("AI Roadmap")
@require_POST
def generate_next_mission(request, mission_id):
    """
    Separate, slower endpoint (calls the AI) — kept apart from
    toggle_mission_task so checking off the last task of the day responds
    instantly, while the next day's mission generates in the background and
    the frontend animates it in once this call returns.

    If a background prefetch (see gemini_service.prefetch_next_mission) is
    already in flight for this phase, we DON'T fire a second concurrent AI
    call — that just burns quota faster. Instead we report status
    "generating" so the frontend polls this same endpoint again shortly.
    """
    from .models import DailyMission
    mission = get_object_or_404(DailyMission, pk=mission_id, roadmap__user=request.user)

    if mission.status != "completed":
        return JsonResponse({"next_mission": None})

    status, ready_mission = gemini_service.check_next_mission_ready(mission.roadmap)

    if status == "ready" and ready_mission and ready_mission.pk != mission.pk:
        return JsonResponse({"next_mission": {
            "id": ready_mission.id,
            "phase_id": ready_mission.phase_id,
            "date_label": ready_mission.date.strftime("%a, %d %b"),
            "tasks": ready_mission.tasks,
        }})

    if status == "generating":
        return JsonResponse({"next_mission": None, "status": "generating"})

    # Nothing cached and nothing in flight — fall back to a live call.
    next_mission, was_cached = gemini_service.get_or_create_daily_mission(mission.roadmap)
    next_mission_data = None
    if next_mission and next_mission.pk != mission.pk:
        next_mission_data = {
            "id": next_mission.id,
            "phase_id": next_mission.phase_id,
            "date_label": next_mission.date.strftime("%a, %d %b"),
            "tasks": next_mission.tasks,
        }

    return JsonResponse({"next_mission": next_mission_data})


@login_required
@premium_required("AI Roadmap")
@require_POST
def clear_checkpoint(request, checkpoint_id):
    from .models import RoadmapCheckpoint
    checkpoint = get_object_or_404(
        RoadmapCheckpoint, pk=checkpoint_id, phase__roadmap__user=request.user
    )
    checkpoint.clear()

    # Immediately generate today's mission for whichever phase is now
    # active — the learner shouldn't have to wait until tomorrow to see
    # the next phase's tasks.
    gemini_service.get_or_create_daily_mission(checkpoint.phase.roadmap)

    messages.success(request, f"Checkpoint cleared: {checkpoint.title} 🏆")
    return redirect("roadmap_home")


@login_required
@premium_required("AI Roadmap")
def take_test(request, phase_id):
    """Show (generating if needed) the checkpoint test for a phase whose
    content is already complete. Reuses an existing pending attempt if one
    exists, so refreshing the page doesn't burn a second AI generation."""
    phase = get_object_or_404(RoadmapPhase, pk=phase_id, roadmap__user=request.user)

    checkpoint = getattr(phase, "checkpoint", None)
    if checkpoint and checkpoint.is_completed:
        messages.info(request, "This phase's checkpoint is already cleared.")
        return redirect("roadmap_home")

    pending = phase.pending_remedial()
    if pending:
        messages.info(request, f'Finish the remedial phase "{pending.title}" first, then you can retake the test.')
        return redirect("roadmap_home")

    test = phase.latest_test()
    if test is None or test.status == "graded":
        weak_topics = test.weak_topics if test else None
        test = gemini_service.generate_phase_test(phase, weak_topics=weak_topics)
        if test is None:
            messages.error(request, "Couldn't generate the test right now — try again in a bit.")
            return redirect("roadmap_home")

    return render(request, "roadmap/test.html", {"phase": phase, "test": test})


@login_required
@premium_required("AI Roadmap")
@require_POST
def submit_test(request, test_id):
    """Grade a submitted test. Passing auto-clears the phase's checkpoint;
    failing leaves the choice to retry to the result page (roadmap_home /
    start_remedial), matching the 'study more and try again' flow."""
    test = get_object_or_404(PhaseTest, pk=test_id, phase__roadmap__user=request.user)

    if test.status != "graded":
        answers = {q["id"]: (request.POST.get(f"answer_{q['id']}", "").strip() or None) for q in test.questions}
        gemini_service.grade_phase_test(test, answers)

        if test.passed:
            checkpoint = getattr(test.phase, "checkpoint", None)
            if checkpoint and not checkpoint.is_completed:
                checkpoint.clear()
                gemini_service.get_or_create_daily_mission(test.phase.roadmap)

    return render(request, "roadmap/test_result.html", {"test": test, "phase": test.phase})


@login_required
@premium_required("AI Roadmap")
@require_POST
def start_remedial(request, phase_id):
    """Learner chose 'Study More & Retake' after failing — generate the
    focused remedial phase and drop them into it."""
    phase = get_object_or_404(RoadmapPhase, pk=phase_id, roadmap__user=request.user)
    test = phase.latest_test()
    weak_topics = test.weak_topics if test else []

    remedial = gemini_service.generate_remedial_phase(phase, weak_topics)
    if remedial is None:
        messages.error(request, "Couldn't generate the remedial phase right now — try again in a bit.")
    else:
        gemini_service.get_or_create_daily_mission(phase.roadmap)
        messages.success(request, f'Remedial phase added: "{remedial.title}" — finish it, then you\'ll retake the test.')

    return redirect("roadmap_home")