from django.conf import settings
from django.db import models
from django.utils import timezone


class JournalEntry(models.Model):
    """
    One "how am I doing right now" journal entry per user per day, written
    from the Home hub. Submitting again on the same day updates that day's
    entry rather than creating a duplicate (see journal_save_view).

    ai_response / ai_suggestions are filled in by Gemini right after save
    (see home/views.py -> _build_journal_prompt). If the AI call fails for
    any reason, the entry still saves — those fields just stay empty and
    the panel shows the entry without an AI reflection.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="journal_entries"
    )
    date = models.DateField(default=timezone.localdate)
    entry_text = models.TextField()

    ai_response = models.TextField(blank=True)          # short reflection paragraph
    ai_suggestions = models.JSONField(default=list, blank=True)  # list of actionable strings
    ai_mood_tag = models.CharField(max_length=40, blank=True)    # e.g. "Motivated", "Burnt Out"
    ai_generated_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "date"], name="one_journal_entry_per_user_per_day")
        ]

    def __str__(self):
        return f"{self.user} — {self.date}"