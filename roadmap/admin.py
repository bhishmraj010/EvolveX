from django.contrib import admin
from .models import Roadmap, RoadmapPhase, RoadmapCheckpoint, DailyMission, RoadmapResource, PhaseTest


class RoadmapPhaseInline(admin.TabularInline):
    model = RoadmapPhase
    extra = 0
    fields = ("order", "title", "difficulty", "status", "completion_pct", "xp_reward")


@admin.register(Roadmap)
class RoadmapAdmin(admin.ModelAdmin):
    list_display = ("goal", "user", "version", "status", "overall_completion_pct", "success_probability", "created_at")
    list_filter = ("status", "current_skill_level", "budget")
    search_fields = ("goal", "user__username", "user__email")
    inlines = [RoadmapPhaseInline]


@admin.register(RoadmapPhase)
class RoadmapPhaseAdmin(admin.ModelAdmin):
    list_display = ("title", "roadmap", "order", "difficulty", "status", "completion_pct")
    list_filter = ("difficulty", "status")


@admin.register(RoadmapCheckpoint)
class RoadmapCheckpointAdmin(admin.ModelAdmin):
    list_display = ("title", "phase", "is_completed", "xp_reward")


@admin.register(DailyMission)
class DailyMissionAdmin(admin.ModelAdmin):
    list_display = ("roadmap", "date", "status", "xp_reward", "was_adaptive")
    list_filter = ("status", "was_adaptive")


@admin.register(RoadmapResource)
class RoadmapResourceAdmin(admin.ModelAdmin):
    list_display = ("title", "roadmap", "phase", "resource_type", "is_free")
    list_filter = ("resource_type", "is_free")


@admin.register(PhaseTest)
class PhaseTestAdmin(admin.ModelAdmin):
    list_display = ("phase", "attempt_number", "status", "score", "passed", "created_at")
    list_filter = ("status", "passed")