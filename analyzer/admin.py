from django.contrib import admin
from .models import AnalyzerReport, AnalyzerRunLog


@admin.register(AnalyzerReport)
class AnalyzerReportAdmin(admin.ModelAdmin):
    list_display = (
        "user", "report_type", "generated_at", "evolution_grade",
        "evolution_score", "discipline_score", "productivity_score",
        "focus_score", "confidence_score", "is_cached",
    )
    list_filter = ("report_type", "evolution_grade", "is_cached")
    search_fields = ("user__username",)
    readonly_fields = ("generated_at",)


@admin.register(AnalyzerRunLog)
class AnalyzerRunLogAdmin(admin.ModelAdmin):
    list_display = ("user", "ran_at", "cache_hit", "succeeded", "prompt_tokens", "completion_tokens")
    list_filter = ("cache_hit", "succeeded")
    search_fields = ("user__username",)