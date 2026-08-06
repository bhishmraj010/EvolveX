from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


# ─── Level Definitions ───────────────────────────────────────────────────────
# Fields: level, name, title, icon, pts_required, win_pts, survive_min, lose_max,
#         time_limit_days, penalty_pts, bonus_pts, special_reward

LEVELS = [
    {
        'level':        1,
        'name':         'Novice',
        'title':        '🌱 The Beginner',
        'icon':         '🌱',
        'pts_required': 0,
        'win_pts':      40,
        'survive_min':  20,
        'lose_max':     19,
        'time_limit':   None,
        'penalty':      0,
        'bonus':        0,
        'special':      'Default starting level',
    },
    {
        'level':        2,
        'name':         'Apprentice',
        'title':        '⚔️ The Fighter',
        'icon':         '⚔️',
        'pts_required': 350,
        'win_pts':      45,
        'survive_min':  30,
        'lose_max':     29,
        'time_limit':   10,
        'penalty':      50,
        'bonus':        20,
        'special':      'Difficulty increases — Win bar raised to 45pts',
    },
    {
        'level':        3,
        'name':         'Warrior',
        'title':        '🛡️ The Resilient',
        'icon':         '🛡️',
        'pts_required': 1000,
        'win_pts':      50,
        'survive_min':  35,
        'lose_max':     34,
        'time_limit':   15,
        'penalty':      80,
        'bonus':        20,
        'special':      'Task Quality Rating unlocked (1–10)',
    },
    {
        'level':        4,
        'name':         'Knight',
        'title':        '🗡️ The Disciplined',
        'icon':         '🗡️',
        'pts_required': 2500,
        'win_pts':      55,
        'survive_min':  40,
        'lose_max':     39,
        'time_limit':   15,
        'penalty':      100,
        'bonus':        30,
        'special':      'Requires 7-day Win streak',
    },
    {
        'level':        5,
        'name':         'Champion',
        'title':        '🔥 The Habitual',
        'icon':         '🔥',
        'pts_required': 5000,
        'win_pts':      60,
        'survive_min':  45,
        'lose_max':     44,
        'time_limit':   20,
        'penalty':      150,
        'bonus':        60,
        'special':      'Diet Tracker unlocked + Habit tracking required',
    },
    {
        'level':        6,
        'name':         'Elite',
        'title':        '⚡ The Consistent',
        'icon':         '⚡',
        'pts_required': 8000,
        'win_pts':      65,
        'survive_min':  45,
        'lose_max':     44,
        'time_limit':   20,
        'penalty':      200,
        'bonus':        0,
        'special':      'No Lose for 10 days + Quality bonus system active',
    },
    {
        'level':        7,
        'name':         'Master',
        'title':        '💎 The Achiever',
        'icon':         '💎',
        'pts_required': 10000,
        'win_pts':      70,
        'survive_min':  45,
        'lose_max':     44,
        'time_limit':   25,
        'penalty':      250,
        'bonus':        0,
        'special':      'Cookie Container unlocked — +10pts per achievement (max 7)',
    },
    {
        'level':        8,
        'name':         'Grandmaster',
        'title':        '👑 The Skilled',
        'icon':         '👑',
        'pts_required': 15000,
        'win_pts':      70,
        'survive_min':  45,
        'lose_max':     44,
        'time_limit':   30,
        'penalty':      300,
        'bonus':        0,
        'special':      'Learn a new skill — 1 Cheat Meal reward',
    },
    {
        'level':        9,
        'name':         'Hero',
        'title':        '🌟 The Legendary',
        'icon':         '🌟',
        'pts_required': 20000,
        'win_pts':      75,
        'survive_min':  50,
        'lose_max':     49,
        'time_limit':   30,
        'penalty':      400,
        'bonus':        50,
        'special':      'Start social media + show skill — Cookie container +3',
    },
    {
        'level':        10,
        'name':         'Legend',
        'title':        '🏆 The Unstoppable',
        'icon':         '🏆',
        'pts_required': 30000,
        'win_pts':      75,
        'survive_min':  50,
        'lose_max':     49,
        'time_limit':   None,
        'penalty':      0,
        'bonus':        0,
        'special':      '3 Freedom Passes — break rules without punishment!',
    },
]


def get_level_data(level_num):
    for l in LEVELS:
        if l['level'] == level_num:
            return l
    return None


# ─── Timezone choices ────────────────────────────────────────────────────────
# A curated, common IANA timezone list for the (optional) manual dropdown in
# Account Settings. Auto-detection (via browser JS + the set_timezone view)
# is the primary path and works with ANY valid IANA name, not just this list
# — this is just what's offered as a fallback/manual-override menu.
TIMEZONE_CHOICES = [
    ('', 'Auto-detect (recommended)'),
    ('Asia/Kolkata', '🇮🇳 India — Asia/Kolkata (IST)'),
    ('America/New_York', '🇺🇸 USA Eastern — America/New_York'),
    ('America/Chicago', '🇺🇸 USA Central — America/Chicago'),
    ('America/Denver', '🇺🇸 USA Mountain — America/Denver'),
    ('America/Los_Angeles', '🇺🇸 USA Pacific — America/Los_Angeles'),
    ('America/Toronto', '🇨🇦 Canada — America/Toronto'),
    ('Europe/London', '🇬🇧 UK — Europe/London'),
    ('Europe/Berlin', '🇩🇪 Germany — Europe/Berlin'),
    ('Europe/Paris', '🇫🇷 France — Europe/Paris'),
    ('Australia/Sydney', '🇦🇺 Australia — Australia/Sydney'),
    ('Asia/Dubai', '🇦🇪 UAE — Asia/Dubai'),
    ('Asia/Riyadh', '🇸🇦 Saudi Arabia — Asia/Riyadh'),
    ('Asia/Qatar', '🇶🇦 Qatar — Asia/Qatar'),
    ('Asia/Singapore', '🇸🇬 Singapore — Asia/Singapore'),
    ('Asia/Tokyo', '🇯🇵 Japan — Asia/Tokyo'),
    ('Asia/Shanghai', '🇨🇳 China — Asia/Shanghai'),
    ('Asia/Dhaka', '🇧🇩 Bangladesh — Asia/Dhaka'),
    ('Asia/Karachi', '🇵🇰 Pakistan — Asia/Karachi'),
    ('Asia/Colombo', '🇱🇰 Sri Lanka — Asia/Colombo'),
]


class CustomUser(AbstractUser):
    email        = models.EmailField(unique=True)
    name         = models.CharField(max_length=100, blank=True)
    avatar       = models.ImageField(upload_to='avatars/', blank=True, null=True)
    bio          = models.TextField(max_length=300, blank=True)
    phone_number = models.CharField(max_length=20, unique=True, blank=True, null=True)

    # IANA timezone name (e.g. 'Asia/Kolkata', 'America/New_York'). Blank
    # means "not detected/set yet" — UserTimezoneMiddleware falls back to
    # the `tz` cookie, then to settings.TIME_ZONE, in that case. Normally
    # auto-populated by browser JS (see base.html) right after login/signup,
    # but can also be overridden manually from Account Settings using
    # TIMEZONE_CHOICES above.
    timezone = models.CharField(
        max_length=64,
        blank=True,
        default='',
        help_text="IANA timezone name, auto-detected from the browser. "
                  "Drives streaks, daily resets, and deadlines in the user's local time.",
    )

    # ── Level System ──
    level            = models.IntegerField(default=1)
    title            = models.CharField(max_length=80, default='🌱 The Beginner')
    badge            = models.CharField(max_length=50, default='Starter')
    total_xp         = models.IntegerField(default=0)
    level_started_at = models.DateTimeField(null=True, blank=True)
    level_deadline   = models.DateTimeField(null=True, blank=True)

    # Extra unlocks
    quality_rating_unlocked  = models.BooleanField(default=False)
    diet_tracker_unlocked    = models.BooleanField(default=False)
    cookie_container_unlocked = models.BooleanField(default=False)
    cookie_container_size    = models.IntegerField(default=0)
    freedom_passes           = models.IntegerField(default=0)
    cheat_meals_allowed      = models.IntegerField(default=0)

    # ── Boss System ──
    # Set to True the moment XP threshold for next level is hit, but the
    # boss for the CURRENT level hasn't been defeated yet. Level-up is
    # blocked while this is True.
    boss_pending = models.BooleanField(default=False)

    def __str__(self):
        return self.username

    def get_display_name(self):
        return self.name or self.username

    def current_level_data(self):
        return get_level_data(self.level)

    def next_level_data(self):
        return get_level_data(self.level + 1)

    def get_win_pts(self):
        """Today's win threshold based on current level."""
        data = self.current_level_data()
        return data['win_pts'] if data else 40

    def get_survive_min(self):
        data = self.current_level_data()
        return data['survive_min'] if data else 20

    def xp_progress_pct(self):
        current = get_level_data(self.level)
        nxt     = get_level_data(self.level + 1)
        if not nxt:
            return 100
        cur_req = current['pts_required']
        nxt_req = nxt['pts_required']
        if nxt_req == cur_req:
            return 100
        pct = (self.total_xp - cur_req) / (nxt_req - cur_req) * 100
        return min(100, max(0, round(pct)))

    def xp_to_next_level(self):
        nxt = get_level_data(self.level + 1)
        if not nxt:
            return 0
        return max(0, nxt['pts_required'] - self.total_xp)

    def days_left(self):
        if not self.level_deadline:
            return None
        delta = self.level_deadline - timezone.now()
        return max(0, delta.days)

    def apply_unlocks(self):
        """Apply special rewards based on level."""
        if self.level >= 3:
            self.quality_rating_unlocked = True
        if self.level >= 5:
            self.diet_tracker_unlocked = True
        if self.level >= 7 and not self.cookie_container_unlocked:
            self.cookie_container_unlocked = True
            self.cookie_container_size = 7
        if self.level >= 8:
            self.cheat_meals_allowed = max(self.cheat_meals_allowed, 1)
        if self.level >= 9:
            self.cookie_container_size = min(10, self.cookie_container_size + 3)
        if self.level >= 10:
            self.freedom_passes = max(self.freedom_passes, 3)

    def check_level_up(self):
        """Check if user qualifies for next level. Returns True if leveled up.

        XP threshold reaching the requirement is NECESSARY but not
        SUFFICIENT anymore. The current level's boss(es) must also be
        defeated. If XP is enough but the boss isn't defeated yet, we
        flip `boss_pending` so the frontend can show the boss battle
        screen, and level-up is held until the boss is cleared (see
        tasks.models.get_pending_boss + tasks.views.boss_battle).
        """
        if self.level >= 10:
            return False
        nxt = get_level_data(self.level + 1)
        if not nxt:
            return False

        if self.total_xp < nxt['pts_required']:
            return False

        # XP is enough — check boss status for the CURRENT level before
        # allowing the level up to go through.
        from tasks.models import get_pending_boss
        pending_boss = get_pending_boss(self, self.level)
        if pending_boss is not None:
            if not self.boss_pending:
                self.boss_pending = True
                self.save()
            return False

        # No boss pending (either none defined for this level, or all
        # defeated) — clear the flag and proceed with normal level up.
        if self.boss_pending:
            self.boss_pending = False

        if self.total_xp >= nxt['pts_required']:
            self.level  += 1
            self.title   = nxt['title']
            self.badge   = nxt['name']
            self.total_xp += nxt['bonus']

            # Apply special unlocks
            self.apply_unlocks()

            # Set deadline for this new level's next level
            next_next = get_level_data(self.level + 1)
            if next_next and next_next['time_limit']:
                self.level_started_at = timezone.now()
                self.level_deadline   = timezone.now() + timezone.timedelta(
                    days=next_next['time_limit']
                )
            else:
                self.level_started_at = timezone.now()
                self.level_deadline   = None

            self.save()
            return True
        return False

    def check_deadline_penalty(self):
        """Apply penalty if deadline passed. Returns True if penalty applied."""
        if not self.level_deadline:
            return False
        if timezone.now() > self.level_deadline:
            nxt = get_level_data(self.level + 1)
            if nxt and nxt['penalty'] > 0:
                self.total_xp = max(0, self.total_xp - nxt['penalty'])
                time_limit    = nxt['time_limit'] or 10
                self.level_deadline = timezone.now() + timezone.timedelta(days=time_limit)
                self.save()
                return True
        return False


class UnlockedBadge(models.Model):
    """
    Tracks which achievement badges (see users/achievements.py -> get_badges)
    a user has already had "unlocked" recorded for, so the Achievement
    Unlocked popup only fires the FIRST time each badge's condition becomes
    true — not on every page load / stat recalculation afterward.
    """
    user       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='unlocked_badges')
    badge_key  = models.CharField(max_length=50)
    unlocked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'badge_key')

    def __str__(self):
        return f"{self.user} — {self.badge_key}"