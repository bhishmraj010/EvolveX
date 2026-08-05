"""
Seeds the 10 level bosses (SLOTH -> LUST) with example challenges and lore.

Usage:
    python manage.py seed_bosses            # create if missing, skip existing
    python manage.py seed_bosses --reset     # delete all existing bosses first

Images are NOT set here -- add them later via Django admin
(each Boss has an `image` field: /admin/ -> Boss -> pick boss -> Image).
"""
from django.core.management.base import BaseCommand
from tasks.models import Boss, BossChallenge


# Challenges are aligned with each level's real numbers from
# users.models.LEVELS (win_pts, pts_required) and unlocked features
# (see users.models.CustomUser.apply_unlocks):
#   Quality Rating   -> unlocked at Level 3+
#   Diet Tracker     -> unlocked at Level 5+
#   Cookie Container -> unlocked at Level 7+
#   Cheat Meals      -> unlocked at Level 8+
#   Freedom Passes   -> unlocked at Level 10+
#
# NOTE: No challenge checks total XP anymore. The boss itself is already
# gated behind the level's XP requirement (see check_level_up), so an
# "Reach N total XP" challenge inside the boss fight would always be
# instantly complete — redundant. Every challenge here is a real action.

BOSSES = [
    {
        'level_number': 1, 'name': 'SLOTH', 'tagline': 'The weight that keeps you in bed',
        'hp': 100,
        'lore': "Born the moment you first hit snooze. It feeds on comfortable "
                "mornings and unfinished todo lists. It has no real power over "
                "you — it only wins if you let the first task of the day slip.",
        'challenges': [
            "Don't skip a single task for 3 days in a row",
            "Start your first task of the day without hitting snooze",
            "Score a Win day (40+ points) on your very first attempt",
            "Complete your first task within 10 minutes of waking up",
        ],
    },
    {
        'level_number': 2, 'name': 'DOUBT', 'tagline': "The voice that says you can't",
        'hp': 150,
        'lore': "Grows in the silence right before you start something new. "
                "It doesn't attack — it just asks 'what if you fail?' on repeat. "
                "It's beaten by doing the thing scared, not by feeling ready first.",
        'challenges': [
            "Try one task type you've never attempted before",
            "Hit the Win threshold (45+ pts) on at least 4 out of 5 days",
            "Complete a 5-star priority task at least once",
            "Tell someone your goal out loud, then follow through on it",
        ],
    },
    {
        'level_number': 3, 'name': 'FEAR', 'tagline': 'What stops you before you start',
        'hp': 200,
        'lore': "A shape-shifter that looks like whatever you're most avoiding. "
                "The longer a task sits undone, the bigger it grows. It shrinks "
                "to nothing the second you actually start the avoided task.",
        'challenges': [
            "Complete the one task you keep avoiding",
            "Build a 7-day streak without missing a single day",
            "Score a Win day (50+ pts) for 3 days in a row",
            "Do the avoided task first thing, before anything else that day",
        ],
    },
    {
        'level_number': 4, 'name': 'GLUTTONY', 'tagline': 'Excess that breaks discipline',
        'hp': 250,
        'lore': "Feasts on broken streaks and 'just one more day off'. It "
                "convinces you that skipping today doesn't matter — then does "
                "it again tomorrow. Consistency is the only thing that starves it.",
        'challenges': [
            "Log a 7-day Win streak (this level's core requirement)",
            "Complete your top-priority (5-star) task 3 days in a row",
            "Avoid a single Lose day for a full week",
            "Skip one comfort habit for 3 days straight (your call, be honest)",
        ],
    },
    {
        'level_number': 5, 'name': 'COMFORT ZONE', 'tagline': 'Growth stops where comfort begins',
        'hp': 300,
        'lore': "Not loud or scary — just warm and familiar. It wraps around "
                "routines that used to be hard and makes them feel like the "
                "ceiling instead of the floor. Beaten by choosing harder, on purpose.",
        'challenges': [
            "Log your meals in the Diet Tracker for 5 days straight",
            "Add one new, harder task to your routine and stick to it for 3 days",
            "Score a Win day (60+ pts) on 5 different days",
            "Try a completely new task category for a full week",
        ],
    },
    {
        'level_number': 6, 'name': 'WRATH', 'tagline': 'The anger that breaks consistency',
        'hp': 350,
        'lore': "Born from a single bad day that spirals into a bad week. It "
                "wants you to quit loudly right after a setback. It's defeated "
                "by showing up again the very next day, calm and unbothered.",
        'challenges': [
            "Go 10 days in a row without a single Lose day",
            "Don't skip a task even after a bad day",
            "Score a Win day (65+ pts) on 6 out of 7 days",
            "Log a task calmly within 1 hour of a stressful moment",
        ],
    },
    {
        'level_number': 7, 'name': 'PRIDE', 'tagline': 'The ego that follows achievement',
        'hp': 400,
        'lore': "Arrives right after your biggest wins, whispering that you've "
                "already made it and can coast now. It's quiet, dangerous, and "
                "only beaten by staying as disciplined after success as before it.",
        'challenges': [
            "Fill your Cookie Container — hit 3 achievements this week",
            "Help someone else track their progress (accountability partner)",
            "Maintain a 10-day Win streak",
            "Publicly give credit to someone who helped your progress",
        ],
    },
    {
        'level_number': 8, 'name': 'GREED', 'tagline': 'Never satisfied, always wanting more',
        'hp': 450,
        'lore': "Never full. It turns healthy ambition into a race that never "
                "ends, where nothing you hit is ever enough. Beaten by proving "
                "you can push harder without losing what you already built.",
        'challenges': [
            "Start learning one new skill and log progress for 5 days",
            "Beat this level's Win threshold by 20%+ on at least 3 days",
            "Complete every task for 5 straight days with zero skips",
            "Take one full rest day without adding extra tasks to prove it",
        ],
    },
    {
        'level_number': 9, 'name': 'ENVY', 'tagline': 'Comparison that steals your focus',
        'hp': 500,
        'lore': "Feeds on scrolling through other people's progress instead of "
                "logging your own. It has no shape of its own — it's only ever "
                "a reflection. It disappears the moment you compete with your past self instead.",
        'challenges': [
            "Beat your own best 7-day XP total",
            "Go 10 days in a row without a single Lose day",
            "Score a Win day (75+ pts) on 8 out of 10 days",
            "Go 5 days without comparing your progress to anyone else's",
        ],
    },
    {
        'level_number': 10, 'name': 'LUST', 'tagline': 'The final desire that tests everything',
        'hp': 666,
        'lore': "The last and heaviest weakness — not one thing, but every "
                "excuse you've ever used, fused into one final craving for the "
                "easy way out. Everything you beat to get here made you strong "
                "enough to beat this too.",
        'challenges': [
            "Maintain perfect discipline for 14 days — zero skips",
            "Stay consistent across Tasks, Diet, and Willpower trackers for 14 days",
            "Identify your biggest personal weakness and control it for a full week",
            "Hold your Win streak for 3 more days after this fight — no slip-ups",
        ],
    },
]


class Command(BaseCommand):
    help = "Seed the 10 level bosses (SLOTH -> LUST) with challenges and lore."

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset', action='store_true',
            help="Delete all existing Boss rows before seeding.",
        )

    def handle(self, *args, **options):
        if options['reset']:
            count, _ = Boss.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"Deleted {count} existing boss-related rows."))

        created_count = 0
        updated_count = 0

        for entry in BOSSES:
            boss, created = Boss.objects.get_or_create(
                level_number=entry['level_number'],
                boss_type='final',
                defaults={
                    'name':    entry['name'],
                    'tagline': entry['tagline'],
                    'hp':      entry['hp'],
                    'lore':    entry['lore'],
                    'order':   0,
                },
            )

            if not created:
                boss.tagline = entry['tagline']
                boss.lore    = entry['lore']
                boss.hp      = entry['hp']
                boss.save()
                updated_count += 1
                self.stdout.write(f"  Updated lore/tagline: L{entry['level_number']} {entry['name']}")

                if not boss.challenges.exists():
                    for i, desc in enumerate(entry['challenges']):
                        BossChallenge.objects.create(boss=boss, description=desc, order=i)
                continue

            created_count += 1
            for i, desc in enumerate(entry['challenges']):
                BossChallenge.objects.create(boss=boss, description=desc, order=i)

            self.stdout.write(self.style.SUCCESS(
                f"  Created: L{entry['level_number']} {entry['name']} "
                f"({len(entry['challenges'])} challenges)"
            ))

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. {created_count} created, {updated_count} updated (lore/tagline refreshed)."
        ))
        self.stdout.write(
            "Add boss images via /admin/ -> Boss -> pick a boss -> upload image."
        )