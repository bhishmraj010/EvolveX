from django.db import models
from django.conf import settings
from django.utils import timezone


WILLPOWER_POINTS = 7
WILLPOWER_DEDUCT = 7


class WillpowerTask(models.Model):
    STATUS_CHOICES = [
        ('pending',   'Pending'),
        ('completed', 'Completed'),
        ('skipped',   'Skipped'),
    ]

    user       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='willpower_tasks')
    title      = models.CharField(max_length=200)
    status     = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    due_date   = models.DateField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.user} | {self.title} | {self.status}"

    def get_points(self):
        if self.status == 'completed':
            return +WILLPOWER_POINTS
        elif self.status == 'skipped':
            return -WILLPOWER_DEDUCT
        return 0


class MealEntry(models.Model):
    MEAL_CHOICES = [
        ('breakfast', 'Breakfast'),
        ('lunch',     'Lunch'),
        ('dinner',    'Dinner'),
        ('snack',     'Snack'),
    ]

    user        = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='meal_entries')
    date        = models.DateField(default=timezone.now)
    meal_type   = models.CharField(max_length=10, choices=MEAL_CHOICES)
    description = models.TextField()
    is_healthy  = models.BooleanField(default=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', 'meal_type']

    def __str__(self):
        return f"{self.user} | {self.date} | {self.meal_type}"
    

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
    user         = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='challenge_progress')
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
    user        = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='boss_defeats')
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
    for boss in bosses.filter(boss_type='mini'):
        if not boss.is_defeated_by(user):
            return boss
    final = bosses.filter(boss_type='final').first()
    if final and not final.is_defeated_by(user):
        return final
    return None