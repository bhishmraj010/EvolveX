from django.conf import settings
from django.db import models
from django.utils import timezone


class AnalyzerReport(models.Model):
    """
    One AI Analyzer run for a user. Extended with premium AI Life Coach fields.
    """
    REPORT_TYPES = [
        ("daily", "Daily"),
        ("weekly", "Weekly"),
        ("monthly", "Monthly"),
    ]
    EVOLUTION_GRADE_CHOICES = [
        ("S", "S"),
        ("A", "A"),
        ("B", "B"),
        ("C", "C"),
        ("D", "D"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="analyzer_reports",
    )
    report_type = models.CharField(max_length=10, choices=REPORT_TYPES, default="weekly")
    generated_at = models.DateTimeField(default=timezone.now)
    period_days = models.PositiveIntegerField(default=30)

    # Core scores (existing)
    discipline_score = models.PositiveIntegerField(default=0)
    productivity_score = models.PositiveIntegerField(default=0)
    focus_score = models.PositiveIntegerField(default=0)
    evolution_score = models.PositiveIntegerField(default=0)

    # Existing text fields
    insights = models.JSONField(default=list, blank=True)
    root_causes = models.JSONField(default=list, blank=True)
    recommendations = models.JSONField(default=list, blank=True)
    prediction_text = models.TextField(blank=True)
    summary_text = models.TextField(blank=True)

    # --- Per-section reports (Todo, Willpower, Diet, Roadmap, Boss Fight) ---
    # Each stores a dict shaped like the SectionReport schema in gemini_service.py:
    # {score, grade, verdict, good_patterns, bad_patterns, insights, recommendations, risk_pct}
    todo_report = models.JSONField(default=dict, blank=True)
    willpower_report = models.JSONField(default=dict, blank=True)
    diet_report = models.JSONField(default=dict, blank=True)
    roadmap_report = models.JSONField(default=dict, blank=True)   # AI-predicted, no dedicated tracking model
    boss_fight_report = models.JSONField(default=dict, blank=True)

    # --- New Premium AI Life Coach Fields ---
    verdict = models.TextField(blank=True)                            # Executive summary
    confidence_score = models.PositiveSmallIntegerField(default=0)   # 0–100

    # Pattern detection
    hidden_patterns = models.JSONField(default=list, blank=True)     # list of str
    success_patterns = models.JSONField(default=list, blank=True)    # list of str
    failure_patterns = models.JSONField(default=list, blank=True)    # list of str

    # Opportunity Engine
    opportunities = models.JSONField(default=list, blank=True)       # list of dict {description, impact}
    best_opportunity = models.JSONField(default=dict, blank=True)    # single dict

    # Risk Analysis (percentages 0–100)
    burnout_risk = models.PositiveSmallIntegerField(default=0)
    streak_break_risk = models.PositiveSmallIntegerField(default=0)
    goal_failure_risk = models.PositiveSmallIntegerField(default=0)
    productivity_decline_risk = models.PositiveSmallIntegerField(default=0)
    consistency_risk = models.PositiveSmallIntegerField(default=0)

    # Goal Prediction
    goal_probability = models.PositiveSmallIntegerField(default=0)   # 0–100
    expected_level = models.PositiveSmallIntegerField(default=0)
    expected_level_days = models.PositiveSmallIntegerField(default=0)
    expected_xp = models.PositiveIntegerField(default=0)
    expected_weekly_xp = models.PositiveIntegerField(default=0)

    # Trend & Grade
    trend_summary = models.TextField(blank=True)
    evolution_grade = models.CharField(
        max_length=1,
        choices=EVOLUTION_GRADE_CHOICES,
        blank=True,
        default=""
    )

    # Token usage (existing)
    prompt_tokens = models.PositiveIntegerField(default=0)
    completion_tokens = models.PositiveIntegerField(default=0)
    is_cached = models.BooleanField(default=False)

    class Meta:
        ordering = ["-generated_at"]

    def __str__(self):
        return f"AnalyzerReport({self.user}, {self.report_type}, {self.generated_at:%Y-%m-%d %H:%M})"

    def score_band(self):
        """green / gold / red – used by UI to color prediction card."""
        if self.evolution_score >= 70:
            return "green"
        if self.evolution_score >= 40:
            return "gold"
        return "red"

    def cache_window_hours(self):
        return {"daily": 12, "weekly": 24, "monthly": 72}.get(self.report_type, 24)

    def is_stale(self):
        elapsed = (timezone.now() - self.generated_at).total_seconds() / 3600
        return elapsed > self.cache_window_hours()


class AnalyzerRunLog(models.Model):
    """Cost/usage log – unchanged."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="analyzer_run_logs",
    )
    ran_at = models.DateTimeField(auto_now_add=True)
    cache_hit = models.BooleanField(default=False)
    prompt_tokens = models.PositiveIntegerField(default=0)
    completion_tokens = models.PositiveIntegerField(default=0)
    succeeded = models.BooleanField(default=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-ran_at"]

    def __str__(self):
        status = "hit" if self.cache_hit else "miss"
        return f"{self.user} — {status} @ {self.ran_at:%Y-%m-%d %H:%M}"