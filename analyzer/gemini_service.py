"""
AI Analyzer service – premium AI Life Coach.
Aggregates user activity across all EvolveX modules and invokes Gemini to produce
a comprehensive behavioral analysis with verdict, patterns, risks, predictions,
and actionable opportunities. Uses Pydantic for response validation.
"""
from collections import Counter
from datetime import timedelta
from typing import List, Dict, Union, Optional
import hashlib
import json
import logging

from django.utils import timezone
from pydantic import BaseModel, Field, ValidationError, conint

from tasks.models import Task, DailyLog, BossDefeat, BossChallengeProgress
from .models import AnalyzerReport, AnalyzerRunLog
from life_simulation.gemini_client import generate_json_with_usage

logger = logging.getLogger(__name__)

# Constants
PERIOD_DAYS_BY_TYPE = {"daily": 1, "weekly": 7, "monthly": 30}
WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


# ---------- Pydantic response schema ----------
class Opportunity(BaseModel):
    description: str
    impact: conint(ge=0, le=100)  # expected impact percentage


class SectionReport(BaseModel):
    """One self-contained mini-report for a single life area (Todo, Willpower,
    Diet, Journal, Roadmap, or Boss Fight). Roadmap has no dedicated tracking data —
    for that section the model must infer/predict purely from level, XP,
    and the other sections' trajectory."""
    score: conint(ge=0, le=100)
    grade: str = Field(pattern=r'^[SABCD]$')
    verdict: str                                    # 1-2 sentence summary for this section only
    good_patterns: List[str] = Field(default_factory=list)
    bad_patterns: List[str] = Field(default_factory=list)
    insights: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    risk_pct: conint(ge=0, le=100)                  # chance this area regresses next period


class AnalyzerResponse(BaseModel):
    # ---- Per-section reports ----
    todo_report: SectionReport
    willpower_report: SectionReport
    diet_report: SectionReport
    journal_report: SectionReport
    roadmap_report: SectionReport
    boss_fight_report: SectionReport

    # ---- Combined / overall analysis (built from all sections above) ----
    verdict: str
    summary: str
    confidence_score: conint(ge=0, le=100)
    discipline_score: conint(ge=0, le=100)
    productivity_score: conint(ge=0, le=100)
    focus_score: conint(ge=0, le=100)
    evolution_score: conint(ge=0, le=100)
    hidden_patterns: List[str] = Field(default_factory=list)
    success_patterns: List[str] = Field(default_factory=list)
    failure_patterns: List[str] = Field(default_factory=list)
    opportunities: List[Opportunity] = Field(default_factory=list)
    best_opportunity: Opportunity = Field(default_factory=lambda: Opportunity(description="", impact=0))
    burnout_risk: conint(ge=0, le=100)
    streak_break_risk: conint(ge=0, le=100)
    goal_failure_risk: conint(ge=0, le=100)
    productivity_decline_risk: conint(ge=0, le=100)
    consistency_risk: conint(ge=0, le=100)
    goal_probability: conint(ge=0, le=100)
    expected_level: conint(ge=0)
    expected_level_days: conint(ge=0)
    expected_xp: conint(ge=0)
    expected_weekly_xp: conint(ge=0)
    trend_summary: str
    evolution_grade: str = Field(pattern=r'^[SABCD]$')
    insights: List[str] = Field(default_factory=list)
    root_causes: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    prediction: str


# ---------- Aggregation ----------
def aggregate_user_data(user, report_type="weekly", previous_reports=None):
    """
    Collect comprehensive activity metrics from all EvolveX modules.
    Returns a dict of numeric summaries and derived statistics.
    """
    period_days = PERIOD_DAYS_BY_TYPE.get(report_type, 7)
    since = timezone.now().date() - timedelta(days=period_days)

    # ---- Tasks ----
    tasks_qs = Task.objects.filter(user=user, due_date__gte=since)
    total_tasks = tasks_qs.count()
    completed_tasks = tasks_qs.filter(status="completed").count()
    skipped_tasks = tasks_qs.filter(status="skipped").count()
    overdue_tasks = tasks_qs.filter(due_date__lt=timezone.now().date(), status__in=["pending", "in_progress"]).count()

    # Completion by priority
    high_priority_qs = tasks_qs.filter(priority__gte=4)
    high_priority_total = high_priority_qs.count()
    high_priority_completed = high_priority_qs.filter(status="completed").count()

    # Weekday vs weekend completion
    weekday_counts = Counter()
    weekday_completed = Counter()
    for t in tasks_qs.only("due_date", "status"):
        wd = t.due_date.weekday()
        weekday_counts[wd] += 1
        if t.status == "completed":
            weekday_completed[wd] += 1
    weekend_total = weekday_counts[5] + weekday_counts[6]
    weekend_completed = weekday_completed[5] + weekday_completed[6]
    weekday_total = total_tasks - weekend_total
    weekday_completed_ct = completed_tasks - weekend_completed
    weekday_rate = round(weekday_completed_ct / weekday_total * 100) if weekday_total else None
    weekend_rate = round(weekend_completed / weekend_total * 100) if weekend_total else None

    # ---- Daily Logs ----
    logs_qs = DailyLog.objects.filter(user=user, date__gte=since)
    win_days = logs_qs.filter(day_status="win").count()
    survive_days = logs_qs.filter(day_status="survive").count()
    lose_days = logs_qs.filter(day_status="lose").count()

    # Streaks: find consecutive wins up to today
    all_logs = DailyLog.objects.filter(user=user).order_by("-date")
    current_win_streak = 0
    current_lose_streak = 0
    for log in all_logs:
        if log.day_status == "win":
            current_win_streak += 1
            current_lose_streak = 0
        elif log.day_status == "lose":
            current_lose_streak += 1
            current_win_streak = 0
        else:
            break

    # ---- Diet ----
    diet_adherence_pct = None
    try:
        from diet.models import DietLog
        diet_qs = DietLog.objects.filter(user=user, date__gte=since)
        if diet_qs.exists():
            on_target = diet_qs.filter(day_status="win").count()
            diet_adherence_pct = round(on_target / diet_qs.count() * 100)
    except Exception:
        logger.exception("Diet aggregation failed (analyzer will show 0/blank diet data)")

    # ---- Willpower ----
    willpower_total = willpower_completed = willpower_skipped = 0
    try:
        from tracker.models import WillpowerTask
        wp_qs = WillpowerTask.objects.filter(user=user, due_date__gte=since)
        willpower_total = wp_qs.count()
        willpower_completed = wp_qs.filter(status="completed").count()
        willpower_skipped = wp_qs.filter(status="skipped").count()
    except Exception:
        logger.exception("Willpower aggregation failed (analyzer will show 0/blank willpower data)")

    # ---- Journal ----
    # Model: JournalEntry lives in the `home` app — fields: user, date, entry_text,
    # ai_response, ai_suggestions, ai_mood_tag (AI-assigned, not user-input),
    # ai_generated_at. One entry per user per day (date is effectively unique).
    journal_entries_count = 0
    journal_days_written = 0
    journal_avg_words = 0
    journal_current_streak = 0
    journal_dominant_mood = None
    journal_ai_reflection_rate = 0
    try:
        from home.models import JournalEntry

        journal_qs = JournalEntry.objects.filter(user=user, date__gte=since)
        journal_entries_count = journal_qs.count()
        journal_days_written = journal_qs.values("date").distinct().count()

        if journal_entries_count:
            total_words = sum(
                len((e.entry_text or "").split()) for e in journal_qs.only("entry_text")
            )
            journal_avg_words = round(total_words / journal_entries_count)

            # How often the AI reflection actually landed (ai_response non-empty)
            with_reflection = journal_qs.exclude(ai_response="").count()
            journal_ai_reflection_rate = round(with_reflection / journal_entries_count * 100)

        # Dominant AI-assigned mood tag for the period
        mood_tags = list(
            journal_qs.exclude(ai_mood_tag="").values_list("ai_mood_tag", flat=True)
        )
        if mood_tags:
            journal_dominant_mood = Counter(mood_tags).most_common(1)[0][0]

        # Streak: consecutive days with an entry, counting back from today
        all_journal_dates = set(
            JournalEntry.objects.filter(user=user).values_list("date", flat=True)
        )
        cursor = timezone.now().date()
        while cursor in all_journal_dates:
            journal_current_streak += 1
            cursor -= timedelta(days=1)
    except Exception:
        # THIS was silently swallowing errors before (bare `except Exception: pass`),
        # so if `journal.models` import path is wrong, or a field name doesn't match,
        # journal_* stayed at 0/None with zero trace in the logs. Now it logs.
        logger.exception("Journal aggregation failed (analyzer will show 0/blank journal data) — check app label / field names on JournalEntry")

    # ---- Boss battles ----
    bosses_defeated = BossDefeat.objects.filter(
        user=user, defeated_at__date__gte=since
    ).count()
    challenges_completed = BossChallengeProgress.objects.filter(
        user=user, completed=True, completed_at__date__gte=since
    ).count()

    # ---- Previous reports for trend ----
    prev_evolution_scores = []
    if previous_reports is not None:
        prev_evolution_scores = [r.evolution_score for r in previous_reports[:5]]

    return {
        "report_type": report_type,
        "period_days": period_days,
        "level": user.level,
        "total_xp": user.total_xp,
        "tasks_total": total_tasks,
        "tasks_completed": completed_tasks,
        "tasks_skipped": skipped_tasks,
        "overdue_tasks": overdue_tasks,
        "completion_rate_pct": round(completed_tasks / total_tasks * 100) if total_tasks else 0,
        "high_priority_total": high_priority_total,
        "high_priority_completed": high_priority_completed,
        "weekday_completion_pct": weekday_rate,
        "weekend_completion_pct": weekend_rate,
        "win_days": win_days,
        "survive_days": survive_days,
        "lose_days": lose_days,
        "current_win_streak": current_win_streak,
        "current_lose_streak": current_lose_streak,
        "diet_adherence_pct": diet_adherence_pct,
        "willpower_total": willpower_total,
        "willpower_completed": willpower_completed,
        "willpower_skipped": willpower_skipped,
        "journal_entries_count": journal_entries_count,
        "journal_days_written": journal_days_written,
        "journal_avg_words": journal_avg_words,
        "journal_current_streak": journal_current_streak,
        "journal_dominant_mood": journal_dominant_mood,
        "bosses_defeated": bosses_defeated,
        "boss_challenges_completed": challenges_completed,
        "prev_evolution_scores": prev_evolution_scores,  # for Gemini to see trend
    }


# ---------- Freshness fingerprint ----------
def _compute_fingerprint(summary):
    """
    Cheap hash of the raw activity counts that feed the report. If this
    changes since the cached report was generated — e.g. the user just wrote
    a journal entry, completed a task, logged a meal — we know the cached
    report is out of date even if it's still inside its time-based cache
    window, and we should regenerate instead of serving stale numbers.
    """
    fingerprint_source = "|".join(str(summary.get(key)) for key in [
        "tasks_total", "tasks_completed", "tasks_skipped", "overdue_tasks",
        "win_days", "survive_days", "lose_days",
        "diet_adherence_pct",
        "willpower_total", "willpower_completed", "willpower_skipped",
        "journal_entries_count", "journal_days_written", "journal_current_streak",
        "bosses_defeated", "boss_challenges_completed",
    ])
    return hashlib.md5(fingerprint_source.encode("utf-8")).hexdigest()


# ---------- Prompt Construction ----------
def _build_prompt(summary):
    prev_scores = summary.get("prev_evolution_scores", [])
    prev_trend = ", ".join(map(str, prev_scores)) if prev_scores else "no previous data"

    return f"""You are an elite AI Life Coach embedded in EvolveX, a gamified self-improvement platform.
Analyze the user's {summary['report_type']} activity summary (last {summary['period_days']} days) and act as a world-class performance coach.
Your analysis must be deep, actionable, and personalized.

You must produce TWO layers of analysis:
LAYER 1 — six independent SECTION REPORTS, one per life area, each scored and reasoned about on its own.
LAYER 2 — one COMBINED OVERALL ANALYSIS that synthesizes all six section reports together (this is the
existing "AI Verdict / Evolution Score / Patterns / Risks / Prediction" analysis — build it FROM the section
reports below, not independently).

DATA (all numbers, no personal text):
- Level: {summary['level']}, Total XP: {summary['total_xp']}
- Tasks: {summary['tasks_completed']}/{summary['tasks_total']} completed ({summary['completion_rate_pct']}%), {summary['tasks_skipped']} skipped, {summary['overdue_tasks']} overdue
- High-priority tasks: {summary['high_priority_completed']}/{summary['high_priority_total']} completed
- Weekday completion rate: {summary['weekday_completion_pct']}% (null = no data)
- Weekend completion rate: {summary['weekend_completion_pct']}% (null = no data)
- Days: {summary['win_days']} win, {summary['survive_days']} survive, {summary['lose_days']} lose
- Current win streak: {summary['current_win_streak']} days, lose streak: {summary['current_lose_streak']} days
- Diet adherence: {summary['diet_adherence_pct']}% (null = not tracked)
- Willpower tasks: {summary['willpower_completed']}/{summary['willpower_total']} completed, {summary['willpower_skipped']} skipped
- Journal: {summary['journal_entries_count']} entries in {summary['period_days']} days, written on {summary['journal_days_written']} distinct days
- Journal avg words/entry: {summary['journal_avg_words']}, current writing streak: {summary['journal_current_streak']} days
- Journal dominant mood: {summary['journal_dominant_mood']} (null = not tracked)
- Boss battles: {summary['bosses_defeated']} bosses defeated, {summary['boss_challenges_completed']} challenges completed
- Previous evolution scores (same report type): {prev_trend}

Note: there is no dedicated "roadmap" tracking data above. For the roadmap_report, infer/predict the user's
trajectory purely from level, XP, and how the other five sections are trending — be explicit that it's a
forward-looking projection, not a measurement.

Return ONLY a valid JSON object (no markdown, no extra text) with this exact structure:

{{
  "todo_report": {{ ...SectionReport for Task/Todo Tracker... }},
  "willpower_report": {{ ...SectionReport for Willpower Tracker... }},
  "diet_report": {{ ...SectionReport for Diet Tracker... }},
  "journal_report": {{ ...SectionReport for Journal... }},
  "roadmap_report": {{ ...SectionReport, predictive, for level/XP Roadmap... }},
  "boss_fight_report": {{ ...SectionReport for Boss Battles... }},

  "verdict": ..., "summary": ..., "confidence_score": ..., "discipline_score": ...,
  "productivity_score": ..., "focus_score": ..., "evolution_score": ...,
  "hidden_patterns": [...], "success_patterns": [...], "failure_patterns": [...],
  "opportunities": [...], "best_opportunity": {{...}},
  "burnout_risk": ..., "streak_break_risk": ..., "goal_failure_risk": ...,
  "productivity_decline_risk": ..., "consistency_risk": ...,
  "goal_probability": ..., "expected_level": ..., "expected_level_days": ...,
  "expected_xp": ..., "expected_weekly_xp": ..., "trend_summary": ...,
  "evolution_grade": ..., "insights": [...], "root_causes": [...],
  "recommendations": [...], "prediction": ...
}}

Each SectionReport object (todo_report / willpower_report / diet_report / journal_report / roadmap_report /
boss_fight_report) must have exactly these fields:
- score: (int 0-100) health of this area specifically.
- grade: (string) one of "S", "A", "B", "C", "D".
- verdict: (string) ONE sentence, max 20 words. Honest summary of THIS area only. No second sentence.
- good_patterns: (list of strings) what's working in this area.
- bad_patterns: (list of strings) what's hurting this area.
- insights: (list of strings) notable observations specific to this area.
- recommendations: (list of strings) 1-3 concrete next actions for this area.
- risk_pct: (int 0-100) likelihood this area regresses in the next period.

For the journal_report specifically: judge consistency (entries per week, streak), depth (avg words —
very low word counts are a bad pattern), and mood trend if mood data is present. If entries_count is 0,
say so plainly and treat it as a bad pattern, not a neutral one.

For the combined/overall fields (verdict, summary, confidence_score, discipline_score, productivity_score,
focus_score, evolution_score, hidden_patterns, success_patterns, failure_patterns, opportunities,
best_opportunity, burnout_risk, streak_break_risk, goal_failure_risk, productivity_decline_risk,
consistency_risk, goal_probability, expected_level, expected_level_days, expected_xp, expected_weekly_xp,
trend_summary, evolution_grade, insights, root_causes, recommendations, prediction) use the same
definitions as before:

- verdict: (string) 2 sentences MAX, each under 20 words. Overall performance and trajectory, synthesized
  across all six sections. No more than 2 sentences, ever.
- summary: (string) ONE sentence, max 15 words. Headline for this {summary['report_type']} report
  (shown at the top of the page).
- confidence_score: (int 0-100) How confident are you in this analysis? Base this on data richness and
  consistency, not randomness.
- discipline_score, productivity_score, focus_score, evolution_score: (int 0-100).
- hidden_patterns: (list of strings) Recurring behavioral patterns that cut across sections (e.g.,
  "Productivity drops sharply on weekends", "High-priority tasks are repeatedly postponed").
- success_patterns: (list of strings) Cross-cutting behaviors that consistently produce better outcomes.
- failure_patterns: (list of strings) Cross-cutting habits that repeatedly reduce performance.
- opportunities: (list of objects with "description" and "impact" where impact is 0-100) Multiple
  personalised improvement opportunities ranked by expected impact.
- best_opportunity: (object with "description" and "impact") The single highest-impact improvement.
- burnout_risk, streak_break_risk, goal_failure_risk, productivity_decline_risk, consistency_risk:
  (int 0-100) Assess each risk based on historical data across all sections.
- goal_probability: (int 0-100) Likelihood of reaching next level or milestone.
- expected_level: (int) Predicted user level after the next {summary['period_days']} days.
- expected_level_days: (int) Estimated days until next level-up.
- expected_xp: (int) Projected total XP after next period.
- expected_weekly_xp: (int) Projected weekly XP gain.
- trend_summary: (string) ONE sentence, max 20 words. Improving, stable, or declining — and why.
- evolution_grade: (string) Overall grade: "S", "A", "B", "C", or "D" based on performance.
- insights: (list of strings) Key cross-section observations.
- root_causes: (list of strings) Why metrics moved, across sections.
- recommendations: (list of strings) Specific next actions, prioritized across all sections.
- prediction: (string) ONE sentence, max 20 words. Future outlook — no essays.

WRITING STYLE — this is critical, follow it strictly for every text field above (verdict, summary,
good_patterns, bad_patterns, insights, recommendations, trend_summary, root_causes, prediction, etc.):
- Write like you're talking to a normal person, not a data analyst. No corporate jargon, no buzzwords
  ("synergy", "leverage", "optimize", "holistic", "paradigm", etc.).
- Keep every sentence short — max ~15-18 words. One idea per sentence.
- Every item in a list field (insights, good_patterns, bad_patterns, recommendations, root_causes,
  opportunities) is EXACTLY ONE short sentence, max 15 words. Never two sentences in one bullet.
- Use simple, everyday words. If a simpler word exists, use it (e.g. "skipped" not "deprioritized",
  "you stopped" not "engagement ceased").
- Be direct and concrete. Say what happened, in plain terms, with a real number if it helps
  (e.g. "You missed 3 out of 5 workouts this week" not "Adherence to the fitness protocol was suboptimal").
- Avoid stacking multiple clauses in one sentence. Split into two sentences instead of using semicolons
  or "which resulted in" style constructions.
- recommendations should read like quick friendly advice, not a policy document — start with an action verb
  ("Set a 10-minute buffer before bed" not "It is recommended that a buffer period be established").

Be critical and honest in every section. All scores are 0-100 unless noted.
"""


# ---------- Gemini caller ----------
def _call_gemini(prompt):
    """Call Gemini and parse response with Pydantic. Returns (data, prompt_tokens, completion_tokens)."""
    raw, prompt_tokens, completion_tokens = generate_json_with_usage(prompt)
    if raw is None:
        return None, prompt_tokens, completion_tokens
    try:
        # generate_json_with_usage returns dict; we need to validate
        validated = AnalyzerResponse(**raw)
        # Convert to dict for db — model_dump() is the Pydantic v2 way (.dict() is deprecated)
        data = validated.model_dump()
        return data, prompt_tokens, completion_tokens
    except ValidationError as e:
        logger.error(f"Gemini response validation failed: {e}")
        return None, prompt_tokens, completion_tokens


# ---------- Public API ----------
def get_or_create_report(user, report_type="weekly", force_refresh=False):
    """
    Serve cached report if fresh; otherwise call Gemini to generate a new one.
    On failure, fallback to last cached report of same type (FR-AN-07).

    IMPORTANT: freshness is checked two ways, not just the time window.
    `is_stale()` alone used to let a report sit "valid" for up to 12/24/72
    hours even if the user logged brand-new activity (e.g. a journal entry)
    minutes after the report was generated — so the UI kept showing
    "0 entries today" even though an entry existed. We now always pull a
    cheap fingerprint of the current activity counts and compare it to the
    fingerprint stored on the cached report; a mismatch forces a refresh
    regardless of how much time has passed.
    """
    latest = AnalyzerReport.objects.filter(user=user, report_type=report_type).first()

    # Gather previous reports for trend (up to 5)
    previous_reports = list(AnalyzerReport.objects.filter(
        user=user, report_type=report_type
    ).exclude(pk=latest.pk if latest else None).order_by("-generated_at")[:5]) if latest else []

    # Aggregation is cheap (plain DB counts, no Gemini call) so we always run
    # it — this is what lets us detect "new data since cache was generated".
    summary = aggregate_user_data(user, report_type, previous_reports)
    current_fingerprint = _compute_fingerprint(summary)

    cache_is_fresh = (
        latest
        and not force_refresh
        and not latest.is_stale()
        and latest.activity_fingerprint == current_fingerprint
    )
    if cache_is_fresh:
        AnalyzerRunLog.objects.create(user=user, cache_hit=True, succeeded=True)
        return latest, True

    prompt = _build_prompt(summary)

    try:
        result, pt, ct = _call_gemini(prompt)
        if result is None:
            raise RuntimeError("Gemini returned invalid response")

        # Create new report
        report = AnalyzerReport.objects.create(
            user=user,
            report_type=report_type,
            period_days=summary["period_days"],
            todo_report=result.get("todo_report", {}),
            willpower_report=result.get("willpower_report", {}),
            diet_report=result.get("diet_report", {}),
            journal_report=result.get("journal_report", {}),
            roadmap_report=result.get("roadmap_report", {}),
            boss_fight_report=result.get("boss_fight_report", {}),
            discipline_score=result.get("discipline_score", 0),
            productivity_score=result.get("productivity_score", 0),
            focus_score=result.get("focus_score", 0),
            evolution_score=result.get("evolution_score", 0),
            summary_text=result.get("summary", ""),
            verdict=result.get("verdict", ""),
            confidence_score=result.get("confidence_score", 0),
            hidden_patterns=result.get("hidden_patterns", []),
            success_patterns=result.get("success_patterns", []),
            failure_patterns=result.get("failure_patterns", []),
            opportunities=result.get("opportunities", []),
            best_opportunity=result.get("best_opportunity", {}),
            burnout_risk=result.get("burnout_risk", 0),
            streak_break_risk=result.get("streak_break_risk", 0),
            goal_failure_risk=result.get("goal_failure_risk", 0),
            productivity_decline_risk=result.get("productivity_decline_risk", 0),
            consistency_risk=result.get("consistency_risk", 0),
            goal_probability=result.get("goal_probability", 0),
            expected_level=result.get("expected_level", 0),
            expected_level_days=result.get("expected_level_days", 0),
            expected_xp=result.get("expected_xp", 0),
            expected_weekly_xp=result.get("expected_weekly_xp", 0),
            trend_summary=result.get("trend_summary", ""),
            evolution_grade=result.get("evolution_grade", ""),
            insights=result.get("insights", []),
            root_causes=result.get("root_causes", []),
            recommendations=result.get("recommendations", []),
            prediction_text=result.get("prediction", ""),
            prompt_tokens=pt,
            completion_tokens=ct,
            is_cached=False,
            activity_fingerprint=current_fingerprint,
        )
        AnalyzerRunLog.objects.create(
            user=user, cache_hit=False, succeeded=True,
            prompt_tokens=pt, completion_tokens=ct,
        )
        return report, False

    except Exception as e:
        logger.exception("Gemini analysis failed")
        AnalyzerRunLog.objects.create(
            user=user, cache_hit=False, succeeded=False, error_message=str(e)[:500],
        )
        # Fallback to latest cache if exists
        if latest:
            return latest, True
        return None, False