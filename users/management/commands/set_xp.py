"""
All-in-one testing helper for the level/boss system.

Usage:
    python manage.py set_xp <username> --status
        Print current level, XP, boss_pending flag, which boss is pending,
        and a list of every BossDefeat/BossChallengeProgress row for this
        user (so you can see exactly what's stored).

    python manage.py set_xp <username> --xp 350
        Set total_xp directly and re-run the level-up/boss check.

    python manage.py set_xp <username> --xp 350 --defeat-boss
        Set XP, then auto-defeat whatever boss is pending for the CURRENT
        level (marks all its challenges complete + records the defeat),
        and re-checks level-up.

    python manage.py set_xp <username> --to-level 10
        Fast-forward through every level from where the user currently is
        up to (but not including) the target level, auto-defeating each
        level's boss along the way. Stops with the user AT the target
        level, XP set to that level's threshold, and that level's own
        boss left PENDING (undefeated) — perfect for demoing a specific
        boss fight (e.g. LUST) without grinding through levels 1-9 first.

    python manage.py set_xp <username> --clear-defeats
        Delete ALL BossDefeat + BossChallengeProgress rows for this user
        (fixes "boss auto-defeats" caused by stray leftover test data).

    python manage.py set_xp <username> --clear-defeats --level 1
        Only clear defeats/progress tied to Level 1 bosses (leaves other
        levels' boss history alone).

    python manage.py set_xp <username> --reset-level
        Full reset: Level 1, 0 XP, boss_pending off, ALL boss progress wiped.

Flags can be combined in one call, e.g.:
    python manage.py set_xp bhishmraj --clear-defeats --xp 350
"""
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = "Set XP / inspect / fix boss state for a user (testing helper)."

    def add_arguments(self, parser):
        parser.add_argument('username', type=str)
        parser.add_argument('--xp', type=int, default=None, help="Set total_xp to this value.")
        parser.add_argument('--defeat-boss', action='store_true',
                             help="Auto-defeat the currently pending boss for the user's level.")
        parser.add_argument('--to-level', type=int, default=None,
                             help="Fast-forward to this level, auto-defeating every boss along "
                                  "the way, leaving the target level's own boss pending.")
        parser.add_argument('--clear-defeats', action='store_true',
                             help="Delete BossDefeat + BossChallengeProgress rows for this user.")
        parser.add_argument('--level', type=int, default=None,
                             help="Restrict --clear-defeats to a specific level_number.")
        parser.add_argument('--reset-level', action='store_true',
                             help="Full reset: Level 1, 0 XP, all boss progress wiped.")
        parser.add_argument('--status', action='store_true',
                             help="Print current level/XP/boss state without changing anything.")

    def handle(self, *args, **options):
        User = get_user_model()
        try:
            user = User.objects.get(username=options['username'])
        except User.DoesNotExist:
            raise CommandError(f"No user named '{options['username']}'")

        from tasks.models import BossDefeat, BossChallengeProgress, get_pending_boss
        from users.models import get_level_data

        # ── Full reset ──
        if options['reset_level']:
            BossDefeat.objects.filter(user=user).delete()
            BossChallengeProgress.objects.filter(user=user).delete()
            user.level = 1
            user.total_xp = 0
            user.boss_pending = False
            user.title = '🌱 The Beginner'
            user.badge = 'Starter'
            user.save()
            self.stdout.write(self.style.SUCCESS(
                f"{user.username} reset to Level 1, 0 XP. All boss progress cleared."
            ))
            return

        # ── Clear stray defeats/progress (does not touch level/XP) ──
        if options['clear_defeats']:
            defeats = BossDefeat.objects.filter(user=user)
            progress = BossChallengeProgress.objects.filter(user=user)
            if options['level'] is not None:
                defeats = defeats.filter(boss__level_number=options['level'])
                progress = progress.filter(challenge__boss__level_number=options['level'])
            d_count = defeats.count()
            p_count = progress.count()
            defeats.delete()
            progress.delete()
            user.boss_pending = False
            user.save()
            self.stdout.write(self.style.SUCCESS(
                f"Cleared {d_count} boss defeat(s) and {p_count} challenge progress row(s)"
                + (f" for level {options['level']}" if options['level'] is not None else " (all levels)")
                + ". boss_pending reset to False."
            ))

        # ── Fast-forward to a target level, auto-defeating bosses along the way ──
        if options['to_level'] is not None:
            target = options['to_level']
            if target < 1 or target > 10:
                raise CommandError("--to-level must be between 1 and 10.")

            safety_counter = 0
            while user.level < target and safety_counter < 20:
                safety_counter += 1
                nxt = get_level_data(user.level + 1)
                if not nxt:
                    break

                user.total_xp = max(user.total_xp, nxt['pts_required'])
                user.save()
                user.check_level_up()  # flips boss_pending if a boss is still undefeated

                pending = get_pending_boss(user, user.level)
                if pending is not None:
                    for challenge in pending.challenges.all():
                        progress, _ = BossChallengeProgress.objects.get_or_create(
                            user=user, challenge=challenge
                        )
                        progress.mark_complete()
                    BossDefeat.objects.get_or_create(user=user, boss=pending)
                    self.stdout.write(f"  Auto-defeated L{pending.level_number} {pending.name}")

                user.check_level_up()
                user.refresh_from_db()

            self.stdout.write(self.style.SUCCESS(
                f"\nFast-forwarded to Level {user.level} (target was {target}). "
                f"XP={user.total_xp}, boss_pending={user.boss_pending}."
            ))
            pending_now = get_pending_boss(user, user.level)
            if pending_now:
                self.stdout.write(self.style.SUCCESS(
                    f"Left pending for you to fight: L{pending_now.level_number} {pending_now.name}"
                ))

        # ── Set XP (only if --to-level wasn't used, to avoid double-setting) ──
        elif options['xp'] is not None:
            user.total_xp = options['xp']
            user.save()
            leveled_up = user.check_level_up()
            self.stdout.write(
                f"XP set to {user.total_xp}. level={user.level}, "
                f"boss_pending={user.boss_pending}, leveled_up_this_call={leveled_up}"
            )

        # ── Auto-defeat pending boss ──
        if options['defeat_boss']:
            boss = get_pending_boss(user, user.level)
            if boss is None:
                self.stdout.write("No pending boss to defeat.")
            else:
                for challenge in boss.challenges.all():
                    progress, _ = BossChallengeProgress.objects.get_or_create(
                        user=user, challenge=challenge
                    )
                    progress.mark_complete()
                BossDefeat.objects.get_or_create(user=user, boss=boss)
                leveled_up2 = user.check_level_up()
                self.stdout.write(self.style.SUCCESS(
                    f"Auto-defeated {boss.name} (Level {boss.level_number}). "
                    f"level={user.level}, leveled_up={leveled_up2}"
                ))

        # ── Status report (also shown by default if no action flags given) ──
        any_action = (
            options['xp'] is not None or options['defeat_boss'] or options['clear_defeats']
            or options['reset_level'] or options['to_level'] is not None
        )
        if options['status'] or not any_action:
            user.refresh_from_db()
            pending = get_pending_boss(user, user.level)
            self.stdout.write(self.style.SUCCESS("\n─── Status ───"))
            self.stdout.write(f"Username:      {user.username}")
            self.stdout.write(f"Level:         {user.level}")
            self.stdout.write(f"Total XP:      {user.total_xp}")
            self.stdout.write(f"boss_pending:  {user.boss_pending}")
            self.stdout.write(f"Pending boss:  {pending.name if pending else '(none — clear to level up)'}")

            defeats = BossDefeat.objects.filter(user=user).select_related('boss')
            self.stdout.write(f"\nBossDefeat rows ({defeats.count()}):")
            for d in defeats:
                self.stdout.write(f"  - L{d.boss.level_number} {d.boss.name} (defeated {d.defeated_at:%Y-%m-%d %H:%M})")
            if not defeats.exists():
                self.stdout.write("  (none)")

            progress = BossChallengeProgress.objects.filter(user=user, completed=True).select_related('challenge__boss')
            self.stdout.write(f"\nCompleted challenge rows ({progress.count()}):")
            for p in progress:
                self.stdout.write(f"  - L{p.challenge.boss.level_number} {p.challenge.boss.name}: {p.challenge.description}")
            if not progress.exists():
                self.stdout.write("  (none)")
            self.stdout.write("")