from django.db import models
from django.conf import settings
from django.utils import timezone


PRIORITY_POINTS = {1: 2, 2: 4, 3: 6, 4: 8, 5: 10}
SKIP_DEDUCTION  = 3
LOSE_PUNISHMENT = 10


class Task(models.Model):
    STATUS_CHOICES = [
        ('pending',   'Pending'),
        ('completed', 'Completed'),
        ('skipped',   'Skipped'),
    ]

    user        = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='tasks')
    title       = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    priority    = models.IntegerField(default=3, choices=[(i, i) for i in range(1, 6)])
    quality     = models.IntegerField(null=True, blank=True)  # 1–10, unlocked at Level 3
    status      = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    due_date    = models.DateField(default=timezone.now)
    order       = models.PositiveIntegerField(default=0)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', '-priority', 'created_at']

    def __str__(self):
        return f"{self.title} ({self.priority}★)"

    def get_points(self):
        base = PRIORITY_POINTS.get(self.priority, 6)
        if self.quality is not None:
            if self.quality >= 7:
                base += 5
            elif self.quality <= 3:
                base -= 5
        return base

    def stars(self):
        return '★' * self.priority + '☆' * (5 - self.priority)


class DailyLog(models.Model):
    STATUS_CHOICES = [
        ('win',     'Day Win'),
        ('survive', 'Day Survive'),
        ('lose',    'Day Lose'),
        ('ongoing', 'Ongoing'),
    ]

    user         = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='daily_logs')
    date         = models.DateField(default=timezone.now)
    total_points = models.IntegerField(default=0)
    day_status   = models.CharField(max_length=10, choices=STATUS_CHOICES, default='ongoing')
    streak       = models.IntegerField(default=0)
    punishment   = models.BooleanField(default=False)
    # Store thresholds used that day
    win_threshold     = models.IntegerField(default=40)
    survive_threshold = models.IntegerField(default=20)

    class Meta:
        unique_together = ('user', 'date')
        ordering = ['-date']

    def __str__(self):
        return f"{self.user} | {self.date} | {self.total_points}pts | {self.day_status}"

    def calculate_status(self):
        if self.total_points >= self.win_threshold:
            return 'win'
        elif self.total_points >= self.survive_threshold:
            return 'survive'
        else:
            return 'lose'

    def save(self, *args, **kwargs):
        self.day_status = self.calculate_status()
        super().save(*args, **kwargs)


# ─── Boss System ───────────────────────────────────────────────────────────
# NOTE: level_number is a plain IntegerField (not a FK) because Levels live
# in users/models.py as a hardcoded LEVELS list, not a DB model.

class Boss(models.Model):
    BOSS_TYPES = [
        ('mini',  'Mini Boss'),
        ('final', 'Final Boss'),
    ]

    level_number = models.IntegerField(help_text="Matches the 'level' key in users.models.LEVELS")
    name         = models.CharField(max_length=100)
    boss_type    = models.CharField(max_length=10, choices=BOSS_TYPES)
    order        = models.PositiveIntegerField(default=0, help_text="Sequence of mini bosses within the level")
    image        = models.ImageField(upload_to='bosses/', blank=True, null=True)
    hp           = models.PositiveIntegerField(default=100)
    tagline      = models.CharField(max_length=150, blank=True, help_text="e.g. 'The weight that keeps you in bed'")
    lore         = models.TextField(blank=True, help_text="Shown in the info (i) tooltip — how this boss 'was born' and how to beat it.")

    class Meta:
        ordering = ['level_number', 'order']

    def __str__(self):
        return f"L{self.level_number} - {self.name} ({self.get_boss_type_display()})"

    def is_defeated_by(self, user):
        return BossDefeat.objects.filter(user=user, boss=self).exists()

    def challenges_completed_by(self, user):
        total = self.challenges.count()
        if total == 0:
            return True
        done = BossChallengeProgress.objects.filter(
            user=user, challenge__boss=self, completed=True
        ).count()
        return done >= total


class BossChallenge(models.Model):
    boss        = models.ForeignKey(Boss, on_delete=models.CASCADE, related_name='challenges')
    description = models.CharField(max_length=200)
    order       = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.boss.name}: {self.description}"


class BossChallengeProgress(models.Model):
    user         = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='tasks_challenge_progress')
    challenge    = models.ForeignKey(BossChallenge, on_delete=models.CASCADE, related_name='progress')
    completed    = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('user', 'challenge')

    def mark_complete(self):
        self.completed    = True
        self.completed_at = timezone.now()
        self.save()


class BossDefeat(models.Model):
    user        = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='tasks_boss_defeats')
    boss        = models.ForeignKey(Boss, on_delete=models.CASCADE, related_name='defeats')
    defeated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'boss')

    def __str__(self):
        return f"{self.user} defeated {self.boss.name}"


def get_bosses_for_level(level_number):
    return Boss.objects.filter(level_number=level_number)


def get_pending_boss(user, level_number):
    """
    Returns the next boss the user must fight for this level, in order:
    mini bosses first (by `order`), then the final boss. Returns None if
    everything for this level is already defeated.
    """
    bosses = get_bosses_for_level(level_number).order_by('boss_type', 'order')
    # mini bosses first
    for boss in bosses.filter(boss_type='mini'):
        if not boss.is_defeated_by(user):
            return boss
    # then final boss, only once all minis are cleared
    final = bosses.filter(boss_type='final').first()
    if final and not final.is_defeated_by(user):
        return final
    return None


# ─── Auto-verified challenges ──────────────────────────────────────────────
# Some challenge descriptions encode a hard number that can be checked
# directly against the user's real stats instead of trusting an honor-system
# "Mark Complete" click. Currently supported pattern: "Reach <N> total XP".

import re
_XP_TARGET_RE = re.compile(r'reach\s+(\d+)\s+total\s+xp', re.IGNORECASE)


def get_auto_verify_info(description, user):
    """
    Returns (is_auto, is_met, progress_label) for a challenge description.
    is_auto=False means this challenge has no automatic check (honor-system).
    """
    match = _XP_TARGET_RE.search(description)
    if match:
        target = int(match.group(1))
        current = user.total_xp
        return True, current >= target, f"{current}/{target} XP"
    return False, None, None


def sync_auto_challenges(boss, user):
    """
    Walks every challenge on this boss; for any that are auto-verifiable,
    creates/updates the BossChallengeProgress row to match the real stat
    check so the rest of the system (challenges_completed_by, etc.) sees
    consistent state without the user needing to click anything.
    """
    for challenge in boss.challenges.all():
        is_auto, is_met, _ = get_auto_verify_info(challenge.description, user)
        if not is_auto:
            continue
        progress, _created = BossChallengeProgress.objects.get_or_create(
            user=user, challenge=challenge
        )
        if is_met and not progress.completed:
            progress.mark_complete()
        elif not is_met and progress.completed:
            # Stat dropped back below target (shouldn't normally happen for
            # cumulative XP, but keep it honest) — un-complete it.
            progress.completed    = False
            progress.completed_at = None
            progress.save()