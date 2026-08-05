from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.core.serializers.json import DjangoJSONEncoder
import json

from .gemini_service import get_or_create_report
from .models import AnalyzerReport

try:
    from subscriptions.access import user_can_access_premium
except ImportError:  # subscriptions app not installed yet — default to open access
    def user_can_access_premium(user):
        return True


VALID_TYPES = {"daily", "weekly", "monthly"}


@login_required
def analyzer_home(request):
    """
    FR-AN-06 — access gate: Level-1 users get unlimited use, users locked
    behind the subscription wall (level >= 2, not subscribed) are shown an
    upsell instead of burning a Gemini call. Founder/Lifetime pass straight
    through.

    Supports Daily / Weekly / Monthly Evolution Reports via ?type=, and
    shows a trend chart of past reports of the same type (Chart.js —
    matches the pattern already used on reports/home.html).
    """
    if not user_can_access_premium(request.user):
        return render(request, "subscriptions/locked.html", {"feature_name": "AI Analyzer"})

    report_type = request.GET.get("type", "weekly")
    if report_type not in VALID_TYPES:
        report_type = "weekly"

    force_refresh = request.GET.get("refresh") == "1"
    report, was_cached = get_or_create_report(
        request.user, report_type=report_type, force_refresh=force_refresh
    )

    # Historical reports of this same type, oldest → newest, for the trend chart
    historical = AnalyzerReport.objects.filter(
        user=request.user,
        report_type=report_type,
    ).order_by("generated_at")

    chart_labels = [r.generated_at.strftime("%b %d") for r in historical]
    chart_evolution = [r.evolution_score for r in historical]
    chart_discipline = [r.discipline_score for r in historical]
    chart_productivity = [r.productivity_score for r in historical]
    chart_focus = [r.focus_score for r in historical]

    return render(request, "analyzer/home.html", {
        "report": report,
        "was_cached": was_cached,
        "report_type": report_type,
        "report_types": [("daily", "Daily"), ("weekly", "Weekly"), ("monthly", "Monthly")],
        "chart_labels": json.dumps(chart_labels, cls=DjangoJSONEncoder),
        "chart_evolution": json.dumps(chart_evolution, cls=DjangoJSONEncoder),
        "chart_discipline": json.dumps(chart_discipline, cls=DjangoJSONEncoder),
        "chart_productivity": json.dumps(chart_productivity, cls=DjangoJSONEncoder),
        "chart_focus": json.dumps(chart_focus, cls=DjangoJSONEncoder),
        "has_history": len(historical) > 1,
        "sections": [
            {"key": "todo", "title": "Todo Tracker", "icon": "list-checks", "data": report.todo_report},
            {"key": "willpower", "title": "Willpower", "icon": "flame", "data": report.willpower_report},
            {"key": "diet", "title": "Diet Tracker", "icon": "utensils", "data": report.diet_report},
            {"key": "roadmap", "title": "Roadmap", "icon": "map", "data": report.roadmap_report},
            {"key": "boss_fight", "title": "Boss Fight", "icon": "swords", "data": report.boss_fight_report},
        ] if report else [],
        "risk_items": [
            ("Burnout", report.burnout_risk if report else 0),
            ("Streak Break", report.streak_break_risk if report else 0),
            ("Goal Failure", report.goal_failure_risk if report else 0),
            ("Productivity Decline", report.productivity_decline_risk if report else 0),
            ("Consistency", report.consistency_risk if report else 0),
        ] if report else [],
    })