from django.contrib import admin
from .models import (
    Task, DailyLog,
    Boss, BossChallenge, BossChallengeProgress, BossDefeat,
)

admin.site.register(Task)
admin.site.register(DailyLog)


class BossChallengeInline(admin.TabularInline):
    model = BossChallenge
    extra = 1


@admin.register(Boss)
class BossAdmin(admin.ModelAdmin):
    list_display  = ('name', 'level_number', 'boss_type', 'order', 'hp')
    list_filter   = ('boss_type', 'level_number')
    ordering      = ('level_number', 'order')
    inlines       = [BossChallengeInline]


@admin.register(BossChallenge)
class BossChallengeAdmin(admin.ModelAdmin):
    list_display = ('description', 'boss', 'order')
    list_filter  = ('boss',)


admin.site.register(BossChallengeProgress)
admin.site.register(BossDefeat)