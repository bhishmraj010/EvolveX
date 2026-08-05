"""
Re-links existing image files sitting in MEDIA_ROOT/bosses/ back to their
Boss rows, without needing to re-upload anything. Useful after a
`seed_bosses --reset` wiped the DB image references but left the actual
files on disk untouched.

Usage:
    python manage.py relink_boss_images            # auto-match by filename keywords
    python manage.py relink_boss_images --dry-run   # preview matches without saving
"""
import os
from django.conf import settings
from django.core.management.base import BaseCommand
from tasks.models import Boss

# Keywords to look for in filenames -> boss name they belong to.
KEYWORD_TO_BOSS = {
    'sloth':       'SLOTH',
    'doubt':       'DOUBT',
    'fear':        'FEAR',
    'gluttony':    'GLUTTONY',
    'comfort':     'COMFORT ZONE',
    'wrath':       'WRATH',
    'pride':       'PRIDE',
    'greed':       'GREED',
    'envy':        'ENVY',
    'lust':        'LUST',
}


class Command(BaseCommand):
    help = "Re-link existing files in media/bosses/ to their Boss rows by filename keyword."

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help="Preview matches without saving.")

    def handle(self, *args, **options):
        bosses_dir = os.path.join(settings.MEDIA_ROOT, 'bosses')

        if not os.path.isdir(bosses_dir):
            self.stdout.write(self.style.WARNING(
                f"No folder found at {bosses_dir} — no boss images have ever been uploaded here."
            ))
            return

        files = os.listdir(bosses_dir)
        if not files:
            self.stdout.write(self.style.WARNING(f"{bosses_dir} exists but is empty. Nothing to relink."))
            return

        self.stdout.write(f"Found {len(files)} file(s) in media/bosses/:")
        for f in files:
            self.stdout.write(f"  - {f}")
        self.stdout.write("")

        matched = 0
        for filename in files:
            lower = filename.lower()
            boss_name = None
            for keyword, name in KEYWORD_TO_BOSS.items():
                if keyword in lower:
                    boss_name = name
                    break

            if not boss_name:
                self.stdout.write(f"  ? {filename} — no keyword match, skipped")
                continue

            try:
                boss = Boss.objects.get(name=boss_name)
            except Boss.DoesNotExist:
                self.stdout.write(f"  ! {filename} matched '{boss_name}' but no such Boss row exists")
                continue

            relative_path = f'bosses/{filename}'
            if options['dry_run']:
                self.stdout.write(f"  → would link {filename} to {boss_name} (L{boss.level_number})")
            else:
                boss.image.name = relative_path
                boss.save()
                self.stdout.write(self.style.SUCCESS(
                    f"  ✅ Linked {filename} → {boss_name} (L{boss.level_number})"
                ))
            matched += 1

        self.stdout.write("")
        if options['dry_run']:
            self.stdout.write(self.style.SUCCESS(f"Dry run done. {matched} file(s) would be linked."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Done. {matched} file(s) linked."))